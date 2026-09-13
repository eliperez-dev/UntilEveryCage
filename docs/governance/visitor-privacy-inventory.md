# Visitor privacy and retention inventory

This inventory is a deployment gate. It must be updated from browser/network and infrastructure observations before publishing a privacy statement.

| Surface | Data sent | Identifier/log fields | Retention/access owner | Status |
|---|---|---|---|---|
| V2 API | Query filters and pagination only | Web-server and provider logs must be confirmed | Maintainer to assign | Verify in deployment |
| Map tiles/assets | Browser requests and approximate map viewport | Provider policy/configuration must be confirmed | Maintainer to assign | Verify in deployment |
| Geocoding pipeline | Restricted operational queries, never visitor location | Restricted pipeline logs | Pipeline maintainer | Development-only provider gate |
| Error/reporting services | Must be confirmed from deployment configuration | Must exclude precise visitor location and source payloads | Maintainer to assign | Not claimed until audited |

Visitor location entry is optional. Device geolocation must not be required. Precise visitor locations and home addresses must not enter shared links, analytics, or public diagnostics. Unknown provider retention or logging behavior is an unresolved deployment limitation, not evidence of no logging.
