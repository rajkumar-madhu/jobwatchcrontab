/* R74: the first-run path is "paste the crontab line you most worry about". We take the schedule
   from it (so missed runs are detected from the first slot, no inference needed), name the job after
   the command, and hand back the same line with the ping appended. */

export const CRON_MACROS: Record<string, string> = {
  "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *", "@weekly": "0 0 * * 0",
  "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *",
};

export type CrontabLine = { schedule: string; command: string; name: string; user?: string };

const FIELD = /^[\d*\/,\-]+$|^[A-Za-z]{3}(-[A-Za-z]{3})?(,[A-Za-z]{3}(-[A-Za-z]{3})?)*$/;   // 15, */5, 1-5, mon,fri, mon-fri, *

/** Parse one crontab entry. Returns null for comments, blank lines, env assignments and anything
 *  that does not start with five schedule fields or a @macro. System crontab lines (with a user
 *  field after the schedule) are accepted when `systemCrontab` is set. */
export function parseCrontabLine(raw: string, systemCrontab = false): CrontabLine | null {
  const line = raw.trim();
  if (!line || line.startsWith("#") || /^[A-Z_][A-Z0-9_]*=/.test(line)) return null;
  const parts = line.split(/\s+/);
  let schedule: string, rest: string[];
  if (parts[0].startsWith("@")) {
    if (parts[0] === "@reboot") return null;         // not a schedule
    const m = CRON_MACROS[parts[0].toLowerCase()];
    if (!m) return null;
    schedule = m; rest = parts.slice(1);
  } else {
    if (parts.length < 6 || !parts.slice(0, 5).every((f) => FIELD.test(f))) return null;
    schedule = parts.slice(0, 5).join(" "); rest = parts.slice(5);
  }
  let user: string | undefined;
  if (systemCrontab && rest.length > 1 && /^[a-z_][a-z0-9_-]*$/.test(rest[0])) { user = rest[0]; rest = rest.slice(1); }
  const command = rest.join(" ").trim();
  if (!command) return null;
  return { schedule, command, name: nameFor(command), user };
}

/** A job name from a command: the basename of the first thing that looks like a program or script,
 *  skipping env assignments, `cd … &&`, sudo/nice/flock/timeout wrappers and interpreters. */
export function nameFor(command: string): string {
  // wrappers and interpreters that precede the real program; the number is how many of their own
  // positional arguments they consume (flock's lock file, timeout's duration, docker exec's container)
  const SKIP: Record<string, number> = { sudo: 0, nice: 0, ionice: 0, chronic: 0, nohup: 0, env: 0, bash: 0, sh: 0, zsh: 0, python: 0, python3: 0,
    node: 0, ruby: 0, perl: 0, php: 0, exec: 0, flock: 1, timeout: 1, docker: 0, cd: 1 };
  // flags that take a value, per wrapper (flock's -n is boolean; sudo's -u is not)
  const FLAGS: Record<string, string[]> = { sudo: ["-u", "-g", "-C"], nice: ["-n"], ionice: ["-c", "-n"], timeout: ["-s", "-k"], docker: ["-u", "-w", "-e"] };
  const toks = command.replace(/\s*(\|\||&&|;|\|)\s*/g, " \u0000 ").split(/\s+/);
  let consume = 0, wrapper = "";
  for (const t of toks) {
    if (t === "\u0000") { consume = 0; wrapper = ""; continue; }
    if (!t) continue;
    if (t.startsWith("-")) { if ((FLAGS[wrapper] ?? []).includes(t)) consume++; continue; }
    if (consume > 0) { consume--; continue; }
    if (/^[A-Z_][A-Z0-9_]*=/.test(t) || /^\d+[smhd]?$/.test(t)) continue;
    const base = t.replace(/^.*\//, "");
    if (wrapper === "docker") { wrapper = ""; consume = t === "exec" || t === "run" ? 1 : 0; continue; }   // docker exec <container> cmd
    if (base in SKIP) { consume = SKIP[base]; wrapper = base; continue; }
    const stem = base.replace(/\.(sh|py|rb|pl|php|js|ts|bash)$/i, "").replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
    if (stem) return stem.slice(0, 60);
  }
  return "my-first-job";
}

/** The same line, with the ping appended: `&&` so a non-zero exit is a failure (no ping → missed). */
export function withPing(entry: CrontabLine, pingUrl: string): string {
  const user = entry.user ? ` ${entry.user}` : "";
  return `${entry.schedule}${user}  ${entry.command} && curl -fsS -m 10 --retry 5 ${pingUrl}`;
}

/** The browser's IANA zone, for the job's tz; crontabs run in the server's local time, which is
 *  usually the same zone the person is in and always worth confirming on the job page. */
export function browserZone(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; }
}
