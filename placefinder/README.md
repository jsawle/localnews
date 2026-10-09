# Place Finder v1.1.0

Find the places mentioned in a document and show them on a map, in a summary table and as a word cloud sized by number of mentions.

Live: https://jsawle.github.io/localnews/placefinder/

- Reads Word (.docx), PDF, .txt/.md/.csv and .html files, pasted text, or a web page address — all in the browser, nothing is uploaded.
- Web addresses: Wikipedia articles (via the Wikipedia API, reference sections removed) and any site that allows cross-origin reading. Sites that block it get a "copy and paste the text" message. You can also link straight to a page: `placefinder/?url=https://en.wikipedia.org/wiki/Silk_Road`.
- Matches text against a gazetteer of ~35,000 places (countries, states/provinces, cities and towns with 15,000+ people, continents, oceans, seas, rivers, lakes, mountains, islands, world regions, well-known volcanoes).
- Filters likely non-places (people's names, "New York Times", ordinary words at the start of a sentence) and picks between same-name places using the rest of the document ("Paris, Texas").
- Untick wrong matches, or change a match with "Which place?". Export CSV or GeoJSON (both can be added to ArcGIS Online / MapMaker maps), and PNG of the map and word cloud.

## Versions

| Part | Version |
|---|---|
| Place Finder app | 1.1.0 |
| Document reader | 1.1 |
| Place finder (matching & disambiguation) | 1.1 |
| Gazetteer data | 1.0 |
| Map | 1.0 |
| Word cloud | 1.0 |

## Changes

- 1.1.0: read a web page from its address (Wikipedia and sites that allow it); `?url=` links; source link in the summary and GeoJSON. Document reader 1.1. Place finder 1.1: a river or mountain range's own name now beats a region that only lists it as an alternative name ("Danube" is the river, not Serbia's Podunavlje district).
- 1.0.0: first release.

## Data and libraries

- Natural Earth (public domain): countries, admin-1, populated places, physical features, borders.
- GeoNames (CC BY 4.0) via the all-the-cities npm package: other cities with 15,000+ people.
- `tools/build_gazetteer.js` rebuilds `data/places.json` and `data/world.json`.
- Libraries in `lib/` (vendored, no CDN): D3 7.9.0 (ISC), d3-cloud 1.2.7 (BSD), topojson-client 3.1.0 (ISC), Mammoth 1.8.0 (BSD-2), PDF.js 3.11.174 (Apache 2.0).

Created by Jason Sawle.
