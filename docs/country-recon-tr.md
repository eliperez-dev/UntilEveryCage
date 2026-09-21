# Turkey source reconnaissance

Status: metadata-only reconnaissance; no facility rows, raw exports, coordinates, traceability data, operational details, or personal data retained.

## Scope and safety

Turkey is not present in the registry. Official sources identify approved food/slaughterhouse lists, livestock systems, environmental services, company registration, and recurring animal-production statistics. Fully automated acquisition through validation, quarantine, transformation, and ingestion is required eventually, but acquisition is gated until contracts, terms, privacy, access controls, and safety are verified. Do not bypass authentication, payment, CAPTCHA, robots, or technical restrictions. Missing/stale records are not closure; do not geocode during reconnaissance.

## Candidate inventory

| ID | Authority / scope | Verified route | Format/cadence | Disposition |
|---|---|---|---|---|
| `tr.tarim.approved-food` | Ministry of Agriculture and Forestry; approved/registered food businesses and slaughterhouses | [Slaughterhouses](https://www.tarimorman.gov.tr/Konular/Hayvancilik/hayvan-refah%C4%B1-kimliklendirme-ve-i%C5%9Fletme-onay/kesimhaneler), [food control](https://www.tarimorman.gov.tr/GKGM/Menu/90/Gida-Ve-Yem-Kontrol) | Official pages advertise lists/searches; exact export, schema, IDs, cadence, licensing, and privacy not pinned | Partial; blocked |
| `tr.tarim.livestock-systems` | Ministry animal registration, HIBS, TURKVET/KKKS and farm/livestock systems | [Livestock services](https://www.tarimorman.gov.tr/HAYGEM/Menu/2/Hayvancilik), [animal systems](https://www.tarimorman.gov.tr/GKGM/Sayfalar/Detay.aspx?TermId=23f6df2f-b835-4924-8e6c-97fc71cb8bee) | Government systems are described; public API/export and sensitivity boundary not verified | Partial; blocked |
| `tr.cevre.environment-permits` | Ministry of Environment, Urbanization and Climate Change; environmental permits/EIA | [Ministry portal](https://csb.gov.tr/) | Service/register discovery only; exact permit/EIA API, geometry, cadence, license, and privacy not pinned | Partial; blocked |
| `tr.mersis.organizations` | Ministry of Trade MERSIS central company registry | [MERSIS login](https://mersis.ticaret.gov.tr/Portal/KullaniciIslemleri/GirisIslemleri) | Account-based service; no automated bulk route verified; do not bypass access controls | Partial; blocked |
| `tr.tuik.animal-statistics` | TurkStat aggregate animal production, slaughter, livestock, and meat statistics | [Animal production 2025](https://veriportali.tuik.gov.tr/en/press/58015), [red meat 2025](https://veriportali.tuik.gov.tr/en/press/58168) | Recurring official releases with metadata; exact API/table IDs, revision policy, licensing, and suppression rules not pinned | Partial; not run; aggregate-only |
| `tr.tarim.inspections-enforcement` | Ministry official controls, food/feed enforcement, and any public animal-use evidence | [Official controls](https://www.tarimorman.gov.tr/Konular/Gida-Ve-Yem-Hizmetleri/Gida-Hizmetleri/Resmi-Kontroller) | Dated notices/services; no stable event or experimentation master verified | Partial; blocked |

## Automation and release gates

Pin exact authorized endpoints/downloads, formats/schema fingerprints, pagination, stable IDs/lifecycle semantics, freshness/cadence, attribution/license, rate limits, privacy/retention, and location-safety rules before any run. Hash and quarantine snapshots, validate them, retain provenance privately, and ingest only a reviewed safe projection. Sensitive farm/facility locations, proprietor identity, traceability records, or vulnerable operational details stop the run and are escalated.

## Recommendation

Turkey is not ingestion-ready. TurkStat aggregate releases are the lowest-risk candidate. Ministry lists and livestock systems remain blocked pending machine contracts and safety review; MERSIS must not be scraped around login or payment controls. Recommend the next unreconned nearby country after inventory check: Cyprus.
