"""Dump the structure of every raw web download (headers, sheet titles, first rows)
into data/raw/_inspect.txt, so parsers can be checked against the real files."""
import csv
import re
import zipfile
from pathlib import Path

import pandas as pd

from common import RAW

out = []


def w(*a):
    out.append(" ".join(str(x) for x in a))


def csv_head(p, n=3):
    with open(p, newline="", encoding="utf-8-sig", errors="replace") as f:
        r = csv.reader(f)
        for i, row in enumerate(r):
            w("   ", row if i == 0 else row[:12])
            if i >= n:
                break


for p in sorted(RAW.rglob("*")):
    if p.is_dir() or p.name.startswith("_") or p.suffix in (".json", ".geojson", ".zip", ".part"):
        continue
    w(f"\n### {p.relative_to(RAW)}  ({p.stat().st_size / 1e6:.1f} MB)")
    try:
        if p.suffix.lower() == ".csv":
            csv_head(p)
        elif p.suffix.lower() in (".xlsx", ".ods"):
            engine = "odf" if p.suffix.lower() == ".ods" else "openpyxl"
            xl = pd.ExcelFile(p, engine=engine)
            for s in xl.sheet_names:
                df = xl.parse(s, header=None, nrows=14)
                cells = [str(v) for v in df.fillna("").values.ravel() if str(v).strip()]
                la = 0
                try:
                    full = xl.parse(s, header=None)
                    la = int(full.astype(str).apply(lambda c: c.str.match(r"^E0[6-9]\d{6}$")).values.sum())
                except Exception:  # noqa: BLE001
                    pass
                w(f"  [sheet] {s}  | LA-code cells: {la}")
                w("     ", " || ".join(cells[:40])[:1500])
    except Exception as e:  # noqa: BLE001
        w("   ERROR", e)

(RAW / "_inspect.txt").write_text("\n".join(out))
print("\n".join(out)[:20000])
