# Mexico source reconnaissance

Status: sanitized metadata handoff; no row-level records or downloaded artifacts are retained here. Reconnaissance is not publication approval or evidence of a healthy pipeline. Observed 2026-09-14 UTC under `docs/ETHICS.md`.

## Sources and findings

### INEGI DENUE

Official documentation: <https://www.inegi.org.mx/servicios/api_denue.html>.

INEGI documents JSON endpoints under `https://www.inegi.org.mx/app/api/denue/v1/consulta/`, including `Buscar`, `Ficha`, `Nombre`, `BuscarEntidad`, `BuscarAreaAct`, `BuscarAreaActEstr`, and `Cuantificar`. Responses may include identification, SCIAN activity, size stratum, administrative location, coordinates, stable `Id`/`CLEE`, geographic keys, and establishment start date.

DENUE is a broad economic directory, not proof of TIF certification, operating status, animal treatment, or completeness. Animal-agriculture candidates require explicit SCIAN mapping and review rather than free-text matching. The API requires a registered token; exact quota/rate-limit terms remain unresolved. Its precise addresses, coordinates, phones, emails, and websites require field minimization and privacy review before any publication.

### SENASICA TIF

Official pages: <https://www.gob.mx/senasica/acciones-y-programas/dictaminacion-y-certificacion> and <https://www.gob.mx/senasica/acciones-y-programas/establecimientos-tipo-inspeccion-federal-tif>.

The official pages define TIF facilities as regulated installations where animals may be slaughtered and animal-origin goods processed, packed, refrigerated, or industrialized. A public ArcGIS FeatureServer route was verified at <https://dj.senasica.gob.mx/mapas/rest/services/Hosted/MP_Infraestructura/FeatureServer/0>. Its observed metadata exposed only `fid`, `estado`, and `municipio`; it must not be assumed to equal the full directory or to provide certification details.

The current full directory artifact, fields, stable identifier, publication date, cadence, and redistribution terms remain unresolved. A secondary 2024 PDF mirror was noted during reconnaissance but must not substitute for a current official release.

### DGSIAP/SIAP

Landing pages: <https://nube.agricultura.gob.mx/datosAbiertos/>, <https://nube.agricultura.gob.mx/datosAbiertos/Agricola.php>, and <https://nube.agricultura.gob.mx/datosAbiertos/Pecuario.php>.

These annual municipal/state production series provide agricultural context, not named farms, slaughterhouses, or facility coordinates. The portal describes reuse subject to attribution and continuity/share-alike-style conditions. A bounded 2025 download attempt failed with connection refusal; no bytes, hash, or artifact are claimed.

## Readiness block (last checked 2026-09-14 UTC)

| Source | Source verification | Private acquisition | Adapter / validation | Terms, privacy, publication | Blocker | Next action |
|---|---|---|---|---|---|---|
| DENUE | Official documentation and API URL patterns verified | Not performed; no token/account | Not implemented or tested | Token terms, contact-field minimization, coordinate policy, and completeness unresolved | No token and SCIAN mapping unresolved | Maintainer-approved bounded API sample or bulk metadata check with URL, timestamp, hash/size where applicable |
| SENASICA/TIF | Official TIF pages and public ArcGIS metadata verified; full directory not verified | Not performed; no row-level query/account | Not implemented; layer completeness and identifiers unknown | Government origin only; precise locations/contact fields need privacy review; terms unresolved | Current directory, schema, cadence, certification semantics | Obtain current official directory privately and compare with GIS layer |
| DGSIAP/SIAP | Official landing pages and current release listing verified | Download attempted and blocked; no artifact retained | Not implemented; source is not a facility registry | Aggregate-only role; attribution/continuity conditions need confirmation | Transport failure and no dictionary/hash | Retry from approved environment and capture artifact provenance privately |

## Open verification gaps

- Confirm DENUE token quotas and bulk-download terms.
- Obtain and verify the current SENASICA TIF directory and compare it with the GIS layer.
- Preserve source identifiers and original values; do not infer closure from disappearance.
- Obtain maintainer decisions for privacy eligibility, project approval, and publication profile. Government origin alone does not establish approval.
