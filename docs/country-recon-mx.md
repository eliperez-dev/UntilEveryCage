# Mexico source reconnaissance

Status: sanitized metadata handoff; no row-level records or downloaded artifacts are retained here. Reconnaissance is not publication approval or evidence of a healthy pipeline. Observed 2026-10-25 under `docs/ETHICS.md`.

## Sources and findings

### INEGI DENUE

Official documentation: <https://www.inegi.org.mx/servicios/api_denue.html>.

INEGI documents JSON endpoints under `https://www.inegi.org.mx/app/api/denue/v1/consulta/`, including `Buscar`, `Ficha`, `Nombre`, `BuscarEntidad`, `BuscarAreaAct`, `BuscarAreaActEstr`, and `Cuantificar`. Responses may include identification, SCIAN activity, size stratum, administrative location, coordinates, stable `Id`/`CLEE`, geographic keys, and establishment start date.

DENUE is a broad economic directory, not proof of TIF certification, operating status, animal treatment, or completeness. The current INEGI catalog is <https://www.inegi.org.mx/rnm/index.php/catalog/1103>; it documents data to March 2025 and SCIAN 2023. The linked 2025 data dictionary is <https://www.inegi.org.mx/rnm/index.php/catalog/1103/download/34478>, and the official SCIAN lookup is <https://www.inegi.org.mx/app/scian/>. The official download page is <https://www.inegi.org.mx/app/descarga/?ti=6>; its instructions describe broad national files. INEGI's FAQ at <https://www.inegi.org.mx/app/mapa/denue/PreguntasF/PreguntasF.aspx> says selected-result ZIP generation requires CAPTCHA. The API documentation at <https://www.inegi.org.mx/servicios/api_denue.html> requires a registered token; none is available for this work. No national multi-million-row download or CAPTCHA flow was attempted. Animal-agriculture candidates require explicit reviewed SCIAN mapping rather than free-text matching. Precise addresses, coordinates, phones, emails, and websites require field minimization and privacy review before any publication.

### SENASICA TIF

Official pages: <https://www.gob.mx/senasica/acciones-y-programas/dictaminacion-y-certificacion> and <https://www.gob.mx/senasica/acciones-y-programas/establecimientos-tipo-inspeccion-federal-tif>.

The official pages define TIF facilities as regulated installations where animals may be slaughtered and animal-origin goods processed, packed, refrigerated, or industrialized. A public ArcGIS FeatureServer route was verified at <https://dj.senasica.gob.mx/mapas/rest/services/Hosted/MP_Infraestructura/FeatureServer/0>. Its metadata exposes only `fid`, `estado`, and `municipio`; the layer is named “Establecimientos TIF a nivel estado” and its `fid` is an OID, not a demonstrated stable facility key. Its state-level point geometry is not suitable as facility-level records.

The official certification page is <https://www.gob.mx/senasica/acciones-y-programas/dictaminacion-y-certificacion>; the current directory record is <https://www.gob.mx/senasica/documentos/directorio-de-establecimientos-tif-del-25-de-marzo-de-2022?state=published>. Search indexing showed a directory publication on 2026-09-07 and certification-page update on 2026-06-30. On 2026-10-25, ordinary HTTPS GET to the official directory page returned anti-bot “Challenge Validation” HTML; no challenge was bypassed. The specifically cited 2025 attachment <https://www.gob.mx/cms/uploads/attachment/file/1025388/DIRECTORIO_TIF_03-11-2025.pdf> returned HTTP 404; cited 2024 attachment URLs using IDs 952269 (<https://www.gob.mx/cms/uploads/attachment/file/952269/DIRECTORIO_TIF_21-10-2024.pdf>) and 889291 (<https://www.gob.mx/cms/uploads/attachment/file/889291/DIRECTORIO_TIF_25-03-2024.pdf>) also returned HTTP 404. The current linked artifact's exact attachment URL, schema, stable identifier, scope, cadence, and terms therefore remain unresolved. A secondary 2024 PDF mirror must not substitute for a current official release.

### DGSIAP/SIAP

Landing pages: <https://nube.agricultura.gob.mx/datosAbiertos/>, <https://nube.agricultura.gob.mx/datosAbiertos/Agricola.php>, and <https://nube.agricultura.gob.mx/datosAbiertos/Pecuario.php>.

These annual municipal/state production series provide agricultural context, not named farms, slaughterhouses, or facility coordinates. The portal describes reuse subject to attribution and continuity/share-alike-style conditions. A bounded 2025 download attempt failed with connection refusal; no bytes, hash, or artifact are claimed.

## Readiness block (last checked 2026-10-25 UTC)

| Source | Source verification | Private acquisition | Adapter / validation | Terms, privacy, publication | Blocker | Next action |
|---|---|---|---|---|---|---|
| DENUE | Official API docs, 2025 INEGI catalog and data dictionary verified | API not used: no token. National bulk route is broad; selected-result route requires CAPTCHA; neither was used to acquire rows | Not implemented or tested | Free-use terms, field minimization, coordinate policy, and completeness need review | Token required for API; selective download is CAPTCHA-gated; a narrow code set and bounded-size acquisition route still need confirmation | Obtain authorized token or an ordinary direct activity-filtered extract; confirm SCIAN 2023 codes, terms, size, and field handling |
| SENASICA/TIF | Official TIF page listing and ArcGIS metadata verified; current full directory not verifiable | Official landing returns challenge HTML; cited 2025 and 2024 PDF URLs return 404; no artifact captured | Not implemented; GIS layer is state-level with no facility identifier | Government origin only; terms and field privacy unresolved | Need accessible current official attachment plus schema, key, scope, and terms | Retry from normally authorized access or use a current official attachment URL; no challenge bypass or secondary mirror |
| DGSIAP/SIAP | Official landing pages and current release listing verified | Download attempted and blocked; no artifact retained | Not implemented; source is not a facility registry | Aggregate-only role; attribution/continuity conditions need confirmation | Transport failure and no dictionary/hash | Retry from approved environment and capture artifact provenance privately |

## Open verification gaps

- Confirm DENUE token quotas, terms, reviewed SCIAN 2023 mapping, and a safely bounded acquisition path.
- Obtain the currently linked SENASICA TIF attachment through ordinary access, then verify its schema and compare with the state-level GIS layer.
- Preserve source identifiers and original values; do not infer closure from disappearance.
- Obtain maintainer decisions for privacy eligibility, project approval, and publication profile. Government origin alone does not establish approval.
