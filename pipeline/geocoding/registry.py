from collections.abc import Callable

from .base import GeocoderAdapter
from .dawa import DawaAdapter
from .geoapify import GeoapifyAdapter


ADAPTER_FACTORIES: dict[str, Callable[[], GeocoderAdapter]] = {
    "dawa": DawaAdapter,
    "geoapify": GeoapifyAdapter,
}


def get_adapter(provider_id: str, *, au_npi_pilot: bool = False) -> GeocoderAdapter:
    try:
        if au_npi_pilot:
            if provider_id != "geoapify":
                raise ValueError("AU NPI pilot requires Geoapify")
            return GeoapifyAdapter(country_code="au", pilot_auto_display=True)
        return ADAPTER_FACTORIES[provider_id]()
    except KeyError as error:
        raise ValueError(f"No adapter registered for provider {provider_id}") from error
