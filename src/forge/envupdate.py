import json
import os
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from forge import envs
from forge.output import emit

REPO_ROOT = Path(__file__).resolve().parents[2]
EXIT_OK = 0
EXIT_JOB = 3


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
        # Discard the possibly-corrupt working-tree lockfile a failed
        # `uv lock --upgrade` may have left behind. profile_dir is
        # envs/<name>, so parents[1] is the repo root.
        subprocess.run(["git", "checkout", "--", str(lock)],
                       cwd=str(Path(profile_dir).parents[1]), check=False)
        return {"error": r.stderr.strip()[-2000:]}
    return diff_versions(before, lock_versions(lock))


def write_report(diffs, smoke, report_dir):
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # ok reflects only what this host can attest: that every profile's lock
    # re-resolved without error. Hardware smoke is deferred to PR review (see
    # cmd_update), so it is advisory in the report, not a gate here.
    ok = not any("error" in d for d in diffs.values())
    payload = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "diffs": diffs, "smoke": smoke, "ok": ok}
    out = report_dir / f"env-update-{stamp}.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, out)
    return str(out)


def _pr_body(diffs, smoke):
    lines = ["Automated env lockfile update.", "",
             "⚠ Hardware smoke is NOT run by this job — it runs on the GPU-less "
             "jumpbox, where these CUDA envs can't build (glibc-only wheels) and "
             "there is no GPU. Run each changed profile's smoke command below on "
             "its smoke_host before merging.", ""]
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
        host = smoke.get(prof, {}).get("smoke_host")
        if host:
            lines.append(f"- smoke ({smoke[prof]['outcome']}): run on `{host}` "
                         f"before merge — `uv run forge --json run "
                         f"recipes/smoke.yaml --host {host} --profile {prof}`")
        else:
            lines.append(f"- smoke: no smoke_host configured for {prof}")
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
        # Hardware smoke is deliberately NOT run here. This job runs on the
        # jumpbox (Alpine musl, no GPU): the CUDA envs can't even build there
        # (bitsandbytes/torch ship glibc-only wheels) and there is no GPU to
        # matmul on. The PR is never auto-merged, so smoke is deferred to the
        # reviewer, who runs it on the profile's smoke_host before merging —
        # the exact command is embedded in the PR body (see _pr_body).
        smoke[name] = {"outcome": "deferred" if (changed and p.get("smoke_host"))
                       else "skipped",
                       "smoke_host": p.get("smoke_host")}
    report = write_report(diffs, smoke, args.report_dir)
    any_change = any(d.get(k) for d in diffs.values()
                     for k in ("changed", "added", "removed"))
    pr_url = None
    pr_error = None
    if any_change and not args.no_pr:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        branch = f"env-update-{stamp}"
        try:
            subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_ROOT, check=True)
            try:
                paths = [f"envs/{name}/uv.lock" for name, d in diffs.items()
                        if any(d.get(k) for k in ("changed", "added", "removed"))]
                subprocess.run(["git", "add", *paths], cwd=REPO_ROOT, check=True)
                subprocess.run(["git", "commit", "-m", f"chore: env lock update {stamp}"],
                               cwd=REPO_ROOT, check=True)
                subprocess.run(["git", "push", "-u", "origin", branch], cwd=REPO_ROOT,
                               check=True)
                # -R is required: origin uses a `github-forge` SSH host alias
                # (deploy key), which gh can't map back to a GitHub repo on its
                # own, so it can't infer the target repo from the remote.
                r = subprocess.run(["gh", "pr", "create", "-R", "GoodAncestor/forge",
                                    "--title", f"env lock update {stamp}", "--body",
                                    _pr_body(diffs, smoke)],
                                   cwd=REPO_ROOT, capture_output=True, text=True, check=True)
                pr_url = r.stdout.strip()
            finally:
                # check=False: the recovery checkout itself must never raise,
                # or we'd strand the checkout on the env-update branch for
                # next week's cron run.
                subprocess.run(["git", "checkout", "main"], cwd=REPO_ROOT, check=False)
        except subprocess.CalledProcessError as e:
            pr_error = str(e)
    payload = {"report": report, "diffs": diffs, "smoke": smoke, "pr": pr_url}
    if pr_error is not None:
        payload["pr_error"] = pr_error
    emit(payload, args.as_json,
         human=f"report: {report}; pr: {pr_url or 'none'}"
               + (f"; pr_error: {pr_error}" if pr_error else ""))
    return EXIT_JOB if pr_error is not None else EXIT_OK


def register_update(esub):
    up = esub.add_parser(
        "update", help="re-resolve lockfiles and open PR (smoke deferred to review)")
    up.add_argument("--no-pr", action="store_true")
    up.add_argument("--report-dir", default=str(REPO_ROOT / "reports"))
    up.set_defaults(func=cmd_update)
