"""Rented-compute providers (Modal, Azure, ...).

Fleet nodes are acquired through the lease system; rented compute is not — you
pay for it by the second and nobody else on the fleet can contend for it. So a
cloud run is an `--off-fleet` run whose command dispatches to a provider.

What lives here is deliberately NOT a job-submission API. It is the
*preflight* layer: a declarative statement of which credentials and CLIs each
provider needs, and a check that reports precisely which of them are absent.
That ordering is on purpose — the credentials arrive after the plumbing, so
the plumbing has to be useful and honest while they are still missing.

No provider method here performs network I/O. Preflight answers "could this
possibly work" from local state only, which keeps it fast, offline-safe, and
testable without touching an account.
"""
import os
import shutil
from pathlib import Path


class Credential:
    """One secret/setting a provider needs, and where it comes from.

    `env` is the environment variable consulted. `path` (optional) is a config
    file the provider's own CLI writes, which satisfies the requirement even
    when the env var is unset — `modal token new` writes ~/.modal.toml rather
    than exporting anything, and we must not report that as missing.
    """

    def __init__(self, env, description, required=True, path=None):
        self.env = env
        self.description = description
        self.required = required
        self.path = path

    def satisfied_by(self, env):
        if env.get(self.env):
            return "env"
        if self.path and Path(self.path).expanduser().exists():
            return "file"
        return None

    def describe(self):
        d = {"env": self.env, "description": self.description,
             "required": self.required}
        if self.path:
            d["file"] = str(self.path)
        return d


class Provider:
    """Base class. Subclasses set name/description/credentials/cli/gpus."""

    name = ""
    description = ""
    #: Credentials consulted, in the order a human should supply them.
    credentials = ()
    #: Executable that must be on PATH to dispatch work, or None.
    cli = None
    #: How to install `cli` if absent — shown to the operator, never run.
    cli_install = None
    #: Accelerator shapes this provider is expected to offer. Declarative
    #: only: forge does not query the provider's live inventory or quota, so
    #: treat these as "ask for this", not "this is available right now".
    gpus = ()

    def preflight(self, env=None):
        """Report readiness from local state. Never raises, never touches the
        network. `ok` means every required credential resolved AND the CLI (if
        one is declared) is on PATH — i.e. dispatch has a chance of working.
        """
        env = os.environ if env is None else env
        resolved, missing = {}, []
        for cred in self.credentials:
            source = cred.satisfied_by(env)
            if source:
                resolved[cred.env] = source
            elif cred.required:
                missing.append(cred.describe())

        cli_path = shutil.which(self.cli) if self.cli else None
        cli_ok = cli_path is not None if self.cli else True

        return {
            "provider": self.name,
            "description": self.description,
            "ok": not missing and cli_ok,
            "resolved": resolved,
            "missing": missing,
            "cli": {"name": self.cli, "path": cli_path, "ok": cli_ok,
                    "install": None if cli_ok else self.cli_install},
            "gpus": list(self.gpus),
        }
