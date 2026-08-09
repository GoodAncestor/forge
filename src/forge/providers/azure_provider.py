"""Microsoft Azure — GPU VMs, funded here by the nonprofit credit grant.

Two constraints shape how this provider should be used, and both are worth
stating in code rather than rediscovering at spend time:

1. Shape. Azure's Blackwell SKUs are Grace-Blackwell *four*-GPU VMs — ND
   GB300 v6 carries 2 Grace CPUs + 4 B300, and ND GB200 v6 the GB200
   equivalent (learn.microsoft.com, checked 2026-08-07). A single 8×Blackwell
   container is therefore not an Azure-shaped request; it is a two-VM
   NVLink-domain job. Whether an 8-GPU non-Grace Blackwell SKU exists in a
   given region is UNVERIFIED — confirm against the live SKU list for the
   subscription before planning around one.
2. Budget. The Good Ancestor grant is $2,000/year (knowledge/infrastructure/
   cloud-accounts.md), which does not go far against Blackwell-class hourly
   rates. Azure is the small lane; treat it as such.

Auth: `az login` writes ~/.azure/azureProfile.json (the signed-in account's
subscription/tenant record), which satisfies the credential without env
vars. The service-principal triple is the headless path.

Deliberately NOT keyed on the bare ~/.azure/ directory: the Azure CLI creates
that directory (config.txt, telemetry cache, clouds.config, ...) on the
*first invocation of any `az` command*, login or not — `az --version` alone
is enough. Treating the directory's mere existence as "logged in" would let
bootstrap/CI tooling that only ever runs `az --version` flip this preflight
to green with no real subscription access behind it, which is exactly the
false-positive this layer exists to avoid. azureProfile.json is written only
by a successful `az login` (or `az account set` afterward), so its presence
is a real signal.
"""
from forge.providers.base import Credential, Provider

#: Written only by a successful `az login` — see module docstring for why
#: this, and not the bare ~/.azure/ directory, is the credential's `path`.
AZURE_LOGIN_PROFILE = "~/.azure/azureProfile.json"


class AzureProvider(Provider):
    name = "azure"
    description = "Azure GPU VMs (nonprofit credit grant; 4-GPU Blackwell SKUs)"
    cli = "az"
    cli_install = ("brew install azure-cli  # macOS; see "
                   "https://learn.microsoft.com/cli/azure/install-azure-cli")
    credentials = (
        Credential("AZURE_SUBSCRIPTION_ID",
                   "Subscription holding the nonprofit credit grant",
                   path=AZURE_LOGIN_PROFILE),
        Credential("AZURE_TENANT_ID",
                   "Directory (tenant) id", path=AZURE_LOGIN_PROFILE),
        Credential("AZURE_CLIENT_ID",
                   "Service-principal app id; omit when using `az login`",
                   required=False),
        Credential("AZURE_CLIENT_SECRET",
                   "Service-principal secret; omit when using `az login`",
                   required=False),
        Credential("AZURE_RESOURCE_GROUP",
                   "Resource group that owns forge VMs and disks",
                   required=False),
        Credential("AZURE_LOCATION",
                   "Region to request capacity in, e.g. eastus2",
                   required=False),
    )
    # Verified SKU families only. Per-region availability and quota are NOT
    # checked here — `az vm list-skus` against the real subscription is the
    # only truth for what this account can actually start.
    gpus = ("Standard_ND_GB300_v6 (4x B300)", "Standard_ND_GB200_v6 (4x GB200)")
