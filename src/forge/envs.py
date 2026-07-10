from pathlib import Path

import yaml

from forge.output import emit

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_PATH = REPO_ROOT / "envs" / "profiles.yaml"
VALID_STATUS = {"locked", "locked-untested", "stub"}
REQUIRED_KEYS = {"description", "torch_index", "hosts", "smoke_host", "status"}


class ProfileError(ValueError):
    pass


def load_profiles(path=None):
    raw = yaml.safe_load(Path(path or PROFILES_PATH).read_text())
    profiles = (raw or {}).get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ProfileError("profiles.yaml must contain a non-empty 'profiles' map")
    for name, p in profiles.items():
        missing = REQUIRED_KEYS - set(p)
        if missing:
            raise ProfileError(f"profile {name}: missing keys {sorted(missing)}")
        if p["status"] not in VALID_STATUS:
            raise ProfileError(f"profile {name}: status must be one of {sorted(VALID_STATUS)}")
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


def cmd_list(args):
    profiles = load_profiles()
    human = "\n".join(f"{n:18} {p['status']:16} {p['description']}"
                      for n, p in profiles.items())
    emit({"profiles": profiles}, args.as_json, human=human)
    return 0
