# Until Every Cage is Empty

An independent, open-source map of the infrastructure of animal exploitation.

[Original website](https://untileverycage.org/) ·
[V2 on Render](https://untileverycage.onrender.com/) ·
[Documentation](docs/README.md) · [Current roadmap](docs/PRODUCT-READINESS.md)

## V2

V2 uses Svelte/TypeScript and MapLibre, served by a Rust/Axum API backed by
PostgreSQL/PostGIS. It provides a map, database search, facility pages,
source-backed and inferred connections, dated datasets, exports and contribution intake.

The legacy vanilla-JavaScript/Leaflet application remains in `static/` during
the transition. It is a migration reference, not the V2 frontend to edit.
Country coverage and launch readiness are recorded in the roadmap and source
inventory, not inferred from the legacy datasets.

## Development

Start with [AGENTS.md](AGENTS.md), [ETHICS.md](docs/ETHICS.md),
[VISION.md](docs/VISION.md), then [the documentation hub](docs/README.md).
For setup, use [development.md](docs/development.md); for frontend commands,
[frontend/README.md](frontend/README.md); for source work,
[pipeline/ONBOARDING.md](pipeline/ONBOARDING.md).

```powershell
python scripts/dev.py --help
python scripts/dev.py --json doctor
```

Use the approved real-data baseline for data-backed acceptance. Keep raw source
rows, private inputs and credentials outside Git. Do not start or reset a
database without checking the development instructions and exact target.

## Contribute

Use the site's Contribute forms for facility tips, evidence, corrections,
duplicates and privacy/removal requests. Software issues and code contributions
can use [GitHub](https://github.com/eliperez-dev/UntilEveryCage).
Private concerns can be sent to **untileverycageproject@protonmail.com**.
Do not put sensitive evidence or credentials in public issues.

## Licences and credits

Software is [AGPL-3.0-or-later](LICENSE). Project compilation rights use
[CC BY-NC-SA 4.0](DATA_LICENSE); upstream records, dependencies and assets retain
their own terms and attribution. See [source rights](docs/architecture/source-rights-decisions.md)
for scope and recorded decisions.

Counter adapted from [ADAPTT](https://www.adaptt.org/).
Inspired by [Final Nail](https://finalnail.com/).
