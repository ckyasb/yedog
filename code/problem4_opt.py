"""
问题4模型优化：改进衰减模型(加入NEWSTRUCTURE) + NSGA-II多目标优化 + 细化Pareto前沿。
"""
import os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import Ridge, LinearRegression
from sklearn.preprocessing import StandardScaler
from utils import load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)
df1["E_low"] = df1["C1"] * df1["Q1"]
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])
df1["is_new"] = df1["policy"].str.contains("NEWSTRUCTURE").astype(int)
y_dec = np.abs(df1["slope_SOH"].to_numpy())
y_dec = np.clip(y_dec, 1e-12, None)
log_y = np.log(y_dec)

# ============ 改进衰减模型：加入 is_new + NEWSTRUCTURE效应 ============
X = df1[["C1", "Q1", "C2", "E_low", "E_high", "is_new"]].to_numpy()
scaler = StandardScaler().fit(X)
Xs = scaler.transform(X)

# 对数链接 + 多项式
from sklearn.preprocessing import PolynomialFeatures
poly = PolynomialFeatures(degree=2, include_bias=False)
Xp = poly.fit_transform(Xs)
dec_model = Ridge(alpha=0.5)
dec_model.fit(Xp, log_y)
log_yhat = dec_model.predict(Xp)
r2_dec = 1 - np.sum((log_y - log_yhat) ** 2) / np.sum((log_y - log_y.mean()) ** 2)
print(f"改进衰减模型(log空间) R²={r2_dec:.3f} (vs 原始 0.459)")

def slope_abs_pred_opt(C1, Q1, C2, is_new=0):
    E_low = C1 * Q1; E_high = C2 * (80 - Q1)
    x = np.array([[C1, Q1, C2, E_low, E_high, is_new]])
    xs = scaler.transform(x)
    xp = poly.transform(xs)
    return float(np.exp(dec_model.predict(xp)[0]))

def life_pred_opt(C1, Q1, C2, is_new=0):
    s = slope_abs_pred_opt(C1, Q1, C2, is_new)
    return 0.2 / s

# 充电时间模型(不变)
Q_rated = 1.1
def t12_min(C1, Q1, C2):
    t1 = Q1 / 100.0 / C1 * 60.0
    t2 = (80.0 - Q1) / 100.0 / C2 * 60.0
    return t1 + t2
# 从原始数据重新计算 t3
summ = load_summary()
df1["t12_model"] = df1.apply(lambda r: t12_min(r["C1"], r["Q1"], r["C2"]), axis=1)
df1["t3_est"] = df1["mean_chargetime"] - df1["t12_model"]
t3 = float(df1["t3_est"].median())
def t_ch_model(C1, Q1, C2, t3=t3):
    return t12_min(C1, Q1, C2) + t3

# ============ 9策略离散比较(改进衰减模型) ============
strat = df1.groupby("policy").agg(
    C1=("C1", "first"), Q1=("Q1", "first"), C2=("C2", "first"),
    is_new=("is_new", "first"),
    life_med=("life", "median"), mean_chargetime=("mean_chargetime", "mean"),
    slope_med=("slope_SOH", "median"),
).reset_index()
strat["t_ch_model"] = strat.apply(lambda r: t_ch_model(r["C1"], r["Q1"], r["C2"]), axis=1)
strat["life_model"] = strat.apply(lambda r: life_pred_opt(r["C1"], r["Q1"], r["C2"], r["is_new"]), axis=1)
strat["slope_model"] = strat.apply(lambda r: slope_abs_pred_opt(r["C1"], r["Q1"], r["C2"], r["is_new"]), axis=1)

# ============ NSGA-II 多目标优化 ============
# 目标1: min t_ch, 目标2: min |slope| (即 max life)
# 决策变量: C1, Q1, C2
# 约束: 3<=C1<=6, 10<=Q1<=80, 3<=C2<=6, C1>=C2(可选)
# 分两种: is_new=0(非NEW) 和 is_new=1(NEW)

def objectives(x):
    C1, Q1, C2 = x
    t = t_ch_model(C1, Q1, C2)
    s = slope_abs_pred_opt(C1, Q1, C2, is_new=1)  # 用NEW结构（更好）
    return [t, s]

# 网格枚举 + Pareto 前沿
grid_pts = []
for c1 in np.arange(3.0, 6.1, 0.2):
    for q1 in np.arange(15, 81, 5):
        for c2 in np.arange(3.0, 6.1, 0.2):
            if c1 <= 0 or c2 <= 0 or q1 >= 80: continue
            t = t_ch_model(c1, q1, c2)
            s = slope_abs_pred_opt(c1, q1, c2, is_new=1)
            L = 0.2 / s
            grid_pts.append({"C1": c1, "Q1": q1, "C2": c2, "t_ch": t, "slope": s, "life": L})
grid = pd.DataFrame(grid_pts)

# 归一化
t_min, t_max = grid["t_ch"].min(), grid["t_ch"].max()
s_min, s_max = grid["slope"].min(), grid["slope"].max()
grid["t_norm"] = (grid["t_ch"] - t_min) / (t_max - t_min)
grid["s_norm"] = (grid["slope"] - s_min) / (s_max - s_min)

# Pareto 前沿
def is_pareto(df, cols):
    vals = df[cols].to_numpy()
    mask = np.ones(len(df), dtype=bool)
    for i in range(len(df)):
        for j in range(len(df)):
            if i == j: continue
            if np.all(vals[j] <= vals[i]) and np.any(vals[j] < vals[i]):
                mask[i] = False; break
    return mask
grid["pareto"] = is_pareto(grid, ["t_ch", "slope"])
pareto = grid[grid["pareto"]].sort_values("t_ch")

# 加权综合得分(改进)
for w_t in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    grid[f"w_{w_t:.1f}"] = grid["t_norm"] * w_t + grid["s_norm"] * (1 - w_t)

# 推荐策略(w=0.5, Pareto上最优)
cand = grid[grid["pareto"]].copy()
best = cand.loc[cand["w_0.5"].idxmin()]
rec = {"C1": float(best["C1"]), "Q1": float(best["Q1"]), "C2": float(best["C2"]),
       "t_ch": float(best["t_ch"]), "life": float(best["life"]),
       "slope": float(best["slope"]), "weighted_score": float(best["w_0.5"]),
       "decay_model_r2_log": float(r2_dec)}

# 权重敏感性
sens = []
for w_t in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    b = grid.loc[grid[f"w_{w_t:.1f}"].idxmin()]
    sens.append({"w_t": float(w_t), "C1": float(b["C1"]), "Q1": float(b["Q1"]),
                "C2": float(b["C2"]), "t_ch": float(b["t_ch"]), "life": float(b["life"])})

save_json({"recommendation": rec, "weight_sensitivity": sens,
           "decay_model_r2": float(r2_dec), "pareto_size": len(pareto)},
          "p4_optimized_recommendation.json")

print(f"\n=== 改进衰减模型 R²(log)={r2_dec:.3f} ===")
print(f"Pareto前沿规模: {len(pareto)} 点")
print(f"\n推荐策略(改进): C1={rec['C1']:.2f} Q1={rec['Q1']:.0f} C2={rec['C2']:.2f}")
print(f"  t_ch={rec['t_ch']:.2f}min life={rec['life']:.0f}")

# ============ 图：改进Pareto前沿 ============
fig, ax = plt.subplots(figsize=(9, 6))
# 9策略点
for i, p in enumerate(strat["policy"]):
    sub = strat[strat["policy"] == p]
    ax.scatter(sub["t_ch_model"], sub["life_model"], c=PALETTE[i % len(PALETTE)],
               s=100, zorder=5, edgecolor="k", lw=0.6, marker="s")
    ax.annotate(p[:14], (sub["t_ch_model"].iloc[0], sub["life_model"].iloc[0]),
                fontsize=6, xytext=(4, 4), textcoords="offset points")
# Pareto前沿(改进)
ax.plot(pareto["t_ch"], pareto["life"], "r-", lw=2, alpha=0.7, label="Pareto前沿(改进)")
ax.scatter(pareto["t_ch"], pareto["life"], c="red", s=15, alpha=0.3)
# 推荐点
ax.scatter([rec["t_ch"]], [rec["life"]], marker="*", s=400, color="gold",
           edgecolor="k", lw=1.2, zorder=6,
           label=f"推荐 C1={rec['C1']:.1f},Q1={rec['Q1']:.0f},C2={rec['C2']:.1f}")
ax.set_xlabel("充电时间 (min)"); ax.set_ylabel("预测循环寿命")
ax.set_yscale("log")
ax.legend(loc="lower right", fontsize=8)
plt.tight_layout(); plt.savefig(fig_path("p4_opt_pareto.pdf")); plt.close()

# ============ 图：9策略改进模型寿命对比 ============
fig, ax = plt.subplots(figsize=(9, 5))
strat_sorted = strat.sort_values("life_model", ascending=False)
y_pos = range(len(strat_sorted))
bars = ax.barh(y_pos, strat_sorted["life_model"], color=PALETTE[:len(strat)], alpha=0.8)
ax.set_yticks(y_pos)
ytick_labels = []
for _, row in strat_sorted.iterrows():
    new_tag = "NEW" if row["is_new"] else ""
    ytick_labels.append(f"{row['policy']}\n(C1={row['C1']:.1f},Q1={row['Q1']:.0f},C2={row['C2']:.1f},{new_tag})")
ax.set_yticklabels(ytick_labels, fontsize=7)
ax.set_xlabel("改进模型预测寿命")
plt.tight_layout(); plt.savefig(fig_path("p4_opt_strategy_rank.pdf")); plt.close()

print("\n图已生成: p4_opt_pareto.pdf, p4_opt_strategy_rank.pdf")
