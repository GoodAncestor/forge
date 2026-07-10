import json as _json
import subprocess
import time
from pathlib import Path

import requests
import yaml
from huggingface_hub import HfApi

from forge import config
from forge.output import emit

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "datasets" / "manifest.yaml"
TIERS = frozenset({"nvidia-open-models", "pretraining", "sft-preference",
                   "historical-1930-1980", "classifiers-quality"})
REQUIRED = {"name", "source", "tier", "license", "approved", "size_bytes", "nas_path"}

MANIFEST_HEADER = """\
# forge dataset archive manifest.
# approved: flipped ONLY by Colby (or an explicitly authorized human decision).
# size_bytes: written by `forge data sizes` — never hand-edited.
# nas_path: relative to FORGE_DATA_ROOT; no absolute paths, no '..'.
"""


class ManifestError(ValueError):
    pass


def load_manifest(path=None):
    raw = yaml.safe_load(Path(path or MANIFEST_PATH).read_text())
    entries = (raw or {}).get("datasets")
    if not isinstance(entries, list) or not entries:
        raise ManifestError("manifest must contain a non-empty 'datasets' list")
    seen = set()
    for e in entries:
        missing = REQUIRED - set(e)
        if missing:
            raise ManifestError(f"entry {e.get('name')}: missing {sorted(missing)}")
        if e["name"] in seen:
            raise ManifestError(f"duplicate name {e['name']}")
        seen.add(e["name"])
        if e["tier"] not in TIERS:
            raise ManifestError(f"entry {e['name']}: unknown tier {e['tier']!r}")
        if not (e["source"].startswith("hf://") or e["source"].startswith("url://")):
            raise ManifestError(f"entry {e['name']}: source must be hf:// or url://")
        p = str(e["nas_path"])
        if p.startswith("/") or ".." in p.split("/"):
            raise ManifestError(f"entry {e['name']}: nas_path must be relative, no '..'")
        if not isinstance(e["approved"], bool):
            raise ManifestError(f"entry {e['name']}: approved must be boolean")
        if e.get("repo_type") not in (None, "dataset", "model"):
            raise ManifestError(f"entry {e['name']}: repo_type must be dataset|model")
    return entries


def save_manifest(entries, path=None):
    Path(path or MANIFEST_PATH).write_text(
        MANIFEST_HEADER + yaml.safe_dump({"datasets": entries}, sort_keys=False, allow_unicode=True))


def entry_dir(entry, root=None):
    return Path(root or config.DATA_ROOT) / entry["nas_path"]


def usage_bytes(root):
    root = Path(root)
    if not root.exists():
        return 0
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file())


def measure_entry(entry, token=None):
    """Measured size in bytes, or None if unmeasurable (e.g. rsync trees,
    API-paginated sources). Never guesses."""
    src = entry["source"]
    if src.startswith("hf://"):
        repo_id = src[len("hf://"):]
        api = HfApi(token=token)
        if entry.get("repo_type") == "model":
            info = api.model_info(repo_id, files_metadata=True)
        else:
            info = api.dataset_info(repo_id, files_metadata=True)
        return sum(s.size or 0 for s in info.siblings)
    url = src[len("url://"):]
    if url.startswith("rsync://") or not url.split("://", 1)[-1].split("/", 1)[-1]:
        return None  # rsync trees and bare-domain API sources: size unknown up front
    if "." not in url.rsplit("/", 1)[-1]:
        return None  # API roots (e.g. chroniclingamerica.loc.gov) — no single file
    # Some hosts (e.g. dumps.wikimedia.org) 403 generic HEAD requests and return
    # a small error body's Content-Length instead of the real file size when no
    # User-Agent is set — send one so measured sizes are real, not error pages.
    r = requests.head(url, allow_redirects=True, timeout=30,
                       headers={"User-Agent": "forge-data-archive/1.0"})
    r.raise_for_status()
    cl = r.headers.get("Content-Length")
    return int(cl) if cl else None


def cmd_sizes(args):
    entries = load_manifest()
    results, errors = [], []
    for e in entries:
        if args.only and e["name"] != args.only:
            continue
        try:
            size = measure_entry(e)
            e["size_bytes"] = size
            results.append({"name": e["name"], "size_bytes": size})
        except Exception as exc:
            errors.append({"name": e["name"], "error": f"{type(exc).__name__}: {exc}"})
    if args.write and not errors:
        save_manifest(entries)
    measurable = [r for r in results if r["size_bytes"]]
    total = sum(r["size_bytes"] for r in measurable)
    payload = {"measured": results, "errors": errors, "total_bytes": total,
               "cap_bytes": int(config.DATA_CAP_TB * 1e12),
               "written": bool(args.write and not errors)}
    human = "\n".join(f"{r['name']:34} {r['size_bytes'] or 'unmeasurable'}"
                      for r in results)
    human += f"\nTOTAL measurable: {total:,} bytes; errors: {len(errors)}"
    emit(payload, args.as_json, human=human)
    return 0 if not errors else 3


def plan_fetch(entries, root, cap_bytes, allow_unsized=False):
    """Pure planning: split candidate entries into to_fetch / skipped / refused.
    Cap math: existing on-disk usage + sum of planned sizes must stay under cap."""
    to_fetch, skipped, refused = [], [], []
    used = usage_bytes(root)
    planned = 0
    for e in entries:
        d = entry_dir(e, root)
        if (d / ".forge-complete").exists():
            skipped.append({"name": e["name"], "reason": "already fetched"})
            continue
        if not e["approved"]:
            refused.append({"name": e["name"], "reason": "not approved"})
            continue
        size = e.get("size_bytes")
        if size is None and not allow_unsized:
            refused.append({"name": e["name"],
                            "reason": "size unknown (run `forge data sizes`, or pass --allow-unsized)"})
            continue
        if used + planned + (size or 0) > cap_bytes or (size is None and used + planned >= cap_bytes):
            refused.append({"name": e["name"],
                            "reason": f"would exceed cap ({used + planned + (size or 0):,} > {cap_bytes:,})"})
            continue
        planned += size or 0
        to_fetch.append(e)
    return {"to_fetch": to_fetch, "skipped": skipped, "refused": refused,
            "used_bytes": used, "planned_bytes": planned, "cap_bytes": cap_bytes}


def fetch_entry(entry, root, rate_limit=None):
    """Download one entry. Sequential, single connection, resumable.
    Writes <dir>/.forge-complete marker JSON on success."""
    dest = entry_dir(entry, root)
    dest.mkdir(parents=True, exist_ok=True)
    src = entry["source"]
    if src.startswith("hf://"):
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=src[len("hf://"):],
                          repo_type=entry.get("repo_type", "dataset"),
                          local_dir=str(dest), max_workers=1)
    else:
        url = src[len("url://"):]
        if url.startswith("rsync://"):
            cmd = ["rsync", "-av", "--partial",
                   url.replace("rsync://", "", 1).replace("/", "::", 1), str(dest)]
            if rate_limit:
                cmd.insert(1, f"--bwlimit={rate_limit}")
        else:
            cmd = ["wget", "-c", "-P", str(dest), url]
            if rate_limit:
                cmd.insert(1, f"--limit-rate={rate_limit}")
        subprocess.run(cmd, check=True)
    (dest / ".forge-complete").write_text(_json.dumps({
        "name": entry["name"], "source": src,
        "completed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bytes": usage_bytes(dest)}))


def cmd_fetch(args):
    if bool(args.name) == bool(args.tier):
        emit({"ok": False,
              "error": "specify exactly one of NAME or --tier"}, args.as_json,
             human="specify exactly one of NAME or --tier")
        return 2
    all_entries = load_manifest()
    if args.name:
        cand = [e for e in all_entries if e["name"] == args.name]
        if not cand:
            emit({"ok": False, "error": f"no manifest entry named {args.name}"},
                 args.as_json)
            return 2
    else:
        cand = [e for e in all_entries if e["tier"] == args.tier]
    root = Path(args.root or config.DATA_ROOT)
    cap = int(config.DATA_CAP_TB * 1e12)
    plan = plan_fetch(cand, root, cap, allow_unsized=args.allow_unsized)
    if args.dry_run:
        emit({"dry_run": True, **{k: ([e["name"] for e in v] if k == "to_fetch" else v)
                                  for k, v in plan.items()}}, args.as_json)
        return 0 if not plan["refused"] else 2
    if plan["refused"] and not plan["to_fetch"]:
        emit({"ok": False, "refused": plan["refused"]}, args.as_json)
        return 2
    done, failed = [], []
    for e in plan["to_fetch"]:          # strictly sequential — single connection
        try:
            fetch_entry(e, root, rate_limit=args.rate_limit)
            done.append(e["name"])
        except Exception as exc:
            failed.append({"name": e["name"], "error": f"{type(exc).__name__}: {exc}"})
            break                        # stop on first failure; resumable next run
    emit({"fetched": done, "failed": failed, "skipped": plan["skipped"],
          "refused": plan["refused"]}, args.as_json)
    return 0 if not failed else 3


def register(subparsers):
    p = subparsers.add_parser("data", help="dataset archive")
    sub = p.add_subparsers(dest="data_command", required=True)

    lst = sub.add_parser("list")
    lst.add_argument("--tier", default=None)
    lst.add_argument("--approved-only", action="store_true")
    lst.set_defaults(func=cmd_list)

    rep = sub.add_parser("report")
    rep.add_argument("--root", default=None)
    rep.set_defaults(func=cmd_report)

    sz = sub.add_parser("sizes")
    sz.add_argument("--write", action="store_true")
    sz.add_argument("--only", default=None)
    sz.set_defaults(func=cmd_sizes)

    ft = sub.add_parser("fetch")
    ft.add_argument("name", nargs="?", default=None)
    ft.add_argument("--tier", default=None)
    ft.add_argument("--root", default=None)
    ft.add_argument("--rate-limit", default=None, help="e.g. 50M (wget/rsync syntax)")
    ft.add_argument("--dry-run", action="store_true")
    ft.add_argument("--allow-unsized", action="store_true")
    ft.set_defaults(func=cmd_fetch)


def _filtered(args):
    entries = load_manifest()
    if args.tier:
        entries = [e for e in entries if e["tier"] == args.tier]
    if getattr(args, "approved_only", False):
        entries = [e for e in entries if e["approved"]]
    return entries


def cmd_list(args):
    entries = _filtered(args)
    human = "\n".join(f"{e['name']:34} {e['tier']:22} approved={e['approved']} "
                      f"size={e['size_bytes']}" for e in entries)
    emit({"datasets": entries}, args.as_json, human=human)
    return 0


def cmd_report(args):
    root = Path(args.root or config.DATA_ROOT)
    entries = load_manifest()
    rows = []
    for e in entries:
        d = entry_dir(e, root)
        on_disk = usage_bytes(d) if d.exists() else 0
        rows.append({"name": e["name"], "tier": e["tier"], "approved": e["approved"],
                     "manifest_size_bytes": e["size_bytes"],
                     "on_disk_bytes": on_disk, "fetched": on_disk > 0,
                     "path": str(d)})
    total = sum(r["on_disk_bytes"] for r in rows)
    payload = {"root": str(root), "total_on_disk_bytes": total,
               "cap_bytes": int(config.DATA_CAP_TB * 1e12), "datasets": rows}
    human = "\n".join(f"{r['name']:34} on_disk={r['on_disk_bytes']:>15,} "
                      f"fetched={r['fetched']}" for r in rows)
    human += f"\nTOTAL {total:,} bytes of cap {payload['cap_bytes']:,}"
    emit(payload, args.as_json, human=human)
    return 0
