# News desert supplementary data pipeline

Builds two ArcGIS Online hosted feature layers for England, plus a supporting constituency layer:

| Layer | Geography | Features |
| --- | --- | --- |
| Tier 1 `nd_lad` | Local authority districts, May 2025 (BGC) | 296 |
| Tier 2 `nd_lsoa` | LSOA 2021 (ONS BFE V10, generalised to ~15 m) | 33,755 |
| Supporting `nd_pcon` | Westminster constituencies, July 2024 (BGC) | 543 |

Data build **v1.0.0**. Each source carries its own version in `scripts/common.py`; bump it when its download, parsing or maths changes.

## Run

```bash
pip install pandas requests openpyxl odfpy arcgis
python scripts/fetch.py           # downloads into data/raw (cached)
python scripts/inspect_raw.py     # optional: dump headers of every download to data/raw/_inspect.txt
python scripts/build.py           # writes data/out/*.geojson, *.csv, fields.json
python scripts/publish.py --profile g4s-publisher   # publish or overwrite, share publicly
```

`build.py` skips any source whose files are missing and lists it under `warnings` in `data/out/fields.json`.

## Sources

| Key | Source | Geography used |
| --- | --- | --- |
| iod2025 | MHCLG IoD 2025: ArcGIS services (IMD rank/decile, district ranks) + File 7 CSV (domain deciles, scores) | LSOA, LAD |
| ruc2021 | ONS Rural Urban Classification 2021 (with LSOA boundaries; LAD 2024 lookup) | LSOA, LAD |
| census2021 | ONS Census 2021 via Nomis bulk: TS001, TS003, TS006, TS007A, TS021, TS037, TS066, TS067 | LSOA, summed to LAD |
| mye2025 | ONS mid-2025 population estimates (MYE5 density/population, MYE2 single-year age) | LAD |
| ces2526 | DCMS Community and Engagement Survey 2025/26 ODS tables | LAD |
| ge2024 | House of Commons Library GE 2024 results (turnout = valid votes ÷ electorate) | PCON; LSOA via best fit; LAD estimate |
| business2026 | ONS UK business: activity, size and location 2026 | LAD |
| ofcom2026 | Ofcom Connected Nations Spring 2026: fixed OA coverage summed to LSOA/LAD; LA full fibre and mobile | LSOA, LAD |

Business demography (births, deaths, survival) is not included yet.

## Method notes

- District vintage is May 2025. Sources keyed on 2023/2024 codes recode Barnsley (E08000016 → E08000038) and Sheffield (E08000019 → E08000039).
- Census counts are summed from LSOA to district before rates are calculated. District density = residents ÷ (sum of LSOA areas implied by TS006).
- GE 2024 district turnout is an estimate: each LSOA takes its best-fit constituency's turnout, weighted by residents aged 16+.
- CES `_sig` fields compare each district's 95% confidence interval with the England figure.
- Ofcom OA percentages are converted to premises counts, summed, then turned back into percentages.

## Licences

OGL v3.0 (ONS, MHCLG, DCMS, Ofcom) and Open Parliament Licence v3.0 (House of Commons Library). Contains OS data © Crown copyright and database right 2026.
