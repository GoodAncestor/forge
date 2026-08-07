"""Modal (modal.com) — serverless GPU containers.

Verified against https://modal.com/docs/guide/gpu on 2026-08-07: accelerator
strings are requested as `gpu="B200:8"`, and B200/B300 both allow up to 8 GPUs
in a single container (2,304 GB GPU RAM ceiling). `B200+` lets Modal pick
B200-or-B300 at B200 billing. That 8-in-one-container limit is why Modal, not
Azure, is the natural home for a single 8×Blackwell job — see azure_provider.

Auth: `modal token new` writes ~/.modal.toml rather than exporting anything,
so the token file counts as satisfying the credential even with no env vars
set. MODAL_TOKEN_ID/SECRET are the headless equivalent for CI and cron.
"""
from forge.providers.base import Credential, Provider

MODAL_CONFIG = "~/.modal.toml"


class ModalProvider(Provider):
    name = "modal"
    description = "Modal serverless GPU containers (up to 8 GPUs/container)"
    cli = "modal"
    cli_install = "uv tool install modal  # then: modal token new"
    credentials = (
        Credential("MODAL_TOKEN_ID",
                   "Modal token id; written by `modal token new` into "
                   f"{MODAL_CONFIG}, or set explicitly for headless use",
                   path=MODAL_CONFIG),
        Credential("MODAL_TOKEN_SECRET",
                   "Modal token secret; same source as MODAL_TOKEN_ID",
                   path=MODAL_CONFIG),
        Credential("MODAL_PROFILE",
                   "Workspace/profile name when the token file holds several",
                   required=False),
    )
    gpus = ("B200:8", "B200+:8", "B300:8", "H200:8", "H100:8", "RTX-PRO-6000")
