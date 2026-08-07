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

Auth: `az login` writes ~/.azure/, which satisfies the credential without env
vars. The service-principal triple is the headless path.
"""
from forge.providers.base import Credential, Provider

AZURE_CONFIG = "~/.azure"


class AzureProvider(Provider):
    name = "azure"
    description = "Azure GPU VMs (nonprofit credit grant; 4-GPU Blackwell SKUs)"
    cli = "az"
    cli_install = ("brew install azure-cli  # macOS; see "
                   "https://learn.microsoft.com/cli/azure/install-azure-cli")
    credentials = (
        Credential("AZURE_SUBSCRIPTION_ID",
                   "Subscription holding the nonprofit credit grant",
                   path=AZURE_CONFIG),
        Credential("AZURE_TENANT_ID",
                   "Directory (tenant) id", path=AZURE_CONFIG),
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
