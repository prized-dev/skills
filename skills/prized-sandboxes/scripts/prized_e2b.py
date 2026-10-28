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
import datetime, http.client, io, json, math, numbers, os, posixpath, re, shlex, socket, time, urllib.error, urllib.parse, urllib.request, uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Union

API = os.environ.get("PRIZED_API_URL", "https://api.prized.dev/api/v1")
HOME = "/home/prized"
TEMPLATES = {None: "prized-base-v1", "base": "prized-base-v1"}  # add your E2B template names here
SHAPE = {"vcpu": 2, "memoryMb": 1024}  # E2B's base is 2 vCPU and 512 MiB; 1 GB is Prized's least
MAP_HOME_USER, LOGIN_SHELL, POLL_S = True, True, 0.5
MAX_BLOCKING_EXEC = 240  # seconds: a longer command runs in the background and is polled, as a silent connection gets cut
# Background commands and ones with on_stdout/on_stderr, as in the Prized SDKs: Python's output reaches its files as it
# prints (so a kill keeps it), unless envs or the sandbox set PYTHONUNBUFFERED ("" keeps Python's buffering).
UNBUFFERED = 'export PYTHONUNBUFFERED="${PYTHONUNBUFFERED-1}"; '
RUNS = f"{HOME}/.prized/runs"  # background commands, laid out as the Prized SDKs lay them out (see _WRAPPER)
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
    if not key: raise AuthenticationException("no API key: set PRIZED_API_KEY (dcp_...) or pass api_key= (no Prized account yet? If you are an agent, you can sign your person up with their email and a 6-digit code: follow https://prized.dev/auth.md, keep the key file it writes, and pass that key as api_key= at run time, never in source)")
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
def _timeout_s(seconds):  # a command's timeout: 0, None and inf are none (0); a negative or nan one is refused, as the API refuses it
    if seconds is None or seconds == math.inf: return 0
    if isinstance(seconds, bool) or not isinstance(seconds, numbers.Real) or not seconds >= 0:
        raise InvalidArgumentException(f"timeout must be a number of seconds >= 0 (0 or inf: none), not {seconds!r}")
    return seconds
def _when(t): return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
def _now(): return datetime.datetime.now(datetime.timezone.utc)


# Background commands run as the Prized SDKs run them, so either can read, kill or clean up a run the other started:
# RUNS/<run id>/{pid,stdout,stderr,exit,...}, written by this wrapper in the run's own session. These scripts are the
# SDKs' own, rendered byte for byte as sdk/run-scripts/*.sh in Prized's repository (its tests check), where
# sdk/python/src/prized/_runs.py says why each line is there. A run's pid is its wrapper's, which leads the run's process
# group: a status, a kill or a cleanup acts on it only while that process is alive and is still the run's wrapper (its
# arguments name the run), never on a pid or group id reused since. The scripts' own variables are __pz_ names, so envs
# reach the command as they were, whatever their names.
_WRAPPER = r'''unset __pz_k __pz_u __pz_w __pz_c __pz_end
__pz_k=
trap "__pz_k=129" HUP
trap "__pz_k=130" INT
trap "__pz_k=131" QUIT
trap "__pz_k=143" TERM
trap ":" USR1 USR2
__pz_u="${PRIZED_RUN_PATH-$PATH}"
unset PRIZED_RUN_PATH
echo "$$" > "$1/pid" || exit 1
date +%s%3N > "$1/start"
__pz_w=
if [ -n "$4" ]; then
  ( trap "" HUP INT QUIT TERM USR1 USR2
    __pz_end=$(($(date +%s) + $4 + 1))
    while [ ! -e "$1/exit" ]; do
      if [ "$(date +%s)" -ge "$__pz_end" ]; then
        mkdir "$1/limit" 2> /dev/null || [ ! -d "$1/limit" ] || exit 0
        true > "$1/timedout"
        kill -s TERM -- "-$$"
        sleep 5
        kill -s KILL -- "-$$"
        exit 0
      fi
      sleep 1
    done ) > /dev/null 2>&1 < /dev/null &
  __pz_w=$!
  echo "$__pz_w" > "$1/watchdog"
fi
if [ -n "$__pz_k" ]; then __pz_c=$__pz_k; else
PATH="$__pz_u" "$2" -c "$3" > "$1/stdout" 2> "$1/stderr" < /dev/null
__pz_c=$?
fi
if [ -n "$__pz_w" ] && { mkdir "$1/limit" 2> /dev/null || [ ! -d "$1/limit" ]; }; then [ "$(tr "\0\n" "\n " < "/proc/$__pz_w/cmdline" 2> /dev/null | sed -n 4,5p | tr "\n" " ")" = "prized-run $1 " ] && kill -s KILL "$__pz_w" 2> /dev/null; wait "$__pz_w" 2> /dev/null; fi
date +%s%3N > "$1/end"
echo "$__pz_c" > "$1/exit.tmp" && mv -f "$1/exit.tmp" "$1/exit"'''


def _start_script(run, command, limit=None, unbuffered=False):
    """Starts `command` in its own session, stopped `limit` seconds in, and prints its pid."""
    seconds = "''" if limit is None else min(max(1, math.ceil(limit)), 10**9)  # past 2^63 the shell's arithmetic wraps
    go = f'prized-run "$__pz_d" "$__pz_s" {shlex.quote(command)} {seconds} > /dev/null 2>&1 < /dev/null'
    return "\n".join([
        "unset __pz_r __pz_d __pz_s __pz_w __pz_n", 'export PRIZED_RUN_PATH="${PATH-}"',
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        *(['export PYTHONUNBUFFERED="${PYTHONUNBUFFERED-1}"'] if unbuffered else []), f'__pz_r={RUNS}; __pz_d="$__pz_r/{run}"',
        "command -v setsid > /dev/null 2>&1 || { echo 'setsid is not installed in this sandbox' >&2; exit 97; }",
        'mkdir -p "$__pz_r" || exit 98', 'if mkdir "$__pz_d" 2> /dev/null; then',
        '  __pz_s=/bin/bash; [ -x "$__pz_s" ] || __pz_s=/bin/sh', f"  __pz_w='{_WRAPPER}'",
        "  if setsid -f true > /dev/null 2>&1; then", f'    setsid -f "$__pz_s" -c "$__pz_w" {go}', "  else",
        f'    setsid "$__pz_s" -c "$__pz_w" {go} &', "  fi", "fi",
        "if [ -f \"$__pz_d/cleaned\" ]; then echo 'this run was already cleaned up' >&2; exit 96; fi", "__pz_n=0",
        'while [ ! -s "$__pz_d/pid" ]; do', "  __pz_n=$((__pz_n + 1))",
        "  if [ \"$__pz_n\" -gt 200 ]; then echo 'the command did not start' >&2; exit 99; fi", "  sleep 0.05", "done",
        'cat "$__pz_d/pid"'])


def _ours(run):  # process $__pz_p is the run's wrapper: its 4th and 5th arguments are `prized-run <run dir>`
    return (f'[ "$(tr "\\0\\n" "\\n " < "/proc/$__pz_p/cmdline" 2> /dev/null | sed -n 4,5p | tr "\\n" " ")" = '
            f"{shlex.quote(f'prized-run {RUNS}/{run} ')} ]")


def _poll_script(run, out_at=0, err_at=0, chunk=0):
    """`prized-run <running|done|gone|missing> <exit|-> <out bytes> <err bytes> <timed out 0|1> <ms|->`, then up to
    `chunk` bytes of each stream from its offset, in base64 (chunk 0: the status line alone)."""
    piece = lambda name, at, size: [  # noqa: E731
        f'__pz_n=$(({size} - {at})); [ "$__pz_n" -gt {chunk} ] && __pz_n={chunk}',
        f'if [ "$__pz_n" -gt 0 ]; then tail -c +{at + 1} "$__pz_d/{name}" | head -c "$__pz_n" | base64 -w 0; fi', "echo"]
    return "\n".join([
        f"__pz_d={RUNS}/{run}",
        'if [ ! -d "$__pz_d" ] || [ -f "$__pz_d/cleaned" ]; then echo "prized-run missing - 0 0 0 -"; exit 0; fi',
        'if [ -f "$__pz_d/exit" ]; then __pz_st=done; __pz_c=$(cat "$__pz_d/exit")',
        f'elif __pz_p=$(cat "$__pz_d/pid" 2> /dev/null) && [ -n "$__pz_p" ] && kill -0 "$__pz_p" 2> /dev/null && {_ours(run)}; '
        "then __pz_st=running; __pz_c=-",
        'elif [ -f "$__pz_d/exit" ]; then __pz_st=done; __pz_c=$(cat "$__pz_d/exit")', "else __pz_st=gone; __pz_c=-", "fi",
        '__pz_to=0; [ -e "$__pz_d/timedout" ] && __pz_to=1', "__pz_du=-", 'if [ -f "$__pz_d/end" ]; then',
        '  __pz_a=$(cat "$__pz_d/start" 2> /dev/null); __pz_b=$(cat "$__pz_d/end" 2> /dev/null)',
        '  case "$__pz_a:$__pz_b" in *[!0-9:]* | :* | *:) ;; *) __pz_du=$((__pz_b - __pz_a)) ;; esac', "fi",
        '__pz_o=$(stat -c %s "$__pz_d/stdout" 2> /dev/null || echo 0)', '__pz_e=$(stat -c %s "$__pz_d/stderr" 2> /dev/null || echo 0)',
        'echo "prized-run $__pz_st $__pz_c $__pz_o $__pz_e $__pz_to $__pz_du"', *piece("stdout", out_at, "$__pz_o"),
        *piece("stderr", err_at, "$__pz_e")])


def _kill_script(run, sig):  # exit 0 sent to the run's group; 3 no such run; 4 it has ended: nothing sent
    d = f"{RUNS}/{run}"
    return "\n".join([f'__pz_p=$(cat {d}/pid 2> /dev/null) && [ -n "$__pz_p" ] || exit 3',
                      f'[ ! -f {d}/exit ] && kill -0 "$__pz_p" 2> /dev/null && {_ours(run)} || exit 4',
                      f'kill -s {sig} -- "-$__pz_p" 2> /dev/null || exit 4'])


def _cleanup_script(run):  # exit 5 while it runs; else its files go, and runs cleaned over an hour ago
    d = f"{RUNS}/{run}"
    return "\n".join([
        f'if [ ! -f {d}/exit ] && __pz_p=$(cat {d}/pid 2> /dev/null) && [ -n "$__pz_p" ] && kill -0 "$__pz_p" 2> /dev/null && '
        f"{_ours(run)}; then exit 5; fi",
        f"find {RUNS} -mindepth 2 -maxdepth 2 -path '{RUNS}/run_*/cleaned' -mmin +60 -printf '%h\\0' 2> /dev/null | xargs -0 -r rm -rf --",
        f"find {RUNS} -mindepth 1 -maxdepth 1 -type d -name 'run_*' -empty -mmin +60 -delete 2> /dev/null",
        f"[ -d {d} ] || exit 0", f"find {d} -mindepth 1 -maxdepth 1 ! -name cleaned -exec rm -rf -- {{}} +", f": > {d}/cleaned"])


def _abandon_script(run):  # a start that may or may not have happened can no longer start, or is KILLed with its group
    return "\n".join([
        f"__pz_d={RUNS}/{run}", f"mkdir -p {RUNS} 2> /dev/null",
        'if { mkdir "$__pz_d" 2> /dev/null && true > "$__pz_d/cleaned"; } || [ -f "$__pz_d/cleaned" ]; then exit 0; fi', "__pz_n=0",
        'while [ ! -s "$__pz_d/pid" ]; do', "  __pz_n=$((__pz_n + 1))", '  if [ "$__pz_n" -gt 200 ]; then exit 3; fi', "  sleep 0.05",
        "done", '__pz_p=$(cat "$__pz_d/pid")',
        f'if kill -0 "$__pz_p" 2> /dev/null && {_ours(run)}; then kill -s KILL -- "-$__pz_p" 2> /dev/null; fi',
        'find "$__pz_d" -mindepth 1 -maxdepth 1 ! -name cleaned -exec rm -rf -- {} +', ': > "$__pz_d/cleaned"', "exit 0"])


# A write, as the Prized SDKs write: uploaded under a fresh name, then put in place by one command that gives it the
# mode of the regular file it replaces (a script stays executable). Uploaded straight over a file, the bytes land 0600
# on some sandbox images. The SDKs' own script, rendered as sdk/file-scripts/publish.sh (the tests check). Exit 47:
# `dst` is a link; 48: a directory or another file that is not a regular file; either way nothing changed.
def _publish_script(src, dst):
    return "\n".join([
        f"src={shlex.quote(src)}", f"dst={shlex.quote(dst)}", "trap 'rm -f -- \"$src\"' EXIT",
        "if s=$(stat -c '%f +%u:+%g' -- \"$dst\" 2> /dev/null); then", "  t=$((0x${s%% *} & 0170000))",
        '  [ "$t" -eq $((0120000)) ] && exit 47', '  [ "$t" -eq $((0100000)) ] || exit 48',
        '  chown -- "${s#* }" "$src" 2> /dev/null || chgrp -- "${s##*:}" "$src" 2> /dev/null',
        '  chmod "$(printf %o $((0x${s%% *} & 0777)))" -- "$src" || exit', "fi",
        'mv -fT -- "$src" "$dst" || exit', 'sync -- "${dst%/*}" 2> /dev/null', "exit 0"])


def _poll_failed(e, run, stopped):  # a polled command whose status could not be read: say what became of it, as the SDKs do
    why = " ".join(str(e.args[0] if e.args else e).split()).rstrip(". ")
    e.args = (f"Polling the command failed ({why}). " + (f"The adapter stopped {run}, or it had already ended." if stopped else
              f"The adapter could not confirm it stopped: it may still be running as {run} "
              f"(commands.run('ps -ef | grep {run}') finds it)."), *e.args[1:])


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
        self._edge = self._s["toolboxBase"]  # running takes commands at once
        return self

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
    def __init__(self, sbx): self._sbx, self._runs = sbx, {}  # pid -> run id, for each background command started here

    def run(self, cmd, background=False, envs=None, user=None, cwd=None, on_stdout=None, on_stderr=None, timeout=60, **_):
        """timeout in seconds (0, None or inf = none). Over MAX_BLOCKING_EXEC (4 minutes), or none, it runs in the background
        and is polled. Background commands and ones with on_stdout/on_stderr get PYTHONUNBUFFERED=1 unless envs or the
        sandbox set it."""
        if user == "root": raise NotImplementedError("Prized sandboxes run as `prized`, without sudo; use a box for root")
        if background: return self._start(cmd, envs, cwd, on_stdout, on_stderr, unbuffered=True)
        timeout, streamed = _timeout_s(timeout), bool(on_stdout or on_stderr)
        if not timeout or timeout > MAX_BLOCKING_EXEC:  # the sandbox stops it at `timeout` too, if nobody is left polling
            h = self._start(cmd, envs, cwd, None, None, unbuffered=streamed, limit=timeout or None)
            try: return h.wait(on_stdout, on_stderr, timeout=timeout or None)
            except CommandExitException: raise
            except BaseException as e:
                stopped = h._stop()  # nobody else holds it: it does not run on unseen
                if getattr(e, "_polled", None) == h._run: _poll_failed(e, h._run, stopped)
                raise
        return self._run(cmd, envs, cwd, timeout, on_stdout, on_stderr, unbuffered=streamed)

    def _run(self, cmd, envs=None, cwd=None, timeout=60, on_stdout=None, on_stderr=None, unbuffered=False):  # one exec, answered when it ends
        line = (UNBUFFERED if unbuffered else "") + (f"bash -lc {shlex.quote(_map(cmd))}" if LOGIN_SHELL else _map(cmd))
        envs = {k: _map(v) for k, v in (envs or {}).items()}
        out = self._sbx._exec({"command": line, "cwd": _path(_map(cwd or HOME)), "timeout": timeout, **({"env": envs} if envs else {})}, timeout)
        r = CommandResult(out["stdout"], out["stderr"], out["exitCode"])
        if on_stdout and r.stdout: on_stdout(r.stdout)  # once, when it ends: no streaming yet
        if on_stderr and r.stderr: on_stderr(r.stderr)
        if out.get("timedOut"): raise TimeoutException(f"command timed out after {timeout}s")
        if r.exit_code != 0: raise CommandExitException(r)
        return r

    def _script(self, script, envs=None, timeout=30, slow=SandboxException):  # an SDK script, sent as the SDKs send it (no login shell)
        envs = {k: _map(v) for k, v in (envs or {}).items()}
        out = self._sbx._exec({"command": script, "cwd": HOME, "timeout": timeout, **({"env": envs} if envs else {})}, timeout)
        if out.get("timedOut"): raise slow(f"a command of the adapter's own did not finish within {timeout}s")
        return out["exitCode"], out["stdout"], out["stderr"]

    def _start(self, cmd, envs, cwd, on_stdout, on_stderr, unbuffered, limit=None):
        run = "run_" + uuid.uuid4().hex[:16]
        line = f"cd {shlex.quote(_path(_map(cwd or HOME)))} && bash -l -c {shlex.quote(_map(cmd))}"
        try: code, out, err = self._script(_start_script(run, line, limit, unbuffered), envs)
        except BaseException as e:  # its answer was lost: it may have started
            if not self._abandon(run) and isinstance(e, SandboxException) and e.args:
                e.args = (f"{e.args[0]}; the command may still be running as {run}", *e.args[1:])
            raise
        if code != 0 or not out.strip().isdigit():
            why = (err or out).strip()[:300]  # no pid within ten seconds, say: it may yet start, unless stopped here
            if self._abandon(run): raise SandboxException(f"the command did not start, or was stopped (exit {code}): {why}")
            raise SandboxException(f"could not confirm the command stopped: it may still be running as {run} ({why})")
        self._runs[int(out.strip())] = run
        return CommandHandle(self._sbx, int(out.strip()), run, on_stdout, on_stderr, limit)

    def _abandon(self, run):  # True once the run can no longer start, or was KILLed with its group
        try: return self._script(_abandon_script(run), timeout=12)[0] == 0
        except Exception: return False  # best effort: the start's own error is the one to raise

    def kill(self, pid, **_):
        """SIGKILL. A background command's pid (one started here, or whose run is in the sandbox): its whole process
        group while it runs, and False once it has ended, whatever holds that pid now. Any other pid: that one process,
        as on E2B."""
        pid = int(pid)
        if pid <= 1: return False  # -1, 0 and 1 would mean every process, or this shell's group
        runs = [self._runs[pid]] if pid in self._runs else [
            r for r in (p.split("/")[-2] for p in self._script(f"grep -lx -- {pid} {RUNS}/run_*/pid 2> /dev/null")[1].split())
            if re.fullmatch(r"run_[0-9a-f]{16}", r)]
        if runs: return any(self._script(_kill_script(r, "KILL"))[0] == 0 for r in runs)
        return self._script(f"kill -s KILL {pid} 2> /dev/null")[0] == 0

    def list(self, **_):
        rows = self._run("ps -u \"$(id -u)\" -o pid=,args=").stdout.splitlines()
        return [ProcessInfo(int(p), a.split(" ")[0], a.split(" ")[1:]) for p, a in (r.strip().split(" ", 1) for r in rows if r.strip())]

    def send_stdin(self, *a, **k): raise NotImplementedError("no stdin on Prized yet; write a file and read it")


class CommandHandle:
    """A background command: it runs in its own session, writing to ~/.prized/runs/<run id>/{stdout,stderr,exit}, as
    the Prized SDKs' runs do. pid is its process group's."""
    def __init__(self, sbx, pid, run, on_stdout=None, on_stderr=None, limit=None):
        self._sbx, self.pid, self._run, self._cb, self._limit, self._done = sbx, pid, run, (on_stdout, on_stderr), limit, False
        self._result = None

    def _status(self, tries=3):  # (running|done|gone|missing, exit code or None, stopped by its time limit)
        for i in range(tries):  # a read: a blip is read again, not the end of the command
            try:
                code, out, _ = self._sbx.commands._script(_poll_script(self._run))
                m = re.match(r"prized-run (running|done|gone|missing) (-|-?\d+) \d+ \d+ ([01]) ", out)
                if code != 0 or not m: raise SandboxException(f"could not read background command {self._run}: {out[:200]}")
                return m[1], None if m[2] == "-" else int(m[2]), m[3] == "1"
            except SandboxException as e:
                if i + 1 == tries:
                    if not isinstance(e, SandboxNotFoundException): e._polled = self._run  # it may still be running
                    raise
                time.sleep(1)

    def _clean(self, tries=1):  # best effort; a run KILLed a moment ago may take a few tries to be gone
        for i in range(tries):
            try:
                if self._sbx.commands._script(_cleanup_script(self._run))[0] != 5: return
            except Exception: return
            if i + 1 < tries: time.sleep(0.25)

    def _stop(self):  # best effort: KILL it and clean up, unless it has ended. Whether it is stopped (or had ended).
        if self._done: return True
        try: code = self._sbx.commands._script(_kill_script(self._run, "KILL"))[0]
        except Exception: return False  # unanswered: it may still run, and this handle can still kill it
        if code not in (0, 3, 4): return False  # the kill itself did not run (no memory for it, say): as unanswered
        self._done = True; self._clean(tries=20 if code == 0 else 1)
        return True

    def wait(self, on_stdout=None, on_stderr=None, poll_s=1.0, timeout=None):
        """The result once it ends (a second wait answers the same); a non-zero exit raises CommandExitException."""
        timeout = _timeout_s(timeout)  # a bad one is refused first, as in prized-e2b.ts
        if self._result is not None:
            if self._result.exit_code != 0: raise CommandExitException(self._result)
            return self._result
        end = time.time() + timeout if timeout else None
        while (st := self._status())[0] == "running":
            if end and time.time() > end:
                self._stop()  # best effort, as the cleanup: the timeout is the error to raise
                raise TimeoutException(f"command timed out after {timeout}s")
            time.sleep(poll_s)
        state, code, timed_out = st
        if state == "missing": raise SandboxException(f"background command {self._run} was cleaned up already")
        out, err = (self._read(f"{RUNS}/{self._run}/{name}") for name in ("stdout", "stderr"))
        r = CommandResult(out, err, -1 if code is None or timed_out else code)  # -1: ended without an exit code (killed), as on E2B
        self._done = True; self._clean()
        for cb, text in zip((on_stdout or self._cb[0], on_stderr or self._cb[1]), (r.stdout, r.stderr)):
            if cb and text: cb(text)
        if timed_out: raise TimeoutException(f"command timed out after {self._limit}s")
        self._result = r
        if r.exit_code != 0: raise CommandExitException(r)
        return r

    def _read(self, path):  # a run killed before its command began has no output files
        try: return self._sbx.files.read(path)
        except FileNotFoundException: return ""

    def kill(self):  # SIGKILL to its whole process group, as E2B's kill does; False once it has ended
        if self._done: return False
        return self._sbx.commands._script(_kill_script(self._run, "KILL"))[0] == 0


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
        """Creates missing directories and replaces the file whole, keeping the mode of a file it replaces (a script
        stays executable). Up to 100 MiB a file."""
        if isinstance(path, list): return self.write_files(path)  # e2b v1's list form
        data = data.read() if hasattr(data, "read") else data
        body, p = data.encode() if isinstance(data, str) else bytes(data), _path(path)
        home = self._home(p) and p != HOME  # staged beside it; elsewhere, a copy in the home folder
        tmp = f"{posixpath.dirname(p)}/.prized-write-{uuid.uuid4().hex}" if home else f"{HOME}/.e2b-tmp/{uuid.uuid4().hex}"
        t, d = shlex.quote(tmp), shlex.quote(p)
        # Outside the home folder the copy also makes the folder, and replaces a link as it always did.
        first = "" if home else f"mkdir -p {shlex.quote(posixpath.dirname(p))} || exit\nif [ -L {d} ]; then mv -fT -- {t} {d}; exit; fi\n"
        try:
            _req("POST", self._url("upload", tmp), data=body, key=self._sbx._key, timeout=660)
            code, out, err = self._sbx.commands._script(first + _publish_script(tmp, p), timeout=MAX_BLOCKING_EXEC, slow=TimeoutException)
        except BaseException:
            self._discard(t); raise
        if code == 47:  # a link: the files API follows it or refuses it, as for any upload
            _req("POST", self._url("upload", p), data=body, key=self._sbx._key, timeout=660)
        elif code == 48: raise InvalidArgumentException(f"{p} is a directory or another file that is not a regular file")
        elif code:
            self._discard(t)  # the script removes it as it exits; not a copy left by a failed mkdir or mv
            raise CommandExitException(CommandResult(out, err, code))
        return WriteInfo(posixpath.basename(p), FileType.FILE, p)

    def _discard(self, quoted):
        try: self._sbx.commands._script(f"rm -f -- {quoted}")
        except Exception: pass  # the write's own error is the one to raise

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
