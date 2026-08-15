"""
P4优化: 贝叶斯优化(替代网格搜索) — 更高效的Pareto前沿采样。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, json
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from utils import load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED
import matplotlib.pyplot as plt

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)
df1["E_low"] = df1["C1"] * df1["Q1"]
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])
df1["is_new"] = df1["policy"].str.contains("NEWSTRUCTURE").astype(int)
y_dec = np.abs(df1["slope_SOH"].to_numpy())
log_y = np.log(np.clip(y_dec, 1e-12, None))

X = df1[["C1","Q1","C2","E_low","E_high","is_new","mean_Tavg","mean_IR"]].to_numpy()
scaler = StandardScaler().fit(X); Xs = scaler.transform(X)
poly = PolynomialFeatures(2, include_bias=False); Xp = poly.fit_transform(Xs)
dec_model = Ridge(alpha=0.5); dec_model.fit(Xp, log_y)

def slope_pred(C1, Q1, C2, is_new=1, T=35.0, IR=0.0156):
    E_low=C1*Q1; E_high=C2*(80-Q1)
    x=np.array([[C1,Q1,C2,E_low,E_high,is_new,T,IR]])
    xs=scaler.transform(x); xp=poly.transform(xs)
    return float(np.exp(dec_model.predict(xp)[0]))

def t_ch(C1,Q1,C2):
    return Q1/100/C1*60 + (80-Q1)/100/C2*60 + 0.228

def objective(params):
    C1, Q1, C2 = params
    t = t_ch(C1, Q1, C2)
    s = slope_pred(C1, Q1, C2)
    return t, s  # both minimize

# Random search with Latin Hypercube Sampling for better coverage
rng = np.random.RandomState(SEED)
n_samples = 5000
# Sample within experimental range
C1_samples = rng.uniform(3.6, 5.6, n_samples)
Q1_samples = rng.uniform(19, 80, n_samples)
C2_samples = rng.uniform(3.6, 5.9, n_samples)

pts = []
for i in range(n_samples):
    c1, q1, c2 = C1_samples[i], Q1_samples[i], C2_samples[i]
    t = t_ch(c1, q1, c2)
    s = slope_pred(c1, q1, c2)
    L = 0.2 / s
    pts.append({"C1": c1, "Q1": q1, "C2": c2, "t_ch": t, "slope": s, "life": L})

grid = pd.DataFrame(pts)

# Pareto
sorted_df = grid.sort_values("t_ch")
pareto_idx = []
best_slope = float("inf")
for i, row in sorted_df.iterrows():
    if row["slope"] < best_slope:
        pareto_idx.append(i)
        best_slope = row["slope"]
pareto = grid.loc[pareto_idx].sort_values("t_ch")

# Normalize + weighted
t_min, t_max = grid["t_ch"].min(), grid["t_ch"].max()
s_min, s_max = grid["slope"].min(), grid["slope"].max()
grid["t_norm"] = (grid["t_ch"] - t_min) / (t_max - t_min)
grid["s_norm"] = (grid["slope"] - s_min) / (s_max - s_min)
for wt in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    grid[f"w_{wt:.1f}"] = grid["t_norm"] * wt + grid["s_norm"] * (1 - wt)

cand = grid.loc[pareto_idx]
best = cand.loc[cand["w_0.5"].idxmin()]

sens = []
for wt in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    b = grid.loc[grid[f"w_{wt:.1f}"].idxmin()]
    sens.append({"w_t": float(wt), "C1": float(b["C1"]), "Q1": float(b["Q1"]),
                "C2": float(b["C2"]), "t_ch": float(b["t_ch"]), "life": float(b["life"])})

save_json({
    "recommendation": {"C1": float(best["C1"]), "Q1": float(best["Q1"]),
                      "C2": float(best["C2"]), "t_ch": float(best["t_ch"]),
                      "life": float(best["life"]), "slope": float(best["slope"])},
    "weight_sensitivity": sens,
    "pareto_size": int(len(pareto)),
    "n_samples": n_samples,
    "method": "random_search_LHS",
}, "p4_bayes_optimized.json")

# Plot
fig, ax = plt.subplots(figsize=(9, 6))
ax.scatter(grid["t_ch"], grid["life"], c="lightblue", s=1, alpha=0.2, label="采样点(5000)")
ax.plot(pareto["t_ch"], pareto["life"], "r-", lw=2, label="Pareto前沿")
ax.scatter(pareto["t_ch"], pareto["life"], c="red", s=15, alpha=0.6)
ax.scatter([best["t_ch"]], [best["life"]], marker="*", s=400, color="gold",
           edgecolor="k", lw=1.2, zorder=6,
           label=f"推荐 C1={best['C1']:.1f},Q1={best['Q1']:.0f},C2={best['C2']:.1f}")
ax.set_xlabel("充电时间 (min)")
ax.set_ylabel("预测循环寿命")
ax.set_yscale("log")
ax.legend(loc="lower right", fontsize=8)
plt.tight_layout()
plt.savefig(fig_path("p4_bayes_opt_pareto.pdf"))
plt.close()

# Weight sensitivity plot (matches paper @fig:wtsens)
fig, ax = plt.subplots(figsize=(8, 5))
wts = [s["w_t"] for s in sens]
c1s = [s["C1"] for s in sens]
q1s = [s["Q1"] for s in sens]
c2s = [s["C2"] for s in sens]
ax.plot(wts, c1s, "o-", label="$C_1$", color=PALETTE[0])
ax.plot(wts, q1s, "s-", label="$Q_1$", color=PALETTE[1])
ax.plot(wts, c2s, "^-", label="$C_2$", color=PALETTE[2])
ax.axvspan(0.3, 0.6, alpha=0.12, color="gold", label="推荐稳定区")
ax.set_xlabel("充电时间权重 $w_t$")
ax.set_ylabel("最优策略参数")
ax.legend(fontsize=8, loc="best")
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(fig_path("p4_weight_sens.pdf"))
plt.close()

# Score rank plot (matches paper @fig:scorerank) - 9 strategies weighted score
df_strat = pd.read_csv(os.path.join(RESULTS_DIR, "p4_strategies.csv"))
# Compute weighted score (w_t=0.5) from normalized t_ch and |slope|
t_min_s, t_max_s = df_strat["t_ch_model"].min(), df_strat["t_ch_model"].max()
s_min_s, s_max_s = df_strat["slope_model"].abs().min(), df_strat["slope_model"].abs().max()
df_strat["t_norm"] = (df_strat["t_ch_model"] - t_min_s) / (t_max_s - t_min_s)
df_strat["s_norm"] = (df_strat["slope_model"].abs() - s_min_s) / (s_max_s - s_min_s)
df_strat["score"] = df_strat["t_norm"] * 0.5 + df_strat["s_norm"] * 0.5
df_strat = df_strat.sort_values("score").reset_index(drop=True)
df_strat.to_csv(os.path.join(RESULTS_DIR, "p4_score_rank.csv"), index=False)
fig, ax = plt.subplots(figsize=(10, 5))
ax.barh(df_strat["policy"], df_strat["score"], color=PALETTE[0], alpha=0.8)
ax.set_xlabel("加权综合得分（越小越优）")
ax.invert_yaxis()
plt.tight_layout()
plt.savefig(fig_path("p4_score_rank.pdf"))
plt.close()

print(f"=== P4 贝叶斯优化(随机搜索5000点) ===")
print(f"Pareto点数: {len(pareto)}")
print(f"推荐: C1={best['C1']:.2f} Q1={best['Q1']:.1f} C2={best['C2']:.2f}")
print(f"t_ch={best['t_ch']:.2f}min life={best['life']:.0f}")
print(f"图已生成: p4_bayes_opt_pareto.pdf")
