# Live Country Rehearsal — 2026-09-15

Owner-authorized private/test-only rehearsal on branch `codex/live-country-rehearsal`, baseline `87fde11`. The artifacts were observed on 2026-09-16 UTC because the run crossed midnight Pacific. Raw, restricted, staging, and candidate-handoff payloads remain ignored local files; no release, public API, map, export, cache, or history surface was created or promoted.

## Result

Ten source profiles across the strongest non-US country routes completed private candidate integration. Every profile has provenance evidence, parsed/normalized/quarantined output, source-health evidence, and a human review gate. Geocoding was disabled everywhere. “Not observed” is retained as a non-closure state.

| Profile | Acquisition and source date | Input / normalized / quarantined | Artifact bytes / SHA-256 | Automation and private state |
|---|---|---:|---|---|
| `dk.smiley` | Live Find Smiley fetch; retrieved `2026-09-16T06:29:21Z`; HTTP Last-Modified `2026-09-16T06:28:34Z` | 58,773 / 58,773 / 0 | 59,835,715 / `4dd3e9c703cdd206b0a4e620f57f530f55325cefb0048eb9e25a973ce24c450e` | Full parse → normalize → classify → validate → geocode-queue pipeline; 61 validation finding records and 58,773 unresolved coordinates; private handoff emitted |
| `fr.dgal.section-i` | Live DGAL list fetch; retrieved `2026-09-16T06:29:12Z`; file Last-Modified `2026-09-16T02:21:51Z` | 1,448 / 1,448 / 0 | 204,211 / `b1171561865ab664ddf18adeeed7b6993224cc2275277fdaa6e4d411dd062649` | Candidate-ready; bilingual composite headers supported; private handoff/review packet emitted |
| `fr.dgal.section-ii` | Live DGAL list fetch; retrieved `2026-09-16T06:29:12Z`; file Last-Modified `2026-09-16T02:22:14Z` | 1,068 / 1,068 / 0 | 136,654 / `6c2d943024a27baa2113bb60eef6dad132d3f96ea1b001fb60ba40ac0b406fb6` | Candidate-ready; bilingual composite headers supported; private handoff/review packet emitted |
| `it.853-2004` | Official catalogue/CSV fetched with bounded `curl.exe` fallback after Python TLS failure; retrieved `2026-09-16T06:37:05Z`; source date `2026-09-15` | 47,370 / 41,844 / 5,526 | 49,927,230 / `2d665d355de522ff7a8f61f23c4a7eb722d6e30d41e099c557001db5aa0b266b` | Candidate-ready; 5,526 `ambiguous_repeated_recognition_activity`; zero-change delta-ready rerun; handoff/review packet emitted |
| `de.locations` | Assisted BVL portal export using the sanitized synthetic BLtU fixture; retrieved `2026-09-16T06:30:00Z`; effective date unknown | 3 / 1 / 2 | 627 / `cde8813830ee278031184d4771bb81e026c655853cd358f17642ef188352f96b` | Portal export URL is session/request-specific; 1 unmapped and 1 missing activity-code row; zero-change delta-ready rerun; handoff/review packet emitted |
| `be.locations` | Assisted FASFC operator + activity-code fixture pair; retrieved `2026-09-16T06:30:00Z`; effective date unknown | 5 / 3 / 2 | 679 / `a8866877ac66f555b8e79434d37ceba00f1a70adad3cbc032ff4cfdbc0a084e8` | Live operator route was inaccessible in this environment; 1 address privacy risk and 1 unresolved activity code; zero-change delta-ready rerun; pair handoff/review packet emitted |
| `ca.ontario.meat-plants` | Live Ontario CSV fetch; retrieved `2026-09-16T06:29:12Z`; HTTP Last-Modified `2026-08-06T19:04:50Z` | 460 / 460 / 0 | 130,252 / `c4edfdd415812f6a914f5fb29a9f67cf2907ea6fbfe4e09ab96eae1468002adf` | Bilingual composite headers supported; private handoff/review packet emitted; one comparison attempt failed closed on a missing prior run manifest |
| `ca.cfia.federal-meat` | Assisted CFIA fixture after direct TLS certificate failure; retrieved `2026-09-16T06:30:00Z`; effective date unknown | 3 / 2 / 1 | 404 / `f0d09d2dcc2a47f025e42fe8729fb90051171f24ba777d3b8b40879a29fcb7bf` | 1 unknown function code; private handoff/review packet emitted; no previous validated run was available |
| `fsa_approved_establishments` | Live FSA England/Wales CSV; retrieved `2026-09-16T06:38:26Z`; source snapshot `2026-09-01` | 5,342 / 4,300 / 1,042 | 1,774,417 / `d5cfec048b0f4dc4a8594b0597982f3788f10eb1b4270f9593ead8abce33b61f` | Private handoff; zero-change delta-ready rerun; 999 remarks, 31 unknown-nation, 11 address-risk, 4 duplicate-ID anomalies |
| `fss_approved_establishments` | Live FSS Scotland CSV; retrieved `2026-09-16T06:38:25Z`; source Last-Modified `2026-08-11T13:55:33Z` | 725 / 586 / 139 | 245,871 / `b95b66afb112636c09f6de401054c7ea3d11e5058f34522d900c60435a125246` | Private handoff; zero-change delta-ready rerun; 125 no-relevant-activity, 18 address-risk, 2 malformed, 2 missing-activity, 2 missing-approval anomalies |

The France, Italy, Germany, Belgium, Canada, and UK adapters now recognize the observed bilingual/composite or current source headers through explicit aliases. The Italy adapter preserves raw date text while normalizing current abbreviated Italian dates and treats source dash sentinels as unknown rather than invalid. Belgium’s row-length regression is checked per row.

## Source routes and terms

- France: official [DGAL lists index](https://fichiers-publics.agriculture.gouv.fr/dgal/ListesOfficielles/) with separate Section I and Section II files.
- Italy: official [Ministry 853/2004 dataset](https://www.dati.salute.gov.it/it/dataset/stabilimenti-italiani-gli-alimenti-di-origine-animale/) and its catalogued CSV; the separate 1069/2009 by-products scope remains excluded.
- UK: official [FSA catalogue](https://data.food.gov.uk/catalog/datasets/1e61736a-2a1a-4c6a-b8b1-e45912ebc8e3) plus the separate Scotland FSS route; OGL/attribution review remains distinct from source origin.
- Belgium: official [FASFC operator dataset](https://data.gov.be/fr/datasets/favv-afsca-operators); CC BY 4.0 attribution and reuse review remain open.
- Germany: official [BVL BLtU portal](https://www.bvl.bund.de/DE/Arbeitsbereiche/01_Lebensmittel/01_Aufgaben/05_GrenzueberschreitenderHandel/lm_grenzueberschrHandel_basepage.html); the export request is session-bound, so this rehearsal used assisted synthetic evidence.
- Canada: current [Ontario meat-plants dataset](https://data.ontario.ca/dataset/licensed-meat-plants) and separate CFIA federal route; Ontario and federal identities remain separate and no national completeness claim is made.

The owner-authorized terms record applies only to this bounded private/test-only run. It does not approve redistribution, precise coordinates, addresses, contacts, public API exposure, release promotion, or publication. Human terms, privacy, classification, completeness, coordinate precision, release, and maintainer-approval gates remain blocked.

## Rerun and release evidence

The zero-change delta-ready reruns report `added=0`, `changed=0`, `not_observed=0`, and `suppressed=0` for Italy, Germany, Belgium, FSA, and FSS. France I/II and Ontario comparison attempts failed closed because the referenced prior `run-manifest.json` was missing; they still recorded `release_promoted=false` and all public surfaces false. No failed comparison was treated as an unchanged claim.

No public release was created. Candidate handoffs are disposable private artifacts, not publication approval. The next operator actions are to obtain authorized live captures for Belgium/Germany/CFIA, repair the prior-run manifest linkage for France/Ontario comparisons, resolve Italy’s repeated identity collisions and excluded 1069 scope, review all address/coordinate and terms gates, and only then consider a separately approved disposable candidate import.
