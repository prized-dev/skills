/**
 * E2B-shaped client for Prized sandboxes, for Node 18+ (or any runtime with fetch). No dependencies: copy this file.
 *
 *   import { Sandbox } from "./prized-e2b";              // was: import { Sandbox } from "e2b"
 *   const sbx = await Sandbox.create({ timeoutMs: 600_000 }); // PRIZED_API_KEY in place of E2B_API_KEY
 *   console.log((await sbx.commands.run("node --version")).stdout);
 *   await sbx.kill();
 *
 * Calls keep E2B's names, options, results and errors. /home/user is /home/prized here: the adapter maps it in paths,
 * in command strings, cwd and env values (settings.mapHomeUser = false turns that off), and relative paths start in the
 * home folder, as on E2B. Commands run in a login shell (`bash -l`), as on E2B. Files outside the home folder (/tmp)
 * go through a copy. Most of what Prized does not have yet throws NotImplementedError naming the alternative.
 * Plain TypeScript only (no enums), so Node 22.18+ runs it as it is. Same behaviour as prized_e2b.py.
 * Guide: https://prized.dev/docs/moving-from-e2b  API: https://prized.dev/docs/sandboxes-api
 */

const HOME = "/home/prized";
/** Knobs. apiUrl defaults to PRIZED_API_URL, then https://api.prized.dev/api/v1. */
export const settings = {
  apiUrl: undefined as string | undefined,
  templates: { base: "prized-base-v1" } as Record<string, string>, // add your E2B template names here
  shape: { vcpu: 2, memoryMb: 1024 }, // E2B's base is 2 vCPU and 512 MiB; 1 GB is Prized's least
  mapHomeUser: true,
  loginShell: true,
  pollMs: 500,
  // A longer command runs in the background and is polled, as a silent connection gets cut. Keep it under 270:
  // Node's fetch gives up on an answer after 300 s.
  maxBlockingExecS: 240,
};
// Background commands and ones with onStdout/onStderr, as in the Prized SDKs: Python's output reaches its files as it
// prints (so a kill keeps it), unless envs or the sandbox set PYTHONUNBUFFERED ("" keeps Python's buffering).
const UNBUFFERED = 'export PYTHONUNBUFFERED="${PYTHONUNBUFFERED-1}"; ';
const RETRIED = new Set(["rate_limited", "sandbox_capacity", "sandbox_not_ready", "resolve_failed", "control_plane_unavailable",
  "sandbox_credentials_unavailable"]);

type Json = Record<string, unknown>;
interface Exec { stdout: string; stderr: string; exitCode: number; timedOut?: boolean }
type Ctor = new (message: string) => Error;

// E2B's error classes, with `statusCode`, and the API's error `code` and answer `body` when it sent one.
export class SandboxError extends Error { override name = "SandboxError"; statusCode?: number; code?: string; body?: Json; }
export class TimeoutError extends SandboxError { override name = "TimeoutError"; }
export class SandboxNotRunningError extends TimeoutError { override name = "SandboxNotRunningError"; }
export class SandboxUnreachableError extends TimeoutError { override name = "SandboxUnreachableError"; }
export class InvalidArgumentError extends SandboxError { override name = "InvalidArgumentError"; }
export class NotEnoughSpaceError extends SandboxError { override name = "NotEnoughSpaceError"; }
export class NotFoundError extends SandboxError { override name = "NotFoundError"; }
export class SandboxNotFoundError extends NotFoundError { override name = "SandboxNotFoundError"; }
export class FileNotFoundError extends NotFoundError { override name = "FileNotFoundError"; }
export class RateLimitError extends SandboxError { override name = "RateLimitError"; }
export class TemplateError extends SandboxError { override name = "TemplateError"; }
/** No answer: the request may or may not have landed. Prized only. */
export class ConnectionError extends SandboxError { override name = "ConnectionError"; }
// As on E2B, these two are not SandboxErrors.
export class AuthenticationError extends Error { override name = "AuthenticationError"; statusCode?: number; code?: string; body?: Json; }
export class ServiceBusyError extends Error { override name = "ServiceBusyError"; statusCode?: number; code?: string; body?: Json; }
export class NotImplementedError extends Error { override name = "NotImplementedError"; }

const BY_STATUS: Record<number, Ctor> = { 400: InvalidArgumentError, 401: AuthenticationError, 403: AuthenticationError,
  404: SandboxNotFoundError, 422: InvalidArgumentError, 429: RateLimitError, 503: ServiceBusyError };
const BY_CODE: Record<string, Ctor> = { template_not_found: TemplateError, path_outside_root: InvalidArgumentError,
  permission_denied: InvalidArgumentError, symlink_not_allowed: InvalidArgumentError };

export interface CommandResult { stdout: string; stderr: string; exitCode: number; error?: string }

/** A command that exited non-zero; `error` is "exit status N", or "signal: killed" (exitCode -1) as on E2B. */
export class CommandExitError extends SandboxError implements CommandResult {
  override name = "CommandExitError";
  stdout: string; stderr: string; exitCode: number; error?: string;
  constructor(r: CommandResult) {
    super(`${r.error}${r.stderr ? `: ${r.stderr.slice(-2000)}` : ""}`);
    this.stdout = r.stdout; this.stderr = r.stderr; this.exitCode = r.exitCode; this.error = r.error;
  }
}

export const FileType = { FILE: "file", DIR: "dir", SYMLINK: "symlink" } as const;
export type FileType = (typeof FileType)[keyof typeof FileType];
export interface WriteInfo { name: string; type?: FileType; path: string }
export type WriteEntry = { path: string; data: WriteData };
export type WriteData = string | ArrayBuffer | ArrayBufferView | Blob | ReadableStream;
export interface EntryInfo extends WriteInfo {
  size: number; mode: number; permissions: string; owner: string; group: string; modifiedTime?: Date; symlinkTarget?: string;
}
export interface ProcessInfo { pid: number; cmd: string; args: string[]; envs: Record<string, string>; tag?: string; cwd?: string }
export interface SandboxInfo {
  sandboxId: string; templateId: string; state: string; startedAt: Date; endAt?: Date;
  metadata: Record<string, string>; cpuCount: number; memoryMB: number;
}
type OnTimeout = "pause" | "kill" | { action: "pause" | "kill"; [k: string]: unknown };
/** requestTimeoutMs, signal and user are accepted and ignored. */
export interface ConnectionOpts { apiKey?: string; requestTimeoutMs?: number; signal?: AbortSignal; user?: string }
export interface SandboxOpts extends ConnectionOpts {
  template?: string;
  /** Becomes the run time (maxRuntimeMin, whole minutes up), 300 000 ms if 0 or unset; with lifecycle onTimeout "pause", the idle time before it pauses. */
  timeoutMs?: number;
  metadata?: Record<string, string>;
  envs?: Record<string, string>;
  lifecycle?: { onTimeout: OnTimeout; autoResume?: boolean };
  autoPause?: boolean;
  allowInternetAccess?: boolean;
  network?: unknown; mcp?: unknown; volumeMounts?: unknown; secure?: boolean;
  /** Prized only: the shape, and minutes paused before it is deleted. */
  vcpu?: number; memoryMb?: number; diskGb?: number; autoDeleteMin?: number;
}
export interface SandboxConnectOpts extends ConnectionOpts { timeoutMs?: number }
export interface SandboxForkOpts extends ConnectionOpts { count?: number; timeoutMs?: number; metadata?: Record<string, string> }
export interface SandboxListOpts extends ConnectionOpts {
  query?: { metadata?: Record<string, string>; state?: string[] }; limit?: number; nextToken?: string; order?: "asc" | "desc";
}
type Output = (data: string) => void | Promise<void>;
export interface CommandStartOpts extends ConnectionOpts {
  background?: boolean; cwd?: string; user?: string; envs?: Record<string, string>;
  onStdout?: Output; onStderr?: Output; stdin?: boolean;
  /** 0 or Infinity = none; a negative one is refused. Over settings.maxBlockingExecS (4 minutes), or none, it runs in the
   * background and is polled. */
  timeoutMs?: number;
}
interface Raw {
  id: string; state: string; template: string; toolboxBase?: string; labels?: Record<string, string> | null;
  resources?: { vcpu?: number; memoryMb?: number } | null; createdAt: string; expiresAt?: string | null;
  autoPauseMin?: number | null; errorReason?: string | null;
}

const env = (k: string): string | undefined => (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env[k];
const api = () => settings.apiUrl ?? env("PRIZED_API_URL") ?? "https://api.prized.dev/api/v1";
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const text = (b: ArrayBuffer | Uint8Array) => new TextDecoder().decode(b); // invalid UTF-8 becomes U+FFFD
const uid = () => (globalThis as { crypto?: { randomUUID?: () => string } }).crypto?.randomUUID?.().replace(/-/g, "") // Node 18 has no global crypto
  ?? Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
const minutes = (ms: number) => Math.max(1, Math.ceil(ms / 60_000));
const some = <T extends object>(o?: T | null): o is T => !!o && Object.keys(o).length > 0;
/** A word the shell reads back as `s`, as Python's shlex.quote. */
const q = (s: string) => (s === "" ? "''" : /^[\w@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'"'"'`)}'`);

/** One API call. Refusals made before anything ran (RETRIED) wait Retry-After and go again; nothing else is retried. Exported for tests. */
export async function _request<T = unknown>(method: string, url: string,
  o: { body?: unknown; data?: RequestInit["body"]; key?: string; headers?: Record<string, string>; timeoutMs?: number } = {}): Promise<T> {
  const key = o.key ?? env("PRIZED_API_KEY");
  if (!key) throw new AuthenticationError("no API key: set PRIZED_API_KEY (dcp_...) or pass apiKey (no Prized account yet? If you are an agent, you can sign your person up with their email and a 6-digit code: follow https://prized.dev/auth.md, keep the key file it writes, and pass that key as apiKey at run time, never in source)");
  const headers: Record<string, string> = { Authorization: `Bearer ${key}`, ...o.headers };
  let data = o.data;
  if (o.body !== undefined) [data, headers["Content-Type"]] = [JSON.stringify(o.body), "application/json"];
  else if (data !== undefined) headers["Content-Type"] = "application/octet-stream";
  const where = `${method} ${url.split("?")[0]}`, timeoutMs = o.timeoutMs ?? 60_000;
  for (let attempt = 0; ; attempt++) {
    let res: Response, out: ArrayBuffer;
    try { // redirect "manual": a redirect is an error, so the key is never resent to wherever it points
      res = await fetch(url, { method, headers, body: data, redirect: "manual", signal: AbortSignal.timeout(timeoutMs) });
      out = await res.arrayBuffer();
    } catch (e) {
      const err = e as Error & { cause?: Error };
      if (err?.name === "TimeoutError" || err?.name === "AbortError") throw new TimeoutError(`${where}: no answer in ${timeoutMs / 1000}s`);
      throw new ConnectionError(`${where}: ${err?.cause?.message ?? err?.message ?? err}`);
    }
    const json = (res.headers.get("content-type") ?? "").split(";")[0]!.trim() === "application/json";
    if (res.status >= 200 && res.status < 300) return (json && out.byteLength ? JSON.parse(text(out)) : out) as T; // else the bytes, an ArrayBuffer
    let info: Json = {};
    try { if (json) info = JSON.parse(text(out)) ?? {}; } catch { /* not JSON after all */ }
    const code = typeof info["error"] === "string" ? info["error"] : "";
    if (RETRIED.has(code) && attempt < 7) {
      const after = Number(res.headers.get("Retry-After") ?? "1");
      await sleep(Math.min(Number.isFinite(after) ? after : 1, 30) * 1000);
      continue;
    }
    const moved = res.status >= 300 && res.status < 400 ? `redirect to ${res.headers.get("location")} not followed` : "";
    const Cls = BY_CODE[code] ?? BY_STATUS[res.status] ?? SandboxError;
    const msg = [res.status, code, info["reason"], info["message"] ?? info["detail"], moved].filter((x) => x !== undefined && x !== "").join(" ");
    throw Object.assign(new Cls(`${where}: ${msg}`), { statusCode: res.status, code, body: info });
  }
}

function toPath(p: string): string {
  if (!p) throw new InvalidArgumentError("empty path");
  if (p === "/home/user" || p.startsWith("/home/user/")) p = HOME + p.slice("/home/user".length);
  const parts: string[] = [];
  for (const part of (p.startsWith("/") ? p : `${HOME}/${p}`).split("/")) {
    if (part === "..") parts.pop();
    else if (part && part !== ".") parts.push(part);
  }
  return "/" + parts.join("/");
}

/** /home/user in a command string or env value, not inside another path (/mnt/home/user). */
const mapHome = (s: string) => (settings.mapHomeUser ? s.replace(/(?<![\w./-])\/home\/user(?=\/|\b|$)/g, HOME) : s);
const mapValues = (o?: Record<string, string>) => Object.fromEntries(Object.entries(o ?? {}).map(([k, v]) => [k, mapHome(v)]));
const basename = (p: string) => p.slice(p.lastIndexOf("/") + 1);
const dirname = (p: string) => p.slice(0, p.lastIndexOf("/")) || "/";
const isHome = (p: string) => p === HOME || p.startsWith(HOME + "/");
/** The errors a background run's status read threw for good, by run: what became of the run is open. */
const polled = new WeakMap<object, string>();
/** A polled command whose status could not be read: say what became of it, as the SDKs do. */
function pollFailed(e: Error, run: string, stopped: boolean): void {
  e.message = `Polling the command failed (${e.message.trim().split(/\s+/).join(" ").replace(/[.\s]+$/, "")}). ` + (stopped
    ? `The adapter stopped ${run}, or it had already ended.`
    : `The adapter could not confirm it stopped: it may still be running as ${run} (commands.run('ps -ef | grep ${run}') finds it).`);
}
/** A command's timeout: 0 and Infinity are none (0); a negative or NaN one is refused, as the API refuses it. */
function timeoutMsOf(ms: number): number {
  if (ms === Infinity) return 0;
  if (typeof ms !== "number" || !(ms >= 0)) {
    throw new InvalidArgumentError(`timeoutMs must be a number of ms >= 0 (0 or Infinity: none), not ${String(ms)}`);
  }
  return ms;
}
const result = (stdout: string, stderr: string, exitCode: number): CommandResult => ({ stdout, stderr, exitCode,
  ...(exitCode === 0 ? {} : { error: exitCode === -1 ? "signal: killed" : `exit status ${exitCode}` }) });

// Background commands run as the Prized SDKs run them, so either can read, kill or clean up a run the other started:
// RUNS/<run id>/{pid,stdout,stderr,exit,...}, written by this wrapper in the run's own session. These scripts are the
// SDKs' own, rendered byte for byte as sdk/run-scripts/*.sh in Prized's repository (its tests check), where
// sdk/typescript/src/shell.ts says why each line is there. A run's pid is its wrapper's, which leads the run's process
// group: a status, a kill or a cleanup acts on it only while that process is alive and is still the run's wrapper (its
// arguments name the run), never on a pid or group id reused since. The scripts' own variables are __pz_ names, so envs
// reach the command as they were, whatever their names.
const RUNS = `${HOME}/.prized/runs`;
/** A shell test: process `pid` is a run's wrapper (or its watchdog): its 4th and 5th arguments are `expected`. */
const isRun = (pid: string, expected: string) =>
  `[ "$(tr "\\0\\n" "\\n " < "/proc/${pid}/cmdline" 2> /dev/null | sed -n 4,5p | tr "\\n" " ")" = ${expected} ]`;
const WRAPPER = [
  "unset __pz_k __pz_u __pz_w __pz_c __pz_end", "__pz_k=", 'trap "__pz_k=129" HUP', 'trap "__pz_k=130" INT',
  'trap "__pz_k=131" QUIT', 'trap "__pz_k=143" TERM', 'trap ":" USR1 USR2', '__pz_u="${PRIZED_RUN_PATH-$PATH}"',
  "unset PRIZED_RUN_PATH", 'echo "$$" > "$1/pid" || exit 1', 'date +%s%3N > "$1/start"', "__pz_w=",
  'if [ -n "$4" ]; then', '  ( trap "" HUP INT QUIT TERM USR1 USR2', "    __pz_end=$(($(date +%s) + $4 + 1))",
  '    while [ ! -e "$1/exit" ]; do', '      if [ "$(date +%s)" -ge "$__pz_end" ]; then',
  '        mkdir "$1/limit" 2> /dev/null || [ ! -d "$1/limit" ] || exit 0', '        true > "$1/timedout"',
  '        kill -s TERM -- "-$$"', "        sleep 5", '        kill -s KILL -- "-$$"', "        exit 0", "      fi", "      sleep 1",
  "    done ) > /dev/null 2>&1 < /dev/null &", "  __pz_w=$!", '  echo "$__pz_w" > "$1/watchdog"', "fi",
  'if [ -n "$__pz_k" ]; then __pz_c=$__pz_k; else', 'PATH="$__pz_u" "$2" -c "$3" > "$1/stdout" 2> "$1/stderr" < /dev/null',
  "__pz_c=$?", "fi",
  'if [ -n "$__pz_w" ] && { mkdir "$1/limit" 2> /dev/null || [ ! -d "$1/limit" ]; }; then '
    + `${isRun("$__pz_w", '"prized-run $1 "')} && kill -s KILL "$__pz_w" 2> /dev/null; wait "$__pz_w" 2> /dev/null; fi`,
  'date +%s%3N > "$1/end"', 'echo "$__pz_c" > "$1/exit.tmp" && mv -f "$1/exit.tmp" "$1/exit"',
].join("\n");
const ours = (run: string) => isRun("$__pz_p", q(`prized-run ${RUNS}/${run} `));

/** Starts `command` in its own session, stopped `limitS` seconds in, and prints its pid. */
function startScript(run: string, command: string, limitS: number | null = null, unbuffered = false): string {
  // At most about 31 years: past 2^63 the shell's arithmetic would wrap the limit negative.
  const limit = limitS === null ? "''" : Math.min(Math.max(1, Math.ceil(limitS)), 1e9);
  const go = `prized-run "$__pz_d" "$__pz_s" ${q(command)} ${limit} > /dev/null 2>&1 < /dev/null`;
  return [
    "unset __pz_r __pz_d __pz_s __pz_w __pz_n", 'export PRIZED_RUN_PATH="${PATH-}"',
    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    ...(unbuffered ? ['export PYTHONUNBUFFERED="${PYTHONUNBUFFERED-1}"'] : []), `__pz_r=${RUNS}; __pz_d="$__pz_r/${run}"`,
    "command -v setsid > /dev/null 2>&1 || { echo 'setsid is not installed in this sandbox' >&2; exit 97; }",
    'mkdir -p "$__pz_r" || exit 98', 'if mkdir "$__pz_d" 2> /dev/null; then',
    '  __pz_s=/bin/bash; [ -x "$__pz_s" ] || __pz_s=/bin/sh', `  __pz_w='${WRAPPER}'`,
    "  if setsid -f true > /dev/null 2>&1; then", `    setsid -f "$__pz_s" -c "$__pz_w" ${go}`, "  else",
    `    setsid "$__pz_s" -c "$__pz_w" ${go} &`, "  fi", "fi",
    `if [ -f "$__pz_d/cleaned" ]; then echo 'this run was already cleaned up' >&2; exit 96; fi`, "__pz_n=0",
    'while [ ! -s "$__pz_d/pid" ]; do', "  __pz_n=$((__pz_n + 1))",
    `  if [ "$__pz_n" -gt 200 ]; then echo 'the command did not start' >&2; exit 99; fi`, "  sleep 0.05", "done",
    'cat "$__pz_d/pid"',
  ].join("\n");
}

/** `prized-run <running|done|gone|missing> <exit|-> <out bytes> <err bytes> <timed out 0|1> <ms|->`, then up to `chunk`
 * bytes of each stream from its offset, in base64 (chunk 0: the status line alone). */
function pollScript(run: string, outAt = 0, errAt = 0, chunk = 0): string {
  const piece = (name: string, at: number, size: string) => [
    `__pz_n=$((${size} - ${at})); [ "$__pz_n" -gt ${chunk} ] && __pz_n=${chunk}`,
    `if [ "$__pz_n" -gt 0 ]; then tail -c +${at + 1} "$__pz_d/${name}" | head -c "$__pz_n" | base64 -w 0; fi`, "echo"];
  return [
    `__pz_d=${RUNS}/${run}`,
    'if [ ! -d "$__pz_d" ] || [ -f "$__pz_d/cleaned" ]; then echo "prized-run missing - 0 0 0 -"; exit 0; fi',
    'if [ -f "$__pz_d/exit" ]; then __pz_st=done; __pz_c=$(cat "$__pz_d/exit")',
    `elif __pz_p=$(cat "$__pz_d/pid" 2> /dev/null) && [ -n "$__pz_p" ] && kill -0 "$__pz_p" 2> /dev/null && ${ours(run)}; `
      + "then __pz_st=running; __pz_c=-",
    'elif [ -f "$__pz_d/exit" ]; then __pz_st=done; __pz_c=$(cat "$__pz_d/exit")', "else __pz_st=gone; __pz_c=-", "fi",
    '__pz_to=0; [ -e "$__pz_d/timedout" ] && __pz_to=1', "__pz_du=-", 'if [ -f "$__pz_d/end" ]; then',
    '  __pz_a=$(cat "$__pz_d/start" 2> /dev/null); __pz_b=$(cat "$__pz_d/end" 2> /dev/null)',
    '  case "$__pz_a:$__pz_b" in *[!0-9:]* | :* | *:) ;; *) __pz_du=$((__pz_b - __pz_a)) ;; esac', "fi",
    '__pz_o=$(stat -c %s "$__pz_d/stdout" 2> /dev/null || echo 0)', '__pz_e=$(stat -c %s "$__pz_d/stderr" 2> /dev/null || echo 0)',
    'echo "prized-run $__pz_st $__pz_c $__pz_o $__pz_e $__pz_to $__pz_du"', ...piece("stdout", outAt, "$__pz_o"),
    ...piece("stderr", errAt, "$__pz_e"),
  ].join("\n");
}

/** Exit 0: sent to the run's group; 3: no such run; 4: it has ended, nothing sent. */
function killScript(run: string, signal: string): string {
  const d = `${RUNS}/${run}`;
  return [`__pz_p=$(cat ${d}/pid 2> /dev/null) && [ -n "$__pz_p" ] || exit 3`,
    `[ ! -f ${d}/exit ] && kill -0 "$__pz_p" 2> /dev/null && ${ours(run)} || exit 4`,
    `kill -s ${signal} -- "-$__pz_p" 2> /dev/null || exit 4`].join("\n");
}

/** Exit 5 while it runs; else its files go, and the runs cleaned up over an hour ago. */
function cleanupScript(run: string): string {
  const d = `${RUNS}/${run}`;
  return [
    `if [ ! -f ${d}/exit ] && __pz_p=$(cat ${d}/pid 2> /dev/null) && [ -n "$__pz_p" ] && kill -0 "$__pz_p" 2> /dev/null && `
      + `${ours(run)}; then exit 5; fi`,
    `find ${RUNS} -mindepth 2 -maxdepth 2 -path '${RUNS}/run_*/cleaned' -mmin +60 -printf '%h\\0' 2> /dev/null | xargs -0 -r rm -rf --`,
    `find ${RUNS} -mindepth 1 -maxdepth 1 -type d -name 'run_*' -empty -mmin +60 -delete 2> /dev/null`,
    `[ -d ${d} ] || exit 0`, `find ${d} -mindepth 1 -maxdepth 1 ! -name cleaned -exec rm -rf -- {} +`, `: > ${d}/cleaned`,
  ].join("\n");
}

/** A start that may or may not have happened can no longer start, or is KILLed with its group. */
function abandonScript(run: string): string {
  return [
    `__pz_d=${RUNS}/${run}`, `mkdir -p ${RUNS} 2> /dev/null`,
    'if { mkdir "$__pz_d" 2> /dev/null && true > "$__pz_d/cleaned"; } || [ -f "$__pz_d/cleaned" ]; then exit 0; fi', "__pz_n=0",
    'while [ ! -s "$__pz_d/pid" ]; do', "  __pz_n=$((__pz_n + 1))", '  if [ "$__pz_n" -gt 200 ]; then exit 3; fi', "  sleep 0.05",
    "done", '__pz_p=$(cat "$__pz_d/pid")',
    `if kill -0 "$__pz_p" 2> /dev/null && ${ours(run)}; then kill -s KILL -- "-$__pz_p" 2> /dev/null; fi`,
    'find "$__pz_d" -mindepth 1 -maxdepth 1 ! -name cleaned -exec rm -rf -- {} +', ': > "$__pz_d/cleaned"', "exit 0",
  ].join("\n");
}

// A write, as the Prized SDKs write: uploaded under a fresh name, then put in place by one command that gives it the
// mode of the regular file it replaces (a script stays executable). Uploaded straight over a file, the bytes land 0600
// on some sandbox images. The SDKs' own script, rendered as sdk/file-scripts/publish.sh (the tests check). Exit 47:
// `dst` is a link; 48: a directory or another file that is not a regular file; either way nothing changed.
function publishScript(src: string, dst: string): string {
  return [
    `src=${q(src)}`, `dst=${q(dst)}`, `trap 'rm -f -- "$src"' EXIT`,
    `if s=$(stat -c '%f +%u:+%g' -- "$dst" 2> /dev/null); then`, "  t=$((0x${s%% *} & 0170000))",
    '  [ "$t" -eq $((0120000)) ] && exit 47', '  [ "$t" -eq $((0100000)) ] || exit 48',
    '  chown -- "${s#* }" "$src" 2> /dev/null || chgrp -- "${s##*:}" "$src" 2> /dev/null',
    '  chmod "$(printf %o $((0x${s%% *} & 0777)))" -- "$src" || exit', "fi",
    'mv -fT -- "$src" "$dst" || exit', 'sync -- "${dst%/*}" 2> /dev/null', "exit 0",
  ].join("\n");
}

/** @internal The SDKs' scripts, exported for tests (they must stay sdk/run-scripts/*.sh and sdk/file-scripts/*.sh). */
export const _runScripts = { WRAPPER, startScript, pollScript, killScript, cleanupScript, abandonScript, publishScript };

function info(s: Raw): SandboxInfo {
  return { sandboxId: s.id, templateId: s.template, state: s.state, startedAt: new Date(s.createdAt),
    endAt: s.expiresAt ? new Date(s.expiresAt) : undefined, metadata: s.labels ?? {},
    cpuCount: s.resources?.vcpu ?? 0, memoryMB: s.resources?.memoryMb ?? 0 };
}

export class Sandbox {
  readonly sandboxId: string;
  readonly commands: Commands;
  readonly files: Filesystem;
  /** @internal */ _s: Raw;
  /** @internal */ _edge: string;
  /** @internal */ readonly _key?: string;

  /** @internal Use Sandbox.create or Sandbox.connect. */
  constructor(sandbox: Raw, apiKey?: string) {
    this._s = sandbox; this._key = apiKey; this.sandboxId = sandbox.id; this._edge = sandbox.toolboxBase ?? "";
    this.commands = new Commands(this); this.files = new Filesystem(this);
  }

  /** create(opts) or create(template, opts). With lifecycle { onTimeout: "pause" } it pauses after `timeoutMs` idle
   * instead; any request resumes it, as autoResume does. Prized only: vcpu, memoryMb and diskGb set the shape;
   * autoDeleteMin deletes it after that many minutes paused. */
  static async create<S extends typeof Sandbox>(this: S, opts?: SandboxOpts): Promise<InstanceType<S>>;
  static async create<S extends typeof Sandbox>(this: S, template: string, opts?: SandboxOpts): Promise<InstanceType<S>>;
  static async create<S extends typeof Sandbox>(this: S, a?: string | SandboxOpts, b?: SandboxOpts): Promise<InstanceType<S>> {
    const o: SandboxOpts = typeof a === "string" ? { ...b, template: a } : { ...a };
    const template = o.template ?? "base";
    if (!Object.hasOwn(settings.templates, template) && !template.startsWith("prized-"))
      throw new TemplateError(`no template "${template}": Prized has prized-base-v1 and prized-agent-v1; set one up and fork it `
        + "(https://prized.dev/docs/sandboxes-own-template), or map it in settings.templates");
    if (o.mcp || o.network || o.allowInternetAccess === false || o.volumeMounts)
      throw new NotImplementedError("no MCP gateway, egress rules or volumes on Prized yet; every sandbox has outbound internet");
    const t = o.lifecycle?.onTimeout;
    const pause = o.autoPause || t === "pause" || (typeof t === "object" && t?.action === "pause");
    const body = { template: settings.templates[template] ?? template, ...(some(o.metadata) ? { labels: o.metadata } : {}),
      ...(some(o.envs) ? { envVars: mapValues(o.envs) } : {}), [pause ? "autoPauseMin" : "maxRuntimeMin"]: minutes(o.timeoutMs || 300_000),
      ...(o.autoDeleteMin ? { autoDeleteMin: Math.trunc(o.autoDeleteMin) } : {}),
      resources: { vcpu: o.vcpu || settings.shape.vcpu, memoryMb: o.memoryMb || settings.shape.memoryMb, ...(o.diskGb ? { diskGb: o.diskGb } : {}) } };
    const headers = { "Idempotency-Key": uid() }; // a retried create returns the same sandbox, never a second
    let out: { sandbox: Raw };
    try { out = await _request("POST", `${api()}/sandboxes?wait=running`, { body, key: o.apiKey, headers }); }
    catch (e) { // the answer was lost: the same key finds what committed
      if (!(e instanceof TimeoutError || e instanceof ConnectionError)) throw e;
      out = await _request("POST", `${api()}/sandboxes`, { body, key: o.apiKey, headers });
    }
    const sbx = new this(out.sandbox, o.apiKey) as InstanceType<S>;
    try { return await sbx._ready(); }
    catch (e) { await sbx.kill().catch(() => {}); throw e; }
  }

  /** Attach by id, resuming it if paused (memory and processes as they were). Like E2B, its time left only grows:
   * to at least `timeoutMs` (default 300 000) from now. */
  static async connect<S extends typeof Sandbox>(this: S, sandboxId: string, opts: SandboxConnectOpts = {}): Promise<InstanceType<S>> {
    const key = opts.apiKey;
    let s = (await _request<{ sandbox: Raw }>("GET", `${api()}/sandboxes/${sandboxId}`, { key })).sandbox;
    if (s.state === "paused" || s.state === "pausing")
      s = (await _request<{ sandbox: Raw }>("POST", `${api()}/sandboxes/${sandboxId}/resume?wait=running`, { key })).sandbox;
    const sbx = await (new this(s, key) as InstanceType<S>)._ready();
    try { await sbx._time(opts.timeoutMs || 300_000, true); }
    catch (e) { // past the run time allowed (the free tier's 60 minutes): it keeps what it has
      if (!(e instanceof RateLimitError && e.body?.["reason"] === "max_runtime")) throw e;
    }
    return sbx;
  }

  async connect(opts: SandboxConnectOpts = {}): Promise<this> {
    const s = await (this.constructor as typeof Sandbox).connect(this.sandboxId, { apiKey: this._key, ...opts });
    this._s = s._s; this._edge = s._edge;
    return this;
  }

  /** @internal */
  async _get(): Promise<Raw> {
    this._s = (await _request<{ sandbox: Raw }>("GET", `${api()}/sandboxes/${this.sandboxId}`, { key: this._key })).sandbox;
    return this._s;
  }

  /** @internal A sandbox made to pause on timeout counts idle time: this is activity, never a deletion time. */
  async _time(ms: number, onlyLonger = false): Promise<void> {
    const s = await this._get(), key = this._key;
    if (s.autoPauseMin) { await _request("POST", `${api()}/sandboxes/${this.sandboxId}/refresh`, { key }); return; }
    const end = s.expiresAt ? Date.parse(s.expiresAt) : undefined;
    if (s.state === "running" && !(onlyLonger && end !== undefined && end >= Date.now() + ms))
      await _request("POST", `${api()}/sandboxes/${this.sandboxId}/timeout`, { body: { inMin: minutes(ms) }, key });
  }

  /** @internal */
  async _ready(waitS = 180): Promise<this> {
    const end = Date.now() + waitS * 1000;
    while (this._s.state === "starting" || this._s.state === "pausing") {
      if (Date.now() > end) throw new TimeoutError(`${this.sandboxId} still ${this._s.state} after ${waitS}s`);
      await sleep(settings.pollMs); await this._get();
    }
    if (this._s.state !== "running") throw new SandboxError(`${this.sandboxId} is ${this._s.state}: ${this._s.errorReason}`);
    this._edge = this._s.toolboxBase ?? ""; // running takes commands at once
    return this;
  }

  /** @internal */
  _exec(body: Json, timeoutS: number): Promise<Exec> {
    return _request<Exec>("POST", `${this._edge}/process/execute`, { body, key: this._key, timeoutMs: (timeoutS + 30) * 1000 });
  }

  /** True once paused (memory and processes kept), false if it already was. betaPause is the old name. */
  async pause(_opts?: unknown): Promise<boolean> {
    if ((await this._get()).state === "paused") return false;
    let s = (await _request<{ sandbox: Raw }>("POST", `${api()}/sandboxes/${this.sandboxId}/pause?wait=paused`, { key: this._key })).sandbox;
    for (const end = Date.now() + 300_000; s.state === "pausing"; s = await this._get()) {
      if (Date.now() > end) throw new TimeoutError(`${this.sandboxId} still pausing after 300s`);
      await sleep(settings.pollMs);
    }
    return true;
  }
  betaPause(opts?: unknown): Promise<boolean> { return this.pause(opts); }
  static async pause(sandboxId: string, opts: ConnectionOpts = {}): Promise<boolean> {
    return new this({ id: sandboxId } as Raw, opts.apiKey).pause();
  }
  static betaPause(sandboxId: string, opts: ConnectionOpts = {}): Promise<boolean> { return this.pause(sandboxId, opts); }

  /** Live copies (memory, disk, processes), all on the parent's machine: up to 256 a call, or a 409 fork_capacity.
   * All or none: each entry is a Sandbox. Each gets the parent's run time unless `timeoutMs` (on the free tier,
   * copies end when the parent does). */
  static async fork<S extends typeof Sandbox>(this: S, sandboxId: string, opts: SandboxForkOpts = {}): Promise<InstanceType<S>[]> {
    const body = { count: opts.count || 1, ...(some(opts.metadata) ? { labels: opts.metadata } : {}),
      ...(opts.timeoutMs ? { maxRuntimeMin: minutes(opts.timeoutMs) } : {}) };
    const url = `${api()}/sandboxes/${sandboxId}/fork`, headers = { "Idempotency-Key": uid() }, key = opts.apiKey;
    let out: { sandboxes: Raw[] };
    try { out = await _request("POST", url, { body, key, headers }); }
    catch (e) { // the answer was lost: the same key finds the copies it made
      if (!(e instanceof TimeoutError || e instanceof ConnectionError)) throw e;
      out = await _request("POST", url, { body, key, headers });
    }
    const kids = out.sandboxes.map((s) => new this(s, key) as InstanceType<S>), failed: unknown[] = [];
    let next = 0;
    await Promise.all(Array.from({ length: Math.min(16, kids.length) }, async () => { // 16 at a time: the key's request limit
      while (next < kids.length && !failed.length) await kids[next++]!._ready().catch((e: unknown) => { failed.push(e); });
    }));
    if (failed.length) { // all or none, as the fork itself is
      await Promise.allSettled(kids.map((k) => k.kill()));
      throw failed[0];
    }
    return kids;
  }
  fork(opts: SandboxForkOpts = {}): Promise<this[]> {
    return (this.constructor as typeof Sandbox).fork(this.sandboxId, { apiKey: this._key, ...opts }) as Promise<this[]>;
  }

  /** True if it was there (one already deleting answers true until it is gone), false if not. */
  static async kill(sandboxId: string, opts: ConnectionOpts = {}): Promise<boolean> {
    try { await _request("DELETE", `${api()}/sandboxes/${sandboxId}`, { key: opts.apiKey }); return true; }
    catch (e) { if (e instanceof NotFoundError) return false; throw e; }
  }
  kill(opts: ConnectionOpts = {}): Promise<boolean> { return Sandbox.kill(this.sandboxId, { apiKey: this._key, ...opts }); }

  /** Deleted `timeoutMs` from now (earlier or later; on the free tier only earlier). On a pause-on-timeout sandbox it
   * counts as activity; a paused sandbox has no clock to set, and a resume starts its run time again. */
  static async setTimeout(sandboxId: string, timeoutMs: number, opts: ConnectionOpts = {}): Promise<void> {
    await new this({ id: sandboxId } as Raw, opts.apiKey)._time(timeoutMs);
  }
  setTimeout(timeoutMs: number, opts: ConnectionOpts = {}): Promise<void> {
    return Sandbox.setTimeout(this.sandboxId, timeoutMs, { apiKey: this._key, ...opts });
  }

  static async getInfo(sandboxId: string, opts: ConnectionOpts = {}): Promise<SandboxInfo> {
    return info((await _request<{ sandbox: Raw }>("GET", `${api()}/sandboxes/${sandboxId}`, { key: opts.apiKey })).sandbox);
  }
  getInfo(opts: ConnectionOpts = {}): Promise<SandboxInfo> { return Sandbox.getInfo(this.sandboxId, { apiKey: this._key, ...opts }); }

  async isRunning(_opts?: unknown): Promise<boolean> {
    try { return (await this._get()).state === "running"; }
    catch (e) { if (e instanceof NotFoundError) return false; throw e; }
  }

  /** E2B's paginator: one page holding every match, filtered here after one GET. */
  static list(opts: SandboxListOpts = {}): SandboxPaginator { return new SandboxPaginator(opts); }

  getHost(_port: number): string {
    throw new NotImplementedError("Prized sandboxes take no inbound connections yet; serve from a box: "
      + "`prized ports share PORT` (https://prized.dev/docs/ports)");
  }
}

/** Matches metadata (labels), and state (default: all but `deleting`, as a deleted sandbox lingers there a moment). */
export class SandboxPaginator {
  hasNext = true;
  nextToken?: string = undefined;
  private readonly opts: SandboxListOpts;
  constructor(opts: SandboxListOpts = {}) { this.opts = opts; }

  async nextItems(_opts?: unknown): Promise<SandboxInfo[]> {
    if (!this.hasNext) throw new Error("No more items to fetch");
    const { metadata = {}, state } = this.opts.query ?? {};
    const all = (await _request<{ sandboxes: Raw[] }>("GET", `${api()}/sandboxes`, { key: this.opts.apiKey })).sandboxes;
    this.hasNext = false;
    return all.filter((s) => Object.entries(metadata).every(([k, v]) => (s.labels ?? {})[k] === v)
      && (state?.length ? state.includes(s.state) : s.state !== "deleting")).map(info);
  }
}

export class Commands {
  private readonly sbx: Sandbox;
  private readonly runs = new Map<number, string>(); // pid -> run id, for each background command started here
  constructor(sbx: Sandbox) { this.sbx = sbx; }

  /** timeoutMs defaults to 60 000 (0 or Infinity = none). Over 4 minutes, or none, it runs in the background and is polled.
   * Background commands and ones with onStdout/onStderr get PYTHONUNBUFFERED=1 unless envs or the sandbox set it. */
  async run(cmd: string, opts: CommandStartOpts & { background: true }): Promise<CommandHandle>;
  async run(cmd: string, opts?: CommandStartOpts & { background?: false }): Promise<CommandResult>;
  async run(cmd: string, opts?: CommandStartOpts): Promise<CommandHandle | CommandResult>;
  async run(cmd: string, o: CommandStartOpts = {}): Promise<CommandHandle | CommandResult> {
    if (o.user === "root") throw new NotImplementedError("Prized sandboxes run as `prized`, without sudo; use a box for root");
    if (o.stdin) throw new NotImplementedError("no stdin on Prized yet; write a file and read it");
    if (o.background) return this._start(cmd, o.envs, o.cwd, o.onStdout, o.onStderr, true);
    const t = timeoutMsOf(o.timeoutMs ?? 60_000), streamed = Boolean(o.onStdout || o.onStderr);
    if (!t || t > settings.maxBlockingExecS * 1000) { // the sandbox stops it at timeoutMs too, if nobody is left polling
      const h = await this._start(cmd, o.envs, o.cwd, undefined, undefined, streamed, t ? t / 1000 : null);
      try { return await h.wait({ onStdout: o.onStdout, onStderr: o.onStderr, timeoutMs: t || undefined }); }
      catch (e) {
        if (e instanceof CommandExitError) throw e;
        const stopped = await h._stop(); // nobody else holds it: it does not run on unseen
        if (polled.get(e as object) === h._runId) pollFailed(e as Error, h._runId, stopped);
        throw e;
      }
    }
    return this._run(cmd, { envs: o.envs, cwd: o.cwd, timeoutS: t / 1000, onStdout: o.onStdout, onStderr: o.onStderr, unbuffered: streamed });
  }

  /** @internal One exec, answered when it ends. */
  async _run(cmd: string, o: { envs?: Record<string, string>; cwd?: string; timeoutS?: number; onStdout?: Output; onStderr?: Output; unbuffered?: boolean } = {}): Promise<CommandResult> {
    const timeout = o.timeoutS ?? 60, envs = mapValues(o.envs);
    const command = (o.unbuffered ? UNBUFFERED : "") + (settings.loginShell ? `bash -lc ${q(mapHome(cmd))}` : mapHome(cmd));
    const out = await this.sbx._exec({ command, cwd: toPath(mapHome(o.cwd || HOME)), timeout, ...(some(envs) ? { env: envs } : {}) }, timeout);
    const r = result(out.stdout, out.stderr, out.exitCode);
    if (o.onStdout && r.stdout) await o.onStdout(r.stdout); // once, when it ends: no streaming yet
    if (o.onStderr && r.stderr) await o.onStderr(r.stderr);
    if (out.timedOut) throw new TimeoutError(`command timed out after ${timeout}s`);
    if (r.exitCode !== 0) throw new CommandExitError(r);
    return r;
  }

  /** @internal An SDK script, sent as the SDKs send it (no login shell). */
  async _script(script: string, envs?: Record<string, string>, timeoutS = 30, slow: Ctor = SandboxError): Promise<Exec> {
    const env = mapValues(envs);
    const out = await this.sbx._exec({ command: script, cwd: HOME, timeout: timeoutS, ...(some(env) ? { env } : {}) }, timeoutS);
    if (out.timedOut) throw new slow(`a command of the adapter's own did not finish within ${timeoutS}s`);
    return out;
  }

  /** @internal */
  async _start(cmd: string, envs?: Record<string, string>, cwd?: string, onStdout?: Output, onStderr?: Output, unbuffered = false,
    limitS: number | null = null): Promise<CommandHandle> {
    const run = `run_${uid().slice(0, 16)}`;
    const line = `cd ${q(toPath(mapHome(cwd || HOME)))} && bash -l -c ${q(mapHome(cmd))}`;
    let out: Exec;
    try { out = await this._script(startScript(run, line, limitS, unbuffered), envs); }
    catch (e) { // its answer was lost: it may have started
      if (!(await this._abandon(run)) && e instanceof SandboxError) e.message += `; the command may still be running as ${run}`;
      throw e;
    }
    const pid = out.stdout.trim();
    if (out.exitCode !== 0 || !/^\d+$/.test(pid)) {
      const why = (out.stderr || out.stdout).trim().slice(0, 300); // no pid within ten seconds, say: it may yet start, unless stopped here
      if (await this._abandon(run)) throw new SandboxError(`the command did not start, or was stopped (exit ${out.exitCode}): ${why}`);
      throw new SandboxError(`could not confirm the command stopped: it may still be running as ${run} (${why})`);
    }
    this.runs.set(Number(pid), run);
    return new CommandHandle(this.sbx, Number(pid), run, onStdout, onStderr, limitS);
  }

  /** True once the run can no longer start, or was KILLed with its group. Best effort: the start's own error is the one to throw. */
  private async _abandon(run: string): Promise<boolean> {
    return this._script(abandonScript(run), undefined, 12).then((r) => r.exitCode === 0, () => false);
  }

  /** SIGKILL. A background command's pid (one started here, or whose run is in the sandbox): its whole process group
   * while it runs, and false once it has ended, whatever holds that pid now. Any other pid: that one process, as on
   * E2B; false if there is none. */
  async kill(pid: number, _opts?: unknown): Promise<boolean> {
    const p = Number(pid);
    if (!Number.isInteger(p) || p <= 1) return false; // -1 and 0 would mean every process, or this shell's group
    const mine = this.runs.get(p);
    const runs = mine ? [mine] : (await this._script(`grep -lx -- ${p} ${RUNS}/run_*/pid 2> /dev/null`)).stdout.split("\n")
      .map((f) => f.split("/").at(-2) ?? "").filter((r) => /^run_[0-9a-f]{16}$/.test(r));
    if (runs.length) {
      for (const r of runs) if ((await this._script(killScript(r, "KILL"))).exitCode === 0) return true;
      return false;
    }
    return (await this._script(`kill -s KILL ${p} 2> /dev/null`)).exitCode === 0;
  }

  async list(_opts?: unknown): Promise<ProcessInfo[]> {
    const rows = (await this._run('ps -u "$(id -u)" -o pid=,args=')).stdout.split("\n").map((r) => r.trim()).filter(Boolean);
    return rows.map((r) => {
      const [pid, ...args] = r.split(/\s+/);
      return { pid: Number(pid), cmd: args[0] ?? "", args: args.slice(1), envs: {} };
    });
  }

  async sendStdin(_pid: number, _data: string | Uint8Array, _opts?: unknown): Promise<void> {
    throw new NotImplementedError("no stdin on Prized yet; write a file and read it");
  }
}

/** A background command: it runs in its own session, writing to ~/.prized/runs/<run id>/{stdout,stderr,exit} until it
 * is waited for, as the Prized SDKs' runs do; pid is its process group's. Callbacks get the whole output once, when
 * wait() sees it end. Unlike on E2B, timeoutMs does not stop it. */
export class CommandHandle {
  readonly pid: number;
  private readonly sbx: Sandbox;
  private readonly run: string;
  private readonly limitS: number | null;
  private cb: [Output?, Output?];
  private done = false;
  private waiting?: Promise<CommandResult>;
  private res?: CommandResult;

  /** @internal */
  constructor(sbx: Sandbox, pid: number, run: string, onStdout?: Output, onStderr?: Output, limitS: number | null = null) {
    this.sbx = sbx; this.pid = pid; this.run = run; this.cb = [onStdout, onStderr]; this.limitS = limitS;
  }
  /** @internal */
  get _runId(): string { return this.run; }
  get stdout(): string { return this.res?.stdout ?? ""; }
  get stderr(): string { return this.res?.stderr ?? ""; }
  get exitCode(): number | undefined { return this.res?.exitCode; }
  get error(): string | undefined { return this.res?.error; }

  /** The result once it ends; a non-zero exit throws CommandExitError, -1 ("signal: killed") after kill(). */
  wait(o: { onStdout?: Output; onStderr?: Output; pollMs?: number; timeoutMs?: number } = {}): Promise<CommandResult> {
    let ms: number;
    try { ms = timeoutMsOf(o.timeoutMs ?? 0); } catch (e) { return Promise.reject(e); } // a bad argument leaves the handle as it was
    this.waiting ??= this.poll({ ...o, timeoutMs: ms || undefined });
    return this.waiting;
  }

  /** running, done, gone (ended without an exit code) or missing; its exit code; whether its time limit stopped it. */
  private async status(tries = 3): Promise<[string, number | undefined, boolean]> {
    for (let i = 0; ; i++) { // a read: a blip is read again, not the end of the command
      try {
        const out = await this.sbx.commands._script(pollScript(this.run));
        const m = /^prized-run (running|done|gone|missing) (-|-?\d+) \d+ \d+ ([01]) /.exec(out.stdout);
        if (out.exitCode !== 0 || !m) throw new SandboxError(`could not read background command ${this.run}: ${out.stdout.slice(0, 200)}`);
        return [m[1]!, m[2] === "-" ? undefined : Number(m[2]), m[3] === "1"];
      } catch (e) {
        if (!(e instanceof SandboxError || e instanceof ServiceBusyError) || i + 1 >= tries) { // a blip is read again
          const open = e instanceof SandboxError || e instanceof ServiceBusyError || e instanceof AuthenticationError;
          if (open && !(e instanceof SandboxNotFoundError)) polled.set(e, this.run); // it may still be running
          throw e;
        }
        await sleep(1000);
      }
    }
  }

  /** A run killed before its command began has no output files. */
  private async output(name: string): Promise<string> {
    try { return await this.sbx.files.read(`${RUNS}/${this.run}/${name}`); }
    catch (e) { if (e instanceof FileNotFoundError) return ""; throw e; }
  }

  private async poll(o: { onStdout?: Output; onStderr?: Output; pollMs?: number; timeoutMs?: number }): Promise<CommandResult> {
    const end = o.timeoutMs ? Date.now() + o.timeoutMs : undefined;
    let st: [string, number | undefined, boolean];
    while ((st = await this.status())[0] === "running") {
      if (end && Date.now() > end) {
        await this._stop(); // best effort, as the cleanup: the timeout is the error to throw
        throw new TimeoutError(`command timed out after ${o.timeoutMs! / 1000}s`);
      }
      await sleep(o.pollMs ?? 1000);
    }
    const [state, code, timedOut] = st;
    if (state === "missing") throw new SandboxError(`background command ${this.run} was cleaned up already`);
    const [out, err] = [await this.output("stdout"), await this.output("stderr")];
    const r = this.res = result(out, err, code === undefined || timedOut ? -1 : code); // -1: ended without an exit code (killed), as on E2B
    this.done = true; await this.clean();
    const [onOut, onErr] = [o.onStdout ?? this.cb[0], o.onStderr ?? this.cb[1]];
    if (onOut && r.stdout) await onOut(r.stdout);
    if (onErr && r.stderr) await onErr(r.stderr);
    if (timedOut) throw new TimeoutError(`command timed out after ${this.limitS}s`);
    if (r.exitCode !== 0) throw new CommandExitError(r);
    return r;
  }

  /** Best effort (a failed cleanup never costs the result); a run KILLed a moment ago may take a few tries to be gone. */
  private async clean(tries = 1): Promise<void> {
    for (let i = 0; i < tries; i++) {
      const code = await this.sbx.commands._script(cleanupScript(this.run)).then((r) => r.exitCode, () => 0);
      if (code !== 5) return;
      if (i + 1 < tries) await sleep(250);
    }
  }

  /** @internal Best effort: KILL it and clean up, unless it has ended. Whether it is stopped, or had ended (unanswered,
   * or a kill that did not run, it may still run, and this handle can still kill it). */
  async _stop(): Promise<boolean> {
    if (this.done) return true;
    let code: number;
    try { code = (await this.sbx.commands._script(killScript(this.run, "KILL"))).exitCode; } catch { return false; }
    if (![0, 3, 4].includes(code)) return false; // the kill itself did not run (no memory for it, say)
    this.done = true; await this.clean(code === 0 ? 20 : 1);
    return true;
  }

  /** SIGKILL to its whole process group (E2B signals the one process); false once it has ended. */
  async kill(): Promise<boolean> {
    if (this.done) return false;
    return (await this.sbx.commands._script(killScript(this.run, "KILL"))).exitCode === 0;
  }

  /** Stops the callbacks; the command keeps running. */
  async disconnect(): Promise<void> { this.cb = [undefined, undefined]; }

  async sendStdin(_data: string | Uint8Array, _opts?: unknown): Promise<void> {
    throw new NotImplementedError("no stdin on Prized yet; write a file and read it");
  }
}

// find's fields, each ended by a NUL (no name holds one): type, size, mode, permissions, owner, group, mtime, link
// target, and the path below the one asked for
const FIND = "-printf '%y\\0%s\\0%m\\0%M\\0%u\\0%g\\0%T@\\0%l\\0%P\\0'";

/** read/write go through the edge, which reaches the home folder only; elsewhere (/tmp) they go through a copy. */
export class Filesystem {
  private readonly sbx: Sandbox;
  constructor(sbx: Sandbox) { this.sbx = sbx; }

  private url(op: string, p: string) { return `${this.sbx._edge}/files/${op}?path=${encodeURIComponent(p)}`; }
  private sh(script: string) { return this.sbx.commands._run(script, { timeoutS: settings.maxBlockingExecS }); }

  async read(path: string, opts?: ConnectionOpts & { format?: "text" }): Promise<string>;
  async read(path: string, opts: ConnectionOpts & { format: "bytes" }): Promise<Uint8Array>;
  async read(path: string, opts: ConnectionOpts & { format: "blob" }): Promise<Blob>;
  async read(path: string, opts: ConnectionOpts & { format: "stream" }): Promise<ReadableStream<Uint8Array>>;
  async read(path: string, opts: ConnectionOpts & { format?: "text" | "bytes" | "blob" | "stream" } = {}): Promise<string | Uint8Array | Blob | ReadableStream<Uint8Array>> {
    const p = toPath(path), src = isHome(p) ? p : `${HOME}/.e2b-tmp-${uid()}`;
    let b: ArrayBuffer;
    try {
      if (src !== p) await this.sh(`cp -- ${q(p)} ${src}`);
      b = await _request<ArrayBuffer>("GET", this.url("download", src), { key: this.sbx._key, timeoutMs: 3_600_000 });
    } catch (e) {
      if (e instanceof NotFoundError || e instanceof CommandExitError) throw new FileNotFoundError(`${p}: ${(e as Error).message}`);
      throw e;
    } finally {
      if (src !== p) await this.sh(`rm -f ${src}`).catch(() => {});
    }
    const format = opts.format ?? "text";
    if (format === "text") return text(b);
    if (format === "bytes") return new Uint8Array(b);
    const blob = new Blob([new Uint8Array(b)]);
    return format === "blob" ? blob : blob.stream();
  }

  /** Creates missing directories and replaces the file whole. Up to 100 MiB a file. */
  async write(path: string, data: WriteData, opts?: ConnectionOpts): Promise<WriteInfo>;
  async write(files: WriteEntry[], opts?: ConnectionOpts): Promise<WriteInfo[]>;
  async write(a: string | WriteEntry[], data?: WriteData | ConnectionOpts): Promise<WriteInfo | WriteInfo[]> {
    if (Array.isArray(a)) return this.writeFiles(a);
    const p = toPath(a), home = isHome(p) && p !== HOME; // staged beside it; elsewhere, a copy in the home folder
    const tmp = home ? `${dirname(p)}/.prized-write-${uid()}` : `${HOME}/.e2b-tmp-${uid()}`;
    const body = data instanceof ReadableStream ? new Uint8Array(await new Response(data).arrayBuffer()) : data as RequestInit["body"];
    const send = (to: string) => _request("POST", this.url("upload", to), { data: body, key: this.sbx._key, timeoutMs: 3_600_000 });
    // Outside the home folder the copy also makes the folder, and replaces a link as it always did.
    const first = home ? "" : `mkdir -p ${q(dirname(p))} || exit\nif [ -L ${q(p)} ]; then mv -fT -- ${q(tmp)} ${q(p)}; exit; fi\n`;
    let out: Exec;
    try {
      await send(tmp);
      out = await this.sbx.commands._script(first + publishScript(tmp, p), undefined, settings.maxBlockingExecS, TimeoutError);
    } catch (e) { await this.discard(tmp); throw e; }
    if (out.exitCode === 47) await send(p); // a link: the files API follows it or refuses it, as for any upload
    else if (out.exitCode === 48) throw new InvalidArgumentError(`${p} is a directory or another file that is not a regular file`);
    else if (out.exitCode !== 0) {
      await this.discard(tmp); // the script removes it as it exits; not a copy left by a failed mkdir or mv
      throw new CommandExitError(result(out.stdout, out.stderr, out.exitCode));
    }
    return { name: basename(p), type: FileType.FILE, path: p };
  }

  /** Best effort: the write's own error is the one to throw. */
  private async discard(tmp: string): Promise<void> { await this.sbx.commands._script(`rm -f -- ${q(tmp)}`).catch(() => {}); }

  async writeFiles(files: WriteEntry[], _opts?: unknown): Promise<WriteInfo[]> {
    const out: WriteInfo[] = [];
    for (const f of files) out.push(await this.write(f.path, f.data));
    return out;
  }

  private async ok(script: string): Promise<boolean> { // true when the script exits 0
    try { await this.sh(script); return true; } catch (e) { if (e instanceof CommandExitError) return false; throw e; }
  }

  private async found(script: string, path: string): Promise<string> { // a missing path is FileNotFoundError, as on E2B
    try { return (await this.sh(script)).stdout; }
    catch (e) {
      if (e instanceof CommandExitError && e.stderr.includes("No such file")) throw new FileNotFoundError(`${toPath(path)}: no such file or directory`);
      throw e;
    }
  }

  private async entries(where: string, depth: string, path: string, follow = ""): Promise<EntryInfo[]> {
    const top = toPath(where), f = (await this.found(`find ${follow} ${q(top)} ${depth} ${FIND}`, path)).split("\0");
    const out: EntryInfo[] = [];
    for (let i = 0; i + 9 <= f.length; i += 9) {
      const [t, size, mode, permissions, owner, group, mtime, link, below] = f.slice(i, i + 9) as string[];
      const p = below ? `${top === "/" ? "" : top}/${below}` : top;
      out.push({ name: basename(p), type: t === "d" ? FileType.DIR : t === "l" ? FileType.SYMLINK : FileType.FILE, path: p,
        size: Number(size), mode: Number.parseInt(mode!, 8), permissions: permissions!, owner: owner!, group: group!,
        modifiedTime: new Date(Number(mtime) * 1000), ...(t === "l" ? { symlinkTarget: link } : {}) });
    }
    return out;
  }

  async list(path: string, opts: ConnectionOpts & { depth?: number } = {}): Promise<EntryInfo[]> {
    const depth = opts.depth ?? 1;
    if (!(depth >= 1)) throw new InvalidArgumentError("depth should be at least one");
    return this.entries(path, `-mindepth 1 -maxdepth ${Math.trunc(depth)}`, path, "-H"); // a symlinked folder lists what it points to
  }

  async getInfo(path: string, _opts?: unknown): Promise<EntryInfo> { return (await this.entries(path, "-maxdepth 0", path))[0]!; }
  exists(path: string, _opts?: unknown): Promise<boolean> { return this.ok(`test -e ${q(toPath(path))}`); }
  makeDir(path: string, _opts?: unknown): Promise<boolean> { return this.ok(`! test -d ${q(toPath(path))} && mkdir -p ${q(toPath(path))}`); }
  async remove(path: string, _opts?: unknown): Promise<void> { await this.sh(`rm -rf -- ${q(toPath(path))}`); }

  async rename(oldPath: string, newPath: string, _opts?: unknown): Promise<EntryInfo> {
    await this.found(`mv -T -- ${q(toPath(oldPath))} ${q(toPath(newPath))}`, oldPath);
    return this.getInfo(newPath);
  }

  async watchDir(..._args: unknown[]): Promise<never> { throw new NotImplementedError("no file watching on Prized yet; poll files.list()"); }
}

export default Sandbox;
