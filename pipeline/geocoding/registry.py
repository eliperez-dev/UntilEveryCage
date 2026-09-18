from collections.abc import Callable

from .base import GeocoderAdapter
from .dawa import DawaAdapter
from .geoapify import GeoapifyAdapter


ADAPTER_FACTORIES: dict[str, Callable[[], GeocoderAdapter]] = {
    "dawa": DawaAdapter,
    "geoapify": GeoapifyAdapter,
}


def get_adapter(provider_id: str) -> GeocoderAdapter:
    try:
        return ADAPTER_FACTORIES[provider_id]()
    except KeyError as error:
        raise ValueError(f"No adapter registered for provider {provider_id}") from error
