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
    ages = {int(float(str(c).rstrip("+"))): c for c in a.columns if re.fullmatch(r"\d+(\.0)?\+?", str(c))}
    tot = pd.to_numeric(a[pick(a.columns, ["All ages"])], errors="coerce")
    g = pd.DataFrame({"LAD25CD": a["LAD25CD"],
                      "mye25_pct_age0_15": pct(a[[ages[i] for i in range(0, 16)]].apply(pd.to_numeric).sum(axis=1), tot),
                      "mye25_pct_age65p": pct(a[[ages[i] for i in ages if i >= 65]].apply(pd.to_numeric).sum(axis=1), tot),
                      "mye25_pop16_64": a[[ages[i] for i in range(16, 65)]].apply(pd.to_numeric).sum(axis=1)})
    o = o.merge(g, on="LAD25CD", how="left")
    s6 = next(s_ for s_ in xl.sheet_names if s_.upper().startswith("MYE6"))
    m6 = header_frame(xl, s6)
    m6["LAD25CD"] = m6["Code"].astype(str).replace(LAD_RECODE)
    o = o.merge(pd.DataFrame({"LAD25CD": m6["LAD25CD"],
                              "mye25_median_age": pd.to_numeric(m6["Mid-2025"], errors="coerce")}),
                on="LAD25CD", how="left")
    field("mye25_median_age", "Median age, mid-2025", "mye2025", {"lad"})
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
# field -> (file key, sheet, alias). Tables are DCMS's district tables (LAD25 codes, 2025/26 columns).
CES_TABLES = {
    "ces_civic_any": ("civic", "A12", "% any civic engagement (participation, consultation or activism), last 12 months"),
    "ces_civic_part": ("civic", "A3", "% civic participation, last 12 months"),
    "ces_civic_cons": ("civic", "A6", "% civic consultation, last 12 months"),
    "ces_civic_act": ("civic", "A9", "% civic activism, last 12 months"),
    "ces_influence": ("decisions", "B3", "% agree they can personally influence local decisions"),
    "ces_involve": ("decisions", "B8", "% would like more involvement in council decisions"),
    "ces_belong": ("neighbourhood", "D3", "% strong sense of belonging to neighbourhood"),
    "ces_trust": ("neighbourhood", "D12", "% say many people in neighbourhood can be trusted"),
    "ces_news_use": ("neighbourhood", "D21", "% who watch, read or listen to local news at all"),
    "ces_news_unaware": ("neighbourhood", "D23", "% who don't know any local news providers"),
    "ces_vol_formal": ("volunteering", "G3", "% formal volunteering at least once a month"),
}


def ces_table(path, sheet):
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="odf")
    h = next(i for i in range(min(20, len(raw)))
             if any(str(v).strip().lower().startswith("percentage 2025/26") for v in raw.iloc[i].tolist()))
    cols = [str(v).strip() for v in raw.iloc[h].tolist()]
    df = raw.iloc[h + 1:].copy()
    df.columns = cols
    est = pick(cols, ["Percentage 2025/26"], exclude=["Lower", "Upper"])
    lo = pick(cols, ["Lower", "2025/26"])
    hi = pick(cols, ["Upper", "2025/26"])
    base = pick(cols, ["Unweighted base", "2025/26"])
    first = df.iloc[0]   # first row after the header is England
    eng = (float(pd.to_numeric(first[est], errors="coerce")), float(pd.to_numeric(first[lo], errors="coerce")),
           float(pd.to_numeric(first[hi], errors="coerce")))
    t = df[df["LAD25 code"].astype(str).str.match(r"^E0[6-9]\d{6}$")]
    out = pd.DataFrame({"LAD25CD": t["LAD25 code"].astype(str).replace(LAD_RECODE),
                        "est": pd.to_numeric(t[est], errors="coerce"),
                        "lo": pd.to_numeric(t[lo], errors="coerce"),
                        "hi": pd.to_numeric(t[hi], errors="coerce"),
                        "base": pd.to_numeric(t[base], errors="coerce")})
    return out, eng


def ces(lad, lsoa):
    files = {k: f"ces2526_{k}.ods" for k in ("civic", "decisions", "neighbourhood", "volunteering")}
    if not have(*files.values()):
        return lad, lsoa
    for m, (fkey, sheet, alias) in CES_TABLES.items():
        try:
            t, eng = ces_table(RAW / files[fkey], sheet)
        except Exception as e:  # noqa: BLE001
            WARN.append(f"CES {m} ({files[fkey]} {sheet}): {e}")
            continue
        # DCMS's rule: different from England only where the two 95% confidence intervals don't overlap
        e_est, e_lo, e_hi = eng
        sig = pd.Series("In line with England", index=t.index)
        sig[t["lo"] > e_hi] = "Above England"
        sig[t["hi"] < e_lo] = "Below England"
        o = pd.DataFrame({"LAD25CD": t["LAD25CD"], m: t["est"].round(1), f"{m}_sig": sig})
        if m == "ces_civic_any":
            o["ces_base"] = t["base"]
            field("ces_base", "Survey respondents in district (unweighted base, CES 2025/26)", "ces2526", {"lad"})
        lad = lad.merge(o.drop_duplicates("LAD25CD"), on="LAD25CD", how="left")
        field(m, f"{alias}, CES 2025/26", "ces2526", {"lad"})
        field(f"{m}_sig", f"{alias}: compared with England {e_est:.1f}% (95% CIs don't overlap)", "ces2526", {"lad"})
        log(f"CES {m} <- {sheet}: {t['est'].notna().sum()} districts, England {e_est:.1f}%, "
            f"above {int((sig == 'Above England').sum())}, below {int((sig == 'Below England').sum())}")
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
def asl_table(xl, number):
    sheet = next(s_ for s_ in xl.sheet_names if s_.strip() == f"Table {number}")
    raw = xl.parse(sheet, header=None)
    h = next(i for i in range(min(15, len(raw)))
             if {"0-4", "Total"} <= {str(v).strip() for v in raw.iloc[i].tolist()})
    cols = ["area"] + [str(v).strip() for v in raw.iloc[h].tolist()[1:]]
    df = raw.iloc[h + 1:].copy()
    df.columns = cols
    df["code"] = df["area"].astype(str).str.extract(r"^([EWSNK]\d{8})\s*:")[0]
    df = df[df["code"].notna()].copy()
    df["LAD25CD"] = df["code"].replace(LAD_RECODE)
    for c in ["0-4", "5-9", "10-19", "20-49", "50-99", "100-249", "250+", "Total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.drop_duplicates("LAD25CD")


def business(lad, lsoa):
    if not have("asl2026.xlsx"):
        return lad, lsoa
    xl = pd.ExcelFile(RAW / "asl2026.xlsx")
    e = asl_table(xl, 10)   # enterprises by district and employment size band
    u = asl_table(xl, 22)   # local units by district and employment size band
    o = pd.DataFrame({"LAD25CD": e["LAD25CD"], "bus_enterprises": e["Total"],
                      "bus_pct_micro": pct(e["0-4"] + e["5-9"], e["Total"])})
    o = o.merge(pd.DataFrame({"LAD25CD": u["LAD25CD"], "bus_local_units": u["Total"]}), on="LAD25CD", how="left")
    lad = lad.merge(o, on="LAD25CD", how="left")
    missing = lad["bus_enterprises"].isna().sum()
    if missing:
        WARN.append(f"ASL: {missing} districts without enterprise counts")
    field("bus_enterprises", "VAT/PAYE enterprises, March 2026", "business2026", {"lad"})
    field("bus_pct_micro", "% of enterprises with 0–9 employees, March 2026", "business2026", {"lad"})
    field("bus_local_units", "VAT/PAYE business local units, March 2026", "business2026", {"lad"})
    if "mye25_pop16_64" in lad:
        lad["bus_ent_per1k_16_64"] = (1000 * lad["bus_enterprises"] / lad["mye25_pop16_64"]).round(1)
        field("bus_ent_per1k_16_64", "Enterprises per 1,000 residents aged 16–64 (March 2026 / mid-2025)",
              "business2026", {"lad"})
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
    def la_file(pattern):
        p = sorted(RAW.rglob(pattern))
        if not p:
            WARN.append(f"Ofcom: no file {pattern}")
            return None
        d = pd.read_csv(p[0], encoding="utf-8-sig", low_memory=False)
        d["LAD25CD"] = d["laua"].astype(str).replace(LAD_RECODE)
        return d[d["LAD25CD"].isin(lad["LAD25CD"])].drop_duplicates("LAD25CD")

    num = lambda s_: pd.to_numeric(s_, errors="coerce")  # noqa: E731
    o = pd.DataFrame({"LAD25CD": lad["LAD25CD"]})
    fx = la_file("*fixed_laua_coverage_r*.csv")
    if fx is not None:
        o = o.merge(pd.DataFrame({"LAD25CD": fx["LAD25CD"],
                                  "ofc_pct_fullfibre": num(fx["Full Fibre availability (% premises)"]).round(1)}),
                    on="LAD25CD", how="left")
        field("ofc_pct_fullfibre", "% premises with full-fibre coverage, Ofcom Jan 2026", "ofcom2026", {"lad"})
    tu = la_file("*full_fibre_take-up_laua*.csv")
    if tu is not None:
        o = o.merge(pd.DataFrame({"LAD25CD": tu["LAD25CD"],
                                  "ofc_ff_takeup": num(tu["Full-fibre take-up (% of full-fibre coverage)"])}),
                    on="LAD25CD", how="left")
        field("ofc_ff_takeup", "Full-fibre take-up, % of premises that can get it, Ofcom Jan 2026", "ofcom2026", {"lad"})
    mb = la_file("*mobile_coverage_laua*.csv")
    if mb is not None:
        # Columns give the % of premises/area covered by exactly 0,1,2,3,4 operators; blanks are 0.
        g = lambda c: num(mb[c]).fillna(0)  # noqa: E731
        o = o.merge(pd.DataFrame({"LAD25CD": mb["LAD25CD"],
                                  "ofc_4g_in_none": g("4G_prem_in_0").round(2),
                                  "ofc_4g_in_all": g("4G_prem_in_4").round(1),
                                  "ofc_4g_geo_all": g("4G_geo_out_4").round(1),
                                  "ofc_5g_out_any": (100 - g("5G_high_confidence_prem_out_0")).round(1)}),
                    on="LAD25CD", how="left")
        for k, a in {"ofc_4g_in_none": "% premises with no indoor 4G from any operator",
                     "ofc_4g_in_all": "% premises with indoor 4G from all four operators",
                     "ofc_4g_geo_all": "% land area with outdoor 4G from all four operators",
                     "ofc_5g_out_any": "% premises with outdoor 5G (high confidence) from at least one operator"}.items():
            field(k, f"{a}, Ofcom Jan 2026", "ofcom2026", {"lad"})
    lad = lad.merge(o, on="LAD25CD", how="left")
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
