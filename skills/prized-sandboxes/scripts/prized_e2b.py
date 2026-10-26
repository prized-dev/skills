"""E2B-shaped client for Prized sandboxes. Standard library only, Python 3.9+. Copy this file into a project.

    from prized_e2b import Sandbox            # was: from e2b import Sandbox
    sbx = Sandbox.create(timeout=600)         # PRIZED_API_KEY in place of E2B_API_KEY
    print(sbx.commands.run("python3 --version").stdout)
    sbx.kill()

Calls keep E2B's names, arguments, results and exceptions. /home/user is /home/prized here: the adapter maps it in
paths, in command strings, cwd and env values (MAP_HOME_USER=False turns that off), and relative paths start in the
home folder, as on E2B. Commands run in a login shell (`bash -l`), as on E2B. Files outside the home folder (/tmp)
go through a copy. Most of what Prized does not have yet raises NotImplementedError naming the alternative.
Guide: https://prized.dev/docs/moving-from-e2b  API: https://prized.dev/docs/sandboxes-api
"""
import datetime, http.client, io, json, os, posixpath, re, shlex, socket, time, urllib.error, urllib.parse, urllib.request, uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Union

API = os.environ.get("PRIZED_API_URL", "https://api.prized.dev/api/v1")
HOME = "/home/prized"
TEMPLATES = {None: "prized-base-v1", "base": "prized-base-v1"}  # add your E2B template names here
SHAPE = {"vcpu": 2, "memoryMb": 1024}  # E2B's base is 2 vCPU and 512 MiB; 1 GB is Prized's least
MAP_HOME_USER, LOGIN_SHELL, PROBE_DELAY, POLL_S = True, True, 0.5, 0.5
MAX_BLOCKING_EXEC = 240  # seconds: a longer command runs in the background and is polled, as a silent connection gets cut
RETRIED = {"rate_limited", "sandbox_capacity", "sandbox_not_ready", "resolve_failed", "control_plane_unavailable",
           "sandbox_credentials_unavailable"}


class SandboxException(Exception): ...
class TimeoutException(SandboxException): ...
class NotFoundException(SandboxException): ...
class SandboxNotFoundException(NotFoundException): ...
class FileNotFoundException(NotFoundException): ...
class AuthenticationException(SandboxException): ...
class InvalidArgumentException(SandboxException): ...
class RateLimitException(SandboxException): ...
class ServiceBusyException(SandboxException): ...
class TemplateException(SandboxException): ...
class ConnectionException(SandboxException): ...  # no answer: the request may or may not have landed
class FileType(str, Enum): FILE = "file"; DIR = "dir"
class SandboxState(str, Enum): RUNNING = "running"; PAUSED = "paused"
ERRORS = {400: InvalidArgumentException, 401: AuthenticationException, 403: AuthenticationException,
          404: SandboxNotFoundException, 422: InvalidArgumentException, 429: RateLimitException, 503: ServiceBusyException}
CODES = {"template_not_found": TemplateException, "path_outside_root": InvalidArgumentException,
         "permission_denied": InvalidArgumentException, "symlink_not_allowed": InvalidArgumentException}


@dataclass
class CommandResult: stdout: str; stderr: str; exit_code: int; error: Optional[str] = None
@dataclass
class WriteInfo: name: str; type: FileType; path: str
@dataclass
class WriteEntry: path: str; data: Union[str, bytes]
@dataclass
class EntryInfo: name: str; type: FileType; path: str; size: int = 0
@dataclass
class ProcessInfo: pid: int; cmd: str; args: list = field(default_factory=list); tag: Optional[str] = None
@dataclass
class SandboxQuery: metadata: Optional[Dict[str, str]] = None; state: Optional[list] = None
@dataclass
class SandboxInfo:
    sandbox_id: str; template_id: str; state: str; started_at: datetime.datetime; end_at: Optional[datetime.datetime]
    metadata: Dict[str, str] = field(default_factory=dict); cpu_count: int = 0; memory_mb: int = 0


class CommandExitException(SandboxException, CommandResult):
    def __init__(self, r):
        CommandResult.__init__(self, r.stdout, r.stderr, r.exit_code, r.error)
        SandboxException.__init__(self, f"Command exited with code {r.exit_code} and error:\n{r.stderr[-2000:]}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a): return None  # never resend the key to wherever a redirect points
_open = urllib.request.build_opener(_NoRedirect).open


def _req(method, url, body=None, data=None, key=None, headers=None, timeout=60):
    """One API call. Refusals made before anything ran (RETRIED) wait Retry-After and go again; nothing else is retried."""
    key = key or os.environ.get("PRIZED_API_KEY")
    if not key: raise AuthenticationException("no API key: set PRIZED_API_KEY (dcp_...) or pass api_key=")
    h = {"Authorization": "Bearer " + key, **(headers or {})}
    if body is not None: data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    where = f"{method} {url.split('?')[0]}"
    for attempt in range(8):
        try:
            with _open(urllib.request.Request(url, data, h, method=method), timeout=timeout) as r:
                out = r.read()
                return json.loads(out) if r.headers.get_content_type() == "application/json" else out
        except urllib.error.HTTPError as e:
            try: info = json.loads(e.read() or b"{}")
            except ValueError: info = {}
            code = info.get("error", "")
            if code in RETRIED and attempt < 7:
                time.sleep(min(float(e.headers.get("Retry-After") or 1), 30)); continue
            cls = CODES.get(code) or ERRORS.get(e.code, SandboxException)
            err = cls(f"{e.code} {code} {info.get('reason') or ''} {info.get('message') or info.get('detail') or ''}".strip())
            err.status, err.code, err.body = e.code, code, info
            raise err from None
        except (OSError, http.client.HTTPException) as e:  # socket.timeout is not TimeoutError before 3.10
            slow = isinstance(e, (socket.timeout, TimeoutError)) or isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError))
            raise (TimeoutException if slow else ConnectionException)(f"{where}: {'no answer in %ss' % timeout if slow else e}") from None


def _path(p):
    if not p: raise InvalidArgumentException("empty path")
    if p == "/home/user" or p.startswith("/home/user/"): p = HOME + p[len("/home/user"):]
    return posixpath.normpath(p if p.startswith("/") else posixpath.join(HOME, p))


def _map(s):  # /home/user in a command string or env value, not inside another path (/mnt/home/user)
    return re.sub(r"(?<![\w./-])/home/user(?=/|\b|$)", HOME, s) if MAP_HOME_USER and isinstance(s, str) else s


def _minutes(seconds): return max(1, -(-int(seconds) // 60))
def _when(t): return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
def _now(): return datetime.datetime.now(datetime.timezone.utc)


class _both:
    """Sandbox.kill(id) and sbx.kill() both work, as on E2B (also connect, set_timeout, get_info, fork)."""
    def __init__(self, f): self.f = f
    def __get__(self, obj, cls):
        if obj is None: return lambda sandbox_id, *a, **k: self.f(cls, sandbox_id, *a, **k)
        return lambda *a, **k: self.f(cls, obj.sandbox_id, *a, **{"api_key": obj._key, **k})


class Sandbox:
    def __init__(self, sandbox=None, api_key=None, **opts):
        if not isinstance(sandbox, dict):  # e2b v1's Sandbox(template, timeout=...) made a sandbox: so does this
            sandbox = type(self).create(**{**({"template": sandbox} if sandbox else {}), **opts}, api_key=api_key)._s
        self._key, self._s = api_key, sandbox
        self.sandbox_id, self._edge = sandbox["id"], sandbox.get("toolboxBase")
        self.commands, self.files = Commands(self), Files(self)

    @classmethod
    def create(cls, template=None, timeout=None, metadata=None, envs=None, api_key=None, allow_internet_access=True,
               lifecycle=None, auto_pause=False, vcpu=None, memory_mb=None, disk_gb=None, auto_delete_min=None, mcp=None,
               network=None, **_):
        """timeout (seconds, default 300) becomes the run time. With lifecycle={"on_timeout": "pause"} (or the old
        auto_pause=True) it pauses after `timeout` idle seconds instead; any request resumes it, as auto_resume does.
        Prized only: vcpu, memory_mb and disk_gb set the shape; auto_delete_min deletes it after that many minutes paused."""
        if template not in TEMPLATES and not str(template).startswith("prized-"):
            raise TemplateException(f"no template {template!r}: Prized has prized-base-v1 and prized-agent-v1; set one up "
                                    "and fork it (https://prized.dev/docs/sandboxes-own-template), or map it in TEMPLATES")
        if mcp or network or allow_internet_access is False:
            raise NotImplementedError("no MCP gateway or egress rules on Prized yet; every sandbox has outbound internet")
        on_timeout = (lifecycle or {}).get("on_timeout")
        pause = auto_pause or on_timeout == "pause" or (isinstance(on_timeout, dict) and on_timeout.get("action") == "pause")
        body = {"template": TEMPLATES.get(template, template), **({"labels": metadata} if metadata else {}),
                **({"envVars": {k: _map(v) for k, v in envs.items()}} if envs else {}),
                ("autoPauseMin" if pause else "maxRuntimeMin"): _minutes(timeout or 300),
                **({"autoDeleteMin": int(auto_delete_min)} if auto_delete_min else {}),
                "resources": {k: v for k, v in (("vcpu", vcpu or SHAPE["vcpu"]), ("memoryMb", memory_mb or SHAPE["memoryMb"]), ("diskGb", disk_gb)) if v}}
        idem = {"Idempotency-Key": uuid.uuid4().hex}  # a retried create returns the same sandbox, never a second
        try: out = _req("POST", f"{API}/sandboxes?wait=running", body, key=api_key, headers=idem)
        except (TimeoutException, ConnectionException):  # the answer was lost: the same key finds what committed
            out = _req("POST", f"{API}/sandboxes", body, key=api_key, headers=idem)
        sbx = cls(out["sandbox"], api_key)
        try: return sbx._ready()
        except BaseException: sbx.kill(); raise

    @_both
    def connect(cls, sandbox_id, timeout=None, api_key=None, **_):
        """Attach by id, resuming it if paused (memory and processes as they were). Like E2B, its time left only grows:
        to at least `timeout` seconds (default 300) from now."""
        s = _req("GET", f"{API}/sandboxes/{sandbox_id}", key=api_key)["sandbox"]
        if s["state"] in ("paused", "pausing"):
            s = _req("POST", f"{API}/sandboxes/{sandbox_id}/resume?wait=running", key=api_key)["sandbox"]
        sbx = cls(s, api_key)._ready()
        try: sbx._time(timeout or 300, only_longer=True)
        except RateLimitException as e:  # past the run time allowed (the free tier's 60 minutes): it keeps what it has
            if e.body.get("reason") != "max_runtime": raise
        return sbx

    def _get(self):
        self._s = _req("GET", f"{API}/sandboxes/{self.sandbox_id}", key=self._key)["sandbox"]
        return self._s

    def _time(self, seconds, only_longer=False):
        """A sandbox made to pause on timeout counts idle time: this is activity, never a deletion time."""
        s = self._get()
        if s.get("autoPauseMin"): return _req("POST", f"{API}/sandboxes/{self.sandbox_id}/refresh", key=self._key)
        end = _when(s.get("expiresAt"))
        if s["state"] == "running" and not (only_longer and end and end >= _now() + datetime.timedelta(seconds=seconds)):
            _req("POST", f"{API}/sandboxes/{self.sandbox_id}/timeout", {"inMin": _minutes(seconds)}, key=self._key)

    def _ready(self, wait_s=180):
        end = time.time() + wait_s
        while self._s["state"] in ("starting", "pausing"):
            if time.time() > end: raise TimeoutException(f"{self.sandbox_id} still {self._s['state']} after {wait_s}s")
            time.sleep(POLL_S); self._get()
        if self._s["state"] != "running": raise SandboxException(f"{self.sandbox_id} is {self._s['state']}: {self._s.get('errorReason')}")
        self._edge = self._s["toolboxBase"]
        for i in range(10):  # right after `running` the edge can answer 409/502 for a moment
            try: self._exec({"command": "true", "cwd": HOME}, 30); return self
            except (SandboxException, ConnectionException) as e:  # no answer at all counts as a 502; a timeout does not
                if isinstance(e, TimeoutException) or getattr(e, "status", 502) not in (409, 502, 503) or i == 9: raise
                time.sleep(PROBE_DELAY * (i + 1))

    def _exec(self, body, timeout):
        return _req("POST", f"{self._edge}/process/execute", body, key=self._key, timeout=timeout + 30)

    def pause(self, **_):
        """True once paused (memory and processes kept), False if it already was. beta_pause is the old name."""
        if self._get()["state"] == "paused": return False
        s, end = _req("POST", f"{API}/sandboxes/{self.sandbox_id}/pause?wait=paused", key=self._key)["sandbox"], time.time() + 300
        while s["state"] == "pausing":
            if time.time() > end: raise TimeoutException(f"{self.sandbox_id} still pausing after 300s")
            time.sleep(POLL_S); s = self._get()
        return True
    beta_pause = pause

    @_both
    def fork(cls, sandbox_id, timeout=None, count=None, metadata=None, api_key=None, **_):
        """Live copies (memory, disk, processes), all on the parent's machine: up to 256 a call, or a 409 fork_capacity.
        Each gets the parent's run time unless `timeout` (on the free tier, copies end when the parent does)."""
        body = {"count": count or 1, **({"labels": metadata} if metadata else {}), **({"maxRuntimeMin": _minutes(timeout)} if timeout else {})}
        url, idem = f"{API}/sandboxes/{sandbox_id}/fork", {"Idempotency-Key": uuid.uuid4().hex}
        try: out = _req("POST", url, body, key=api_key, headers=idem)
        except (TimeoutException, ConnectionException):  # the answer was lost: the same key finds the copies it made
            out = _req("POST", url, body, key=api_key, headers=idem)
        kids = [cls(s, api_key) for s in out["sandboxes"]]
        try: return [k._ready() for k in kids]
        except BaseException:  # all or none, as the fork itself is
            for k in kids: k.kill()
            raise

    @_both
    def kill(cls, sandbox_id, api_key=None, **_):
        """True if it was there (one already deleting answers True until it is gone), False if not."""
        try: _req("DELETE", f"{API}/sandboxes/{sandbox_id}", key=api_key); return True
        except NotFoundException: return False

    @_both
    def set_timeout(cls, sandbox_id, timeout, api_key=None, **_):
        """Deleted `timeout` seconds from now (earlier or later; on the free tier only earlier). On a pause-on-timeout
        sandbox it counts as activity; a paused sandbox has no clock to set, and a resume starts its run time again."""
        cls(_req("GET", f"{API}/sandboxes/{sandbox_id}", key=api_key)["sandbox"], api_key)._time(timeout)

    @_both
    def get_info(cls, sandbox_id, api_key=None, **_):
        return cls._info(_req("GET", f"{API}/sandboxes/{sandbox_id}", key=api_key)["sandbox"])

    @staticmethod
    def _info(s):
        r = s.get("resources") or {}
        return SandboxInfo(s["id"], s["template"], s["state"], _when(s["createdAt"]), _when(s.get("expiresAt")),
                           s.get("labels") or {}, r.get("vcpu", 0), r.get("memoryMb", 0))

    def is_running(self, **_):
        try: return self._get()["state"] == "running"
        except NotFoundException: return False

    @classmethod
    def list(cls, query=None, api_key=None, **_):
        """One page holding every match, filtered here after one GET: metadata (labels), and state (default: all but
        `deleting`, as a deleted sandbox lingers there a moment)."""
        meta, states = (query.metadata or {}, query.state) if query else ({}, None)
        return _Page(cls._info(s) for s in _req("GET", f"{API}/sandboxes", key=api_key)["sandboxes"]
                     if all((s.get("labels") or {}).get(k) == v for k, v in meta.items())
                     and (s["state"] in states if states else s["state"] != "deleting"))

    def get_host(self, port):
        raise NotImplementedError("Prized sandboxes take no inbound connections yet; serve from a box: "
                                  "`prized ports share PORT` (https://prized.dev/docs/ports)")

    def __enter__(self): return self
    def __exit__(self, *exc): self.kill()


class _Page(list):  # e2b v1 returns a list, v2 a paginator (while p.has_next: p.next_items()): this is both
    def __init__(self, items): super().__init__(items); self.has_next = True
    def next_items(self): self.has_next = False; return list(self)


class Commands:
    def __init__(self, sbx): self._sbx = sbx

    def run(self, cmd, background=False, envs=None, user=None, cwd=None, on_stdout=None, on_stderr=None, timeout=60, **_):
        """timeout in seconds (0 = none). Over MAX_BLOCKING_EXEC (4 minutes), or none, it runs in the background and is polled."""
        if user == "root": raise NotImplementedError("Prized sandboxes run as `prized`, without sudo; use a box for root")
        if background: return self._start(cmd, envs, cwd, on_stdout, on_stderr)
        if not timeout or timeout > MAX_BLOCKING_EXEC:
            return self._start(cmd, envs, cwd, None, None).wait(on_stdout, on_stderr, timeout=timeout or None)
        return self._run(cmd, envs, cwd, timeout, on_stdout, on_stderr)

    def _run(self, cmd, envs=None, cwd=None, timeout=60, on_stdout=None, on_stderr=None):  # one exec, answered when it ends
        line = f"bash -lc {shlex.quote(_map(cmd))}" if LOGIN_SHELL else _map(cmd)
        envs = {k: _map(v) for k, v in (envs or {}).items()}
        out = self._sbx._exec({"command": line, "cwd": _path(_map(cwd or HOME)), "timeout": timeout, **({"env": envs} if envs else {})}, timeout)
        r = CommandResult(out["stdout"], out["stderr"], out["exitCode"])
        if on_stdout and r.stdout: on_stdout(r.stdout)  # once, when it ends: no streaming yet
        if on_stderr and r.stderr: on_stderr(r.stderr)
        if out.get("timedOut"): raise TimeoutException(f"command timed out after {timeout}s")
        if r.exit_code != 0: raise CommandExitException(r)
        return r

    def _start(self, cmd, envs, cwd, on_stdout, on_stderr):
        d = f"{HOME}/.e2b-runs/{uuid.uuid4().hex[:12]}"
        inner = (f"echo $$ > {d}/pid; {{ cd {shlex.quote(_path(_map(cwd or HOME)))} && bash -l -c {shlex.quote(_map(cmd))}; }}"
                 f" > {d}/out 2> {d}/err < /dev/null; echo $? > {d}/exit")
        script = (f"mkdir -p {d} && : > {d}/out && : > {d}/err && setsid -f bash -c {shlex.quote(inner)} > /dev/null 2>&1 < /dev/null; "
                  f"for i in $(seq 100); do [ -s {d}/pid ] && break; sleep 0.05; done; cat {d}/pid")
        return CommandHandle(self._sbx, int(self._run(script, envs, timeout=30).stdout.strip()), d, on_stdout, on_stderr)

    def kill(self, pid, **_):  # its process group (a background handle's pid leads one), else the one process
        pid = int(pid)
        return self._run(f"{{ kill -KILL -- -{pid} || kill -KILL {pid}; }} 2>/dev/null && echo 1 || true").stdout.strip() == "1"

    def list(self, **_):
        rows = self._run("ps -u \"$(id -u)\" -o pid=,args=").stdout.splitlines()
        return [ProcessInfo(int(p), a.split(" ")[0], a.split(" ")[1:]) for p, a in (r.strip().split(" ", 1) for r in rows if r.strip())]

    def send_stdin(self, *a, **k): raise NotImplementedError("no stdin on Prized yet; write a file and read it")


class CommandHandle:
    """A background command: it runs in its own session, writing to ~/.e2b-runs/<id>/{out,err,exit}."""
    def __init__(self, sbx, pid, d, on_stdout=None, on_stderr=None):
        self._sbx, self.pid, self._d, self._cb, self._done = sbx, pid, d, (on_stdout, on_stderr), False

    def wait(self, on_stdout=None, on_stderr=None, poll_s=1.0, timeout=None):
        d, run, end = self._d, self._sbx.commands._run, time.time() + timeout if timeout else None
        alive = f"kill -0 {self.pid} 2>/dev/null && ! ps -o stat= -p {self.pid} | grep -q Z"
        while not (code := run(f"cat {d}/exit 2>/dev/null || {{ {alive}; }} || cat {d}/exit 2>/dev/null || echo -1").stdout.strip()):
            if end and time.time() > end:
                self.kill(); self._done = True; run(f"rm -rf {d}")
                raise TimeoutException(f"command timed out after {timeout}s")
            time.sleep(poll_s)
        r = CommandResult(self._sbx.files.read(f"{d}/out"), self._sbx.files.read(f"{d}/err"), int(code))
        self._done = True; run(f"rm -rf {d}")
        for cb, text in zip((on_stdout or self._cb[0], on_stderr or self._cb[1]), (r.stdout, r.stderr)):
            if cb and text: cb(text)
        if r.exit_code != 0: raise CommandExitException(r)
        return r

    def kill(self):  # SIGKILL to its whole session, as E2B's kill does; False once it has ended
        if self._done: return False
        out = self._sbx.commands._run(f"kill -KILL -- -{self.pid} 2>/dev/null && {{ [ -s {self._d}/exit ] || echo -1 > {self._d}/exit; echo 1; }} || true")
        return out.stdout.strip() == "1"


class Files:
    """read/write go through the edge, which reaches the home folder only; elsewhere (/tmp) they go through a copy."""
    def __init__(self, sbx): self._sbx = sbx

    def _url(self, op, p): return f"{self._sbx._edge}/files/{op}?path={urllib.parse.quote(p)}"
    def _home(self, p): return p == HOME or p.startswith(HOME + "/")
    def _sh(self, script): return self._sbx.commands._run(script, timeout=MAX_BLOCKING_EXEC)

    def read(self, path, format="text", **_):
        p = _path(path); src = p if self._home(p) else f"{HOME}/.e2b-tmp/{uuid.uuid4().hex}"
        try:
            if src != p: self._sh(f"mkdir -p {HOME}/.e2b-tmp && cp -- {shlex.quote(p)} {src}")
            b = _req("GET", self._url("download", src), key=self._sbx._key, timeout=660)
        except (NotFoundException, CommandExitException) as e: raise FileNotFoundException(f"{p}: {e}") from None
        finally:
            if src != p: self._sh(f"rm -f {src}")
        return b.decode(errors="replace") if format == "text" else io.BytesIO(b) if format == "stream" else bytearray(b)

    def write(self, path, data=None, **_):
        """Creates missing directories and replaces the file whole. Up to 100 MiB a file."""
        if isinstance(path, list): return self.write_files(path)  # e2b v1's list form
        data = data.read() if hasattr(data, "read") else data
        p = _path(path); dst = p if self._home(p) else f"{HOME}/.e2b-tmp/{uuid.uuid4().hex}"
        _req("POST", self._url("upload", dst), data=data.encode() if isinstance(data, str) else bytes(data), key=self._sbx._key, timeout=660)
        if dst != p:
            try: self._sh(f"mkdir -p {shlex.quote(posixpath.dirname(p))} && mv -fT {dst} {shlex.quote(p)}")
            except BaseException:
                try: self._sh(f"rm -f {dst}")
                except Exception: pass  # the write's own error is the one to raise
                raise
        return WriteInfo(posixpath.basename(p), FileType.FILE, p)

    def write_files(self, files, **_):
        return [self.write(*((f["path"], f["data"]) if isinstance(f, dict) else (f.path, f.data))) for f in files]

    def _ok(self, script):  # True when the script exits 0
        try: self._sh(script); return True
        except CommandExitException: return False

    def _found(self, script, path):  # run it; a missing path is FileNotFoundException, as on E2B
        try: return self._sh(script).stdout
        except CommandExitException as e:
            if "No such file" in e.stderr: raise FileNotFoundException(f"{_path(path)}: no such file or directory") from None
            raise

    def exists(self, path, **_): return self._ok(f"test -e {shlex.quote(_path(path))}")
    def make_dir(self, path, **_): return self._ok(f"! test -d {shlex.quote(_path(path))} && mkdir -p {shlex.quote(_path(path))}")
    def remove(self, path, **_): self._sh(f"rm -rf -- {shlex.quote(_path(path))}")

    def rename(self, old_path, new_path, **_):
        self._found(f"mv -T -- {shlex.quote(_path(old_path))} {shlex.quote(_path(new_path))}", old_path)
        return self.get_info(new_path)

    def list(self, path, depth=1, **_):
        out = self._found(f"find {shlex.quote(_path(path))} -mindepth 1 -maxdepth {int(depth)} -printf '%y\\t%s\\t%p\\n'", path)
        return [EntryInfo(posixpath.basename(p), FileType.DIR if t == "d" else FileType.FILE, p, int(s))
                for t, s, p in (line.split("\t", 2) for line in out.splitlines())]

    def get_info(self, path, **_):
        p = _path(path)
        t, s = self._found(f"stat -c '%F\t%s' -- {shlex.quote(p)}", path).strip().split("\t")
        return EntryInfo(posixpath.basename(p), FileType.DIR if t == "directory" else FileType.FILE, p, int(s))

    def watch_dir(self, *a, **k): raise NotImplementedError("no file watching on Prized yet; poll files.list()")
