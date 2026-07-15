import os
from pathlib import Path

import yaml

from forge.output import emit

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_PATH = REPO_ROOT / "envs" / "profiles.yaml"
OVERLAY_ENV = "FORGE_FLEET_CONFIG"
VALID_STATUS = {"locked", "locked-untested", "stub"}
# hosts/smoke_host are NOT in the public profiles.yaml — they are physical
# fleet topology, injected from a private overlay (see _load_overlay).
REQUIRED_KEYS = {"description", "torch_index", "status"}


class ProfileError(ValueError):
    pass


def _load_overlay():
    """Per-profile host bindings ({hosts: [...], smoke_host: ...}) live outside
    this (public) repo — in a private fleet config pointed to by
    $FORGE_FLEET_CONFIG (a directory containing profiles.hosts.yaml, or the file
    itself). Absent → every profile resolves to an empty fleet, which is the
    correct default for a clone that has no hardware of its own."""
    raw_path = os.environ.get(OVERLAY_ENV)
    if not raw_path:
        return {}
    path = Path(raw_path)
    if path.is_dir():
        path = path / "profiles.hosts.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def load_profiles(path=None, overlay=None):
    raw = yaml.safe_load(Path(path or PROFILES_PATH).read_text())
    profiles = (raw or {}).get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ProfileError("profiles.yaml must contain a non-empty 'profiles' map")
    overlay = _load_overlay() if overlay is None else overlay
    for name, p in profiles.items():
        missing = REQUIRED_KEYS - set(p)
        if missing:
            raise ProfileError(f"profile {name}: missing keys {sorted(missing)}")
        if p["status"] not in VALID_STATUS:
            raise ProfileError(f"profile {name}: status must be one of {sorted(VALID_STATUS)}")
        # Merge private host bindings over the public class definition.
        binding = overlay.get(name) or {}
        p["hosts"] = binding.get("hosts", [])
        p["smoke_host"] = binding.get("smoke_host")
        if not isinstance(p["hosts"], list):
            raise ProfileError(f"profile {name}: hosts must be a list")
    return profiles


def profile_for_host(host, profiles):
    for name, p in profiles.items():
        if host in p["hosts"]:
            return name
    return None


def register(subparsers):
    env = subparsers.add_parser("env", help="environment profiles")
    esub = env.add_subparsers(dest="env_command", required=True)
    lst = esub.add_parser("list", help="list hardware profiles")
    lst.set_defaults(func=cmd_list)

    from forge.envupdate import register_update
    register_update(esub)


def cmd_list(args):
    profiles = load_profiles()
    human = "\n".join(f"{n:18} {p['status']:16} {p['description']}"
                      for n, p in profiles.items())
    emit({"profiles": profiles}, args.as_json, human=human)
    return 0
