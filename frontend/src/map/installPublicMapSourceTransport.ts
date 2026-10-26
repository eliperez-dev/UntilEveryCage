import { GeoJSONSource } from 'maplibre-gl';
import { installPublicMapTransport, type PublicTransportPrototype } from './publicMapSourceTransport';

// A pinned, source-parameter boundary; no worker actor or main source data is replaced.
installPublicMapTransport(GeoJSONSource.prototype as unknown as PublicTransportPrototype);
