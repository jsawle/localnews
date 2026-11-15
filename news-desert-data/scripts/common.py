"""Shared helpers for the news desert supplementary-data pipeline.

Data build version and per-source versions live here so every output
(CSV, GeoJSON, item descriptions) carries the same numbers.
"""
import json
import os
import re
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "out"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

DATA_BUILD_VERSION = "1.0.0"

# Bump a source's version whenever its download, parsing or maths changes.
SOURCE_VERSIONS = {
    "geography": "1.0.0",
    "iod2025": "1.0.0",
    "ruc2021": "1.0.0",
    "census2021": "1.0.0",
    "mye2025": "1.0.0",
    "ces2526": "1.0.0",
    "ge2024": "1.0.0",
    "business2026": "1.0.0",
    "ofcom2026": "1.0.0",
}

UA = {"User-Agent": "news-desert-pipeline/1.0 (+ArcGIS Online build)"}
ONS = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"
MHCLG = "https://services-eu1.arcgis.com/EbKcOS6EXZroSyoi/arcgis/rest/services"

# LAD vintage used throughout: May 2025 (296 English districts; same codes as May 2026).
# Older sources keyed on 2023/2024 codes use the two Barnsley/Sheffield recodes.
LAD_RECODE = {"E08000016": "E08000038", "E08000019": "E08000039"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 120), **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt == 3:
                raise
            log(f"retry {attempt + 1} for {url[:90]}: {e}")
            time.sleep(3 * (attempt + 1))


def download(url, dest, force=False):
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        log(f"cached {dest.name}")
        return dest
    log(f"downloading {url}")
    r = get(url, stream=True, timeout=600)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    log(f"saved {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def find_links(page_url, pattern):
    """Return absolute hrefs on a page whose URL matches a regex."""
    html = get(page_url).text
    hrefs = re.findall(r'href="([^"]+)"', html)
    out = []
    for h in hrefs:
        h = urllib.parse.urljoin(page_url, h.replace("&amp;", "&"))
        if re.search(pattern, h, re.I) and h not in out:
            out.append(h)
    return out


def arcgis_query(layer_url, where="1=1", out_fields="*", geometry=False,
                 out_sr=4326, max_offset=None, precision=None, page=2000,
                 order_by=None, fmt="json"):
    """Page through an ArcGIS feature layer. Returns list of attribute dicts,
    or a GeoJSON FeatureCollection dict when fmt='geojson'."""
    feats, off = [], 0
    while True:
        p = {"where": where, "outFields": out_fields, "returnGeometry": str(geometry).lower(),
             "f": fmt, "resultOffset": off, "resultRecordCount": page}
        if order_by:
            p["orderByFields"] = order_by
        if geometry:
            p["outSR"] = out_sr
            if max_offset:
                p["maxAllowableOffset"] = max_offset
            if precision:
                p["geometryPrecision"] = precision
        r = get(layer_url + "/query", params=p, timeout=300)
        d = r.json()
        if "error" in d:
            raise RuntimeError(f"{layer_url}: {d['error']}")
        batch = d.get("features", [])
        feats += batch
        more = d.get("exceededTransferLimit") or d.get("properties", {}).get("exceededTransferLimit")
        if not batch or not more:
            break
        off += len(batch)
    if fmt == "geojson":
        return {"type": "FeatureCollection", "features": feats}
    return [f["attributes"] for f in feats]


def save_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)


def load_json(path):
    with open(path) as f:
        return json.load(f)


def england_lad(code):
    return isinstance(code, str) and code[:3] in ("E06", "E07", "E08", "E09")
