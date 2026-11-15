"""Smoke test: generate synthetic versions of the web downloads (shaped like the real
files as far as known) and run build.py against them in a temp raw folder."""
import json, shutil, sys, tempfile, zipfile
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import common
src = common.RAW
tmp = Path(tempfile.mkdtemp()); raw = tmp / "raw"; out = tmp / "out"; raw.mkdir(); out.mkdir()
for f in ["lsoa_lad25.json","lsoa_pcon24.json","oa_lsoa.json","bnd_lad25.geojson","bnd_pcon24.geojson","bnd_lsoa21.geojson","iod_lsoa_mhclg.json","iod_lad_mhclg.json","ruc_lad24.json"]:
    (raw/f).symlink_to(src/f)
rng = np.random.default_rng(1)
lsoa = pd.DataFrame(json.load(open(src/"lsoa_lad25.json")))
codes = lsoa.LSOA21CD.tolist(); n=len(codes)
def nomis(t, cols):
    df = pd.DataFrame({"date":2021,"geography":codes,"geography code":codes})
    for c,v in cols.items(): df[c]=v
    df.to_csv(raw/f"census2021-{t}-lsoa.csv", index=False)
pop = rng.integers(1000,3000,n)
nomis("ts001", {"Residence type: Total; measures: Value":pop, "Residence type: Lives in a household; measures: Value":pop-10})
nomis("ts006", {"Population Density: Persons per square kilometre; measures: Value":rng.uniform(50,20000,n)})
bands=["Aged 4 years and under","Aged 5 to 9 years","Aged 10 to 14 years","Aged 15 to 19 years","Aged 65 to 69 years","Aged 70 to 74 years","Aged 75 to 79 years","Aged 80 to 84 years","Aged 85 years and over"]
nomis("ts007a", {"Age: Total":pop, **{f"Age: {b}":pop//20 for b in bands}})
nomis("ts003", {"Household composition: Total; measures: Value":pop//2, "Household composition: One-person household; measures: Value":pop//6,
  "Household composition: One-person household: Aged 66 years and over; measures: Value":pop//12, "Household composition: One-person household: Other; measures: Value":pop//12,
  "Household composition: Single family household: Lone parent family; measures: Value":pop//20,
  "Household composition: Single family household: Lone parent family: With dependent children; measures: Value":pop//30})
nomis("ts021", {"Ethnic group: Total: All usual residents":pop, "Ethnic group: Asian, Asian British or Asian Welsh":pop//10,"Ethnic group: Asian, Asian British or Asian Welsh: Indian":pop//30,
  "Ethnic group: Black, Black British, Black Welsh, Caribbean or African":pop//20,"Ethnic group: Mixed or Multiple ethnic groups":pop//30,
  "Ethnic group: Mixed or Multiple ethnic groups: Other Mixed or Multiple ethnic groups":pop//90,"Ethnic group: White":pop//2,
  "Ethnic group: White: English, Welsh, Scottish, Northern Irish or British":pop//2,"Ethnic group: Other ethnic group":pop//40,"Ethnic group: Other ethnic group: Arab":pop//100})
nomis("ts037", {"General health: Total: All usual residents":pop,"General health: Very good health":pop//2,"General health: Bad health":pop//20,"General health: Very bad health":pop//60})
nomis("ts066", {"Economic activity status: Total: All usual residents aged 16 years and over":pop*0.8,
  "Economic activity status: Economically active (excluding full-time students)":pop*0.5,
  "Economic activity status: Economically active (excluding full-time students): In employment":pop*0.47,
  "Economic activity status: Economically active (excluding full-time students): Unemployed":pop*0.03,
  "Economic activity status: Economically active and a full-time student":pop*0.04,
  "Economic activity status: Economically active and a full-time student: Unemployed":pop*0.01})
nomis("ts067", {"Highest level of qualification: Total: All usual residents aged 16 years and over":pop*0.8,"Highest level of qualification: No qualifications":pop*0.15,"Highest level of qualification: Level 4 qualifications or above":pop*0.3})
lad = pd.DataFrame(json.load(open(src/"iod_lad_mhclg.json")))
lad_codes = lad.LAD24CD.tolist()
# MYE workbook
with pd.ExcelWriter(raw/"mye2025.xlsx") as xw:
    hdr = ["Code","Name","Geography","Area (sq km)","Estimated Population mid-2025","2025 people per sq. km","Estimated Population mid-2024","2024 people per sq. km","Estimated Population mid-2021","2021 people per sq. km"]
    rows=[["E92000001","England","Country",130000,58e6,446,57.8e6,444,56.5e6,434]]+[[c,"x","District",100,200000,2000,198000,1980,190000,1900] for c in lad_codes]
    pd.DataFrame([["MYE5: Population density"],[""],hdr]+rows).to_excel(xw, sheet_name="MYE5", header=False, index=False)
    hdr2=["Code","Name","Geography","All ages"]+[str(i) for i in range(91)]
    rows2=[[c,"x","District",200000]+[2200]*91 for c in lad_codes]
    pd.DataFrame([["MYE2 persons"],hdr2]+rows2).to_excel(xw, sheet_name="MYE2 - Persons", header=False, index=False)
# CES ods
for key, titles in {"civic":["Table 3.1: Civic engagement at least once in the last 12 months, by local authority","Table 3.2: Civic participation by local authority"],
                    "decisions":["Table 1.11: Agree they can personally influence decisions affecting their local area, by local authority"],
                    "neighbourhood":["Table 1.11: Feel they belong to their neighbourhood, by local authority","Table 4.11: Many people in neighbourhood can be trusted, by local authority"],
                    "volunteering":["Table 2.3: Formal volunteering at least once a month, by local authority"]}.items():
    with pd.ExcelWriter(raw/f"ces2526_{key}.ods", engine="odf") as xw:
        for i,t in enumerate(titles):
            body=[[t],["Source: CES"],["Area code","Area name","Percentage (%)","Lower confidence limit (%)","Upper confidence limit (%)","Base"]]
            body+=[["E92000001","England",46,45.8,46.2,175000]]
            body+=[[c,"x",float(rng.uniform(35,60)),40,52,500] for c in lad_codes]
            pd.DataFrame(body).to_excel(xw, sheet_name=f"T{i}", header=False, index=False)
# GE2024
pc = pd.DataFrame(json.load(open(src/"lsoa_pcon24.json")))[["PCON24CD","PCON24NM"]].drop_duplicates()
pd.DataFrame({"ONS ID":pc.PCON24CD,"Constituency name":pc.PCON24NM,"Electorate":72000,"Valid votes":rng.integers(30000,50000,len(pc)),"Invalid votes":150}).to_csv(raw/"ge2024_constituency.csv",index=False)
# ASL
with pd.ExcelWriter(raw/"asl2026.xlsx") as xw:
    for nm,t in [("Table 4","Table 4: Enterprises by employment size band and local authority district"),("Table 9","Table 9: Local units by employment size band and local authority district")]:
        body=[[t],[""],["Code","District","0-4","5-9","10-19","20-49","50-99","100-249","250+","Total"]]+[[c,"x",500,100,50,20,10,5,2,687] for c in lad_codes]
        pd.DataFrame(body).to_excel(xw, sheet_name=nm, header=False, index=False)
# Ofcom
oa = pd.DataFrame(json.load(open(src/"oa_lsoa.json")))
(raw/"ofcom_fixed").mkdir()
pd.DataFrame({"output_area":oa.OA21CD,"All Premises":150,"SFBB availability (% premises)":95.0,"Gigabit availability (% premises)":80.0,"% of premises unable to receive 10Mbit/s":1.0}).to_csv(raw/"ofcom_fixed"/"202601_fixed_oa_coverage_r1.csv",index=False)
pd.DataFrame({"laua":lad_codes,"laua_name":"x","Full Fibre availability (% premises)":80.0}).to_csv(raw/"ofcom_fixed"/"202601_fixed_laua_coverage_r1.csv",index=False)
pd.DataFrame({"laua":lad_codes,"laua_name":"x","Full-fibre take-up (% of full-fibre coverage)":40.0}).to_csv(raw/"ofcom_fixed"/"202601_full_fibre_take-up_laua_r1.csv",index=False)
(raw/"ofcom_mobile").mkdir()
pd.DataFrame({"laua":lad_codes,"laua_name":"x","4G_prem_in_4":70.0,"4G_geo_out_4":60.0,"5G_prem_out_1":90.0}).to_csv(raw/"ofcom_mobile"/"202601_mobile_coverage_laua_r1.csv",index=False)
# run build with patched paths
import build
build.RAW = raw; build.OUT = out; common.RAW = raw; common.OUT = out
build.main()
lad_out = pd.read_csv(out/"nd_lad.csv"); lsoa_out = pd.read_csv(out/"nd_lsoa.csv")
print(lad_out.shape, lsoa_out.shape)
print(lad_out.isna().sum()[lad_out.isna().sum()>0])
print(lad_out.iloc[0].to_string()[:3000])
