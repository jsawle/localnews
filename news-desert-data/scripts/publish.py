"""Stage 3: publish the built layers to ArcGIS Online and share them publicly.

    python scripts/publish.py --profile g4s-publisher            # publish / overwrite all layers
    python scripts/publish.py --profile g4s-publisher --dry-run  # show what would happen

Needs the ArcGIS API for Python (pip install arcgis) and a saved profile.
Layers are published from GeoJSON. Re-running overwrites them in place, so
item IDs, and any maps built on them, survive updates.
"""
import argparse
import json
from pathlib import Path

from common import DATA_BUILD_VERSION, OUT, SOURCE_VERSIONS, log

FOLDER = "News desert programme"
TAGS = ["news desert", "local news", "England", "IMD 2025", "Census 2021", "OGL"]

LAYERS = {
    "nd_lad": {
        "title": "News desert supplementary data: districts (England)",
        "service": "news_desert_districts_england",
        "snippet": "Deprivation, Census 2021, population change, civic life, GE 2024 turnout, business and "
                   "digital connectivity for England's 296 local authority districts (May 2025).",
        "tier": "lad",
    },
    "nd_lsoa": {
        "title": "News desert supplementary data: neighbourhoods (LSOA 2021, England)",
        "service": "news_desert_lsoa_england",
        "snippet": "Deprivation, Census 2021, rurality, broadband and GE 2024 constituency turnout for "
                   "England's 33,755 Lower layer Super Output Areas.",
        "tier": "lsoa",
    },
    "nd_pcon": {
        "title": "News desert supplementary data: GE 2024 turnout by constituency (England)",
        "service": "news_desert_ge2024_turnout_england",
        "snippet": "Electorate, valid votes and turnout at the 4 July 2024 general election for "
                   "England's 543 Westminster constituencies.",
        "tier": "pcon",
    },
}

SOURCES = [
    # key, name, publisher, release, licence
    ("geography", "Boundaries and lookups (LAD May 2025 BGC, LSOA 2021 BFE generalised, PCON July 2024 BGC)",
     "ONS Open Geography Portal", "2025–2026", "OGL v3.0; contains OS data © Crown copyright and database right"),
    ("iod2025", "English Indices of Deprivation 2025", "MHCLG", "30 Oct 2025 (corrected 17 Nov 2025)", "OGL v3.0"),
    ("ruc2021", "Rural Urban Classification 2021", "ONS", "2025", "OGL v3.0"),
    ("census2021", "Census 2021 topic summaries TS001, TS003, TS006, TS007A, TS021, TS037, TS066, TS067",
     "ONS (Nomis bulk)", "2022–2023", "OGL v3.0"),
    ("mye2025", "Population estimates for England and Wales, mid-2025", "ONS", "29 Jul 2026", "OGL v3.0"),
    ("ces2526", "Community and Engagement Survey 2025/26", "DCMS with MHCLG", "31 Jul 2026", "OGL v3.0"),
    ("ge2024", "General election 2024 results", "House of Commons Library", "2024", "Open Parliament Licence"),
    ("business2026", "UK business: activity, size and location 2026", "ONS", "24 Sep 2026", "OGL v3.0"),
    ("ofcom2026", "Connected Nations update: Spring 2026", "Ofcom", "13 May 2026", "OGL v3.0"),
]

CREDITS = ("Contains public sector information licensed under the Open Government Licence v3.0 "
           "(ONS, MHCLG, DCMS, Ofcom) and Parliamentary information licensed under the Open Parliament "
           "Licence v3.0. Contains OS data © Crown copyright and database right 2026.")


def description(meta, tier):
    fields = {k: v for k, v in meta["fields"].items() if tier in v["tiers"]}
    used = sorted({v["source"] for v in fields.values()})
    rows = "".join(f"<tr><td>{n}</td><td>{p}</td><td>{r}</td><td>{l}</td><td>{SOURCE_VERSIONS.get(k, '')}</td></tr>"
                   for k, n, p, r, l in SOURCES if k in used)
    frows = "".join(f"<tr><td><code>{k}</code></td><td>{v['alias']}</td></tr>" for k, v in fields.items())
    notes = ""
    if tier == "lad":
        notes = ("<p>GE 2024 turnout is published for constituencies, which don't nest in districts. "
                 "<code>ge24_turnout_est</code> weights each LSOA's constituency turnout by its residents aged 16+ "
                 "(Census 2021) and averages to the district. Treat it as an estimate.</p>"
                 "<p>Community and Engagement Survey figures have wide confidence intervals at district level; "
                 "use the <code>_sig</code> fields (above / in line with / below England) for comparisons.</p>")
    if tier == "lsoa":
        notes = ("<p>LSOA boundaries are ONS full-resolution (BFE V10) generalised server-side to about 15 m. "
                 "<code>ge24_turnout_pcon</code> is the turnout of the constituency each LSOA best fits; it is "
                 "not measured for the LSOA.</p>")
    return (f"<p>Supplementary data for the news desert programme. England only. Data build "
            f"<b>v{DATA_BUILD_VERSION}</b>.</p>{notes}"
            f"<p><b>Sources and versions</b></p><table><tr><th>Source</th><th>Publisher</th><th>Release</th>"
            f"<th>Licence</th><th>Version</th></tr>{rows}</table>"
            f"<p><b>Fields</b></p><table><tr><th>Field</th><th>Description</th></tr>{frows}</table>"
            f"<p>Census 2021 labour market figures were collected during lockdown and furlough; ONS advises care.</p>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="g4s-publisher")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()

    from arcgis.gis import GIS
    from arcgis.features import FeatureLayerCollection

    meta = json.loads((OUT / "fields.json").read_text())
    gis = GIS(profile=a.profile)
    me = gis.users.me
    log(f"signed in as {me.username} ({me.role}) to {gis.properties.urlKey}.{gis.properties.customBaseUrl}")
    if not a.dry_run and FOLDER not in [f["title"] for f in me.folders]:
        try:
            gis.content.folders.create(FOLDER)
        except AttributeError:
            gis.content.create_folder(FOLDER)

    results = {}
    for key, cfg in LAYERS.items():
        if a.only and key not in a.only:
            continue
        path = OUT / f"{key}.geojson"
        if not path.exists():
            log(f"skip {key}: {path.name} not built")
            continue
        q = f'title:"{cfg["title"]}" AND owner:{me.username}'
        existing = [i for i in gis.content.search(q, max_items=20) if i.title == cfg["title"]]
        svc = next((i for i in existing if i.type == "Feature Service"), None)
        src = next((i for i in existing if i.type == "GeoJson"), None)
        log(f"{key}: service={svc.id if svc else None} source={src.id if src else None}")
        if a.dry_run:
            continue
        props = {"title": cfg["title"], "snippet": cfg["snippet"], "tags": TAGS,
                 "description": description(meta, cfg["tier"]), "accessInformation": CREDITS,
                 "licenseInfo": "Open Government Licence v3.0 and Open Parliament Licence v3.0 (see description)."}
        if src and svc:
            src.update(item_properties={"title": cfg["title"]}, data=str(path))
            svc = src.publish(overwrite=True, file_type="geojson")
        else:
            try:
                src = gis.content.folders.get(FOLDER).add({**props, "type": "GeoJson"}, file=str(path)).result()
            except AttributeError:
                src = gis.content.add({**props, "type": "GeoJson"}, data=str(path), folder=FOLDER)
            svc = src.publish(publish_parameters={"name": cfg["service"], "hasStaticData": True,
                                                  "maxRecordCount": 2000,
                                                  "layerInfo": {"capabilities": "Query"}},
                              file_type="geojson")
        svc.update(item_properties=props)
        # Field aliases
        lyr = svc.layers[0]
        names = {f["name"] for f in lyr.properties.fields}
        upd = [{"name": n, "alias": meta["fields"][n]["alias"][:255]} for n in names if n in meta["fields"]]
        if upd:
            lyr.manager.update_definition({"fields": upd})
        # Public sharing (the source GeoJSON item stays private)
        try:
            svc.sharing.sharing_level = "EVERYONE"
        except AttributeError:
            svc.share(everyone=True)
        results[key] = {"id": svc.id, "url": svc.url, "home": svc.homepage}
        log(f"{key}: published {svc.homepage}")
    (OUT / "published.json").write_text(json.dumps(results, indent=2))
    log("done", json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
