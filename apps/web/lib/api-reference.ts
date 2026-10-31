/* R59 API reference, rebuilt in R69 as a full per-endpoint reference.
   Everything here is derived at build time from openapi.json, the same document the web client's
   types come from. The API adds the written summaries, minimum roles (x-min-role), auth schemes,
   error responses and ping endpoints (cronsentinel/apidocs.py), so this file only reshapes: it
   flattens schemas into field tables, builds example payloads and writes code samples. */
import "server-only";
import fs from "node:fs";
import path from "node:path";

export const APP_BASE = "https://app.example.com";
export const INGEST_BASE = "https://ingest.example.com";
const METHODS = ["get", "post", "put", "patch", "delete"] as const;

export type Field = { name: string; type: string; required: boolean; description: string; enumValues?: string[]; default?: string;
  constraints: string[]; nullable: boolean; children?: Field[] };
export type Response = { status: string; description: string; fields?: Field[]; example?: string; headers?: string[] };
export type Op = {
  id: string; method: string; path: string; summary: string; description: string; tag: string; group: string;
  role: string | null; auth: "key" | "none" | "ping-token"; base: string;
  pathParams: Field[]; queryParams: Field[]; body: { fields: Field[]; example: string; isArray: boolean } | null;
  responses: Response[]; samples: { curl: string; python: string; go: string };
};
export type Group = { tag: string; slug: string; name: string; description: string; ops: Op[] };

type Spec = { paths: Record<string, Record<string, any>>; components: { schemas: Record<string, any> }; tags: { name: string; "x-displayName": string; description: string }[] };

let cached: { spec: Spec; groups: Group[] } | null = null;

function spec(): Spec {
  return JSON.parse(fs.readFileSync(path.join(process.cwd(), "openapi.json"), "utf8"));
}

/* ---------- schemas ---------- */

function deref(s: any, sp: Spec): any {
  let cur = s;
  for (let i = 0; i < 10 && cur?.$ref; i++) cur = sp.components.schemas[cur.$ref.split("/").pop()];
  return cur ?? {};
}

/** Unwrap Optional[...] (anyOf with null) and single-member allOf. */
function unwrap(s: any, sp: Spec): { s: any; nullable: boolean } {
  s = deref(s, sp);
  let nullable = false;
  for (let i = 0; i < 5; i++) {
    const alts = s.anyOf ?? s.oneOf;
    if (alts) {
      const non = alts.filter((a: any) => a.type !== "null");
      if (non.length < alts.length) nullable = true;
      if (non.length === 1) { s = { ...deref(non[0], sp), description: s.description ?? deref(non[0], sp).description, default: s.default ?? deref(non[0], sp).default, title: s.title }; continue; }
      return { s, nullable };
    }
    if (s.allOf?.length === 1) { s = { ...deref(s.allOf[0], sp), description: s.description }; continue; }
    break;
  }
  return { s, nullable };
}

function typeLabel(s: any, sp: Spec): string {
  const u = unwrap(s, sp).s;
  const alts = u.anyOf ?? u.oneOf;
  if (alts) return alts.filter((a: any) => a.type !== "null").map((a: any) => typeLabel(a, sp)).join(" | ");
  if (u.type === "array") return `array of ${typeLabel(u.items ?? {}, sp)}`;
  if (u.enum) return "enum";
  if (u.const !== undefined) return "string";
  if (u.type === "object" || u.properties) return u.title && s.$ref ? "object" : "object";
  if (u.format && u.type === "string") return u.format === "date-time" ? "timestamp" : u.format;
  return u.type ?? "any";
}

const patternEnum = (s: any): string[] | undefined => {
  const m = typeof s.pattern === "string" ? /^\^\(([\w|-]+)\)\$$/.exec(s.pattern) : null;
  return m ? m[1].split("|") : undefined;
};

function constraints(s: any): string[] {
  const c: string[] = [];
  if (s.minimum !== undefined) c.push(`≥ ${s.minimum}`);
  if (s.exclusiveMinimum !== undefined) c.push(`> ${s.exclusiveMinimum}`);
  if (s.maximum !== undefined) c.push(`≤ ${s.maximum}`);
  if (s.minLength !== undefined && s.minLength > 0) c.push(`min length ${s.minLength}`);
  if (s.maxLength !== undefined) c.push(`max length ${s.maxLength}`);
  if (s.minItems !== undefined && s.minItems > 0) c.push(`min ${s.minItems} items`);
  if (s.maxItems !== undefined) c.push(`max ${s.maxItems} items`);
  if (s.pattern && !/^\^\(([\w|-]+)\)\$$/.test(s.pattern)) c.push(`pattern ${s.pattern}`);
  return c;
}

function fields(schema: any, sp: Spec, depth = 0): Field[] {
  const s = unwrap(schema, sp).s;
  const obj = s.type === "array" ? unwrap(s.items ?? {}, sp).s : s;
  if (!obj.properties) return [];
  const req = new Set<string>(obj.required ?? []);
  return Object.entries<any>(obj.properties).map(([name, raw]) => {
    const { s: p, nullable } = unwrap(raw, sp);
    const inner = p.type === "array" ? unwrap(p.items ?? {}, sp).s : p;
    const f: Field = {
      name, type: typeLabel(raw, sp), required: req.has(name), description: (raw.description ?? p.description ?? "").trim(),
      constraints: constraints(p), nullable,
    };
    const en = p.enum ?? inner.enum ?? patternEnum(p);
    if (en) f.enumValues = en.map(String);
    const d = raw.default ?? p.default;
    if (d !== undefined && d !== null && !(Array.isArray(d) && d.length === 0) && !(typeof d === "object" && !Array.isArray(d) && Object.keys(d).length === 0)) f.default = JSON.stringify(d);
    if (depth < 2 && inner.properties) f.children = fields(inner, sp, depth + 1);
    return f;
  });
}

/* ---------- examples ---------- */

const UUIDS = ["3f2a8c1e-6b7d-4e0a-9c51-2d8e4f1a7b90", "b71c0e94-2a3f-4d58-8e16-5f9a0c3d2e71", "0d9e5a72-8c41-4b3e-a6f0-7e2b1c9d4a58"];
let uuidN = 0;

function nameExample(name: string, s: any): unknown {
  const n = name.toLowerCase();
  if (n === "id" || n.endsWith("_id")) return UUIDS[uuidN++ % UUIDS.length];
  if (n.endsWith("ids")) return [UUIDS[0]];
  if (n === "email" || n.endsWith("_email")) return "ana@example.com";
  if (n === "name" || n === "job_name") return "nightly-database-backup";
  if (n === "slug") return "payments";
  if (n === "schedule" || n === "cron" || n === "expression" || n === "schedule_expr" || n === "expr") return "0 2 * * *";
  if (n === "sla_target") return 99.5;
  if (n === "metrics") return { rows: 1200, size_bytes: 4200000000 };
  if (n === "timezone" || n === "tz") return "Europe/London";
  if (n === "role") return "developer";
  if (n === "host" || n === "hostname") return "db-01";
  if (n === "invite_url") return "https://app.example.com/signup?invite=Xk3…";
  if (n.includes("url")) return n.includes("ping") ? `${INGEST_BASE}/ping/k7Qw2nXc9rTb` : "https://hooks.example.com/jobwatch";
  if (n.endsWith("_at") || n === "since" || n === "until" || n === "at" || n === "starts" || n === "ends") return "2026-10-01T02:00:07Z";
  if (n === "message" || n === "body" || n === "note" || n === "text") return "Restarted the replica; backup re-run succeeded.";
  if (n === "question") return "Why did nightly-database-backup fail last night?";
  if (n === "tags") return ["backup", "production"];
  if (n === "domain") return "example.com";
  if (n.includes("token") && !n.includes("hint") || n === "key" || n.endsWith("_key")) return "jw_live_7Hc2…";
  if (n === "duration_ms" || n === "grace_ms") return 92000;
  if (n === "schedule_human") return "At 02:00 every day";
  if (n === "heartbeat_token_hint") return "…9rTb";
  if (n === "reliability_score") return 98.4;
  if (n === "last_status") return "success";
  if (n === "success_rate") return 99.2;
  if (n.includes("seconds") || n.endsWith("_s")) return 300;
  if (n === "exit_code") return 0;
  if (n === "output") return "dumped 4.2 GB in 92 s\n";
  if (n === "description") return "Postgres dump to S3";
  if (n === "workspace" || n === "organization" || n === "org_name") return "Acme";
  return undefined;
}

function example(schema: any, sp: Spec, name = "", depth = 0): unknown {
  const raw = schema ?? {};
  if (raw.example !== undefined) return raw.example;
  if (raw.examples?.length) return raw.examples[0];
  const { s, nullable } = unwrap(raw, sp);
  if (s.example !== undefined) return s.example;
  if (s.examples?.length) return s.examples[0];
  if (s.default !== undefined && s.default !== null && !(Array.isArray(s.default) && !s.default.length)) return s.default;
  if (s.enum) return s.enum[0];
  if (patternEnum(s)) return patternEnum(s)![0];
  if (s.const !== undefined) return s.const;
  if (depth > 4) return s.type === "array" ? [] : s.type === "object" ? {} : null;
  let byName = name ? nameExample(name, s) : undefined;
  if (byName === undefined && s.type === "string" && !s.format) {
    const m = /`([a-z][a-z0-9_-]*)`/.exec(raw.description ?? s.description ?? "");
    if (m && /(one of|:|`, `|`\s+or\s+`)/.test(raw.description ?? s.description ?? "")) byName = m[1];
  }
  const alts = s.anyOf ?? s.oneOf;
  if (alts) return example(alts.find((a: any) => a.type !== "null") ?? alts[0], sp, name, depth + 1);
  if (s.type === "array") {
    if (Array.isArray(byName)) return byName;
    return [example(s.items ?? {}, sp, name.replace(/s$/, ""), depth + 1)];
  }
  if (s.type === "object" || s.properties) {
    if (!s.properties) return {};
    const o: Record<string, unknown> = {};
    for (const [k, v] of Object.entries<any>(s.properties)) {
      const val = example(v, sp, k, depth + 1);
      if (val !== undefined) o[k] = val;
    }
    return o;
  }
  if (byName !== undefined && !(typeof byName === "string" && s.type && s.type !== "string")) return byName;
  if (nullable && depth > 0 && !name) return null;
  switch (s.type) {
    case "string":
      if (s.format === "uuid") return UUIDS[uuidN++ % UUIDS.length];
      if (s.format === "date-time") return "2026-10-01T02:00:07Z";
      if (s.format === "date") return "2026-10-01";
      if (s.format === "email") return "ana@example.com";
      if (s.format === "uri") return "https://hooks.example.com/jobwatch";
      return name ? name.replace(/_/g, "-") : "string";
    case "integer": return s.minimum ?? (s.maximum !== undefined ? Math.min(s.maximum, 10) : 10);
    case "number": return 1.5;
    case "boolean": return true;
    default: return null;
  }
}

/** Request examples show what a caller would really send: required fields plus optional ones with a
 *  meaningful example, not every optional field filled with a placeholder. */
function requestExample(schema: any, sp: Spec): unknown {
  const full = example(schema, sp);
  const s = unwrap(schema, sp).s;
  if (!s.properties || typeof full !== "object" || full === null || Array.isArray(full)) return full;
  const req = new Set<string>(s.required ?? []);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(full as Record<string, unknown>)) {
    const ps = unwrap(s.properties[k], sp).s;
    const placeholder = v === null || v === 1.5 || v === k.replace(/_/g, "-") || v === "string" || (Array.isArray(v) && (v.length === 0 || v[0] === k.replace(/s$/, "").replace(/_/g, "-")))
      || (typeof v === "object" && v !== null && !Array.isArray(v) && Object.keys(v).length === 0);
    const isDefault = ps.default !== undefined && JSON.stringify(ps.default) === JSON.stringify(v);
    const optionalRef = !req.has(k) && ps.format === "uuid";
    if (req.has(k) || (!placeholder && !isDefault && !optionalRef)) out[k] = v;
  }
  return out;
}

/* ---------- code samples ---------- */

function pyLiteral(v: unknown, ind = 0): string {
  const pad = "    ".repeat(ind + 1), end = "    ".repeat(ind);
  if (v === null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (Array.isArray(v)) return v.length ? `[${v.map((x) => pyLiteral(x, ind)).join(", ")}]` : "[]";
  if (typeof v === "object") {
    const e = Object.entries(v as object);
    return e.length ? `{\n${e.map(([k, x]) => `${pad}${JSON.stringify(k)}: ${pyLiteral(x, ind + 1)}`).join(",\n")},\n${end}}` : "{}";
  }
  return JSON.stringify(v);
}

function samples(op: Omit<Op, "samples">, bodyEx: unknown, queryEx: Record<string, unknown>): Op["samples"] {
  const url = op.base + op.path.replace(/\{(\w+)\}/g, (_, p) => (p === "token" ? "<token>" : p === "status" ? "success" : `<${p}>`));
  const qs = Object.keys(queryEx).length ? "?" + new URLSearchParams(Object.entries(queryEx).map(([k, v]) => [k, String(v)])).toString() : "";
  const M = op.method.toUpperCase();
  const json = bodyEx === undefined ? null : JSON.stringify(bodyEx, null, 2);
  const key = op.auth === "key";

  const curl = [`curl ${M === "GET" ? "" : `-X ${M} `}"${url}${qs}"`];
  if (key) curl.push(`  -H "X-API-Key: $JOBWATCH_API_KEY"`);
  if (json) curl.push(`  -H "Content-Type: application/json"`, `  -d '${json.replace(/'/g, "'\\''")}'`);
  if (op.auth === "ping-token" && M === "GET") curl[0] = `curl -fsS -m 10 --retry 5 "${url}${qs}"`;

  const py = ["import os", "import requests", ""];
  const args = [`    "${url}"`];
  if (key) args.push(`    headers={"X-API-Key": os.environ["JOBWATCH_API_KEY"]}`);
  if (Object.keys(queryEx).length) args.push(`    params=${pyLiteral(queryEx, 1)}`);
  if (json) args.push(`    json=${pyLiteral(bodyEx, 1)}`);
  args.push("    timeout=10");
  py.push(`resp = requests.${op.method.toLowerCase()}(\n${args.join(",\n")},\n)`, "resp.raise_for_status()");
  const has204 = op.responses.some((r) => r.status === "204");
  if (!has204) py.push("print(resp.json())");
  if (!key) py.splice(0, 1);

  const go = ["package main", "", "import (", ...(json ? ['\t"bytes"'] : []), '\t"fmt"', '\t"io"', '\t"net/http"', ...(key ? ['\t"os"'] : []), '\t"time"', ")", "", "func main() {"];
  if (json) go.push(`\tbody := []byte(\`${json}\`)`);
  go.push(`\treq, err := http.NewRequest("${M}", "${url}${qs}", ${json ? "bytes.NewReader(body)" : "nil"})`, "\tif err != nil {", "\t\tpanic(err)", "\t}");
  if (key) go.push('\treq.Header.Set("X-API-Key", os.Getenv("JOBWATCH_API_KEY"))');
  if (json) go.push('\treq.Header.Set("Content-Type", "application/json")');
  go.push("\tclient := &http.Client{Timeout: 10 * time.Second}", "\tresp, err := client.Do(req)", "\tif err != nil {", "\t\tpanic(err)", "\t}",
    "\tdefer resp.Body.Close()", "\tout, _ := io.ReadAll(resp.Body)", '\tfmt.Println(resp.Status, string(out))', "}");
  return { curl: curl.join(" \\\n"), python: py.join("\n"), go: go.join("\n") };
}

/* ---------- operations ---------- */

export const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function buildOp(p: string, method: string, o: any, sp: Spec, groupSlug: string): Op {
  uuidN = 0;
  const params = (o.parameters ?? []) as any[];
  const toField = (x: any): Field => {
    const { s, nullable } = unwrap(x.schema ?? {}, sp);
    return { name: x.name, type: typeLabel(x.schema ?? {}, sp), required: !!x.required, description: (x.description ?? s.description ?? "").trim(),
      enumValues: (s.enum ?? patternEnum(s))?.map(String), default: s.default !== undefined && s.default !== null ? JSON.stringify(s.default) : undefined, constraints: constraints(s), nullable };
  };
  const bodySchema = o.requestBody?.content?.["application/json"]?.schema;
  const bodyEx = bodySchema ? requestExample(bodySchema, sp) : undefined;
  const body = bodySchema ? { fields: fields(bodySchema, sp), example: JSON.stringify(bodyEx, null, 2), isArray: unwrap(bodySchema, sp).s.type === "array" } : null;

  const responses: Response[] = Object.entries<any>(o.responses ?? {}).sort(([a], [b]) => a.localeCompare(b)).map(([status, r]) => {
    const media = r.content?.["application/json"] ?? {};
    const sch = media.schema && Object.keys(media.schema).length ? media.schema : null;
    const ok = status.startsWith("2");
    let description = r.description === "Successful Response" ? (status === "201" ? "Created." : status === "204" ? "No content." : "Success.") : r.description;
    if (status === "422") description = "The request body or a parameter failed validation. `detail` lists each field error.";
    const res: Response = { status, description };
    if (r.headers) res.headers = Object.keys(r.headers);
    if (ok && media.example !== undefined) {
      if (sch) { const f = fields(sch, sp); if (f.length) res.fields = f; }
      res.example = JSON.stringify(media.example, null, 2);
    } else if (sch && ok) {
      const f = fields(sch, sp);
      if (f.length) res.fields = f;
      const ex = example(sch, sp);
      if (ex !== null && ex !== undefined && !(typeof ex === "object" && !Array.isArray(ex) && !Object.keys(ex).length)) res.example = JSON.stringify(ex, null, 2);
    } else if (!ok) {
      const msg: Record<string, string> = { "401": "authentication required", "403": `requires role >= ${o["x-min-role"] ?? "viewer"}`, "404": "not found", "429": "rate limit exceeded", "409": "conflict" };
      res.example = status === "422"
        ? JSON.stringify({ detail: [{ type: "missing", loc: ["body", body?.fields.find((f) => f.required)?.name ?? "name"], msg: "Field required" }] }, null, 2)
        : JSON.stringify({ detail: msg[status] ?? "error" }, null, 2);
    }
    return res;
  });

  const queryParams = params.filter((x) => x.in === "query").map(toField);
  const queryEx: Record<string, unknown> = {};
  for (const q of queryParams) if (q.required) queryEx[q.name] = q.enumValues?.[0] ?? (q.type === "integer" ? 7 : q.type === "uuid" ? UUIDS[0] : nameExample(q.name, {}) ?? "value");

  const auth: Op["auth"] = o["x-auth"] === "ping-token" ? "ping-token" : o["x-min-role"] ? "key" : "none";
  const summary = o.summary ?? `${method.toUpperCase()} ${p}`;
  const partial = {
    id: slugify(summary), method: method.toUpperCase(), path: p, summary, description: o.description ?? "", tag: o.tags?.[0] ?? "other", group: groupSlug,
    role: o["x-min-role"] ?? null, auth, base: o.servers?.[0]?.url ?? APP_BASE,
    pathParams: params.filter((x) => x.in === "path").map(toField), queryParams, body, responses,
  };
  return { ...partial, samples: samples(partial, bodyEx, queryEx) };
}

export function apiReference(): Group[] {
  if (cached) return cached.groups;
  const sp = spec();
  const tags = sp.tags ?? [];
  const byTag = new Map<string, Op[]>();
  for (const [p, ops] of Object.entries(sp.paths)) {
    for (const m of METHODS) {
      const o = ops[m];
      if (!o || o["x-internal"]) continue;
      const tag = o.tags?.[0] ?? "other";
      const list = byTag.get(tag) ?? [];
      list.push(buildOp(p, m, o, sp, slugify(tag)));
      byTag.set(tag, list);
    }
  }
  const order = (op: Op) => ["GET", "POST", "PUT", "PATCH", "DELETE"].indexOf(op.method);
  const groups: Group[] = tags.filter((t) => byTag.has(t.name)).map((t) => {
    const ops = byTag.get(t.name)!.sort((a, b) => {
      const ra = a.path.replace(/\/\{[^}]+\}.*/, ""), rb = b.path.replace(/\/\{[^}]+\}.*/, "");
      return ra.localeCompare(rb) || a.path.split("/").length - b.path.split("/").length || order(a) - order(b) || a.path.localeCompare(b.path);
    });
    const seen = new Map<string, number>();
    for (const op of ops) { const n = seen.get(op.id) ?? 0; seen.set(op.id, n + 1); if (n) op.id = `${op.id}-${n + 1}`; }
    return { tag: t.name, slug: slugify(t.name), name: t["x-displayName"] ?? t.name, description: t.description ?? "", ops };
  });
  cached = { spec: sp, groups };
  return groups;
}

export function apiGroup(slug: string): Group | undefined {
  return apiReference().find((g) => g.slug === slug);
}

/** The public spec served for download: internal browser-flow operations removed. */
export function publicSpec(): unknown {
  const sp = spec() as any;
  const paths: Record<string, any> = {};
  for (const [p, ops] of Object.entries<any>(sp.paths)) {
    const kept = Object.fromEntries(Object.entries<any>(ops).filter(([, o]) => !o["x-internal"]));
    if (Object.keys(kept).length) paths[p] = kept;
  }
  return { ...sp, servers: [{ url: APP_BASE, description: "Your Argus app host" }], paths, tags: sp.tags.filter((t: any) => t.name !== "auth") };
}

export function apiNav(): { slug: string; name: string; ops: { id: string; method: string; summary: string; path: string }[] }[] {
  return apiReference().map((g) => ({ slug: g.slug, name: g.name, ops: g.ops.map((o) => ({ id: o.id, method: o.method, summary: o.summary, path: o.path })) }));
}
