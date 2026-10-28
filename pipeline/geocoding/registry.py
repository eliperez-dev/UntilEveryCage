from collections.abc import Callable
import os

from .base import GeocoderAdapter
from .dawa import DawaAdapter
from .geoapify import GeoapifyAdapter
from .locationiq import LocationIqAdapter
from .private_profiles import profile_by_id
from .accounts import account_for_provider, LOCATIONIQ_KEY_ENVS


ADAPTER_FACTORIES: dict[str, Callable[[], GeocoderAdapter]] = {
    "dawa": DawaAdapter,
    "geoapify": GeoapifyAdapter,
    "locationiq": LocationIqAdapter,
}


def get_adapter(provider_id: str, *, au_npi_pilot: bool = False,
                private_source_profile_id: str | None = None,
                provider_account: str | None = None) -> GeocoderAdapter:
    account = account_for_provider(provider_id, provider_account)
    if provider_id == "locationiq":
        key = os.environ.get(LOCATIONIQ_KEY_ENVS[account], "").strip()
        if not key:
            raise ValueError("selected LocationIQ account key is not configured")
    try:
        if private_source_profile_id is not None:
            profile = profile_by_id(private_source_profile_id)
            if profile is None:
                raise ValueError("private source profile is not enabled")
            if provider_id != profile.get("provider_id", "geoapify"):
                raise ValueError("private source profile provider does not match")
            if provider_id == "locationiq":
                return LocationIqAdapter(api_key=key, country_code=profile["country_code"].lower(),
                                         private_source_profile=True,
                                         query_kind=profile.get("query_kind"),
                                         first_pass_source=(profile["profile_id"] in {
                                             "locationiq-es-aesan-rgseaa",
                                             "locationiq-es-cat-feed-sandach",
                                             "locationiq-gb-fsa-approved-establishments",
                                             "locationiq-gb-fss-approved-establishments",
                                             "locationiq-nz-mpi-rmp",
                                         }))
            return GeoapifyAdapter(country_code=profile["country_code"].lower(),
                                   private_source_profile=True,
                                   locality_only=profile.get("query_kind") in {
                                       "mailing_locality_only", "verified_municipality_only"},
                                   municipality_only=profile.get("query_kind") == "verified_municipality_only",
                                   allow_locality_match=profile.get("allow_locality_match", True))
        if au_npi_pilot:
            if provider_id != "geoapify":
                raise ValueError("AU NPI pilot requires Geoapify")
            return GeoapifyAdapter(country_code="au", pilot_auto_display=True)
        if provider_id == "locationiq":
            return LocationIqAdapter(api_key=key)
        return ADAPTER_FACTORIES[provider_id]()
    except KeyError as error:
        raise ValueError(f"No adapter registered for provider {provider_id}") from error
