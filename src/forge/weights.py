"""Per-job weight source: where a cloud job's model weights come from.

Colby 2026-08-07 (projects/forge/WEIGHT-SOURCES.md): weight source is a
parameter of a JOB, not a property of the provider.  Two kinds are modelled:

  hf          public or gated Hugging Face repo, pulled in-container
  private-hf  a private repo under the GoodAncestor HF org (Path B bridge,
              ruled yes 2026-11-07)

Spec syntax:  hf:<org/repo>[@revision]   private-hf:<org/repo>[@revision]

Preflight here is READ-ONLY: it GETs whoami-v2 and the repo's metadata with
the token.  It never creates a repo, uploads, or submits anything, and the
token value is never returned or logged.
"""
import os
from dataclasses import dataclass
from pathlib import Path

import requests

HF_API = "https://huggingface.co/api"
KINDS = ("hf", "private-hf")
TOKEN_ENVS = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
TOKEN_FILE = "~/.cache/huggingface/token"


class BadWeightSpec(ValueError):
    pass


@dataclass(frozen=True)
class WeightSource:
    kind: str
    repo: str
    revision: str = "main"

    def describe(self):
        return {"kind": self.kind, "repo": self.repo, "revision": self.revision}


def parse(spec):
    kind, sep, rest = (spec or "").partition(":")
    if not sep or kind not in KINDS:
        raise BadWeightSpec(f"weight source {spec!r}: kind must be one of {list(KINDS)} "
                            f"(form <kind>:<org/repo>[@revision])")
    repo, _, rev = rest.partition("@")
    if repo.count("/") != 1 or not all(repo.split("/")):
        raise BadWeightSpec(f"weight source {spec!r}: repo must look like org/name")
    return WeightSource(kind, repo, rev or "main")


def resolve_token(env=None):
    """Return (token, origin) or (None, None).  Origin names where it came
    from; the token itself must never be printed."""
    env = os.environ if env is None else env
    for name in TOKEN_ENVS:
        if env.get(name):
            return env[name].strip(), f"env:{name}"
    p = Path(TOKEN_FILE).expanduser()
    if p.is_file():
        t = p.read_text().strip()
        if t:
            return t, "file"
    return None, None


def _can_read_content(whoami):
    """True when the token may read repo content.  Classic read/write/admin
    tokens can; fine-grained tokens must list repo.content.read in some scope."""
    tok = (whoami.get("auth") or {}).get("accessToken") or {}
    if tok.get("role") != "fineGrained":
        return True
    for scope in (tok.get("fineGrained") or {}).get("scoped", []):
        if "repo.content.read" in scope.get("permissions", []):
            return True
    return False


def preflight(source, env=None, get=requests.get, timeout=15):
    """Check a WeightSource.  Returns a status dict; never raises, never writes."""
    token, origin = resolve_token(env)
    out = {**source.describe(), "ok": False, "token": origin, "checks": {}}
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    if source.kind == "private-hf" and not token:
        out["checks"]["token"] = "missing: private-hf needs HF_TOKEN / HUGGING_FACE_HUB_TOKEN or ~/.cache/huggingface/token"
        return out

    whoami = None
    if token:
        try:
            r = get(f"{HF_API}/whoami-v2", headers=headers, timeout=timeout)
            if r.status_code == 200:
                whoami = r.json()
                out["checks"]["whoami"] = "ok"
            else:
                out["checks"]["whoami"] = f"http {r.status_code}"
        except requests.RequestException as e:
            out["checks"]["whoami"] = f"unreachable: {type(e).__name__}"
        if whoami is None:
            return out
        if source.kind == "private-hf":
            can = _can_read_content(whoami)
            out["checks"]["repo.content.read"] = "ok" if can else "token lacks repo.content.read"
            if not can:
                return out

    try:
        r = get(f"{HF_API}/models/{source.repo}/revision/{source.revision}",
                headers=headers, timeout=timeout)
    except requests.RequestException as e:
        out["checks"]["repo"] = f"unreachable: {type(e).__name__}"
        return out
    if r.status_code == 200:
        private = bool(r.json().get("private"))
        out["checks"]["repo"] = "ok"
        if source.kind == "private-hf" and not private:
            out["checks"]["private"] = "repo is public; kind private-hf expects a private repo"
            return out
        out["ok"] = True
    elif r.status_code in (401, 403):
        out["checks"]["repo"] = f"http {r.status_code}: gated, private, or token not authorised"
    elif r.status_code == 404:
        out["checks"]["repo"] = "not found (or revision absent)"
    else:
        out["checks"]["repo"] = f"http {r.status_code}"
    return out
