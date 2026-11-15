"""Stage 1: download every source into data/raw.

    python scripts/fetch.py            # everything
    python scripts/fetch.py arcgis     # only ArcGIS-hosted sources (boundaries, lookups, IoD services, RUC)
    python scripts/fetch.py web        # only the web downloads (GOV.UK, ONS, Nomis, Ofcom, Parliament)
    python scripts/fetch.py census ofcom ...   # named sources

Each source writes into data/raw/<name>... and is skipped if already cached.
"""
import sys
import zipfile

from common import (MHCLG, ONS, RAW, arcgis_query, download, find_links, log,
                    save_json)

# ---------------------------------------------------------------- ArcGIS-hosted
LSOA_BFE = f"{ONS}/LSOA_2021_EW_BFE_V10_RUC/FeatureServer/3"


def fetch_geography():
    p = RAW / "lsoa_lad25.json"
    if not p.exists():
        rows = arcgis_query(f"{ONS}/LSOA21_WD25_LAD25_EW_LU_v2/FeatureServer/0",
                            where="LAD25CD LIKE 'E%'",
                            out_fields="LSOA21CD,LSOA21NM,WD25CD,WD25NM,LAD25CD,LAD25NM")
        save_json(rows, p); log("lsoa->lad25", len(rows))
    p = RAW / "lsoa_pcon24.json"
    if not p.exists():
        rows = arcgis_query(f"{ONS}/LSOA21_PCON24_LAD21_EW_LU/FeatureServer/0",
                            where="LSOA21CD LIKE 'E%'", out_fields="LSOA21CD,PCON24CD,PCON24NM")
        save_json(rows, p); log("lsoa->pcon24", len(rows))
    p = RAW / "oa_lsoa.json"
    if not p.exists():
        rows = arcgis_query(f"{ONS}/OA_LSOA_MSOA_EW_DEC_2021_LU_v3/FeatureServer/0",
                            where="OA21CD LIKE 'E%'", out_fields="OA21CD,LSOA21CD")
        save_json(rows, p); log("oa->lsoa", len(rows))
    # Boundaries as GeoJSON (WGS84)
    p = RAW / "bnd_lad25.geojson"
    if not p.exists():
        fc = arcgis_query(f"{ONS}/LAD_MAY_2025_UK_BGC_V2/FeatureServer/0", where="LAD25CD LIKE 'E%'",
                          out_fields="LAD25CD,LAD25NM", geometry=True, precision=6,
                          order_by="LAD25CD", fmt="geojson")
        save_json(fc, p); log("LAD boundaries", len(fc["features"]))
    p = RAW / "bnd_pcon24.geojson"
    if not p.exists():
        fc = arcgis_query(f"{ONS}/Westminster_Parliamentary_Constituencies_July_2024_Boundaries_UK_BGC/FeatureServer/0",
                          where="PCON24CD LIKE 'E%'", out_fields="PCON24CD,PCON24NM", geometry=True,
                          precision=6, order_by="PCON24CD", fmt="geojson")
        save_json(fc, p); log("PCON boundaries", len(fc["features"]))
    p = RAW / "bnd_lsoa21.geojson"
    if not p.exists():
        # Full-resolution ONS boundaries generalised server-side to about 10–15 m (similar to ONS BGC 20 m).
        fc = arcgis_query(LSOA_BFE, where="LSOA21CD LIKE 'E%'",
                          out_fields="LSOA21CD,LSOA21NM,RUC21CD,RUC21NM,Urban_rura",
                          geometry=True, max_offset=0.00015, precision=6,
                          order_by="LSOA21CD", fmt="geojson")
        save_json(fc, p); log("LSOA boundaries", len(fc["features"]))


def fetch_iod_services():
    p = RAW / "iod_lsoa_mhclg.json"
    if not p.exists():
        rows = arcgis_query(f"{MHCLG}/LSOA_IMD2025_OSGB1936/FeatureServer/0",
                            out_fields="LSOA21CD,IMDRank,IMDDecil")
        save_json(rows, p); log("IoD LSOA (MHCLG service)", len(rows))
    p = RAW / "iod_lad_mhclg.json"
    if not p.exists():
        rows = arcgis_query(f"{MHCLG}/LA_LT_IMD2025_OSGB1936/FeatureServer/0",
                            out_fields="LAD24CD,LAD24NM,RAvgRankLTLA,RAvgScorLTLA,RPLMD10LTLA,RExtLTLA,RLocConLTLA")
        save_json(rows, p); log("IoD LAD (MHCLG service)", len(rows))


def fetch_ruc():
    p = RAW / "ruc_lad24.json"
    if not p.exists():
        rows = arcgis_query(f"{ONS}/LAD24_RUC21_EW_LU/FeatureServer/0", where="LAD24CD LIKE 'E%'",
                            out_fields="LAD24CD,LAD24NM,RUC21CD,RUC21NM,Urban_rural_flag")
        save_json(rows, p); log("RUC LAD", len(rows))
    # LSOA RUC comes with the LSOA boundaries (fetch_geography).


# ---------------------------------------------------------------- web downloads
IOD_FILE7 = ("https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/"
             "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv")
CENSUS_TABLES = ["ts001", "ts003", "ts006", "ts007a", "ts021", "ts037", "ts066", "ts067"]
CES_PAGES = {
    "civic": "https://www.gov.uk/government/statistics/community-and-engagement-survey-202526-civic-engagement",
    "decisions": "https://www.gov.uk/government/statistics/community-and-engagement-survey-202526-local-decisions",
    "neighbourhood": "https://www.gov.uk/government/statistics/community-and-engagement-survey-202526-neighbourhood",
    "volunteering": "https://www.gov.uk/government/statistics/community-and-engagement-survey-202526-volunteering",
}
MYE_PAGE = ("https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/"
            "populationestimates/datasets/estimatesofthepopulationforenglandandwales")
ASL_PAGE = ("https://www.ons.gov.uk/businessindustryandtrade/business/activitysizeandlocation/"
            "datasets/ukbusinessactivitysizeandlocation")
OFCOM_PAGE = "https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/connected-nations-update-spring-2026"
GE2024_CANDIDATES = [
    "https://researchbriefings.files.parliament.uk/documents/CBP-10009/HoC-GE2024-results-by-constituency.csv",
]
GE2024_PAGE = "https://commonslibrary.parliament.uk/research-briefings/cbp-10009/"


def fetch_iod_file7():
    download(IOD_FILE7, RAW / "iod2025_file7.csv")


def fetch_census():
    for t in CENSUS_TABLES:
        z = download(f"https://www.nomisweb.co.uk/output/census/2021/census2021-{t}.zip",
                     RAW / f"census2021-{t}.zip")
        with zipfile.ZipFile(z) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith("-lsoa.csv")]
            if not names:
                raise RuntimeError(f"{t}: no LSOA csv in {zf.namelist()}")
            zf.extract(names[0], RAW)
            (RAW / names[0]).rename(RAW / f"census2021-{t}-lsoa.csv")
            log(f"{t}: extracted {names[0]}")


def fetch_mye():
    links = find_links(MYE_PAGE, r"mid2025.*\.xlsx$|2025.*\.xlsx$")
    log("MYE candidate links:", *links, sep="\n  ")
    if not links:
        raise RuntimeError("No mid-2025 xlsx link found on the MYE dataset page")
    download(links[0], RAW / "mye2025.xlsx")


def fetch_ces():
    for key, page in CES_PAGES.items():
        links = find_links(page, r"\.ods$")
        log(f"CES {key}:", *links, sep="\n  ")
        if not links:
            raise RuntimeError(f"No ODS on {page}")
        download(links[0], RAW / f"ces2526_{key}.ods")


def fetch_ge2024():
    for url in GE2024_CANDIDATES:
        try:
            download(url, RAW / "ge2024_constituency.csv")
            return
        except Exception as e:  # noqa: BLE001
            log(f"GE2024 candidate failed: {e}")
    links = find_links(GE2024_PAGE, r"\.csv$")
    log("GE2024 CSV links on briefing page:", *links, sep="\n  ")
    pick = [u for u in links if "constituency" in u.lower()] or links
    if not pick:
        raise RuntimeError("No GE2024 constituency CSV found")
    download(pick[0], RAW / "ge2024_constituency.csv")


def fetch_business():
    links = find_links(ASL_PAGE, r"\.xlsx$")
    log("ASL links:", *links[:6], sep="\n  ")
    pick = [u for u in links if "2026" in u] or links
    download(pick[0], RAW / "asl2026.xlsx")


def fetch_ofcom():
    links = find_links(OFCOM_PAGE, r"\.zip")
    log("Ofcom zips:", *links, sep="\n  ")
    for u in links:
        name = "ofcom_fixed.zip" if "fixed" in u.lower() else "ofcom_mobile.zip" if "mobile" in u.lower() else None
        if name:
            z = download(u, RAW / name)
            with zipfile.ZipFile(z) as zf:
                log(name, "contains", len(zf.namelist()), "files:", *zf.namelist()[:12])
                zf.extractall(RAW / name.replace(".zip", ""))


ARCGIS = {"geography": fetch_geography, "iod_services": fetch_iod_services, "ruc": fetch_ruc}
WEB = {"iod_file7": fetch_iod_file7, "census": fetch_census, "mye": fetch_mye, "ces": fetch_ces,
       "ge2024": fetch_ge2024, "business": fetch_business, "ofcom": fetch_ofcom}

if __name__ == "__main__":
    args = sys.argv[1:] or ["arcgis", "web"]
    todo = {}
    for a in args:
        if a == "arcgis":
            todo.update(ARCGIS)
        elif a == "web":
            todo.update(WEB)
        else:
            todo[a] = {**ARCGIS, **WEB}[a]
    failed = []
    for name, fn in todo.items():
        log(f"== {name}")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            log(f"FAILED {name}: {e}")
    log("done; failed:", failed or "none")
    sys.exit(1 if failed else 0)
