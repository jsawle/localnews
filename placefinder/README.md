# Place Finder v1.0.0

Find the places mentioned in a document and show them on a map, in a summary table and as a word cloud sized by number of mentions.

Live: https://jsawle.github.io/localnews/placefinder/

- Reads Word (.docx), PDF, .txt/.md/.csv and .html files, or pasted text — all in the browser, nothing is uploaded.
- Matches text against a gazetteer of ~35,000 places (countries, states/provinces, cities and towns with 15,000+ people, continents, oceans, seas, rivers, lakes, mountains, islands, world regions, well-known volcanoes).
- Filters likely non-places (people's names, "New York Times", ordinary words at the start of a sentence) and picks between same-name places using the rest of the document ("Paris, Texas").
- Untick wrong matches, or change a match with "Which place?". Export CSV or GeoJSON (both can be added to ArcGIS Online / MapMaker maps), and PNG of the map and word cloud.

## Versions

| Part | Version |
|---|---|
| Place Finder app | 1.0.0 |
| Document reader | 1.0 |
| Place finder (matching & disambiguation) | 1.0 |
| Gazetteer data | 1.0 |
| Map | 1.0 |
| Word cloud | 1.0 |

## Data and libraries

- Natural Earth (public domain): countries, admin-1, populated places, physical features, borders.
- GeoNames (CC BY 4.0) via the all-the-cities npm package: other cities with 15,000+ people.
- `tools/build_gazetteer.js` rebuilds `data/places.json` and `data/world.json`.
- Libraries in `lib/` (vendored, no CDN): D3 7.9.0 (ISC), d3-cloud 1.2.7 (BSD), topojson-client 3.1.0 (ISC), Mammoth 1.8.0 (BSD-2), PDF.js 3.11.174 (Apache 2.0).

Created by Jason Sawle.
