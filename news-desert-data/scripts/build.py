"""Stage 2: build the district (tier 1), LSOA (tier 2) and constituency tables + GeoJSON.

    python scripts/build.py

Any source whose raw files are missing is skipped with a warning, so the build
runs with whatever has been fetched. Outputs go to data/out/.
"""
import csv
import json
import re
from pathlib import Path

import pandas as pd

from common import (DATA_BUILD_VERSION, LAD_RECODE, OUT, RAW, SOURCE_VERSIONS,
                    load_json, log, save_json)

FIELDS = {}   # field -> {"alias": ..., "source": ..., "tiers": set()}
WARN = []


def field(name, alias, source, tiers):
    FIELDS[name] = {"alias": alias, "source": source, "tiers": tiers}


def pick(cols, must, exclude=()):
    """Shortest column whose name contains every string in `must` (case-insensitive)."""
    def n(t):
        return re.sub(r"\s+", " ", str(t).lower().replace("-", " "))
    c = [x for x in cols if all(n(m) in n(x) for m in must)
         and not any(n(e) in n(x) for e in exclude)]
    if not c:
        raise KeyError(f"no column with {must} (excluding {exclude}); columns: {list(cols)[:60]}")
    return min(c, key=len)


def pct(num, den):
    return (100 * num / den.where(den > 0)).round(1)


def have(*names):
    missing = [n for n in names if not (RAW / n).exists()]
    if missing:
        WARN.append(f"skipped: missing {', '.join(missing)}")
        log("skip, missing", *missing)
        return False
    return True


# ------------------------------------------------------------------ geography
def base_tables():
    lad_lu = pd.DataFrame(load_json(RAW / "lsoa_lad25.json"))
    pcon_lu = pd.DataFrame(load_json(RAW / "lsoa_pcon24.json"))
    lsoa = lad_lu[["LSOA21CD", "LSOA21NM", "LAD25CD", "LAD25NM"]].merge(
        pcon_lu[["LSOA21CD", "PCON24CD", "PCON24NM"]], on="LSOA21CD", how="left")
    bnd = load_json(RAW / "bnd_lsoa21.geojson")
    ruc = pd.DataFrame([f["properties"] for f in bnd["features"]])[
        ["LSOA21CD", "RUC21CD", "RUC21NM", "Urban_rura"]].rename(
        columns={"RUC21CD": "ruc_code", "RUC21NM": "ruc_name", "Urban_rura": "ruc_urban_rural"})
    lsoa = lsoa.merge(ruc, on="LSOA21CD", how="left")
    lad = lsoa.groupby(["LAD25CD", "LAD25NM"], as_index=False).size().rename(columns={"size": "lsoa_count"})
    r = pd.DataFrame(load_json(RAW / "ruc_lad24.json"))
    r["LAD25CD"] = r["LAD24CD"].replace(LAD_RECODE)
    lad = lad.merge(r[["LAD25CD", "RUC21CD", "RUC21NM", "Urban_rural_flag"]].rename(
        columns={"RUC21CD": "ruc_code", "RUC21NM": "ruc_name", "Urban_rural_flag": "ruc_urban_rural"}),
        on="LAD25CD", how="left")
    for t in ("lad", "lsoa"):
        pass
    field("lsoa_count", "Number of LSOAs (2021) in district", "geography", {"lad"})
    field("ruc_code", "Rural Urban Classification 2021 code", "ruc2021", {"lad", "lsoa"})
    field("ruc_name", "Rural Urban Classification 2021", "ruc2021", {"lad", "lsoa"})
    field("ruc_urban_rural", "Urban or rural (RUC 2021)", "ruc2021", {"lad", "lsoa"})
    log("base:", len(lsoa), "LSOAs,", len(lad), "districts")
    return lad, lsoa


# ------------------------------------------------------------------ IoD 2025
IOD_DOMAINS = {  # field prefix -> words identifying the domain in File 7 headers
    "imd": ["Index of Multiple Deprivation"],
    "inc": ["Income", "Score"],
    "emp": ["Employment"],
    "edu": ["Education"],
    "hea": ["Health"],
    "cri": ["Crime"],
    "bar": ["Barriers"],
    "liv": ["Living Environment"],
    "idaci": ["IDACI"],
    "idaopi": ["IDAOPI"],
}
IOD_NAMES = {"imd": "Index of Multiple Deprivation", "inc": "Income", "emp": "Employment",
             "edu": "Education, skills and training", "hea": "Health deprivation and disability",
             "cri": "Crime", "bar": "Barriers to housing and services", "liv": "Living environment",
             "idaci": "Income deprivation affecting children (IDACI)",
             "idaopi": "Income deprivation affecting older people (IDAOPI)"}


def iod(lad, lsoa):
    s = pd.DataFrame(load_json(RAW / "iod_lsoa_mhclg.json")).rename(
        columns={"IMDRank": "imd_rank", "IMDDecil": "imd_decile"})
    lsoa = lsoa.merge(s, on="LSOA21CD", how="left")
    field("imd_rank", "IMD 2025 rank (1 = most deprived of 33,755)", "iod2025", {"lsoa"})
    field("imd_decile", "IMD 2025 decile (1 = most deprived 10%)", "iod2025", {"lsoa"})

    if (RAW / "iod2025_file7.csv").exists():
        f7 = pd.read_csv(RAW / "iod2025_file7.csv", encoding="utf-8-sig")
        cols = list(f7.columns)
        code = pick(cols, ["LSOA code"])
        keep = {code: "LSOA21CD"}
        for k, words in IOD_DOMAINS.items():
            if k == "imd":
                continue
            ex = ("Affecting",) if k in ("inc",) else ()
            try:
                dec = pick(cols, words[:1] + ["Decile"], exclude=ex)
                keep[dec] = f"{k}_decile"
                field(f"{k}_decile", f"{IOD_NAMES[k]} decile, IoD 2025 (1 = most deprived 10%)", "iod2025", {"lsoa"})
            except KeyError as e:
                WARN.append(f"IoD File 7: {e}")
        sc = pick(cols, ["Index of Multiple Deprivation", "Score"])
        keep[sc] = "imd_score"
        field("imd_score", "IMD 2025 score (higher = more deprived)", "iod2025", {"lsoa"})
        lsoa = lsoa.merge(f7[list(keep)].rename(columns=keep), on="LSOA21CD", how="left")
    else:
        WARN.append("IoD domains skipped: File 7 not downloaded")

    l = pd.DataFrame(load_json(RAW / "iod_lad_mhclg.json"))
    l["LAD25CD"] = l["LAD24CD"].replace(LAD_RECODE)
    l = l.rename(columns={"RAvgScorLTLA": "imd_rank_avg_score", "RAvgRankLTLA": "imd_rank_avg_rank",
                          "RPLMD10LTLA": "imd_rank_pct_d10", "RExtLTLA": "imd_rank_extent",
                          "RLocConLTLA": "imd_rank_local_conc"})
    lad = lad.merge(l.drop(columns=["LAD24CD", "LAD24NM"]), on="LAD25CD", how="left")
    for k, a in {"imd_rank_avg_score": "IMD 2025 district rank of average score (1 = most deprived of 296)",
                 "imd_rank_avg_rank": "IMD 2025 district rank of average rank (1 = most deprived)",
                 "imd_rank_pct_d10": "IMD 2025 district rank: share of LSOAs in most deprived 10% (1 = highest)",
                 "imd_rank_extent": "IMD 2025 district rank of extent (1 = most deprived)",
                 "imd_rank_local_conc": "IMD 2025 district rank of local concentration (1 = most deprived)"}.items():
        field(k, a, "iod2025", {"lad"})
    g = lsoa.groupby("LAD25CD").agg(n=("LSOA21CD", "size"),
                                    d1=("imd_decile", lambda x: (x == 1).sum()),
                                    d12=("imd_decile", lambda x: (x <= 2).sum())).reset_index()
    g["imd_pct_lsoa_d10"] = pct(g["d1"], g["n"])
    g["imd_pct_lsoa_d20"] = pct(g["d12"], g["n"])
    lad = lad.merge(g[["LAD25CD", "imd_pct_lsoa_d10", "imd_pct_lsoa_d20"]], on="LAD25CD", how="left")
    field("imd_pct_lsoa_d10", "% of district's LSOAs in England's most deprived 10% (IMD 2025)", "iod2025", {"lad"})
    field("imd_pct_lsoa_d20", "% of district's LSOAs in England's most deprived 20% (IMD 2025)", "iod2025", {"lad"})
    return lad, lsoa


# ------------------------------------------------------------------ Census 2021
def census_csv(t):
    p = RAW / f"census2021-{t}-lsoa.csv"
    df = pd.read_csv(p, encoding="utf-8-sig")
    code = pick(df.columns, ["geography code"])
    df = df.rename(columns={code: "LSOA21CD"})
    return df[df["LSOA21CD"].str.startswith("E")]


def lone_col(cols):
    try:
        return pick(cols, ["Lone parent", "With dependent children"])
    except KeyError:
        WARN.append("TS003: no lone-parent-with-dependent-children category; used all lone-parent families")
        return pick(cols, ["Lone parent family"])


def census(lad, lsoa):
    tabs = ["ts001", "ts003", "ts006", "ts007a", "ts021", "ts037", "ts066", "ts067"]
    if not have(*[f"census2021-{t}-lsoa.csv" for t in tabs]):
        return lad, lsoa
    c = pd.DataFrame({"LSOA21CD": lsoa["LSOA21CD"]})

    d = census_csv("ts001"); c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD,
        "n_pop": d[pick(d.columns, ["Total"])]}), on="LSOA21CD", how="left")
    d = census_csv("ts006"); dens = d[pick([x for x in d.columns if x != "LSOA21CD"], ["density"])] \
        if any("density" in x.lower() for x in d.columns) else d.iloc[:, -1]
    c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD, "density": pd.to_numeric(dens, errors="coerce")}),
                on="LSOA21CD", how="left")
    c["n_area_km2"] = c["n_pop"] / c["density"]

    d = census_csv("ts007a"); cols = d.columns
    young = [pick(cols, ["4 years and under"]), pick(cols, ["5 to 9"]), pick(cols, ["10 to 14"])]
    old = [pick(cols, [b]) for b in ("65 to 69", "70 to 74", "75 to 79", "80 to 84", "85 years and over")]
    c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD, "n_age_tot": d[pick(cols, ["Total"])],
                              "n_age0_14": d[young].sum(axis=1), "n_age65p": d[old].sum(axis=1)}),
                on="LSOA21CD", how="left")

    d = census_csv("ts003"); cols = d.columns
    c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD, "n_hh": d[pick(cols, ["Total"])],
                              "n_hh_1p_66": d[pick(cols, ["person household", "66"])],
                              "n_hh_1p_oth": d[pick(cols, ["person household", "Other"])],
                              "n_hh_lone_dep": d[lone_col(cols)]}),
                on="LSOA21CD", how="left")

    d = census_csv("ts021"); cols = d.columns
    c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD, "n_eth_tot": d[pick(cols, ["Total"])],
                              "n_wbrit": d[pick(cols, ["English, Welsh, Scottish, Northern Irish or British"])],
                              "n_asian": d[pick(cols, ["Asian, Asian British or Asian Welsh"])],
                              "n_black": d[pick(cols, ["Black, Black British"])],
                              "n_mixed": d[pick(cols, ["Mixed or Multiple"])],
                              "n_oth_eth": d[pick(cols, ["Other ethnic group"])]}),
                on="LSOA21CD", how="left")

    d = census_csv("ts037"); cols = d.columns
    c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD, "n_hlth_tot": d[pick(cols, ["Total"])],
                              "n_bad": d[pick(cols, ["Bad health"], exclude=["Very bad"])] +
                                       d[pick(cols, ["Very bad health"])]}),
                on="LSOA21CD", how="left")

    d = census_csv("ts066"); cols = d.columns
    ae = pick(cols, ["Economically active (excluding full-time students)"])
    ast = pick(cols, ["Economically active and a full-time student"])
    ue = pick(cols, ["Economically active (excluding full-time students)", "Unemployed"])
    ust = pick(cols, ["Economically active and a full-time student", "Unemployed"])
    c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD, "n_res16p": d[pick(cols, ["Total"])],
                              "n_active": d[ae] + d[ast], "n_unemp": d[ue] + d[ust]}),
                on="LSOA21CD", how="left")

    d = census_csv("ts067"); cols = d.columns
    c = c.merge(pd.DataFrame({"LSOA21CD": d.LSOA21CD, "n_qual_tot": d[pick(cols, ["Total"])],
                              "n_noqual": d[pick(cols, ["No qualifications"])],
                              "n_l4": d[pick(cols, ["Level 4"])]}),
                on="LSOA21CD", how="left")

    counts = [x for x in c.columns if x.startswith("n_")]
    lad_c = c.merge(lsoa[["LSOA21CD", "LAD25CD"]], on="LSOA21CD").groupby("LAD25CD")[counts].sum().reset_index()

    def derive(x):
        o = pd.DataFrame(index=x.index)
        o["cen21_pop"] = x["n_pop"].round(0)
        o["cen21_density"] = (x["n_pop"] / x["n_area_km2"]).round(1)
        o["cen21_pct_age0_14"] = pct(x["n_age0_14"], x["n_age_tot"])
        o["cen21_pct_age65p"] = pct(x["n_age65p"], x["n_age_tot"])
        o["cen21_pct_hh_1p_66p"] = pct(x["n_hh_1p_66"], x["n_hh"])
        o["cen21_pct_hh_1p"] = pct(x["n_hh_1p_66"] + x["n_hh_1p_oth"], x["n_hh"])
        o["cen21_pct_hh_lone_par"] = pct(x["n_hh_lone_dep"], x["n_hh"])
        o["cen21_pct_bad_health"] = pct(x["n_bad"], x["n_hlth_tot"])
        o["cen21_pct_not_wbrit"] = pct(x["n_eth_tot"] - x["n_wbrit"], x["n_eth_tot"])
        o["cen21_pct_asian"] = pct(x["n_asian"], x["n_eth_tot"])
        o["cen21_pct_black"] = pct(x["n_black"], x["n_eth_tot"])
        o["cen21_pct_mixed"] = pct(x["n_mixed"], x["n_eth_tot"])
        o["cen21_pct_other_eth"] = pct(x["n_oth_eth"], x["n_eth_tot"])
        o["cen21_pct_noqual"] = pct(x["n_noqual"], x["n_qual_tot"])
        o["cen21_pct_level4"] = pct(x["n_l4"], x["n_qual_tot"])
        o["cen21_unemp_rate"] = pct(x["n_unemp"], x["n_active"])
        o["cen21_res16p"] = x["n_res16p"].round(0)
        return o

    lsoa = lsoa.merge(pd.concat([c[["LSOA21CD"]], derive(c)], axis=1), on="LSOA21CD", how="left")
    lad = lad.merge(pd.concat([lad_c[["LAD25CD"]], derive(lad_c)], axis=1), on="LAD25CD", how="left")
    for k, a in {"cen21_pop": "Usual residents, Census 2021",
                 "cen21_density": "Residents per km², Census 2021",
                 "cen21_pct_age0_14": "% aged 0–14, Census 2021",
                 "cen21_pct_age65p": "% aged 65 and over, Census 2021",
                 "cen21_pct_hh_1p_66p": "% households: one person aged 66+, Census 2021",
                 "cen21_pct_hh_1p": "% one-person households, Census 2021",
                 "cen21_pct_hh_lone_par": "% households: lone parent with dependent children, Census 2021",
                 "cen21_pct_bad_health": "% in bad or very bad health, Census 2021",
                 "cen21_pct_not_wbrit": "% not White British, Census 2021",
                 "cen21_pct_asian": "% Asian, Asian British or Asian Welsh, Census 2021",
                 "cen21_pct_black": "% Black, Black British, Black Welsh, Caribbean or African, Census 2021",
                 "cen21_pct_mixed": "% Mixed or Multiple ethnic groups, Census 2021",
                 "cen21_pct_other_eth": "% Other ethnic group, Census 2021",
                 "cen21_pct_noqual": "% aged 16+ with no qualifications, Census 2021",
                 "cen21_pct_level4": "% aged 16+ with Level 4+ qualifications, Census 2021",
                 "cen21_unemp_rate": "Unemployed as % of economically active 16+, Census 2021 (lockdown period)",
                 "cen21_res16p": "Usual residents aged 16+, Census 2021"}.items():
        field(k, a, "census2021", {"lad", "lsoa"})
    return lad, lsoa


# ------------------------------------------------------------------ Mid-2025 population estimates
def header_frame(xl, sheet, must=("Code",)):
    raw = xl.parse(sheet, header=None)
    for i in range(min(20, len(raw))):
        row = [str(v) for v in raw.iloc[i].tolist()]
        if all(any(m.lower() == r.strip().lower() for r in row) for m in must):
            df = raw.iloc[i + 1:].copy()
            df.columns = [str(v).strip() for v in raw.iloc[i]]
            return df
    raise KeyError(f"{sheet}: header with {must} not found")


def mye(lad, lsoa):
    if not have("mye2025.xlsx"):
        return lad, lsoa
    xl = pd.ExcelFile(RAW / "mye2025.xlsx")
    s5 = next(s for s in xl.sheet_names if s.upper().startswith("MYE5"))
    d = header_frame(xl, s5)
    d["LAD25CD"] = d["Code"].astype(str).replace(LAD_RECODE)
    d = d[d["LAD25CD"].isin(lad["LAD25CD"])]
    o = pd.DataFrame({"LAD25CD": d["LAD25CD"]})
    for y in ("2025", "2024", "2021"):
        o[f"mye{y[2:]}_pop"] = pd.to_numeric(d[pick(d.columns, ["Estimated Population", f"mid-{y}"])], errors="coerce")
    o["mye25_density"] = pd.to_numeric(d[pick(d.columns, ["2025", "per sq"])], errors="coerce").round(1)
    o["mye_chg_24_25_pct"] = pct(o["mye25_pop"] - o["mye24_pop"], o["mye24_pop"]).round(2)
    o["mye_chg_21_25_pct"] = pct(o["mye25_pop"] - o["mye21_pop"], o["mye21_pop"]).round(2)
    s2 = next(s for s in xl.sheet_names if s.upper().startswith("MYE2") and "PERSON" in s.upper())
    a = header_frame(xl, s2)
    a["LAD25CD"] = a["Code"].astype(str).replace(LAD_RECODE)
    a = a[a["LAD25CD"].isin(lad["LAD25CD"])]
    ages = {int(float(c)): c for c in a.columns if re.fullmatch(r"\d+(\.0)?", str(c))}
    tot = pd.to_numeric(a[pick(a.columns, ["All ages"])], errors="coerce")
    g = pd.DataFrame({"LAD25CD": a["LAD25CD"],
                      "mye25_pct_age0_15": pct(a[[ages[i] for i in range(0, 16)]].apply(pd.to_numeric).sum(axis=1), tot),
                      "mye25_pct_age65p": pct(a[[ages[i] for i in ages if i >= 65]].apply(pd.to_numeric).sum(axis=1), tot),
                      "mye25_pop16_64": a[[ages[i] for i in range(16, 65)]].apply(pd.to_numeric).sum(axis=1)})
    o = o.merge(g, on="LAD25CD", how="left")
    lad = lad.merge(o, on="LAD25CD", how="left")
    for k, a_ in {"mye25_pop": "Population mid-2025 (ONS estimate)", "mye24_pop": "Population mid-2024 (ONS estimate)",
                  "mye21_pop": "Population mid-2021 (ONS estimate)", "mye25_density": "Residents per km², mid-2025",
                  "mye_chg_24_25_pct": "Population change mid-2024 to mid-2025, %",
                  "mye_chg_21_25_pct": "Population change mid-2021 to mid-2025, %",
                  "mye25_pct_age0_15": "% aged 0–15, mid-2025", "mye25_pct_age65p": "% aged 65 and over, mid-2025",
                  "mye25_pop16_64": "Population aged 16–64, mid-2025"}.items():
        field(k, a_, "mye2025", {"lad"})
    return lad, lsoa


# ------------------------------------------------------------------ Community and Engagement Survey 2025/26
# measure field -> (file key, regex matched against the table title/notes text)
CES_MEASURES = {
    "ces_civic_any": ("civic", r"civic engagement"),
    "ces_civic_part": ("civic", r"civic participation"),
    "ces_civic_cons": ("civic", r"civic consultation"),
    "ces_civic_act": ("civic", r"civic activism"),
    "ces_influence": ("decisions", r"(can )?personally influence"),
    "ces_involve": ("decisions", r"more involved"),
    "ces_vol_formal": ("volunteering", r"formal volunteering.*(once a month|monthly)"),
    "ces_belong": ("neighbourhood", r"belong"),
    "ces_trust": ("neighbourhood", r"trust"),
}
CES_ALIAS = {"ces_civic_any": "% any civic engagement in last 12 months",
             "ces_civic_part": "% civic participation in last 12 months",
             "ces_civic_cons": "% civic consultation in last 12 months",
             "ces_civic_act": "% civic activism in last 12 months",
             "ces_influence": "% agree they can influence local decisions",
             "ces_involve": "% want more involvement in council decisions",
             "ces_vol_formal": "% formal volunteering at least once a month",
             "ces_belong": "% feel they belong to their neighbourhood",
             "ces_trust": "% say many people in neighbourhood can be trusted"}


def find_header(raw, first):
    """Nearest row above `first` that looks like a header: 3+ cells, mostly text, no area codes."""
    for h in range(first - 1, -1, -1):
        row = [v for v in raw.iloc[h].tolist() if str(v) != "nan" and str(v).strip()]
        if len(row) < 3:
            continue
        numeric = sum(1 for v in row if re.fullmatch(r"-?[\d.,]+%?", str(v).strip()))
        if numeric / len(row) < 0.3 and not any(re.fullmatch(r"E\d{8}", str(v)) for v in row):
            return h
    raise KeyError("no header row found")


def ces_tables(path):
    """Yield (sheet, title_text, DataFrame) for every sheet holding LA-coded rows."""
    xl = pd.ExcelFile(path, engine="odf")
    for s in xl.sheet_names:
        raw = xl.parse(s, header=None)
        is_code = raw.astype(str).apply(lambda c: c.str.match(r"^E0[6-9]\d{6}$"))
        if is_code.values.sum() < 200:
            continue
        code_col = is_code.sum().idxmax()
        first = is_code[code_col].idxmax()
        hdr = find_header(raw, first)
        title = " ".join(str(v) for v in raw.iloc[:max(hdr, 1)].values.ravel() if str(v) != "nan")
        df = raw.iloc[hdr + 1:].copy()
        df.columns = [str(v).strip() for v in raw.iloc[hdr]]
        df = df.rename(columns={df.columns[code_col]: "code"})
        yield s, title, df


def ces(lad, lsoa):
    files = {k: f"ces2526_{k}.ods" for k in ("civic", "decisions", "neighbourhood", "volunteering")}
    if not have(*files.values()):
        return lad, lsoa
    out = pd.DataFrame({"LAD25CD": lad["LAD25CD"]})
    found = {}
    for fkey, fname in files.items():
        for s, title, df in ces_tables(RAW / fname):
            for m, (k, rx) in CES_MEASURES.items():
                if k != fkey or m in found or not re.search(rx, f"{s} {title}", re.I):
                    continue
                cols = list(df.columns)
                try:
                    est = pick(cols, ["%"], exclude=["lower", "upper", "confidence", "base"]) \
                        if any("%" in c for c in cols) else pick(cols, ["estimate"])
                    lo = pick(cols, ["lower"])
                    hi = pick(cols, ["upper"])
                except KeyError as e:
                    WARN.append(f"CES {m} in sheet {s}: {e}")
                    continue
                t = df[["code", est, lo, hi]].copy()
                t.columns = ["code", "est", "lo", "hi"]
                for c in ("est", "lo", "hi"):
                    t[c] = pd.to_numeric(t[c], errors="coerce")
                scale = 100 if t["est"].max() <= 1 else 1
                t[["est", "lo", "hi"]] *= scale
                eng = df[df.astype(str).apply(lambda r: r.str.fullmatch(r"England").any(), axis=1)]
                eng_val = pd.to_numeric(eng[est], errors="coerce").dropna()
                eng_val = eng_val.iloc[0] * scale if len(eng_val) else None
                t["LAD25CD"] = t["code"].replace(LAD_RECODE)
                t = t[t["LAD25CD"].isin(lad["LAD25CD"])].drop_duplicates("LAD25CD")
                out = out.merge(t[["LAD25CD", "est"]].rename(columns={"est": m}).assign(**{m: lambda x: x[m].round(1)}),
                                on="LAD25CD", how="left")
                if eng_val is not None:
                    sig = pd.Series("In line with England", index=t.index)
                    sig[t["lo"] > eng_val] = "Above England"
                    sig[t["hi"] < eng_val] = "Below England"
                    out = out.merge(pd.DataFrame({"LAD25CD": t["LAD25CD"], f"{m}_sig": sig}), on="LAD25CD", how="left")
                    field(f"{m}_sig", f"{CES_ALIAS[m]}: compared with England (95% CI)", "ces2526", {"lad"})
                field(m, f"{CES_ALIAS[m]}, CES 2025/26", "ces2526", {"lad"})
                found[m] = f"{fname} / {s}"
                log(f"CES {m} <- {fname} sheet {s} ({t['est'].notna().sum()} LAs, England {eng_val})")
    for m in CES_MEASURES:
        if m not in found:
            WARN.append(f"CES measure not found: {m}")
    lad = lad.merge(out, on="LAD25CD", how="left")
    return lad, lsoa


# ------------------------------------------------------------------ General election 2024 turnout
def ge2024(lad, lsoa):
    if not have("ge2024_constituency.csv"):
        return lad, lsoa, None
    d = pd.read_csv(RAW / "ge2024_constituency.csv", encoding="utf-8-sig")
    cols = d.columns
    code = pick(cols, ["ONS ID"]) if any("ons id" in c.lower() for c in cols) else pick(cols, ["code"])
    p = pd.DataFrame({"PCON24CD": d[code], "ge24_electorate": pd.to_numeric(d[pick(cols, ["Electorate"])], errors="coerce"),
                      "ge24_valid_votes": pd.to_numeric(d[pick(cols, ["Valid votes"])], errors="coerce"),
                      "ge24_invalid_votes": pd.to_numeric(d[pick(cols, ["Invalid votes"])], errors="coerce")})
    p = p[p["PCON24CD"].astype(str).str.startswith("E")]
    p["ge24_turnout"] = pct(p["ge24_valid_votes"], p["ge24_electorate"])
    field("ge24_electorate", "Electorate, general election 4 July 2024", "ge2024", {"pcon"})
    field("ge24_valid_votes", "Valid votes, general election 2024", "ge2024", {"pcon"})
    field("ge24_invalid_votes", "Invalid (rejected) votes, general election 2024", "ge2024", {"pcon"})
    field("ge24_turnout", "Turnout %, general election 2024 (valid votes ÷ electorate)", "ge2024", {"pcon"})
    lsoa = lsoa.merge(p[["PCON24CD", "ge24_turnout"]].rename(columns={"ge24_turnout": "ge24_turnout_pcon"}),
                      on="PCON24CD", how="left")
    field("ge24_turnout_pcon", "GE 2024 turnout % of the constituency this LSOA best fits", "ge2024", {"lsoa"})
    w = lsoa["cen21_res16p"] if "cen21_res16p" in lsoa else pd.Series(1.0, index=lsoa.index)
    t = pd.DataFrame({"LAD25CD": lsoa["LAD25CD"], "w": w, "wt": w * lsoa["ge24_turnout_pcon"],
                      "PCON24CD": lsoa["PCON24CD"]})
    g = t.groupby("LAD25CD").agg(wt=("wt", "sum"), w=("w", "sum"), n=("PCON24CD", "nunique")).reset_index()
    g["ge24_turnout_est"] = (g["wt"] / g["w"]).round(1)
    lad = lad.merge(g[["LAD25CD", "ge24_turnout_est"]].assign(ge24_pcon_count=g["n"]), on="LAD25CD", how="left")
    field("ge24_turnout_est", "GE 2024 turnout %, estimated for district (constituency turnout weighted by residents 16+)",
          "ge2024", {"lad"})
    field("ge24_pcon_count", "Number of constituencies overlapping district (LSOA best fit)", "ge2024", {"lad"})
    return lad, lsoa, p


# ------------------------------------------------------------------ Business counts (ONS ASL 2026)
def business(lad, lsoa):
    if not have("asl2026.xlsx"):
        return lad, lsoa
    xl = pd.ExcelFile(RAW / "asl2026.xlsx")
    ent = loc = None
    for s in xl.sheet_names:
        raw = xl.parse(s, header=None, nrows=8)
        title = " ".join(str(v) for v in raw.values.ravel() if str(v) != "nan").lower()
        if "employment size" in title and ("district" in title or "local authorit" in title):
            if "enterprise" in title and ent is None:
                ent = s
            elif "local unit" in title and loc is None:
                loc = s
    log("ASL sheets: enterprises", ent, "| local units", loc)
    if not ent:
        WARN.append("ASL: no enterprises-by-size-by-district sheet found; check _inspect.txt")
        return lad, lsoa

    def size_table(sheet):
        raw = xl.parse(sheet, header=None)
        is_code = raw.astype(str).apply(lambda c: c.str.match(r"^E0[6-9]\d{6}$"))
        code_col = is_code.sum().idxmax()
        first = is_code[code_col].idxmax()
        hdr = find_header(raw, first)
        df = raw.iloc[hdr + 1:].copy()
        df.columns = [str(v).strip() for v in raw.iloc[hdr]]
        df = df.rename(columns={df.columns[code_col]: "code"})
        df["LAD25CD"] = df["code"].astype(str).replace(LAD_RECODE)
        return df[df["LAD25CD"].isin(lad["LAD25CD"])].drop_duplicates("LAD25CD")

    e = size_table(ent)
    tot = pd.to_numeric(e[pick(e.columns, ["Total"])], errors="coerce")
    micro_cols = [c for c in e.columns if re.match(r"^0\s*-\s*4$|^5\s*-\s*9$", c.replace("to", "-"))]
    o = pd.DataFrame({"LAD25CD": e["LAD25CD"], "bus_enterprises": tot})
    if micro_cols:
        o["bus_pct_micro"] = pct(e[micro_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1), tot)
        field("bus_pct_micro", "% of enterprises with 0–9 employees, March 2026", "business2026", {"lad"})
    else:
        WARN.append(f"ASL: micro size-band columns not found in {list(e.columns)}")
    if loc:
        l = size_table(loc)
        o = o.merge(pd.DataFrame({"LAD25CD": l["LAD25CD"],
                                  "bus_local_units": pd.to_numeric(l[pick(l.columns, ["Total"])], errors="coerce")}),
                    on="LAD25CD", how="left")
        field("bus_local_units", "Business local units (VAT/PAYE), March 2026", "business2026", {"lad"})
    lad = lad.merge(o, on="LAD25CD", how="left")
    den = lad["mye25_pop16_64"] if "mye25_pop16_64" in lad else None
    if den is not None:
        lad["bus_ent_per1k_16_64"] = (1000 * lad["bus_enterprises"] / den).round(1)
        field("bus_ent_per1k_16_64", "Enterprises per 1,000 residents aged 16–64 (2026 / mid-2025)", "business2026", {"lad"})
    field("bus_enterprises", "VAT/PAYE enterprises, March 2026", "business2026", {"lad"})
    return lad, lsoa


# ------------------------------------------------------------------ Ofcom Connected Nations Spring 2026
def ofcom(lad, lsoa):
    fixed = RAW / "ofcom_fixed"
    oa_files = sorted(fixed.rglob("*fixed_oa_coverage*.csv")) if fixed.exists() else []
    oa_files = [p for p in oa_files if "_res_" not in p.name]
    if not oa_files:
        WARN.append("Ofcom: fixed OA coverage file not found")
        return lad, lsoa
    d = pd.read_csv(oa_files[0], encoding="utf-8-sig", low_memory=False)
    cols = list(d.columns)
    oa = pick(cols, ["output_area"]) if any("output_area" in c for c in cols) else pick(cols, ["oa"])
    prem = pick(cols, ["All Premises"]) if any(c.strip().lower() == "all premises" for c in cols) \
        else pick(cols, ["premises"], exclude=["%", "mbit", "gigabit", "sfbb", "ufbb", "uso", "nga", "fwa"])
    measures = {"ofc_pct_gigabit": (["Gigabit", "%"], "% premises with gigabit-capable broadband"),
                "ofc_pct_sfbb": (["SFBB", "%"], "% premises with superfast broadband (30 Mbit/s+)"),
                "ofc_pct_below10": (["unable to receive 10Mbit"], "% premises unable to get 10 Mbit/s download")}
    oa_lu = pd.DataFrame(load_json(RAW / "oa_lsoa.json"))
    t = d[[oa, prem]].rename(columns={oa: "OA21CD", prem: "prem"})
    for m, (must, alias) in measures.items():
        try:
            c = pick(cols, must, exclude=["FWA"])
        except KeyError as e:
            WARN.append(f"Ofcom OA: {e}")
            continue
        t["n_" + m] = pd.to_numeric(d[c], errors="coerce") / 100 * pd.to_numeric(d[prem], errors="coerce")
        field(m, f"{alias}, Ofcom Jan 2026", "ofcom2026", {"lad", "lsoa"})
    t["prem"] = pd.to_numeric(t["prem"], errors="coerce")
    t = t.merge(oa_lu, on="OA21CD", how="inner")
    sums = [c for c in t.columns if c.startswith("n_")] + ["prem"]
    by_lsoa = t.groupby("LSOA21CD")[sums].sum().reset_index()
    by_lad = by_lsoa.merge(lsoa[["LSOA21CD", "LAD25CD"]], on="LSOA21CD").groupby("LAD25CD")[sums].sum().reset_index()
    for df in (by_lsoa, by_lad):
        for m in measures:
            if "n_" + m in df:
                df[m] = pct(df["n_" + m], df["prem"])
        df["ofc_premises"] = df["prem"].round(0)
    keep = ["ofc_premises"] + [m for m in measures if m in by_lsoa]
    field("ofc_premises", "Premises (Ofcom premises base, Jan 2026)", "ofcom2026", {"lad", "lsoa"})
    lsoa = lsoa.merge(by_lsoa[["LSOA21CD"] + keep], on="LSOA21CD", how="left")
    lad = lad.merge(by_lad[["LAD25CD"] + keep], on="LAD25CD", how="left")

    # LA-only files: full fibre coverage/take-up and mobile coverage
    la_cols = {}
    for p in sorted(RAW.rglob("*laua*.csv")):
        la = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        lc = pick(la.columns, ["laua"], exclude=["name"])
        la["LAD25CD"] = la[lc].astype(str).replace(LAD_RECODE)
        la = la[la["LAD25CD"].isin(lad["LAD25CD"])]
        if "full_fibre_take" in p.name or "take-up" in p.name:
            try:
                c = pick(la.columns, ["take-up"])
                la_cols["ofc_ff_takeup"] = (la[["LAD25CD", c]], "Full-fibre take-up, % of premises with full-fibre coverage")
            except KeyError as e:
                WARN.append(f"Ofcom take-up: {e}")
        elif "fixed" in p.name and "_res_" not in p.name:
            try:
                c = pick(la.columns, ["Full Fibre", "%"])
                la_cols["ofc_pct_fullfibre"] = (la[["LAD25CD", c]], "% premises with full-fibre coverage")
            except KeyError as e:
                WARN.append(f"Ofcom full fibre: {e}")
        elif "mobile" in p.name:
            (RAW / "_ofcom_mobile_columns.txt").write_text("\n".join(la.columns))
            for m, must, alias in [("ofc_4g_in_all", ["4G", "prem", "in", "4"], "% premises with indoor 4G from all 4 operators"),
                                   ("ofc_4g_geo_all", ["4G", "geo", "4"], "% geographic area with outdoor 4G from all 4 operators"),
                                   ("ofc_5g_out_any", ["5G", "prem", "out", "1"], "% premises with outdoor 5G from at least one operator")]:
                try:
                    c = pick(la.columns, must)
                    la_cols[m] = (la[["LAD25CD", c]], alias)
                except KeyError as e:
                    WARN.append(f"Ofcom mobile {m}: {e}")
    for m, (df, alias) in la_cols.items():
        df = df.rename(columns={df.columns[1]: m})
        df[m] = pd.to_numeric(df[m], errors="coerce").round(1)
        lad = lad.merge(df.drop_duplicates("LAD25CD"), on="LAD25CD", how="left")
        field(m, f"{alias}, Ofcom Jan 2026", "ofcom2026", {"lad"})
    return lad, lsoa


# ------------------------------------------------------------------ outputs
def round_coords(geom, nd):
    def ring(r):
        out = []
        for x, y in r:
            pt = [round(x, nd), round(y, nd)]
            if not out or pt != out[-1]:
                out.append(pt)
        if out[0] != out[-1]:
            out.append(out[0])
        return out if len(out) >= 4 else None
    if geom["type"] == "Polygon":
        rings = [r for r in (ring(r) for r in geom["coordinates"]) if r]
        return {"type": "Polygon", "coordinates": rings}
    polys = []
    for p in geom["coordinates"]:
        rings = [r for r in (ring(r) for r in p) if r]
        if rings:
            polys.append(rings)
    return {"type": "MultiPolygon", "coordinates": polys}


def write_geojson(df, bnd_file, key, name, nd):
    fc = load_json(RAW / bnd_file)
    props = df.set_index(key).to_dict("index")
    feats = []
    for f in fc["features"]:
        k = f["properties"][key]
        if k not in props:
            continue
        p = {key: k, **{c: (None if pd.isna(v) else (int(v) if isinstance(v, float) and v.is_integer() and c.endswith(("_count", "_pop", "_rank", "_decile", "units", "enterprises", "premises", "electorate", "votes", "res16p")) else v))
                        for c, v in props[k].items()}}
        feats.append({"type": "Feature", "properties": p, "geometry": round_coords(f["geometry"], nd)})
    save_json({"type": "FeatureCollection", "features": feats}, OUT / f"{name}.geojson")
    df.to_csv(OUT / f"{name}.csv", index=False)
    log(f"wrote {name}: {len(feats)} features, {len(df.columns)} fields, "
        f"{(OUT / f'{name}.geojson').stat().st_size / 1e6:.1f} MB")


def main():
    lad, lsoa = base_tables()
    lad, lsoa = iod(lad, lsoa)
    lad, lsoa = census(lad, lsoa)
    lad, lsoa = mye(lad, lsoa)
    lad, lsoa = ces(lad, lsoa)
    lad, lsoa, pcon = ge2024(lad, lsoa)
    lad, lsoa = business(lad, lsoa)
    lad, lsoa = ofcom(lad, lsoa)

    lad["data_version"] = DATA_BUILD_VERSION
    lsoa["data_version"] = DATA_BUILD_VERSION
    field("data_version", "Data build version", "geography", {"lad", "lsoa", "pcon"})
    for col, a, tiers in [("LAD25CD", "District code (May 2025)", {"lad", "lsoa"}),
                          ("LAD25NM", "District name", {"lad", "lsoa"}),
                          ("LSOA21CD", "LSOA code (2021)", {"lsoa"}), ("LSOA21NM", "LSOA name (2021)", {"lsoa"}),
                          ("PCON24CD", "Constituency code (July 2024)", {"lsoa", "pcon"}),
                          ("PCON24NM", "Constituency name", {"lsoa", "pcon"})]:
        field(col, a, "geography", tiers)

    assert lad["LAD25CD"].is_unique and len(lad) == 296, len(lad)
    assert lsoa["LSOA21CD"].is_unique and len(lsoa) == 33755, len(lsoa)
    write_geojson(lad, "bnd_lad25.geojson", "LAD25CD", "nd_lad", 6)
    write_geojson(lsoa, "bnd_lsoa21.geojson", "LSOA21CD", "nd_lsoa", 5)
    if pcon is not None:
        names = pd.DataFrame(load_json(RAW / "lsoa_pcon24.json"))[["PCON24CD", "PCON24NM"]].drop_duplicates()
        pcon = names.merge(pcon, on="PCON24CD", how="left")
        pcon["data_version"] = DATA_BUILD_VERSION
        write_geojson(pcon, "bnd_pcon24.geojson", "PCON24CD", "nd_pcon", 6)

    meta = {"data_build_version": DATA_BUILD_VERSION, "source_versions": SOURCE_VERSIONS,
            "fields": {k: {**v, "tiers": sorted(v["tiers"])} for k, v in FIELDS.items()},
            "warnings": WARN}
    save_json(meta, OUT / "fields.json")
    log("warnings:\n  " + "\n  ".join(WARN) if WARN else "no warnings")


if __name__ == "__main__":
    main()
