import { describe, expect, it } from "vitest";
import { nameFor, parseCrontabLine, withPing } from "@/lib/crontab";

describe("parseCrontabLine", () => {
  it("splits schedule and command and names the job after the script", () => {
    const e = parseCrontabLine("15 2 * * *  /opt/jobs/pg-backup.sh --full >> /var/log/pg.log 2>&1");
    expect(e).toEqual({ schedule: "15 2 * * *", command: "/opt/jobs/pg-backup.sh --full >> /var/log/pg.log 2>&1", name: "pg-backup", user: undefined });
  });
  it("accepts steps, ranges, lists and names", () => {
    expect(parseCrontabLine("*/5 * * * * curl -s https://x")?.schedule).toBe("*/5 * * * *");
    expect(parseCrontabLine("0 9-17 * * mon-fri /bin/ping-standup")?.schedule).toBe("0 9-17 * * mon-fri");
    expect(parseCrontabLine("30 1,13 * * 1,4 /x.sh")?.schedule).toBe("30 1,13 * * 1,4");
  });
  it("expands @macros and rejects @reboot", () => {
    expect(parseCrontabLine("@daily /usr/local/bin/certbot renew")?.schedule).toBe("0 0 * * *");
    expect(parseCrontabLine("@reboot /x.sh")).toBeNull();
  });
  it("ignores comments, blanks and environment lines", () => {
    expect(parseCrontabLine("# 0 2 * * * /x.sh")).toBeNull();
    expect(parseCrontabLine("")).toBeNull();
    expect(parseCrontabLine("MAILTO=ops@acme.io")).toBeNull();
    expect(parseCrontabLine("just some words here and more")).toBeNull();
  });
  it("reads the user column of /etc/crontab entries only when asked", () => {
    expect(parseCrontabLine("0 3 * * * postgres /usr/bin/vacuumdb -a", true)).toMatchObject({ user: "postgres", command: "/usr/bin/vacuumdb -a", name: "vacuumdb" });
    expect(parseCrontabLine("0 3 * * * postgres /usr/bin/vacuumdb -a")?.command).toBe("postgres /usr/bin/vacuumdb -a");
  });
});

describe("nameFor", () => {
  it("skips wrappers, env, cd and interpreters", () => {
    expect(nameFor("cd /srv/app && PYTHONPATH=. /usr/bin/python3 manage.py send_digest")).toBe("manage");
    expect(nameFor("flock -n /tmp/x.lock timeout 3600 bash /opt/etl/nightly_load.sh")).toBe("nightly_load");
    expect(nameFor("docker exec db pg_dump -U app > /b/db.sql")).toBe("pg_dump");
    expect(nameFor("sudo -u www php /var/www/artisan schedule:run")).toBe("artisan");
  });
  it("falls back when nothing looks like a program", () => expect(nameFor("--flag-only")).toBe("my-first-job"));
});

describe("withPing", () => {
  it("appends the ping with && so a failing command never pings", () => {
    const e = parseCrontabLine("15 2 * * * /opt/jobs/pg-backup.sh")!;
    expect(withPing(e, "https://ingest.example/ping/abc")).toBe("15 2 * * *  /opt/jobs/pg-backup.sh && curl -fsS -m 10 --retry 5 https://ingest.example/ping/abc");
  });
  it("keeps the user column for system crontabs", () => {
    const e = parseCrontabLine("0 3 * * * postgres /usr/bin/vacuumdb -a", true)!;
    expect(withPing(e, "U")).toBe("0 3 * * * postgres  /usr/bin/vacuumdb -a && curl -fsS -m 10 --retry 5 U");
  });
});
