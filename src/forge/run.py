import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from forge import config, recipes
from forge.heartbeat import LeaseHeartbeat
from forge.lease import FleetUnreachable, LeaseClient, LeaseRefused
from forge.output import emit

REPO_ROOT = Path(__file__).resolve().parents[2]
EXIT_OK, EXIT_REFUSED, EXIT_JOB, EXIT_INFRA, EXIT_PAUSED = 0, 2, 3, 4, 75


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _child_env(run_dir):
    """Env for the training/quant/surgery subprocess. The profile envs under
    envs/<profile> are separate uv projects that do NOT install the root
    `forge` package (src-layout) — every recipe imports `forge.train.*` /
    `forge.quant.*` / `forge.surgery.*`, so without this the child fails at
    import before doing any work. PYTHONPATH is honored by the interpreter
    regardless of which venv `uv run --project ...` activates."""
    src = str(REPO_ROOT / "src")
    existing = os.environ.get("PYTHONPATH")
    pythonpath = src + (os.pathsep + existing if existing else "")
    return {**os.environ, "FORGE_RUN_DIR": str(run_dir), "PYTHONPATH": pythonpath}


def execute(recipe_path, host, off_fleet=False, target_type="node", gpu_name=None,
            run_root=None, as_json=False, dry_run=False, use_uv_project=True,
            poll_sec=5.0):
    try:
        recipe = recipes.load_recipe(recipe_path)
    except recipes.RecipeError as e:
        emit({"ok": False, "error": str(e)}, as_json)
        return EXIT_REFUSED

    run_dir = Path(run_root or REPO_ROOT / "runs") / \
        f"{recipe['name']}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    inner = recipes.render_command(recipe, run_dir=run_dir, recipe_path=Path(recipe_path))
    if use_uv_project:
        cmd = ["uv", "run", "--project", str(REPO_ROOT / "envs" / recipe["profile"]),
               *inner]
    else:
        cmd = inner
    if dry_run:
        emit({"dry_run": True, "cmd": cmd, "run_dir": str(run_dir)}, as_json)
        return EXIT_OK

    run_dir.mkdir(parents=True, exist_ok=True)

    client, lease, hb = None, None, None
    if not off_fleet:
        client = LeaseClient()
        try:
            node = client.node(host)
            if node and node.get("serving"):
                models = sorted({s.get("model") for s in node["serving"]})
                print(f"WARNING: {host} is serving {models}. Consider a floor lease "
                      f"first: forge lease acquire --mode floor --target-type pool "
                      f"--name {models[0]} --min-floor 1", file=sys.stderr)
            target_name = gpu_name if target_type == "gpu" else host
            lease = client.acquire(config.HOLDER, target_type, target_name,
                                   mode="exclusive", ttl_sec=28800,
                                   notes=f"forge run {recipe['name']}")
        except LeaseRefused as e:
            emit({"ok": False, "error": str(e)}, as_json)
            return EXIT_REFUSED
        except FleetUnreachable as e:
            emit({"ok": False, "error": str(e)}, as_json)
            return EXIT_INFRA
        hb = LeaseHeartbeat(client, lease["id"])
        hb.start()

    # From here on, the lease is live (unless off_fleet) and the heartbeat thread
    # may be running. NO MATTER WHAT goes wrong below — Popen failure, poll-loop
    # exception, killpg failure — we must stop the heartbeat, attempt lease
    # release, restore signal handlers, close the log fd, and write run.json
    # with a contract exit code. Nothing after lease acquisition may raise past
    # this point uncaught.
    interrupted = {"flag": False}

    def _on_sig(signum, frame):
        interrupted["flag"] = True

    started = _now()
    old_term = old_int = None
    log = None
    proc = None
    child_exit = None
    try:
        old_term = signal.signal(signal.SIGTERM, _on_sig)
        old_int = signal.signal(signal.SIGINT, _on_sig)
        log = open(run_dir / "job.log", "ab")
        proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, env=_child_env(run_dir))
        while proc.poll() is None:
            if interrupted["flag"] or (hb and hb.lost.is_set()):
                # A stop signal was sent — whether that becomes "paused" or
                # "failed" is decided below purely from child_exit, never
                # from the mere fact that we asked the child to stop.
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=recipe["grace_sec"])
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                break
            time.sleep(poll_sec)
        child_exit = proc.returncode
    except Exception as e:
        if proc is not None and proc.returncode is not None:
            child_exit = proc.returncode
        print(f"ERROR: forge run failed: {e}", file=sys.stderr)
    finally:
        if old_term is not None:
            signal.signal(signal.SIGTERM, old_term)
        if old_int is not None:
            signal.signal(signal.SIGINT, old_int)
        if log:
            log.close()
        if hb:
            hb.stop()
        if client and lease:
            try:
                client.release(lease["id"])
            except Exception:
                print(f"WARNING: lease release failed for {lease['id']} — release "
                      f"manually: forge lease release --id {lease['id']}", file=sys.stderr)

    # Trust the child's exit code, not whether a stop signal was sent: only an
    # honest 75 (the checkpoint handshake) means the job actually checkpointed.
    # A SIGKILLed straggler (-9), a launch failure (None), or any other nonzero
    # exit is "failed" even if we sent SIGTERM first — a downstream auto-resume
    # must never trust a checkpoint that doesn't exist.
    if child_exit == 0:
        outcome, rc = "completed", EXIT_OK
    elif child_exit == 75:
        outcome, rc = "paused", EXIT_PAUSED
    else:
        outcome, rc = "failed", EXIT_JOB

    manifest = {
        "recipe": recipe["name"],
        "recipe_sha256": hashlib.sha256(Path(recipe_path).read_bytes()).hexdigest(),
        "host": host, "off_fleet": off_fleet,
        "lease_id": lease["id"] if lease else None,
        "cmd": cmd, "started": started, "ended": _now(),
        "child_exit": child_exit, "outcome": outcome,
        "run_dir": str(run_dir),
    }
    (run_dir / "run.json").write_text(json.dumps(manifest, indent=2))
    emit(manifest, as_json,
         human=f"{outcome.upper()} {recipe['name']} on {host} (exit {child_exit}) "
               f"→ {run_dir}")
    return rc


def register(subparsers):
    p = subparsers.add_parser("run", help="run a recipe under lease")
    p.add_argument("recipe")
    p.add_argument("--host", required=True)
    p.add_argument("--target-type", default="node", choices=["node", "gpu"])
    p.add_argument("--gpu-name", default=None,
                   help="gpu target name, e.g. 'ai-silo:2' (required with --target-type gpu)")
    p.add_argument("--off-fleet", action="store_true")
    p.add_argument("--run-root", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_run)


def cmd_run(args):
    if args.target_type == "gpu" and not args.gpu_name:
        emit({"ok": False, "error": "--gpu-name required with --target-type gpu"},
             args.as_json)
        return EXIT_REFUSED
    return execute(recipe_path=args.recipe, host=args.host,
                   off_fleet=args.off_fleet, target_type=args.target_type,
                   gpu_name=args.gpu_name, run_root=args.run_root,
                   as_json=args.as_json, dry_run=args.dry_run)
