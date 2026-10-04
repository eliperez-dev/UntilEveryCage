from collections.abc import Callable

from .base import GeocoderAdapter
from .dawa import DawaAdapter
from .geoapify import GeoapifyAdapter
from .private_profiles import profile_by_id


ADAPTER_FACTORIES: dict[str, Callable[[], GeocoderAdapter]] = {
    "dawa": DawaAdapter,
    "geoapify": GeoapifyAdapter,
}


def get_adapter(provider_id: str, *, au_npi_pilot: bool = False,
                private_source_profile_id: str | None = None) -> GeocoderAdapter:
    try:
        if private_source_profile_id is not None:
            if provider_id != "geoapify":
                raise ValueError("private source profiles require Geoapify")
            profile = profile_by_id(private_source_profile_id)
            if profile is None:
                raise ValueError("private source profile is not enabled")
            return GeoapifyAdapter(country_code=profile["country_code"].lower(),
                                   private_source_profile=True)
        if au_npi_pilot:
            if provider_id != "geoapify":
                raise ValueError("AU NPI pilot requires Geoapify")
            return GeoapifyAdapter(country_code="au", pilot_auto_display=True)
        return ADAPTER_FACTORIES[provider_id]()
    except KeyError as error:
        raise ValueError(f"No adapter registered for provider {provider_id}") from error
