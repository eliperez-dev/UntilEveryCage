"""Canada adapter compatibility entry point for the shared source queue."""

from pipeline.geocoding.source_queue import build_geocode_queue as _build_shared_queue


def build_geocode_queue(records, artifact, output_dir):
    return _build_shared_queue(records, artifact, output_dir, country_name="Canada")
