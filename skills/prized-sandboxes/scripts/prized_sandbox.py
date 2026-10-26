"""Prized Sandboxes from Python, standard library only (Python 3.8+). Copy this file into a project.

    from prized_sandbox import Sandbox
    with Sandbox.create(max_runtime_min=30) as sbx:
        print(sbx.exec("python3 --version")["stdout"])

Run it as a script to check a key end to end: python3 prized_sandbox.py "python3 --version"
API reference: https://prized.dev/docs/sandboxes-api.md
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = "https://api.prized.dev/api/v1"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would resend the key to wherever a redirect points, so none is followed: a 3xx raises HTTPError."""

    def redirect_request(self, *args):
        return None


_open = urllib.request.build_opener(_NoRedirect).open


def _call(method, url, body=None, data=None, idem=None, timeout=3660):
    key = os.environ["PRIZED_API_KEY"]  # dcp_...; never hardcode it
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/octet-stream"}
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    if idem:
        headers["Idempotency-Key"] = idem  # a retry with the same key and body answers the first result
    req = urllib.request.Request(url, data, headers, method=method)
    try:
        with _open(req, timeout=timeout) as r:
            out = r.read()
            return json.loads(out) if r.headers.get_content_type() == "application/json" else out
    except urllib.error.HTTPError as e:
        out = e.read()
        e.msg = out[:500].decode("utf-8", "replace")  # {"error": "code", ...}: see the Errors table
        raise


def _code(err):
    """The API's error code from an HTTPError raised by _call ("" when the body says none)."""
    try:
        return json.loads(err.msg).get("error", "")
    except (ValueError, AttributeError):
        return ""


def _allocate(url, body):
    """POST a create or fork under its own Idempotency-Key. When the answer is lost (an interrupt, a
    timeout, a dropped connection, a 5xx), the same key replays what committed, if anything, and a
    delete is tried for every sandbox it names before the error is raised. Best effort: a replay or
    delete that fails too leaves that sandbox to maxRuntimeMin."""
    idem = uuid.uuid4().hex
    try:
        return _call("POST", url, body, idem=idem)
    except BaseException as e:
        if not (isinstance(e, urllib.error.HTTPError) and e.code < 500):  # a 3xx or 4xx made nothing
            try:
                out = _call("POST", url.split("?")[0], body, idem=idem, timeout=30)
            except Exception:
                out = {}  # the replay failed too: maxRuntimeMin ends whatever committed
            for s in out.get("sandboxes") or ([out["sandbox"]] if out.get("sandbox") else []):
                try:
                    _call("DELETE", f"{API}/sandboxes/{s['id']}", timeout=30)
                except Exception:
                    pass  # one failed delete does not skip the rest
        raise


class Sandbox:
    def __init__(self, sandbox):
        self.id = sandbox["id"]
        self.toolbox = sandbox.get("toolboxBase")

    @classmethod
    def create(cls, template="prized-base-v1", vcpu=2, memory_mb=4096, max_runtime_min=60, env=None):
        body = {"template": template, "resources": {"vcpu": vcpu, "memoryMb": memory_mb}, "maxRuntimeMin": max_runtime_min}
        if env:
            body["envVars"] = env  # secrets go here: stored encrypted, never returned
        sbx = cls(_allocate(f"{API}/sandboxes?wait=running", body)["sandbox"])
        try:
            return sbx.wait()
        except BaseException:
            sbx.delete()  # don't leave it billing until maxRuntimeMin
            raise

    def get(self):
        return _call("GET", f"{API}/sandboxes/{self.id}")["sandbox"]

    def wait(self):
        """Until running, when it takes commands."""
        while (s := self.get())["state"] == "starting":
            time.sleep(1)
        if s["state"] != "running":
            raise RuntimeError(f"{self.id} is {s['state']}: {s['errorReason']}")
        self.toolbox = s["toolboxBase"]  # always read it, never build it
        return self

    def exec(self, command, cwd=None, env=None, timeout=None, retry=(409, 429, 503)):
        """bash -c as user prized in /home/prized/work. Returns {stdout, stderr, exitCode, durationMs, timedOut?}.
        A failing command still answers 200: check exitCode. timeout is seconds (default 300, max 3600)."""
        body = {"command": command, **{k: v for k, v in (("cwd", cwd), ("env", env), ("timeout", timeout)) if v}}
        for i in range(6):
            try:
                return _call("POST", f"{self.toolbox}/process/execute", body)
            except urllib.error.HTTPError as e:
                # 409 and 429 come before the command runs, and so does the edge's 503 sandbox_not_ready;
                # another 503 may have come after it ran, so it is not retried
                before_run = e.code != 503 or _code(e) == "sandbox_not_ready"
                if e.code not in retry or not before_run or i == 5:
                    raise
                time.sleep(i + 1)

    def write(self, path, data: bytes):  # absolute path under /home/prized, up to 100 MiB
        return _call("POST", f"{self.toolbox}/files/upload?path={urllib.parse.quote(path)}", data=data)

    def read(self, path) -> bytes:
        return _call("GET", f"{self.toolbox}/files/download?path={urllib.parse.quote(path)}")

    def fork(self, count):
        """count live copies (memory, disk, processes). 409 fork_capacity carries `fits`: fork that many or fewer.
        A copy that never comes up gets a delete tried for every copy in the batch before the error is raised;
        a delete that fails leaves that copy to maxRuntimeMin."""
        out = _allocate(f"{API}/sandboxes/{self.id}/fork", {"count": count})
        copies = [Sandbox(s) for s in out["sandboxes"]]
        try:
            for c in copies:
                c.wait()
        except BaseException:
            for c in copies:
                try:
                    c.delete()
                except Exception:
                    pass  # maxRuntimeMin ends any delete that failed
            raise
        return copies

    def pause(self):
        return _call("POST", f"{API}/sandboxes/{self.id}/pause?wait=paused")["sandbox"]

    def delete(self):
        _call("DELETE", f"{API}/sandboxes/{self.id}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.delete()


if __name__ == "__main__":
    with Sandbox.create(max_runtime_min=10) as sbx:
        r = sbx.exec(" ".join(sys.argv[1:]) or "uname -a")
        print(sbx.id, "exit", r["exitCode"])
        print(r["stdout"], end="")
        print(r["stderr"], end="", file=sys.stderr)
