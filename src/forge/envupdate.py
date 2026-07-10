import json
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from forge import envs
from forge.output import emit

REPO_ROOT = Path(__file__).resolve().parents[2]


def lock_versions(lock_path):
    data = tomllib.loads(Path(lock_path).read_text())
    return {p["name"]: p["version"] for p in data.get("package", [])
            if "name" in p and "version" in p}


def diff_versions(before, after):
    return {
        "changed": {k: [before[k], after[k]] for k in before
                    if k in after and before[k] != after[k]},
        "added": {k: v for k, v in after.items() if k not in before},
        "removed": {k: v for k, v in before.items() if k not in after},
    }


def update_profile(profile_dir):
    lock = Path(profile_dir) / "uv.lock"
    before = lock_versions(lock)
    r = subprocess.run(["uv", "lock", "--upgrade"], cwd=str(profile_dir),
                       check=False, capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": r.stderr.strip()[-2000:]}
    return diff_versions(before, lock_versions(lock))


def write_report(diffs, smoke, report_dir):
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ok = (not any("error" in d for d in diffs.values())
          and all(s.get("outcome") in ("completed", "skipped")
                  for s in smoke.values()))
    payload = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "diffs": diffs, "smoke": smoke, "ok": ok}
    out = report_dir / f"env-update-{stamp}.json"
    out.write_text(json.dumps(payload, indent=2))
    return str(out)


def _pr_body(diffs, smoke):
    lines = ["Automated env lockfile update.", ""]
    for prof, d in diffs.items():
        lines.append(f"## {prof}")
        if "error" in d:
            lines.append(f"LOCK FAILED: {d['error']}")
            continue
        for name, (a, b) in sorted(d["changed"].items()):
            lines.append(f"- {name}: {a} -> {b}")
        for name, v in sorted(d["added"].items()):
            lines.append(f"- {name}: added {v}")
        for name, v in sorted(d["removed"].items()):
            lines.append(f"- {name}: removed (was {v})")
        lines.append(f"- smoke: {smoke.get(prof, {}).get('outcome', 'not run')}")
        lines.append("")
    return "\n".join(lines)


def cmd_update(args):
    profiles = envs.load_profiles()
    diffs, smoke = {}, {}
    for name, p in profiles.items():
        d = REPO_ROOT / "envs" / name
        if not (d / "uv.lock").exists():
            continue
        diffs[name] = update_profile(d)
        changed = any(diffs[name].get(k) for k in ("changed", "added", "removed"))
        if args.no_smoke or not changed or not p.get("smoke_host"):
            smoke[name] = {"outcome": "skipped"}
            continue
        r = subprocess.run(
            ["uv", "run", "forge", "--json", "run", "recipes/smoke.yaml",
             "--host", p["smoke_host"]],
            cwd=str(REPO_ROOT), capture_output=True, text=True)
        smoke[name] = {"outcome": "completed" if r.returncode == 0 else "failed",
                       "exit": r.returncode}
    report = write_report(diffs, smoke, args.report_dir)
    any_change = any(d.get(k) for d in diffs.values()
                     for k in ("changed", "added", "removed"))
    pr_url = None
    if any_change and not args.no_pr:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        branch = f"env-update-{stamp}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "add", "envs"], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: env lock update {stamp}"],
                       cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "push", "-u", "origin", branch], cwd=REPO_ROOT, check=True)
        r = subprocess.run(["gh", "pr", "create", "--title",
                            f"env lock update {stamp}", "--body",
                            _pr_body(diffs, smoke)],
                           cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        pr_url = r.stdout.strip()
        subprocess.run(["git", "checkout", "main"], cwd=REPO_ROOT, check=True)
    emit({"report": report, "diffs": diffs, "smoke": smoke, "pr": pr_url},
         args.as_json, human=f"report: {report}; pr: {pr_url or 'none'}")
    return 0


def register_update(esub):
    up = esub.add_parser("update", help="re-resolve lockfiles, smoke, open PR")
    up.add_argument("--no-smoke", action="store_true")
    up.add_argument("--no-pr", action="store_true")
    up.add_argument("--report-dir", default=str(REPO_ROOT / "reports"))
    up.set_defaults(func=cmd_update)
