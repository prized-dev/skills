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
  probeDelayMs: 500,
  // A longer command runs in the background and is polled, as a silent connection gets cut. Keep it under 270:
  // Node's fetch gives up on an answer after 300 s.
  maxBlockingExecS: 240,
};
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
  /** 0 = none. Over settings.maxBlockingExecS (4 minutes), or none, it runs in the background and is polled. */
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
  if (!key) throw new AuthenticationError("no API key: set PRIZED_API_KEY (dcp_...) or pass apiKey");
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
const result = (stdout: string, stderr: string, exitCode: number): CommandResult => ({ stdout, stderr, exitCode,
  ...(exitCode === 0 ? {} : { error: exitCode === -1 ? "signal: killed" : `exit status ${exitCode}` }) });

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
    this._edge = this._s.toolboxBase ?? "";
    for (let i = 0; ; i++) { // right after `running` the edge can answer 409/502 for a moment
      try { await this._exec({ command: "true", cwd: HOME }, 30); return this; }
      catch (e) { // no answer at all counts as a 502; a timeout does not
        const status = e instanceof ConnectionError ? 502 : (e as { statusCode?: number }).statusCode;
        if (e instanceof TimeoutError || ![409, 502, 503].includes(status!) || i === 9) throw e;
        await sleep(settings.probeDelayMs * (i + 1));
      }
    }
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
  constructor(sbx: Sandbox) { this.sbx = sbx; }

  /** timeoutMs defaults to 60 000 (0 = none). Over 4 minutes, or none, it runs in the background and is polled. */
  async run(cmd: string, opts: CommandStartOpts & { background: true }): Promise<CommandHandle>;
  async run(cmd: string, opts?: CommandStartOpts & { background?: false }): Promise<CommandResult>;
  async run(cmd: string, opts?: CommandStartOpts): Promise<CommandHandle | CommandResult>;
  async run(cmd: string, o: CommandStartOpts = {}): Promise<CommandHandle | CommandResult> {
    if (o.user === "root") throw new NotImplementedError("Prized sandboxes run as `prized`, without sudo; use a box for root");
    if (o.stdin) throw new NotImplementedError("no stdin on Prized yet; write a file and read it");
    if (o.background) return this._start(cmd, o.envs, o.cwd, o.onStdout, o.onStderr);
    const t = o.timeoutMs ?? 60_000;
    if (!t || t > settings.maxBlockingExecS * 1000)
      return (await this._start(cmd, o.envs, o.cwd)).wait({ onStdout: o.onStdout, onStderr: o.onStderr, timeoutMs: t || undefined });
    return this._run(cmd, { envs: o.envs, cwd: o.cwd, timeoutS: t / 1000, onStdout: o.onStdout, onStderr: o.onStderr });
  }

  /** @internal One exec, answered when it ends. */
  async _run(cmd: string, o: { envs?: Record<string, string>; cwd?: string; timeoutS?: number; onStdout?: Output; onStderr?: Output } = {}): Promise<CommandResult> {
    const timeout = o.timeoutS ?? 60, envs = mapValues(o.envs);
    const command = settings.loginShell ? `bash -lc ${q(mapHome(cmd))}` : mapHome(cmd);
    const out = await this.sbx._exec({ command, cwd: toPath(mapHome(o.cwd || HOME)), timeout, ...(some(envs) ? { env: envs } : {}) }, timeout);
    const r = result(out.stdout, out.stderr, out.exitCode);
    if (o.onStdout && r.stdout) await o.onStdout(r.stdout); // once, when it ends: no streaming yet
    if (o.onStderr && r.stderr) await o.onStderr(r.stderr);
    if (out.timedOut) throw new TimeoutError(`command timed out after ${timeout}s`);
    if (r.exitCode !== 0) throw new CommandExitError(r);
    return r;
  }

  /** @internal */
  async _start(cmd: string, envs?: Record<string, string>, cwd?: string, onStdout?: Output, onStderr?: Output): Promise<CommandHandle> {
    const d = `${HOME}/.e2b-run-${uid().slice(0, 12)}`;
    const inner = `echo $$ > ${d}/pid; { cd ${q(toPath(mapHome(cwd || HOME)))} && bash -l -c ${q(mapHome(cmd))}; }`
      + ` > ${d}/out 2> ${d}/err < /dev/null; echo $? > ${d}/exit`;
    const script = `mkdir -p ${d} && : > ${d}/out && : > ${d}/err && setsid -f bash -c ${q(inner)} > /dev/null 2>&1 < /dev/null; `
      + `for i in $(seq 100); do [ -s ${d}/pid ] && break; sleep 0.05; done; cat ${d}/pid`;
    const pid = Number.parseInt((await this._run(script, { envs, timeoutS: 30 })).stdout.trim(), 10);
    if (!Number.isInteger(pid)) throw new SandboxError(`the command did not start (no pid in ${d})`);
    return new CommandHandle(this.sbx, pid, d, onStdout, onStderr);
  }

  /** SIGKILL to its process group (a background handle's pid leads one), else the one process; false if not found.
   * E2B signals the one process; the group also takes what it started. */
  async kill(pid: number, _opts?: unknown): Promise<boolean> {
    const p = Number(pid);
    if (!Number.isInteger(p) || p <= 1) return false; // -1 and 0 would mean every process, or this shell's group
    return (await this._run(`{ kill -KILL -- -${p} || kill -KILL ${p}; } 2>/dev/null && echo 1 || true`)).stdout.trim() === "1";
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

/** A background command: it runs in its own session, writing to ~/.e2b-run-<id>/{out,err,exit} until it is waited
 * for. Callbacks get the whole output once, when wait() sees it end. Unlike on E2B, timeoutMs does not stop it. */
export class CommandHandle {
  readonly pid: number;
  private readonly sbx: Sandbox;
  private readonly dir: string;
  private cb: [Output?, Output?];
  private done = false;
  private waiting?: Promise<CommandResult>;
  private res?: CommandResult;

  /** @internal */
  constructor(sbx: Sandbox, pid: number, dir: string, onStdout?: Output, onStderr?: Output) {
    this.sbx = sbx; this.pid = pid; this.dir = dir; this.cb = [onStdout, onStderr];
  }
  get stdout(): string { return this.res?.stdout ?? ""; }
  get stderr(): string { return this.res?.stderr ?? ""; }
  get exitCode(): number | undefined { return this.res?.exitCode; }
  get error(): string | undefined { return this.res?.error; }

  /** The result once it ends; a non-zero exit throws CommandExitError, -1 ("signal: killed") after kill(). */
  wait(o: { onStdout?: Output; onStderr?: Output; pollMs?: number; timeoutMs?: number } = {}): Promise<CommandResult> {
    this.waiting ??= this.poll(o);
    return this.waiting;
  }

  private async poll(o: { onStdout?: Output; onStderr?: Output; pollMs?: number; timeoutMs?: number }): Promise<CommandResult> {
    const d = this.dir, run = (s: string) => this.sbx.commands._run(s), end = o.timeoutMs ? Date.now() + o.timeoutMs : undefined;
    const alive = `kill -0 ${this.pid} 2>/dev/null && ! ps -o stat= -p ${this.pid} | grep -q Z`;
    let code: string;
    while (!(code = (await run(`cat ${d}/exit 2>/dev/null || { ${alive}; } || cat ${d}/exit 2>/dev/null || echo -1`)).stdout.trim())) {
      if (end && Date.now() > end) {
        await this.kill().catch(() => false); // best effort, as the cleanup: the timeout is the error to throw
        this.done = true; await this.clean();
        throw new TimeoutError(`command timed out after ${o.timeoutMs! / 1000}s`);
      }
      await sleep(o.pollMs ?? 1000);
    }
    const [out, err] = [await this.sbx.files.read(`${d}/out`), await this.sbx.files.read(`${d}/err`)];
    const r = this.res = result(out, err, Number.parseInt(code, 10));
    this.done = true; await this.clean();
    const [onOut, onErr] = [o.onStdout ?? this.cb[0], o.onStderr ?? this.cb[1]];
    if (onOut && r.stdout) await onOut(r.stdout);
    if (onErr && r.stderr) await onErr(r.stderr);
    if (r.exitCode !== 0) throw new CommandExitError(r);
    return r;
  }

  /** Best effort: a failed cleanup never costs the result. */
  private async clean(): Promise<void> {
    await this.sbx.commands._run(`rm -rf ${this.dir}`).catch(() => {});
  }

  /** SIGKILL to its whole session (E2B signals the one process); false once it has ended. */
  async kill(): Promise<boolean> {
    if (this.done) return false;
    const d = this.dir;
    const out = await this.sbx.commands._run(`kill -KILL -- -${this.pid} 2>/dev/null && { [ -s ${d}/exit ] || echo -1 > ${d}/exit; echo 1; } || true`);
    return out.stdout.trim() === "1";
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
    const p = toPath(a), dst = isHome(p) ? p : `${HOME}/.e2b-tmp-${uid()}`;
    const body = data instanceof ReadableStream ? new Uint8Array(await new Response(data).arrayBuffer()) : data as RequestInit["body"];
    await _request("POST", this.url("upload", dst), { data: body, key: this.sbx._key, timeoutMs: 3_600_000 });
    if (dst !== p) {
      try { await this.sh(`mkdir -p ${q(dirname(p))} && mv -fT ${dst} ${q(p)}`); }
      catch (e) { await this.sh(`rm -f ${dst}`).catch(() => {}); throw e; } // the write's own error is the one to throw
    }
    return { name: basename(p), type: FileType.FILE, path: p };
  }

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
