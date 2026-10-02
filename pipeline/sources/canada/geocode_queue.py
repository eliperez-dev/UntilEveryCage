"""Canada adapter compatibility entry point for the shared source queue."""

from pipeline.geocoding.source_queue import build_source_location_queue


def build_geocode_queue(records, artifact, output_dir):
    return build_source_location_queue(records, artifact, output_dir)
