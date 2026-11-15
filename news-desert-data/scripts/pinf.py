"""Build England layers from the PINF Local News Database (December 2025).

Input : data/raw/pinf_2025.xlsx  (not redistributed: no open licence stated by PINF)
Output: data/out/pinf_districts.json  attributes for the 296 English districts (LAD May 2025)
        data/out/pinf_outlets.geojson  one point per outlet per English district it covers
        data/out/pinf_fields.json      aliases, descriptions, version, QA notes

Point positions. PINF's LOCATION is often the publisher's office rather than the area
served (only ~58% of English outlets have a LOCATION inside a district they cover), so
each outlet is drawn once in every district it covers:
  - at its LOCATION when that falls inside the district, otherwise
  - on an evenly spaced grid inside the district, nearest its centre first.
`position` records which, so placed points are never mistaken for addresses.
"""
import json, math, re, sys
from pathlib import Path
import pandas as pd
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "out"
PINF_VERSION = "1.0.0"          # bump when parsing, placement or field maths changes
LAD_RECODE = {"E08000016": "E08000038", "E08000019": "E08000039"}
XLSX = RAW / "pinf_2025.xlsx"

MEDIA = {"Print and Online": "pinf_n_print_online", "Online": "pinf_n_online", "Print": "pinf_n_print",
         "Community Radio": "pinf_n_comm_radio", "BBC Local Radio": "pinf_n_bbc_radio",
         "Local TV Station": "pinf_n_local_tv"}


def yn(v):
    return "Yes" if str(v).strip().lower() in ("yes", "true", "1", "1.0") else "No"


def clean(v):
    return None if (v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() in ("", "NA")) else str(v).strip()


def codes(s):
    return [LAD_RECODE.get(c, c) for c in re.split(r";\s*", str(s or "")) if c.strip()]


def grid_points(poly, n, taken):
    """n evenly spaced points inside poly, nearest its representative point first."""
    c = poly.representative_point()
    k = math.cos(math.radians(c.y))
    minx, miny, maxx, maxy = poly.bounds
    area = poly.area * k                                   # rough, in degree² at local scale
    step = math.sqrt(area / max(n * 6, 12))
    for _ in range(8):
        pts, y, row = [], miny + step / 2, 0
        while y < maxy:
            x = minx + (step / k) * (0.5 if row % 2 else 0) + step / (2 * k)
            while x < maxx:
                p = Point(round(x, 6), round(y, 6))
                if poly.contains(p) and (p.x, p.y) not in taken:
                    pts.append(p)
                x += step / k
            y += step * 0.866; row += 1
        if len(pts) >= n:
            pts.sort(key=lambda p: ((p.x - c.x) * k) ** 2 + (p.y - c.y) ** 2)
            return pts[:n]
        step /= 1.6
    raise RuntimeError("could not place points")


def main():
    bnd = json.load(open(RAW / "bnd_lad25.geojson"))
    lad = {f["properties"]["LAD25CD"]: (f["properties"]["LAD25NM"], shape(f["geometry"])) for f in bnd["features"]}
    lad_codes = list(lad); polys = [lad[c][1] for c in lad_codes]; tree = STRtree(polys)
    qa = []

    # ---------- outlets ----------
    m = pd.read_excel(XLSX, sheet_name="Map data")
    n0 = len(m); m = m.drop_duplicates()
    qa.append(f"Map data: {n0} rows, {n0 - len(m)} exact duplicate rows removed, {len(m)} outlets UK-wide")
    m["cov"] = m.COVERAGE_LAD_2023.apply(codes)
    m = m[m["cov"].apply(lambda c: any(x.startswith("E") for x in c))].copy()
    bad = sorted({c for cs in m["cov"] for c in cs if c.startswith("E") and c not in lad})
    if bad: sys.exit(f"unknown LAD codes {bad}")
    qa.append(f"{len(m)} outlets cover at least one English district")

    def lad_at(s):
        if not isinstance(s, str) or "," not in s: return None
        x, y = map(float, s.split(",")); p = Point(x, y)
        for i in tree.query(p):
            if polys[i].contains(p): return lad_codes[i], p
        return None

    rows = []
    for r in m.itertuples(index=False):
        hit = lad_at(r.LOCATION)
        cov = [c for c in r.cov if c.startswith("E")]
        for c in cov:
            rows.append(dict(title_id=r.TITLE_ID, title=clean(r.TITLE), owner=clean(r.OWNER),
                             media_type=clean(r.MEDIA_TYPE), independent=yn(r.INDEPENDENT),
                             solo_editor=clean(r.SOLO_EDITOR_JOURNALIST), conduct_code=clean(r.CONDUCT_CODE),
                             url=clean(r.URL), n_districts=len(cov), coverage_codes="; ".join(cov),
                             coverage_names="; ".join(lad[x][0] for x in cov), district_code=c,
                             district_name=lad[c][0],
                             pt_=hit[1] if hit and hit[0] == c else None))
    o = pd.DataFrame(rows)
    taken = {(p.x, p.y) for p in o.pt_.dropna()}
    o["position"] = o.pt_.apply(lambda p: "Outlet address (PINF LOCATION)" if p is not None else
                                "Placed inside the district served (address elsewhere or missing)")
    for c, g in o[o.pt_.isna()].sort_values("title").groupby("district_code"):
        pts = grid_points(lad[c][1], len(g), taken)
        for i, p in zip(g.index, pts): o.at[i, "pt_"] = p; taken.add((p.x, p.y))
    qa.append(f"{len(o)} outlet points ({o.position.str.startswith('Outlet').sum()} at PINF address, "
              f"{o.position.str.startswith('Placed').sum()} placed inside the district served)")
    assert all(lad[r.district_code][1].contains(r.pt_) for r in o.itertuples()), "point outside its district"
    o["data_version"] = f"PINF Dec 2025 build {PINF_VERSION}"
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.pt_.x, r.pt_.y]},
              "properties": {k: (None if isinstance(v, float) and math.isnan(v) else v)
                             for k, v in r._asdict().items() if k != "pt_"}}
             for r in o.itertuples(index=False)]
    json.dump({"type": "FeatureCollection", "features": feats}, open(OUT / "pinf_outlets.geojson", "w"),
              separators=(",", ":"), ensure_ascii=False, allow_nan=False)

    # ---------- districts ----------
    d = pd.read_excel(XLSX, sheet_name="District level")
    d["code"] = d.District_code.replace(LAD_RECODE)
    d = d[d.code.str.startswith("E")].set_index("code")
    assert set(d.index) == set(lad), "district codes do not match LAD May 2025"
    lc = pd.read_excel(XLSX, sheet_name="LaunchesClosures")
    lc["code"] = lc.District.map(dict(zip(d.District, d.index)))
    launch = set(lc[lc.Event == "Launch"].code.dropna()); closure = set(lc[lc.Event == "Closure"].code.dropna())

    def klass(r):
        a, b = clean(r.NewsDeserts_oasisabs), clean(r.Dryland_oasispop)
        if a in ("Absolute news desert", "Relative news desert"): return a
        if b == "Drylands": return "Dryland"
        if (a and "oasis" in a.lower()) or (b and "oasis" in b.lower()): return "News oasis"
        return "Other districts"

    per = o.groupby(["district_code", "media_type"]).title_id.nunique().unstack(fill_value=0)
    ind = o[o.independent == "Yes"].groupby("district_code").title_id.nunique()
    # District lists rebuilt from the outlet table: PINF's district sheet still carries some
    # pre-rename owner names (e.g. MEDIA CONCIERGE LIMITED for ICONIC MEDIA LIMITED).
    lists = {}
    for c, g in o.groupby("district_code"):
        t = sorted(f"{r.title} ({r.owner or 'unspecified owner'})" for r in g.itertuples())
        w = sorted({r.owner for r in g.itertuples() if isinstance(r.owner, str)})
        lists[c] = ("; ".join(t), "; ".join(w) or None)
    out = []
    for c, (nm, _) in lad.items():
        r = d.loc[c]
        rec = dict(LAD25CD=c, LAD25NM=nm, region=clean(r.Region), pinf_geography=clean(r.Geography),
                   pinf_ruc_cluster=clean(r["ruc-cluster-label"]),
                   pinf_titles=int(r.N_TITLES), pinf_owners=int(r.N_OWNERS),
                   pinf_per100k=round(float(r["Outlets per 100,000"]), 2),
                   pinf_rank_uk=None if pd.isna(r.Rank) else int(r.Rank),
                   pinf_pop_2022=int(r.LAD_2022_pop), pinf_area_km2=None if pd.isna(r.area_sq_km) else float(r.area_sq_km),
                   pinf_monopoly=yn(r.IS_MONOPOLY), pinf_class=klass(r),
                   pinf_desert_oasis=clean(r.NewsDeserts_oasisabs) or "None",
                   pinf_dryland_oasis=clean(r.Dryland_oasispop) or "None",
                   pinf_launch=("Yes" if c in launch else "No"), pinf_closure=("Yes" if c in closure else "No"),
                   pinf_titles_list=lists.get(c, (None, None))[0], pinf_owners_list=lists.get(c, (None, None))[1])
        for mt, f in MEDIA.items():
            rec[f] = int(per.loc[c, mt]) if (c in per.index and mt in per.columns) else 0
        rec["pinf_n_independent"] = int(ind.get(c, 0))
        rec["data_version"] = f"PINF Dec 2025 build {PINF_VERSION}"
        out.append(rec)
    dd = pd.DataFrame(out)
    recount = dd[list(MEDIA.values())].sum(axis=1)
    mism = dd[recount != dd.pinf_titles]
    qa.append("District outlet counts recounted from the outlet list match PINF's N_TITLES in "
              f"{len(dd) - len(mism)} of {len(dd)} districts" +
              ("; differs in " + ", ".join(f"{r.LAD25NM} (PINF {r.pinf_titles}, outlet list {recount[i]})"
                                          for i, r in mism.iterrows()) if len(mism) else ""))
    qa.append("pinf_class counts: " + json.dumps(dd.pinf_class.value_counts().to_dict()))
    json.dump(out, open(OUT / "pinf_districts.json", "w"), separators=(",", ":"), ensure_ascii=False, allow_nan=False)

    A = {  # aliases
        "LAD25CD": "District code (May 2025)", "LAD25NM": "District", "region": "Region",
        "pinf_geography": "Authority type", "pinf_ruc_cluster": "Rural–urban cluster (PINF)",
        "pinf_titles": "Local news outlets", "pinf_owners": "Owners (publishers)",
        "pinf_per100k": "Outlets per 100,000 people", "pinf_rank_uk": "UK rank, outlets per 100,000 (1 = most)",
        "pinf_pop_2022": "Population 2022 (used by PINF)", "pinf_area_km2": "Area km² (PINF)",
        "pinf_monopoly": "Single-owner monopoly", "pinf_class": "News provision class",
        "pinf_desert_oasis": "PINF desert/oasis (by outlets)", "pinf_dryland_oasis": "PINF dryland/oasis (per person)",
        "pinf_launch": "Outlet launched since Apr 2024", "pinf_closure": "Outlet closed since Apr 2024",
        "pinf_titles_list": "Outlets (owner)", "pinf_owners_list": "Owners",
        "pinf_n_print_online": "Print and online outlets", "pinf_n_online": "Online-only outlets",
        "pinf_n_print": "Print-only outlets", "pinf_n_comm_radio": "Community radio stations",
        "pinf_n_bbc_radio": "BBC local radio", "pinf_n_local_tv": "Local TV stations",
        "pinf_n_independent": "Independent outlets", "data_version": "Data version",
        "title_id": "PINF title ID", "title": "Outlet", "owner": "Owner", "media_type": "Media type",
        "independent": "Independent (turnover under £2m)", "solo_editor": "Solo editor/journalist",
        "conduct_code": "Code of conduct / regulator", "url": "Website", "n_districts": "Districts covered",
        "coverage_codes": "Coverage district codes", "coverage_names": "Coverage districts",
        "district_code": "District code (this point)", "district_name": "District (this point)",
        "position": "Point position"}
    json.dump({"version": PINF_VERSION, "aliases": A, "qa": qa}, open(OUT / "pinf_fields.json", "w"), indent=1, ensure_ascii=False)
    print("\n".join(qa))


if __name__ == "__main__":
    main()
