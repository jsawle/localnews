"""District-level associations between PINF local news provision and supplementary data (England, n=296)."""
import json, numpy as np, pandas as pd
from scipy import stats

OUT = "/home/claude/nd/analysis"
d = pd.read_csv("/home/claude/nd/data/out/nd_lad.csv")
p = pd.DataFrame(json.load(open("/home/claude/nd/data/out/pinf_districts.json")))
df = d.merge(p, on="LAD25CD", suffixes=("", "_p"))
df["log_pop"] = np.log(df.mye25_pop); df["log_density"] = np.log(df.mye25_density)
df["deprivation"] = 297 - df.imd_rank_avg_score            # higher = more deprived
df["desert"] = df.pinf_class.isin(["Absolute news desert", "Relative news desert"]).astype(int)
df["low_prov"] = df.pinf_class.isin(["Absolute news desert", "Relative news desert", "Dryland"]).astype(int)
df["indep_share"] = np.where(df.pinf_titles > 0, df.pinf_n_independent / df.pinf_titles.clip(lower=1), np.nan)

X = {  # explanatory measures
    "ge24_turnout_est": "GE 2024 turnout", "ces_civic_any": "Any civic engagement", "ces_civic_part": "Civic participation",
    "ces_civic_cons": "Civic consultation", "ces_civic_act": "Civic activism", "ces_influence": "Feel can influence local decisions",
    "ces_involve": "Want more involvement", "ces_belong": "Belong to neighbourhood", "ces_trust": "Trust people in neighbourhood",
    "ces_vol_formal": "Formal volunteering", "ces_news_use": "Use local news at all", "ces_news_unaware": "Know no local news provider",
    "deprivation": "Deprivation (IMD 2025)", "log_density": "Population density", "log_pop": "Population",
    "mye25_median_age": "Median age", "cen21_pct_age65p": "% aged 65+", "cen21_pct_not_wbrit": "% not White British",
    "cen21_pct_noqual": "% no qualifications", "cen21_pct_level4": "% degree-level", "cen21_unemp_rate": "Unemployment",
    "cen21_pct_bad_health": "% bad health", "mye_chg_21_25_pct": "Population growth 2021–25",
    "bus_ent_per1k_16_64": "Businesses per 1,000 aged 16–64", "ofc_pct_gigabit": "Gigabit broadband", "ofc_4g_geo_all": "4G all-operator area"}
Y = {"pinf_per100k": "Outlets per 100,000", "pinf_titles": "Number of outlets"}

regions = pd.get_dummies(df.region, drop_first=True).astype(float)
def resid(v, ctrl):
    m = v.notna() & ctrl.notna().all(axis=1)
    A = np.column_stack([np.ones(m.sum()), ctrl[m].values])
    r = pd.Series(np.nan, index=v.index)
    r[m] = v[m].values - A @ np.linalg.lstsq(A, v[m].values, rcond=None)[0]
    return r
def partial_spearman(x, y, ctrl_cols):
    rk = lambda s: s.rank()
    C = pd.concat([df[c].rank() for c in ctrl_cols], axis=1)
    C = pd.concat([C, regions], axis=1)
    rx, ry = resid(rk(df[x]), C), resid(rk(df[y]), C)
    m = rx.notna() & ry.notna()
    return stats.pearsonr(rx[m], ry[m])

def bh(pv):
    pv = np.asarray(pv); n = len(pv); o = np.argsort(pv); q = np.empty(n)
    q[o] = np.minimum.accumulate((pv[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)

rows = []
for y, yl in Y.items():
    for x, xl in X.items():
        m = df[[x, y]].notna().all(axis=1)
        rho, pr = stats.spearmanr(df.loc[m, x], df.loc[m, y])
        ctrl = [c for c in ["log_pop", "log_density"] if c != x]
        pr_rho, pr_p = partial_spearman(x, y, ctrl)
        rows.append(dict(outcome=yl, measure=xl, field=x, n=int(m.sum()), rho=rho, p=pr, partial_rho=pr_rho, partial_p=pr_p))
R = pd.DataFrame(rows)
R["q"] = bh(R.p); R["partial_q"] = bh(R.partial_p)
R.round(4).to_csv(f"{OUT}/correlations.csv", index=False)

# deserts vs the rest (absolute + relative), raw medians and adjusted difference
G = []
for x, xl in X.items():
    a, b = df.loc[df.desert == 1, x].dropna(), df.loc[df.desert == 0, x].dropna()
    u = stats.mannwhitneyu(a, b)
    pr_rho, pr_p = partial_spearman(x, "desert", [c for c in ["log_pop", "log_density"] if c != x])
    G.append(dict(measure=xl, desert_median=a.median(), other_median=b.median(), n_desert=len(a), p=u.pvalue,
                  partial_rho=pr_rho, partial_p=pr_p))
G = pd.DataFrame(G); G["q"] = bh(G.p); G["partial_q"] = bh(G.partial_p)
G.round(4).to_csv(f"{OUT}/deserts_vs_rest.csv", index=False)

# geography: where deserts and low provision fall
geo = {"by_rural_urban": df.groupby("ruc_urban_rural").agg(n=("desert", "size"), deserts=("desert", "sum"),
            low=("low_prov", "sum"), median_per100k=("pinf_per100k", "median")).reset_index().to_dict("records"),
       "by_region": df.groupby("region").agg(n=("desert", "size"), deserts=("desert", "sum"),
            median_per100k=("pinf_per100k", "median")).reset_index().to_dict("records"),
       "by_ruc_name": df.groupby("ruc_name").agg(n=("desert", "size"), deserts=("desert", "sum"),
            median_per100k=("pinf_per100k", "median")).reset_index().to_dict("records")}

# spatial clustering: Moran's I on log(per100k) and on residual after controls (queen contiguity)
from shapely.geometry import shape
from shapely.strtree import STRtree
b = json.load(open("/home/claude/nd/data/raw/bnd_lad25.geojson"))
geoms = {f["properties"]["LAD25CD"]: shape(f["geometry"]).buffer(0.0005) for f in b["features"]}
codes = list(df.LAD25CD); polys = [geoms[c] for c in codes]; tree = STRtree(polys)
W = np.zeros((len(codes), len(codes)))
for i, g in enumerate(polys):
    for j in tree.query(g):
        if j != i and g.intersects(polys[j]): W[i, j] = 1
rs = W.sum(1); W = W / np.where(rs == 0, 1, rs)[:, None]
def moran(z, perms=999, seed=1):
    z = np.asarray(z, float); z = z - z.mean(); I = (z @ W @ z) / (z @ z)
    rng = np.random.default_rng(seed); sims = np.array([(lambda s: (s @ W @ s) / (s @ s))(rng.permutation(z)) for _ in range(perms)])
    return I, (np.sum(sims >= I) + 1) / (perms + 1)
lp = np.log(df.pinf_per100k + 0.1)
C = pd.concat([df[["log_pop", "log_density"]], regions], axis=1)
res = resid(lp, C)
geo["moran_log_per100k"] = moran(lp); geo["moran_resid_after_pop_density_region"] = moran(res.fillna(0))
geo["moran_desert"] = moran(df.desert)
geo["islands"] = [codes[i] for i in np.where(rs == 0)[0]]

# multivariable model: what predicts log outlets per 100k together?
import numpy.linalg as la
cols = ["log_pop", "log_density", "deprivation", "ge24_turnout_est", "ces_civic_any", "mye25_median_age", "cen21_pct_not_wbrit"]
M = df[cols + ["pinf_per100k"]].dropna()
Z = (M[cols] - M[cols].mean()) / M[cols].std()
A = np.column_stack([np.ones(len(M)), Z.values, regions.loc[M.index].values])
yv = np.log(M.pinf_per100k + 0.1).values
beta, *_ = la.lstsq(A, yv, rcond=None)
res_m = yv - A @ beta; dof = len(yv) - A.shape[1]; s2 = res_m @ res_m / dof
se = np.sqrt(np.diag(s2 * la.inv(A.T @ A)))
tv = beta / se; pv = 2 * stats.t.sf(np.abs(tv), dof)
geo["model"] = {"n": len(M), "r2": 1 - (res_m @ res_m) / ((yv - yv.mean()) @ (yv - yv.mean())),
                "terms": {c: dict(beta_std=round(beta[i + 1], 3), p=round(pv[i + 1], 4)) for i, c in enumerate(cols)}}
json.dump(geo, open(f"{OUT}/geography.json", "w"), indent=1, default=float)
df.to_csv(f"{OUT}/joined.csv", index=False)

pd.set_option("display.width", 220)
print(R.sort_values(["outcome", "partial_p"]).round(3).to_string(index=False))
print(G.sort_values("partial_p").round(3).to_string(index=False))
print(json.dumps(geo, indent=1, default=float)[:6000])
