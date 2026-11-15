"""District-level local election turnout, England, 2021-2025, with the election year on every figure.

Input : data/raw/leh/leh_{2021..2025}.xlsx  House of Commons Library / Elections Centre
        Local Elections Handbook datasets (ward-level electorate and turnout). Open Parliament Licence.
Output: data/out/le_districts.json, data/out/le_districts.csv, data/out/le_fields.json

Turnout for a district-year = ward electorates x ward turnout, summed, / summed electorate, over the wards
(or county divisions) that had a contest that year. Districts vote in different years and some elect only a
third of seats at a time, so every figure carries its year and election type, and `le_latest_*` says which
year it is from. County council elections (2021, 2025) are mapped to the district each division sits in.
The 2026 handbook dataset had not been published when this was built.
"""
import json, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw" / "leh", ROOT / "data" / "out"
LE_VERSION = "1.0.0"            # bump when parsing, matching or turnout maths changes
YEARS = [2021, 2022, 2023, 2024, 2025]
RECODE = {"E08000016": "E08000038", "E08000019": "E08000039"}
TYPES = {"SC": "County council", "CC": "County council", "MB": "Metropolitan borough", "LB": "London borough",
         "UAA": "Unitary council, all seats", "UAT": "Unitary council, a third of seats", "UA": "Unitary council",
         "UC": "Unitary council", "SDA": "District council, all seats", "SDT": "District council, a third of seats",
         "SD": "District council"}
ALIAS = {"bath and north east somerset": "bath and north east somerset", "bristol": "bristol, city of",
         "herefordshire": "herefordshire, county of", "hull": "kingston upon hull, city of",
         "kingston upon hull": "kingston upon hull, city of", "durham": "county durham",
         "st helens": "st. helens", "st albans": "st albans", "kings lynn and west norfolk": "king's lynn and west norfolk",
         "newcastle under lyme": "newcastle-under-lyme", "stoke on trent": "stoke-on-trent",
         "stockton on tees": "stockton-on-tees", "southend on sea": "southend-on-sea",
         "stratford on avon": "stratford-on-avon", "barrow in furness": "barrow-in-furness",
         "newcastle upon tyne": "newcastle upon tyne", "telford and the wrekin": "telford and wrekin",
         "the wrekin": "telford and wrekin", "epsom and ewell": "epsom and ewell", "basingstoke and dean": "basingstoke and deane",
         "blackburn": "blackburn with darwen", "brighton and hove": "brighton and hove", "medway towns": "medway",
         "east riding": "east riding of yorkshire", "south bucks": None, "nuneaton and bedworth": "nuneaton and bedworth",
         "kings lynn": "king's lynn and west norfolk", "west northants": "west northamptonshire",
         "north northants": "north northamptonshire", "shepway": "folkestone and hythe", "isle of wight": "isle of wight",
         "bournemouth christchurch and poole": "bournemouth, christchurch and poole", "bcp": "bournemouth, christchurch and poole",
         "cheshire west and chester": "cheshire west and chester", "newark and sherwood": "newark and sherwood",
         "scilly isles": "isles of scilly", "vale of white horse": "vale of white horse"}


def norm(s):
    s = str(s).lower().replace("&", "and").replace("-", " ").replace(".", "").replace("'", "")
    s = re.sub(r"\b(city of|council|borough|district|county of|royal)\b", " ", s)
    return re.sub(r"\s+", " ", s.replace(",", " ")).strip()


def main():
    lad = pd.read_csv(OUT / "nd_lad.csv")[["LAD25CD", "LAD25NM"]]
    codes = set(lad.LAD25CD)
    by_name = {norm(n): c for c, n in zip(lad.LAD25CD, lad.LAD25NM)}
    for k, v in ALIAS.items():
        if v and norm(v) in by_name: by_name.setdefault(norm(k), by_name[norm(v)])
    qa, frames = [], []

    def add(year, df, code=None, name=None, elect=None, turn=None, typ=None, pct=True):
        d = pd.DataFrame({"year": year, "elect": pd.to_numeric(df[elect], errors="coerce"),
                          "turn": pd.to_numeric(df[turn], errors="coerce"), "type": df[typ].astype(str).str.strip()})
        if not pct: d["turn"] *= 100
        if code is not None:
            d["lad"] = df[code].astype(str).str.strip().replace(RECODE)
        else:
            d["lad"] = df[name].map(lambda n: by_name.get(norm(n)))
            miss = sorted({str(n) for n in df[name][d.lad.isna()].dropna()})
            if miss: qa.append(f"{year}: names not matched to an English district: {', '.join(miss)}")
        n0 = len(d)
        d = d[d.lad.isin(codes) & d.elect.gt(0) & d.turn.gt(0)]
        qa.append(f"{year}: {len(d)} of {n0} ward/division rows used ({d.lad.nunique()} districts)")
        frames.append(d)

    x = lambda y, sheet, **k: pd.read_excel(RAW / f"leh_{y}.xlsx", sheet_name=sheet, **k).rename(columns=lambda c: str(c).strip())
    add(2021, x(2021, "Wards-results", header=1), code="Local authority code", elect="Electorate", turn="Turnout (%)", typ="Type")
    add(2022, x(2022, "Wards-results", header=1), code="Local authority code", elect="Electorate", turn="Turnout (%)", typ="Type")
    add(2023, x(2023, "Ward_Level"), name="DISTRICTNAME", elect="ELECT", turn="TURNOUT", typ="TYPE")
    add(2024, x(2024, "Wards results", header=1), code="Local authority code", elect="Electorate", turn="Turnout (%)",
        typ="Local authority type", pct=False)
    add(2025, x(2025, "Ward results", header=1), name="Lower tier authority", elect="Electorate", turn="Turnout (EC method)",
        typ="Local authority type", pct=False)
    w = pd.concat(frames)
    w["votes"] = w.elect * w.turn / 100
    g = w.groupby(["lad", "year"]).agg(elect=("elect", "sum"), votes=("votes", "sum"), wards=("turn", "size"),
                                       type=("type", lambda s: s.mode().iat[0])).reset_index()
    g["turnout"] = (100 * g.votes / g.elect).round(1)
    g["type_label"] = g.type.map(TYPES).fillna(g.type)
    g["county"] = g.type.isin(["SC", "CC"])
    # comparable across years: gap to the median district voting in the same year and tier (county / own council)
    g["rel"] = g.turnout - g.groupby(["year", "county"]).turnout.transform("median")

    out = []
    for c, n in zip(lad.LAD25CD, lad.LAD25NM):
        r = {"LAD25CD": c, "LAD25NM": n}
        s = g[g.lad == c].sort_values("year")
        for y in YEARS:
            m = s[s.year == y]
            r[f"le{y}_turnout"] = float(m.turnout.iat[0]) if len(m) else None
            r[f"le{y}_type"] = m.type_label.iat[0] if len(m) else "No election"
            r[f"le{y}_electorate"] = int(m.elect.iat[0]) if len(m) else None
        r["le_years_held"] = ", ".join(str(y) for y in s.year) or "None 2021-25"
        last = s.iloc[-1] if len(s) else None
        r["le_latest_turnout"] = float(last.turnout) if last is not None else None
        r["le_latest_year"] = int(last.year) if last is not None else None
        r["le_latest_type"] = last.type_label if last is not None else "No election 2021-25"
        r["le_latest_label"] = f"{last.turnout:.1f}% in {int(last.year)} ({last.type_label})" if last is not None else "No election 2021-25"
        own = s[~s.county]
        lo = own.iloc[-1] if len(own) else None
        r["le_own_turnout"] = float(lo.turnout) if lo is not None else None
        r["le_own_year"] = int(lo.year) if lo is not None else None
        r["le_own_type"] = lo.type_label if lo is not None else "No own-council election 2021-25"
        r["le_relative_turnout"] = round(float(s.rel.mean()), 1) if len(s) else None
        r["data_version"] = f"Local elections 2021-25 build {LE_VERSION}"
        out.append(r)
    d = pd.DataFrame(out)
    qa.append(f"Districts with any local election 2021-25: {d.le_latest_year.notna().sum()} of {len(d)}; "
              f"with an own-council election: {d.le_own_year.notna().sum()}")
    qa.append("Latest election year counts: " + json.dumps(d.le_latest_year.dropna().astype(int).value_counts().sort_index().to_dict()))
    qa.append("No election 2021-25: " + (", ".join(d[d.le_latest_year.isna()].LAD25NM) or "none"))
    for y in YEARS:
        t = g[g.year == y]; qa.append(f"{y}: England turnout across contested wards {100 * t.votes.sum() / t.elect.sum():.1f}% ({len(t)} districts)")

    A = {"LAD25CD": "District code (May 2025)", "LAD25NM": "District", "le_years_held": "Years with a local election, 2021-25",
         "le_latest_turnout": "Local election turnout %, most recent election (see year)", "le_latest_year": "Year of most recent local election",
         "le_latest_type": "Type of most recent local election", "le_latest_label": "Most recent local election: turnout, year and type",
         "le_own_turnout": "Turnout %, most recent election to the district's own council (see year)",
         "le_own_year": "Year of most recent own-council election", "le_own_type": "Type of most recent own-council election",
         "le_relative_turnout": "Local turnout vs same-year median, average 2021-25 (percentage points)",
         "data_version": "Data version"}
    for y in YEARS:
        A[f"le{y}_turnout"] = f"Local election turnout %, May {y}"
        A[f"le{y}_type"] = f"Type of local election, May {y}"
        A[f"le{y}_electorate"] = f"Electorate in wards contested, May {y}"
    d.to_csv(OUT / "le_districts.csv", index=False)
    json.dump(json.loads(d.to_json(orient="records")), open(OUT / "le_districts.json", "w"), separators=(",", ":"), allow_nan=False)
    json.dump({"version": LE_VERSION, "aliases": A, "qa": qa}, open(OUT / "le_fields.json", "w"), indent=1)
    print("\n".join(qa))


if __name__ == "__main__":
    main()
