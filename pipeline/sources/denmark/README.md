# Denmark source entry points

Denmark-specific commands are exposed from this directory so country logic has
a stable home as more sources are added. The historical commands under
`pipeline/scripts/stages/` and `pipeline/run-denmark-pipeline.py` remain valid
compatibility paths and retain their argument behavior.

The current launchers intentionally delegate to the established implementations
to avoid duplicating acquisition, parsing, normalization, classification, and
validation logic. New source-specific behavior should be added here first;
generic release, geocoding, restriction, and maintenance commands remain in
their shared locations.

Example:

```powershell
python pipeline/sources/denmark/run-denmark-pipeline.py --help
```
