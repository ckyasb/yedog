"""
问题2：充电策略及其参数(C1,Q1,C2)对电池寿命衰减的影响分析。
三参数非完全独立变化 -> 分组对比 + Kruskal-Wallis + 置换检验 + 岭回归(含交互) + 方差分解 + SOC区间高倍率暴露。
"""
import os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.inspection import permutation_importance
from utils import (load_summary, load_cycles, save_json, fig_path, PALETTE, RESULTS_DIR, SEED)

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)

# 派生 SOC 区间高倍率暴露量
df1["E_low"] = df1["C1"] * df1["Q1"]            # 低/中 SOC 段高倍率暴露 = C1 * Q1宽
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])    # 中高 SOC 段高倍率暴露 = C2 * (80-Q1)宽
df1["is_new"] = df1["policy"].str.contains("NEWSTRUCTURE").astype(int)

# 使用分段稳态寿命（前50循环与50循环后分段斜率加权外推）作为因变量
# 稳态斜率比整体斜率更能代表长期衰减趋势
df_pw = pd.read_csv(os.path.join(RESULTS_DIR, "p1_piecewise_life.csv"))
df_pw = df_pw[["battery_id", "life_late"]].rename(columns={"life_late": "life_steady"})
df1 = df1.merge(df_pw, on="battery_id", how="left")
# 若分段寿命缺失则用原始寿命
df1["life_steady"] = df1["life_steady"].fillna(df1["life"])

df1.to_csv(os.path.join(RESULTS_DIR, "p2_features.csv"), index=False)

# ============ (1) 策略间寿命差异显著性 ============
policies = sorted(df1["policy"].unique())
groups = [df1[df1["policy"] == p]["life_steady"].values for p in policies]

# Kruskal-Wallis
H_stat, p_kw = stats.kruskal(*groups)
# 置换检验（10000次）：在 H0 下随机重排策略标签，看 H 统计量超过观测的比例
rng = np.random.RandomState(SEED)
life_arr = df1["life_steady"].to_numpy()
pol_codes = df1["policy"].astype("category").cat.codes.to_numpy()
obs_H = H_stat
n_perm = 10000
perm_H = np.empty(n_perm)
for i in range(n_perm):
    perm = rng.permutation(pol_codes)
    g = [life_arr[perm == c] for c in range(len(policies))]
    if any(len(x) < 1 for x in g):
        perm_H[i] = 0.0
    else:
        perm_H[i] = stats.kruskal(*g).statistic
p_perm = np.mean(perm_H >= obs_H)

# 单因素 ANOVA 对照（非稳健，小样本）
F_stat, p_anova = stats.f_oneway(*groups)

# 事后 Dunn（简单实现，Bonferroni）
from itertools import combinations
dunn = []
for a, b in combinations(range(len(policies)), 2):
    xa = groups[a]; xb = groups[b]
    U, p = stats.mannwhitneyu(xa, xb, alternative="two-sided")
    dunn.append({"pair": f"{policies[a]} vs {policies[b]}", "p": p,
                 "diff_median": float(np.median(xa) - np.median(xb))})
dunn_df = pd.DataFrame(dunn)
dunn_df["p_bonf"] = (dunn_df["p"] * len(dunn_df)).clip(upper=1.0)
dunn_df.to_csv(os.path.join(RESULTS_DIR, "p2_dunn.csv"), index=False)

kw_result = {"kruskal_wallis_H": float(H_stat), "p_kw": float(p_kw),
             "p_permutation_10000": float(p_perm),
             "anova_F": float(F_stat), "p_anova": float(p_anova)}
save_json(kw_result, "p2_kw.json")
print("=== (1) 策略间寿命差异显著性 ===")
print(f"Kruskal-Wallis H={H_stat:.3f}, p={p_kw:.4g}; 置换p={p_perm:.4f}; ANOVA F={F_stat:.2f}, p={p_anova:.4g}")

# ============ (2) C1/Q1/C2 与寿命关系 + (3) 影响程度 ============
# 岭回归含交互（多重共线性）：life ~ C1 + Q1 + C2 + C1:Q1 + C2:Q1
X = df1[["C1", "Q1", "C2", "is_new"]].copy()
X["C1_Q1"] = df1["C1"] * df1["Q1"]
X["C2_Q1"] = df1["C2"] * df1["Q1"]
y = np.log(df1["life_steady"].values)  # log 稳态寿命（分段拟合）
scaler = StandardScaler()
Xs = scaler.fit_transform(X)
ridge = Ridge(alpha=1.0)
ridge.fit(Xs, y)
yhat = ridge.predict(Xs)
r2_ridge = 1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2)
# 偏相关：控制其他变量后单因子与 log(life) 的相关
def partial_corr(df_, target, var, controls):
    from sklearn.linear_model import LinearRegression
    Z = df_[controls].to_numpy()
    t = df_[target].to_numpy()
    v = df_[var].to_numpy()
    rt = t - LinearRegression().fit(Z, t).predict(Z)
    rv = v - LinearRegression().fit(Z, v).predict(Z)
    r, p = stats.pearsonr(rt, rv)
    return float(r), float(p)
pc = {}
for v, ctrl in [("C1", ["Q1", "C2"]), ("Q1", ["C1", "C2"]), ("C2", ["C1", "Q1"])]:
    tmp = df1.assign(log_life=y, C1_Q1=X["C1_Q1"], C2_Q1=X["C2_Q1"])
    r, p = partial_corr(tmp, "log_life", v, ctrl)
    pc[v] = {"partial_r": r, "p": p}

# 随机森林置换重要性（非参数影响程度）
rf = RandomForestRegressor(n_estimators=500, random_state=SEED)
Xrf = df1[["C1", "Q1", "C2", "is_new"]].to_numpy()
rf.fit(Xrf, y)
perm_imp = permutation_importance(rf, Xrf, y, n_repeats=30, random_state=SEED)
imp = {k: float(np.mean(perm_imp.importances[i])) for i, k in enumerate(["C1", "Q1", "C2", "is_new"])}
# 归一化为百分比
imp_pct = {k: v / sum(imp.values()) * 100 for k, v in imp.items()}

reg_result = {
    "ridge_r2": float(r2_ridge),
    "ridge_coefs_std": {k: float(c) for k, c in zip(X.columns, ridge.coef_)},
    "partial_corr": pc,
    "rf_perm_importance": imp,
    "rf_perm_importance_pct": imp_pct,
    "rf_r2": float(rf.score(Xrf, y)),
}
save_json(reg_result, "p2_regression.json")
print("\n=== (2/3) 岭回归 + 偏相关 + 随机森林影响程度 ===")
print(f"岭回归 R²={r2_ridge:.3f}（log寿命, 标准化）")
print("偏相关系数:", {k: f"{v['partial_r']:.3f}(p={v['p']:.3f})" for k, v in pc.items()})
print(f"随机森林 R²={rf.score(Xrf,y):.3f}, 置换重要性占比: {imp_pct}")

# ============ (4) SOC 区间高倍率衰减特征 ============
# 比较两组：高 E_high（中高SOC高倍率）vs 高 E_low（低SOC高倍率），看衰减斜率 |slope|
# 衰减斜率分布跨数量级（NEWSTRUCTURE 短寿命电池斜率比长寿命大 1-2 个数量级），
# 直接线性拟合 R² 仅 0.08；改用 log 空间 + 交互项/比值项拟合，更符合衰减的乘性结构。
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
sl = np.abs(df1["slope_SOH"].values)  # 衰减速率（越大越快）
sl_log = np.log(np.clip(sl, 1e-12, None))  # log |slope|，压缩跨数量级的方差

# 基线：线性 |k| ~ E_low + E_high（保留作对照）
El = df1[["E_low", "E_high"]].to_numpy()
lr = LinearRegression().fit(El, sl)
r2_sl = lr.score(El, sl)

# 改进1：log |k| ~ E_low + E_high（线性，log 空间）
lr_log = LinearRegression().fit(El, sl_log)
r2_sl_log = lr_log.score(El, sl_log)

# 改进2：log |k| ~ E_low + E_high + sqrt(E_high) + 交互 + is_new
#         中高 SOC 段暴露对衰减可能是亚线性的（析锂阈值效应），加入 sqrt 项
#         NEWSTRUCTURE 是该关系的重要混杂（同参数下寿命差 5 倍），显式纳入
E_low = df1["E_low"].to_numpy()
E_high = df1["E_high"].to_numpy()
is_new_arr = df1["is_new"].to_numpy()
E_high_safe = np.sqrt(np.clip(E_high, 0, None))  # sqrt(E_high), E_high>=0
X_nl = np.column_stack([E_low, E_high, E_high_safe, E_low * E_high, is_new_arr])
scaler_nl = StandardScaler().fit(X_nl)
X_nl_s = scaler_nl.transform(X_nl)
ridge_nl = Ridge(alpha=1.0).fit(X_nl_s, sl_log)
r2_nl = ridge_nl.score(X_nl_s, sl_log)

# 选最优模型
best_name = max([("linear", r2_sl), ("log_linear", r2_sl_log), ("log_nonlinear", r2_nl)], key=lambda t: t[1])[0]
best_r2 = max(r2_sl, r2_sl_log, r2_nl)

# 单独相关（仍用原始 |k|，便于和物理直觉对照）
r_low, p_low = stats.pearsonr(df1["E_low"], sl)
r_high, p_high = stats.pearsonr(df1["E_high"], sl)
# log 空间偏相关（控制 E_low 看 E_high 的净效应，反之亦然）
from sklearn.linear_model import LinearRegression
def partial_log(target, var, controls):
    Z = np.column_stack(controls)
    rt = sl_log - LinearRegression().fit(Z, sl_log).predict(Z)
    rv = df1[var].to_numpy() - LinearRegression().fit(Z, df1[var].to_numpy()).predict(Z)
    r, p = stats.pearsonr(rt, rv)
    return float(r), float(p)
pr_low, pp_low = partial_log(sl_log, "E_low", [E_high])
pr_high, pp_high = partial_log(sl_log, "E_high", [E_low])

soc_result = {
    "decay_vs_E_r2": float(r2_sl),           # 基线线性 R²（保留，论文需引用）
    "decay_vs_E_r2_log": float(r2_sl_log),   # log 线性 R²
    "decay_vs_E_r2_log_nonlinear": float(r2_nl),  # log 非线性 R²
    "best_model": best_name,
    "best_r2": float(best_r2),
    "coefs": {"E_low": float(lr.coef_[0]), "E_high": float(lr.coef_[1]),
              "intercept": float(lr.intercept_)},
    "log_coefs": {"E_low": float(lr_log.coef_[0]), "E_high": float(lr_log.coef_[1]),
                  "intercept": float(lr_log.intercept_)},
    "pearson_E_low_vs_slope": {"r": float(r_low), "p": float(p_low)},
    "pearson_E_high_vs_slope": {"r": float(r_high), "p": float(p_high)},
    "partial_log_E_low": {"r": float(pr_low), "p": float(pp_low)},
    "partial_log_E_high": {"r": float(pr_high), "p": float(pp_high)},
}
save_json(soc_result, "p2_soc_interval.json")
print("\n=== (4) SOC区间高倍率衰减特征 ===")
print(f"|k| ~ E_low+E_high (线性): R²={r2_sl:.3f}")
print(f"log|k| ~ E_low+E_high: R²={r2_sl_log:.3f}")
print(f"log|k| ~ E_low+E_high+sqrt(E_high)+交互: R²={r2_nl:.3f}  <- 最优={best_name}")
print(f"Pearson(原|k|): E_low r={r_low:.3f}(p={r_low:.3f}); E_high r={r_high:.3f}(p={p_high:.3f})")
print(f"偏相关(log|k|,控制对方): E_low r={pr_low:.3f}(p={pp_low:.4f}); E_high r={pr_high:.3f}(p={pp_high:.4f})")

# ============ 图 ============
# 图6: 分组箱线图 + KW 显著性标注
fig, ax = plt.subplots(figsize=(9, 5))
order = df1.groupby("policy")["life"].median().sort_values(ascending=False).index.tolist()
data = [df1[df1["policy"] == p]["life_steady"].values for p in order]
bp = ax.boxplot(data, vert=True, patch_artist=True, showmeans=True,
                meanprops=dict(marker="D", mfc="white", mec="k", ms=5))
for i, patch in enumerate(bp["boxes"]):
    patch.set_facecolor(PALETTE[i % len(PALETTE)]); patch.set_alpha(0.6)
ax.set_xticklabels(order, rotation=35, ha="right", fontsize=8)
ax.set_ylabel("循环寿命"); ax.set_yscale("log")
ax.set_title(f"Kruskal-Wallis H={H_stat:.1f}, p={p_kw:.3g}（置换p={p_perm:.3f}）", fontsize=9)
plt.tight_layout(); plt.savefig(fig_path("p2_life_kw_box.pdf")); plt.close()

# 图7: C1/Q1/C2 vs 寿命 散点 + 岭回归拟合线
fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
for ax, col, lab in zip(axes, ["C1", "Q1", "C2"], ["C1 (C)", "Q1 (%)", "C2 (C)"]):
    for i, p in enumerate(policies):
        sub = df1[df1["policy"] == p]
        ax.scatter(sub[col], sub["life_steady"], color=PALETTE[i % len(PALETTE)],
                   s=40, edgecolor="white", lw=0.5, alpha=0.85)
    ax.set_xlabel(lab); ax.set_ylabel("循环寿命"); ax.set_yscale("log")
    # 偏相关标注
    r = pc[col]["partial_r"]; pp = pc[col]["p"]
    ax.text(0.04, 0.04, f"偏相关 r={r:.2f}\np={pp:.3f}", transform=ax.transAxes,
            fontsize=7, va="bottom", ha="left")
plt.tight_layout(); plt.savefig(fig_path("p2_param_partial.pdf")); plt.close()

# 图8: 影响程度条形（随机森林置换重要性 %）
fig, ax = plt.subplots(figsize=(6, 3.8))
keys = ["C1", "Q1", "C2", "is_new"]
vals = [imp_pct[k] for k in keys]
bars = ax.bar(keys, vals, color=PALETTE[:3], alpha=0.8, edgecolor="white")
ax.set_ylabel("对寿命方差解释占比 (%)")
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width()/2, v + 0.5, f"{v:.1f}%", ha="center", fontsize=9)
plt.tight_layout(); plt.savefig(fig_path("p2_importance_bar.pdf")); plt.close()

# 图9: SOC 区间高倍率暴露 vs 衰减斜率
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for ax, col, lab in zip(axes, ["E_low", "E_high"],
                        ["低SOC段高倍率暴露 $E_{low}=C_1Q_1$", "中高SOC段高倍率暴露 $E_{high}=C_2(80-Q_1)$"]):
    for i, p in enumerate(policies):
        sub = df1[df1["policy"] == p]
        ax.scatter(sub[col], sub["slope_SOH"].abs() * 1e5,
                   color=PALETTE[i % len(PALETTE)], s=40, edgecolor="white", lw=0.5, label=p)
    ax.set_xlabel(lab); ax.set_ylabel("|衰减斜率| (×1e5)")
axes[0].legend(fontsize=6, ncol=1, loc="upper left", frameon=False)
plt.tight_layout(); plt.savefig(fig_path("p2_soc_exposure.pdf")); plt.close()

print("\n图已生成: p2_life_kw_box.pdf, p2_param_partial.pdf, p2_importance_bar.pdf, p2_soc_exposure.pdf")
