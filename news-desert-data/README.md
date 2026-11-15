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
python scripts/local_elections.py  # local election turnout by year; needs data/raw/leh/leh_2021..2025.xlsx
python scripts/pinf.py            # PINF news layers; needs data/raw/pinf_2025.xlsx (not redistributed)
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
- CES `_sig` fields use the DCMS rule: a district is above or below England only when its 95% confidence interval does not overlap England's.
- Ofcom OA percentages are converted to premises counts, summed, then turned back into percentages.

## Published layers

Live on GIS-4-Schools (folder *News desert programme*, owner Si_Claudius), shared publicly, query-only, Web Mercator. Published 15 November 2026 from data build v1.0.0.

| Layer | Item | Feature service |
| --- | --- | --- |
| Districts (tier 1) | [6b694dd4…](https://gis-4-schools.maps.arcgis.com/home/item.html?id=6b694dd490694ee2a0e4c4b3f76b63d8) | `https://services4.arcgis.com/HNLEA4GfnbCFQZGa/arcgis/rest/services/news_desert_districts_england/FeatureServer/0` |
| Neighbourhoods, LSOA (tier 2) | [0f15224a…](https://gis-4-schools.maps.arcgis.com/home/item.html?id=0f15224ae9f443359cdeb1cc9c609ddb) | `https://services4.arcgis.com/HNLEA4GfnbCFQZGa/arcgis/rest/services/news_desert_lsoa_england/FeatureServer/0` |
| GE 2024 turnout by constituency | [ba8ea457…](https://gis-4-schools.maps.arcgis.com/home/item.html?id=ba8ea457f54a49f7936d5e3a35ab10ba) | `https://services4.arcgis.com/HNLEA4GfnbCFQZGa/arcgis/rest/services/news_desert_ge2024_turnout_england/FeatureServer/0` |

The source GeoJSON items sit in the same folder, unshared, so the layers can be overwritten in place. The built files, field aliases and item descriptions are on the `news-desert-data` branch (`publish_manifest.json`).

### Local election turnout by year (public)

Built by `scripts/local_elections.py` from the House of Commons Library / Elections Centre Local Elections Handbook datasets for May 2021 to May 2025 (ward-level electorate and turnout, Open Parliament Licence). The 2026 dataset was not yet published in November 2026.

Layer: [7433402d…](https://gis-4-schools.maps.arcgis.com/home/item.html?id=7433402db5db430fb87ba264256aa89b), `https://services4.arcgis.com/HNLEA4GfnbCFQZGa/arcgis/rest/services/news_desert_local_election_turnout_england/FeatureServer/0`

Districts vote in different years, so the year is in every field: `le2021_turnout` … `le2025_turnout` (with `_type` and `_electorate`), `le_latest_turnout` + `le_latest_year` + `le_latest_type` + `le_latest_label`, and `le_own_*` (excluding county council elections). `le_relative_turnout` is each election's gap to the same-year, same-tier median, averaged, for comparing districts that voted in different years. County divisions are assigned to their district. Version: `LE_VERSION` (1.0.0). The web map (v1.1.0) has one layer per year.

`analysis/correlate.py` is the district-level correlation analysis of PINF provision against the supplementary data.

### PINF local news layers (private)

Built by `scripts/pinf.py` from the PINF Local News Database, December 2025 (`data/raw/pinf_2025.xlsx`, supplied by hand). PINF states no licence for this data, so the file and its outputs are **not** committed here or on the `news-desert-data` branch, and the layers stay private until PINF confirms reuse terms.

| Layer | Item | Notes |
| --- | --- | --- |
| Local news provision by district | [fb047184…](https://gis-4-schools.maps.arcgis.com/home/item.html?id=fb04718405114d79ad16ee16a5ee633b) | 296 districts; PINF counts, outlets per 100,000, desert/dryland/oasis class, monopoly, launch/closure flags |
| Local news outlets | [1d0fc1a5…](https://gis-4-schools.maps.arcgis.com/home/item.html?id=1d0fc1a5f24a4d6fb0ee4561b8ce7194) | 968 outlets as 1,040 points, one per district served |
| Web map | [75957fe0…](https://gis-4-schools.maps.arcgis.com/home/item.html?id=75957fe0270641aea2ba352a049d5d13) | PINF layers plus IMD 2025 and GE 2024 turnout context |

PINF's `LOCATION` is often a publisher's office (only 58% of English outlets sit inside a district they cover), so each outlet point is drawn in the district it serves: at `LOCATION` when that is inside the district, otherwise on a grid near the district centre. The `position` field records which. PINF version: `PINF_VERSION` in `scripts/pinf.py` (1.0.0).

## Licences

OGL v3.0 (ONS, MHCLG, DCMS, Ofcom) and Open Parliament Licence v3.0 (House of Commons Library). Contains OS data © Crown copyright and database right 2026.
