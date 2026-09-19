# Visitor privacy and retention inventory

This inventory is a deployment gate. The repository observations below were
made from the checked-in application on 2026-09-15; they do not establish what
the deployed host, CDN, reverse proxy, error reporter, or providers retain.
Those settings require a deployment-specific browser/network and
infrastructure audit before a privacy statement or affected v2 capability is
published.

| Surface/provider evidence | Data sent | Identifier/log fields | Retention/access owner | Status |
|---|---|---|---|---|
| V2 API (`src/main.rs`, frontend V2 clients) | Profile, filters, pagination, and cursor in the request URL | Application/proxy/provider request logs are not configured in this repository | Maintainer to assign | Code shape observed; deployment logging unknown |
| Legacy API origin (`static/modules/constants.js`) | Browser requests to the configured Railway API, including legacy endpoints | Railway/web-server logs and retention are unknown | Hosting operator/provider to confirm | Legacy surface remains an audit item |
| Legacy Leaflet CDN (`static/index.html`) | Browser IP/referrer/user-agent and asset request metadata; Leaflet JS/CSS | unpkg retention/control is unknown | Hosting operator/provider to confirm | External dependency present in legacy page |
| Legacy marker assets (`static/modules/constants.js`) | Browser asset requests to raw GitHub and cdnjs | Provider request metadata/retention unknown | Hosting operator/provider to confirm | External dependency present in legacy page |
| Legacy map tiles (`static/modules/MapManager.js`) | Tile requests containing the map tile coordinates/viewport; no device geolocation code observed | OpenStreetMap and ArcGIS provider logging/retention unknown | Hosting operator/provider to confirm | Must be audited or removed before a visitor-data claim |
| External directions (`static/modules/popupBuilder.js`) | A user click can send a displayed latitude/longitude to Google Maps | Google retention/control outside project control | Visitor chooses provider; project must disclose | Legacy click-through disclosure required |
| Geocoding pipeline (`pipeline/geocoding`, `pipeline/config`) | Restricted operational address queries only; not visitor location | Restricted pipeline logs; provider retention and deletion limits unresolved | Pipeline maintainer | Development-only provider gate |
| Analytics/error reporting | No analytics or error-reporting integration found by repository search | Deployment/CDN/provider behavior still unknown | Maintainer to audit | No “no tracking” or “no logging” claim follows |
| Application diagnostics (`/health/diagnostics`) | No request payload, address, path, or forwarded address in response | Returns coarse control status only | Service operator | Implemented and covered by Rust contract; host logs still unknown |

Repository search found no `navigator.geolocation` use. Visitor location entry is
optional and device geolocation must not be required. Precise visitor
locations and home addresses must not enter shared links, analytics, or public
diagnostics. Unknown provider retention, CDN behavior, proxy configuration,
and log deletion are unresolved deployment limitations, not evidence of no
logging. The legacy page's external map/directions requests are separate from
the Svelte V2 preview's blank local map background and must not be conflated.

Before launch, capture a browser network trace for each supported route and
the reverse-proxy/hosting/error-reporting configuration. Record actual request
fields, access owner, retention/deletion behavior, and any provider control
limits here. A missing analytics script is not proof that infrastructure logs
are absent.
