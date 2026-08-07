"""Rented-compute provider registry. See base.py for the contract."""
from forge.providers.azure_provider import AzureProvider
from forge.providers.base import Credential, Provider
from forge.providers.modal_provider import ModalProvider

PROVIDERS = {p.name: p() for p in (ModalProvider, AzureProvider)}

__all__ = ["PROVIDERS", "Provider", "Credential", "get"]


class UnknownProvider(KeyError):
    pass


def get(name):
    try:
        return PROVIDERS[name]
    except KeyError:
        raise UnknownProvider(
            f"unknown provider {name!r} (known: {sorted(PROVIDERS)})") from None
