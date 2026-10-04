# Netherlands NVWA approved-food source adapter (v0)

Status: implemented and live-acquisition verified for private candidate preview only. No public release, deployment, or publication is authorized. The broader country source reconnaissance remains in [`../../country-recon-nl.md`](../../country-recon-nl.md); the current row-free acquisition evidence is [`nl-nvwa-approved-food-v0.json`](../../../data/manifests/nl-nvwa-approved-food-v0.json).

## Source and coverage

The source is the NVWA approved slaughterhouse/cutting-establishment viewer and its current control XML plus Berichtenboek SOAP service. The adapter follows only the eight current `overig_303` through `overig_310` lists. This is not a complete Netherlands facility census. The adapter version is `nvwa-approved-food-v0`; its normalized observation schema is `nvwa-approval-observations-v1`.

The SOAP request is a bounded `zoekBedrijf` POST (one-second delay between calls, maximum 10,000 rows per page, 100 pages per list, 8 MiB per response). The four list-filter collection values are sent as empty collection elements: sending them as `xsi:nil` causes the current service to fail with an Oracle uninitialized-collection fault. All SOAP pages and the control XML are retained only under the ignored private `data/raw/nl.nvwa.approved-food/` tree. A row-free SHA-256/size/count manifest is committed separately.

## Identity, observations, and normalization

`erkenningsnummer` is the source-qualified recognition identifier. Each SOAP record remains a distinct approval/activity/product/species observation, including repeated recognition numbers and identical duplicate rows. Stable row keys include the list code, recognition number (or a quarantine marker), a field digest, and a duplicate ordinal. There is no name-only collapse or cross-list summed facility count.

The live capture on 2026-10-04 returned 1,259 XML observations across the eight lists; all 1,259 normalized and none quarantined for a missing recognition number. This is a count of observations, not 1,259 facilities. Unique recognition numbers are reported separately within each list. The service's `cvgTotal`/`cvgReturned` values match its deduplicated result count and can be lower than XML observation count (for example, 115 versus 118 in `overig_303`). Both are retained as distinct diagnostics.

Every source field is retained in restricted parsed evidence. The normalized record keeps address, postcode, and place only under `private_location_evidence`, including `address_lines`, `address`, optional `postal_code` and `city`, and `country_code: NL`. No coordinates are supplied by NVWA. Source-scope eligibility and privacy screening are separate; the source address may enter the separately approved private Netherlands geocoding profile after its privacy filter. Acquisition itself makes no geocoder calls. No source absence or missing `opheffingsdatum` is interpreted as closure.

## Rights and release controls

The current NVWA copyright page says site content is CC0 unless an item states an exception. The package uses text/control data only, does not use logos or house style, and must not imply NVWA endorsement. Privacy and third-party rights still apply. The bounded capture is restricted local staging; candidate handoff is human-gated, `release_state` remains `not-created`, and map/API/export publication remains disabled.

## Running the source lane

From the repository root, with the standard gate environment available:

```powershell
& .\target\standard-gate-venv\Scripts\python.exe -m pipeline.sources.netherlands.nvwa_approved_food.refresh `
  --fetch --run-dir target/nvwa-nl-live --output-root data/raw --run-id <new-run-id>
```

To process an already retained private bundle without another network request, pass its `bundle-manifest.json` using `--bundle <path>` instead of `--fetch`. Use a new run ID for each live acquisition; the adapter refuses accidental raw-artifact replacement. Focused synthetic contract tests are:

```powershell
& .\target\standard-gate-venv\Scripts\python.exe -m unittest pipeline.sources.netherlands.nvwa_approved_food.test_adapter -v
```

The adapter bridge for the shared runner is `pipeline.sources.netherlands.nvwa_approved_food.refresh.NvwaRefreshAdapter`. Root integration owns its common registration and private import-preview invocation. Do not directly write candidate rows into a retained database or promote a release.
