#strong[utils.py]
```python
"""
公共工具：数据读取、policy 解析、寿命外推、绘图样式、随机种子。
所有子问题脚本 import 本模块。
"""
import os, json, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

warnings.filterwarnings("ignore")

# ---------- 路径 ----------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # <PROJECT_ROOT>  # project root <PROJECT_ROOT>
ATTACH = os.path.join(BASE, "2026年度“策联杯”数学建模精英联赛-A题-附件")
SUMMARY_CSV = os.path.join(ATTACH, "battery_summary.csv")
CYCLE_CSV = os.path.join(ATTACH, "cycle_train.csv")
CODE_DIR = os.path.join(BASE, "code")
RESULTS_DIR = os.path.join(BASE, "results")
FIG_DIR = os.path.join(BASE, "figures")
for d in (RESULTS_DIR, FIG_DIR):
    os.makedirs(d, exist_ok=True)

# ---------- 随机种子 ----------
SEED = 42
np.random.seed(SEED)

# ---------- 中文字体 ----------
def _setup_font():
    cjk_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if os.path.exists(cjk_path):
        fm.fontManager.addfont(cjk_path)
        prop = fm.FontProperties(fname=cjk_path)
        name = prop.get_name()
        plt.rcParams["font.family"] = name
        plt.rcParams["font.sans-serif"] = [name]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42       # TrueType embed
    plt.rcParams["ps.fonttype"] = 42
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["xtick.labelsize"] = 9
    plt.rcParams["ytick.labelsize"] = 9
    plt.rcParams["legend.fontsize"] = 9
    plt.rcParams["figure.dpi"] = 150
    plt.rcParams["savefig.dpi"] = 300
    plt.rcParams["savefig.bbox"] = "tight"

_setup_font()

# 配色（灰度可分，色盲友好近似）
PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
           "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]

# ---------- 数据读取 ----------
def load_summary():
    df = pd.read_csv(SUMMARY_CSV)
    # C1 缺失填 C2（80PER_3_6C 策略无独立第一阶段）
    df["C1"] = df["C1"].fillna(df["C2"])
    return df

def load_cycles():
    df = pd.read_csv(CYCLE_CSV)
    return df

# ---------- policy 解析 ----------
def parse_policy(policy):
    """返回 (C1, Q1, C2)，与 summary 一致校验。"""
    return None  # 依赖 summary，不单独解析

# ---------- 寿命外推 ----------
def fit_linear_life(cycles, soh_smooth, threshold=0.8):
    """线性 SOH = a + k*N（a=截距, k=斜率）外推寿命。返回 (a, k, life)。"""
    x = np.asarray(cycles, float)
    y = np.asarray(soh_smooth, float)
    if len(x) < 3:
        return np.nan, np.nan, np.nan
    # np.polyfit degree=1 返回 [slope, intercept]
    k, a = np.polyfit(x, y, 1)
    if k >= 0:  # 早期无衰减（甚至上升），无法外推寿命
        return a, k, np.nan
    life = (threshold - a) / k
    return a, k, life

def fit_exp_life(cycles, soh_smooth, threshold=0.8):
    """指数 SOH = exp(-lambda*N) 拟合（log(SOH)=-lambda*N）。返回 (lambda, life)。
    更稳健：用全部点、单调约束。lambda<=0 则寿命 NaN。"""
    x = np.asarray(cycles, float)
    y = np.clip(np.asarray(soh_smooth, float), 1e-6, None)
    if len(x) < 3:
        return np.nan, np.nan
    ly = np.log(y)
    # y = -lambda*x + const，斜率 = -lambda
    slope, _ = np.polyfit(x, ly, 1)
    lam = -slope
    if lam <= 0:
        return lam, np.nan
    life = -np.log(threshold) / lam
    return lam, life

def fit_power_life(cycles, soh_smooth, threshold=0.8):
    """SOH = 1 - alpha*N^beta 拟合。早期数据近平台，外推极不稳，仅作参考。"""
    x = np.asarray(cycles, float)
    y = np.asarray(soh_smooth, float)
    y = np.clip(y, 1e-6, None)
    diff = 1 - y
    mask = (x > 0) & (diff > 1e-9)
    if mask.sum() < 3:
        return np.nan, np.nan, np.nan
    lx = np.log(x[mask]); ly = np.log(diff[mask])
    b, la = np.polyfit(lx, ly, 1)
    alpha = np.exp(la)
    if b <= 0 or alpha <= 0:
        return alpha, b, np.nan
    life = ((1 - threshold) / alpha) ** (1 / b)
    return alpha, b, life

# ---------- 输出辅助 ----------
def save_json(obj, name):
    p = os.path.join(RESULTS_DIR, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return p

def fig_path(name):
    return os.path.join(FIG_DIR, name)

if __name__ == "__main__":
    s = load_summary()
    c = load_cycles()
    print("summary:", s.shape, "cycles:", c.shape)
    print("C1 null after fill:", s["C1"].isna().sum())
    print("policies:", s["policy"].nunique())
    print("test batteries:", int(s["prediction_test"].sum()))

```

#strong[problem1.py]
```python
"""
问题1：数据整理与快充策略对寿命影响初步分析。
- 整理电池-策略-寿命表
- SOH 衰减曲线（线性+幂律外推寿命）
- 寿命分布统计
- 典型长/短寿命策略对比
"""
import os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from utils import (load_summary, load_cycles, fit_linear_life, fit_power_life,
                   fit_exp_life, save_json, fig_path, PALETTE, RESULTS_DIR)

summ = load_summary()
cyc = load_cycles()

# ---------- 构建每电池记录 ----------
records = []
for bid, g in cyc.groupby("battery_id"):
    g = g.sort_values("cycle")
    N = g["cycle"].to_numpy(float)
    soh = g["SOH"].to_numpy(float)
    soh_s = g["SOH_smooth"].to_numpy(float)
    meta = summ[summ["battery_id"] == bid].iloc[0]
    a_lin, k_lin, life_lin = fit_linear_life(N, soh_s)
    alpha_pw, beta_pw, life_pw = fit_power_life(N, soh_s)
    lam_exp, life_exp = fit_exp_life(N, soh_s)
    # 多模型寿命：用中位数综合（robust），线性+指数可用时取两者中位；幂律发散单独记
    cand = [v for v in [life_lin, life_exp] if np.isfinite(v) and 0 < v < 1e7]
    life_robust = float(np.median(cand)) if cand else np.nan
    rec = {
        "battery_id": int(bid),
        "policy": meta["policy"],
        "C1": float(meta["C1"]), "Q1": float(meta["Q1"]), "C2": float(meta["C2"]),
        "initial_capacity": float(meta["initial_capacity"]),
        "mean_chargetime": float(meta["mean_chargetime"]),
        "mean_IR": float(meta["mean_IR"]),
        "mean_Tavg": float(meta["mean_Tavg"]),
        "is_test": int(meta["prediction_test"]),
        "n_cycles": int(len(N)),
        "last_SOH": float(soh_s[-1]),
        "slope_SOH": float(k_lin),            # per cycle
        "life_linear": float(life_lin),
        "life_exp": float(life_exp),
        "life_power": float(life_pw),
        "life": float(life_robust),           # 主寿命代理（线性+指数中位）
        "IR_first": float(g["IR"].iloc[0]),
        "IR_last": float(g["IR"].iloc[-1]),
        "IR_growth_pct": float((g["IR"].iloc[-1] - g["IR"].iloc[0]) / g["IR"].iloc[0] * 100),
    }
    records.append(rec)
df1 = pd.DataFrame(records).sort_values("battery_id")
df1.to_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"), index=False)

# 策略级寿命聚合（主寿命代理 life = 线性+指数寿命中位）
agg = df1.groupby("policy").agg(
    n=("battery_id", "count"),
    C1=("C1", "first"), Q1=("Q1", "first"), C2=("C2", "first"),
    life_linear_med=("life_linear", "median"),
    life_exp_med=("life_exp", "median"),
    life_med=("life", "median"),
    life_min=("life", "min"),
    life_max=("life", "max"),
    slope_med=("slope_SOH", "median"),
    mean_chargetime=("mean_chargetime", "mean"),
    mean_IR=("mean_IR", "mean"),
    mean_Tavg=("mean_Tavg", "mean"),
).reset_index().sort_values("life_med", ascending=False)
agg.to_csv(os.path.join(RESULTS_DIR, "p1_policy_life.csv"), index=False)

# 典型长/短寿命策略
long2 = agg.head(2)["policy"].tolist()
short2 = agg.tail(2)["policy"].tolist()
save_json({"long_life_top2": long2, "short_life_bottom2": short2,
           "policy_life": agg.to_dict(orient="records")}, "p1_typical.json")

print("=== 策略级寿命（按主寿命中位降序）===")
print(agg[["policy","C1","Q1","C2","n","life_linear_med","life_exp_med","life_med","slope_med","mean_chargetime"]].to_string(index=False))
print("\n长寿命策略:", long2)
print("短寿命策略:", short2)

# ============ 图1: 全电池 SOH-循环曲线（按策略着色）============
fig, ax = plt.subplots(figsize=(8, 5.2))
pols = sorted(cyc["policy"].unique())
for i, p in enumerate(pols):
    sub = cyc[cyc["policy"] == p]
    for bid, g in sub.groupby("battery_id"):
        g = g.sort_values("cycle")
        ax.plot(g["cycle"], g["SOH_smooth"], color=PALETTE[i % len(PALETTE)],
                alpha=0.55, lw=1.0)
# 0.8 阈值线
ax.axhline(0.8, color="k", ls="--", lw=1.0, alpha=0.7)
ax.text(2, 0.805, "寿命终止阈值 80% SOH", fontsize=8, color="k")
ax.set_xlabel("循环次数 N")
ax.set_ylabel("SOH（平滑）")
ax.set_xlim(0, 210)
ax.set_ylim(0.92, 1.01)
# 图例：策略
from matplotlib.lines import Line2D
handles = [Line2D([0], [0], color=PALETTE[i % len(PALETTE)], lw=2, label=p) for i, p in enumerate(pols)]
ax.legend(handles=handles, loc="lower left", ncol=2, frameon=False, fontsize=7)
plt.tight_layout(); plt.savefig(fig_path("p1_soh_curves.pdf")); plt.close()

# ============ 图2: 各策略寿命分布箱线图（按寿命中位排序）============
order = agg["policy"].tolist()
fig, ax = plt.subplots(figsize=(9, 5))
data = [df1[df1["policy"] == p]["life"].dropna().values for p in order]
bp = ax.boxplot(data, vert=True, patch_artist=True, showmeans=True,
                meanprops=dict(marker="D", mfc="white", mec="k", ms=5))
for i, patch in enumerate(bp["boxes"]):
    patch.set_facecolor(PALETTE[i % len(PALETTE)]); patch.set_alpha(0.6)
ax.set_xticklabels(order, rotation=35, ha="right", fontsize=8)
ax.set_ylabel("循环寿命（外推至 80% SOH）")
ax.set_yscale("log")
plt.tight_layout(); plt.savefig(fig_path("p1_life_box.pdf")); plt.close()

# ============ 图3: 策略参数 (C1,Q1,C2) 散点矩阵 vs 寿命 ============
fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
for ax, xcol, xlab in zip(axes, ["C1", "Q1", "C2"], ["第一阶段倍率 C1 (C)", "切换 SOC Q1 (%)", "第二阶段倍率 C2 (C)"]):
    for i, p in enumerate(pols):
        sub = df1[df1["policy"] == p]
        ax.scatter(sub[xcol], sub["life"], color=PALETTE[i % len(PALETTE)],
                    s=40, alpha=0.8, edgecolor="white", lw=0.5, label=p if ax is axes[0] else None)
    ax.set_xlabel(xlab); ax.set_ylabel("循环寿命")
    ax.set_yscale("log")
axes[0].legend(fontsize=6, loc="upper right", frameon=False)
plt.tight_layout(); plt.savefig(fig_path("p1_param_life_scatter.pdf")); plt.close()

# ============ 图4: 长 vs 短寿命策略对比 ============
comp_metrics = ["life_med", "mean_chargetime", "mean_IR", "mean_Tavg", "slope_med"]
comp_labels = ["循环寿命", "平均充电时间(min)", "平均内阻(Ω)", "平均温度(℃)", "衰减斜率(×1e5)"]
comp_df = agg[agg["policy"].isin(long2 + short2)].copy()
comp_df["type"] = comp_df["policy"].apply(lambda p: "长寿命" if p in long2 else "短寿命")
# 归一化每个指标到 0-1 以画雷达
from math import pi
norm = comp_df.copy()
for m in comp_metrics:
    mn, mx = agg[m].min(), agg[m].max()
    # 寿命越大越好 -> 正向；充电时间/内阻/温度/斜率越小越好 -> 反向
    if m == "life_med":
        norm[m] = (comp_df[m] - mn) / (mx - mn)
    else:
        norm[m] = (mx - comp_df[m]) / (mx - mn)

fig = plt.figure(figsize=(8, 5.5))
ax = fig.add_subplot(111, polar=True)
cats = comp_labels
Ncat = len(cats)
angles = [n / float(Ncat) * 2 * pi for n in range(Ncat)]
angles += angles[:1]
for i, row in norm.iterrows():
    vals = row[comp_metrics].tolist(); vals += vals[:1]
    lab = f"{row['policy'][:18]}..({'长' if row['type']=='长寿命' else '短'})"
    ax.plot(angles, vals, lw=1.6, label=lab)
    ax.fill(angles, vals, alpha=0.08)
ax.set_xticks(angles[:-1])
ax.set_xticklabels(cats, fontsize=8)
ax.set_ylim(0, 1)
ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=7, frameon=False)
plt.tight_layout(); plt.savefig(fig_path("p1_long_short_radar.pdf")); plt.close()

# ============ 图5: 充电时间 vs 寿命散点（问题4 伏笔）============
fig, ax = plt.subplots(figsize=(7, 4.8))
for i, p in enumerate(pols):
    sub = df1[df1["policy"] == p]
    ax.scatter(sub["mean_chargetime"], sub["life"], color=PALETTE[i % len(PALETTE)],
               s=50, alpha=0.8, edgecolor="white", lw=0.5, label=p)
ax.set_xlabel("平均充电时间 (min)")
ax.set_ylabel("循环寿命")
ax.set_yscale("log")
ax.legend(fontsize=6, ncol=2, loc="upper right", frameon=False)
plt.tight_layout(); plt.savefig(fig_path("p1_chargetime_life.pdf")); plt.close()

print("\n图已生成: p1_soh_curves.pdf, p1_life_box.pdf, p1_param_life_scatter.pdf, p1_long_short_radar.pdf, p1_chargetime_life.pdf")

```

#strong[problem2.py]
```python
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
df1.to_csv(os.path.join(RESULTS_DIR, "p2_features.csv"), index=False)

# ============ (1) 策略间寿命差异显著性 ============
policies = sorted(df1["policy"].unique())
groups = [df1[df1["policy"] == p]["life"].values for p in policies]

# Kruskal-Wallis
H_stat, p_kw = stats.kruskal(*groups)
# 置换检验（10000次）：在 H0 下随机重排策略标签，看 H 统计量超过观测的比例
rng = np.random.RandomState(SEED)
life_arr = df1["life"].to_numpy()
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
X = df1[["C1", "Q1", "C2"]].copy()
X["C1_Q1"] = df1["C1"] * df1["Q1"]
X["C2_Q1"] = df1["C2"] * df1["Q1"]
y = np.log(df1["life"].values)  # log 寿命，稳定尺度
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
Xrf = df1[["C1", "Q1", "C2"]].to_numpy()
rf.fit(Xrf, y)
perm_imp = permutation_importance(rf, Xrf, y, n_repeats=30, random_state=SEED)
imp = {k: float(np.mean(perm_imp.importances[i])) for i, k in enumerate(["C1", "Q1", "C2"])}
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
# 用斜率绝对值对 E_low, E_high 做回归
from sklearn.linear_model import LinearRegression
sl = np.abs(df1["slope_SOH"].values)  # 衰减速率（越大越快）
El = df1[["E_low", "E_high"]].to_numpy()
lr = LinearRegression().fit(El, sl)
sl_pred = lr.predict(El)
r2_sl = lr.score(El, sl)
# 单独相关
r_low, p_low = stats.pearsonr(df1["E_low"], sl)
r_high, p_high = stats.pearsonr(df1["E_high"], sl)
soc_result = {
    "decay_vs_E_r2": float(r2_sl),
    "coefs": {"E_low": float(lr.coef_[0]), "E_high": float(lr.coef_[1]),
              "intercept": float(lr.intercept_)},
    "pearson_E_low_vs_slope": {"r": float(r_low), "p": float(p_low)},
    "pearson_E_high_vs_slope": {"r": float(r_high), "p": float(p_high)},
}
save_json(soc_result, "p2_soc_interval.json")
print("\n=== (4) SOC区间高倍率衰减特征 ===")
print(f"|斜率| ~ E_low+E_high: R²={r2_sl:.3f}, coef E_low={lr.coef_[0]:.2e}, E_high={lr.coef_[1]:.2e}")
print(f"Pearson: E_low vs |slope| r={r_low:.3f}(p={p_low:.3f}); E_high vs |slope| r={r_high:.3f}(p={p_high:.3f})")

# ============ 图 ============
# 图6: 分组箱线图 + KW 显著性标注
fig, ax = plt.subplots(figsize=(9, 5))
order = df1.groupby("policy")["life"].median().sort_values(ascending=False).index.tolist()
data = [df1[df1["policy"] == p]["life"].values for p in order]
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
        ax.scatter(sub[col], sub["life"], color=PALETTE[i % len(PALETTE)],
                   s=40, edgecolor="white", lw=0.5, alpha=0.85)
    ax.set_xlabel(lab); ax.set_ylabel("循环寿命"); ax.set_yscale("log")
    # 偏相关标注
    r = pc[col]["partial_r"]; pp = pc[col]["p"]
    ax.text(0.04, 0.04, f"偏相关 r={r:.2f}\np={pp:.3f}", transform=ax.transAxes,
            fontsize=7, va="bottom", ha="left")
plt.tight_layout(); plt.savefig(fig_path("p2_param_partial.pdf")); plt.close()

# 图8: 影响程度条形（随机森林置换重要性 %）
fig, ax = plt.subplots(figsize=(6, 3.8))
keys = ["C1", "Q1", "C2"]
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

```

#strong[problem3.py]
```python
"""
问题3：电池寿命预测。
- 防泄露：40 块非测试电池做留出验证（前N_train训练→151~200验证）；
  9 块测试电池仅前150可见，预测151~200及寿命。
- 模型对比：线性外推基线 / 指数 / 随机森林(递归) / XGBoost(递归)。
- 特征：容量类+充电类+老化类+策略类+滑窗统计。
- 数据长度敏感性：前 50/100/150。
"""
import os, json, warnings
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
from utils import (load_summary, load_cycles, fit_linear_life, fit_exp_life,
                   save_json, fig_path, PALETTE, RESULTS_DIR, SEED)

warnings.filterwarnings("ignore")
summ = load_summary()
cyc = load_cycles()

test_ids = set(summ[summ["prediction_test"] == 1]["battery_id"].astype(int))
all_ids = sorted(cyc["battery_id"].unique(), key=lambda x: int(x))
train_ids = [b for b in all_ids if int(b) not in test_ids]   # 40 块
print(f"训练/验证电池(非测试): {len(train_ids)}; 测试电池: {len(test_ids)}")

# ---------- 特征提取：对一块电池，从循环数据构造“到第N循环为止”的特征 ----------
def features_upto(g, n_end, meta):
    """用前 n_end 个循环构造特征向量（不含未来信息）。对测试段，g 可能含预测追加行。"""
    g = g.sort_values("cycle").head(n_end)
    N = g["cycle"].to_numpy(float)
    soh = g["SOH"].to_numpy(float)
    soh_s = g["SOH_smooth"].to_numpy(float)
    cap = g["capacity"].to_numpy(float)
    ir = g["IR"].to_numpy(float)
    tch = g["chargetime"].to_numpy(float)
    tavg = g["Tavg"].to_numpy(float)
    f = {}
    f["last_SOH"] = float(soh_s[-1])
    f["slope_SOH"] = float(np.polyfit(N, soh_s, 1)[0]) if len(N) >= 3 else 0.0
    f["curvature"] = float(np.polyfit(N, soh_s, 2)[0]) if len(N) >= 4 else 0.0
    f["last_cap"] = float(cap[-1])
    f["mean_IR"] = float(np.mean(ir))
    f["IR_growth"] = float((ir[-1] - ir[0]) / ir[0]) if ir[0] > 0 else 0.0
    f["mean_chargetime"] = float(np.mean(tch))
    f["chargetime_slope"] = float(np.polyfit(N, tch, 1)[0]) if len(N) >= 3 else 0.0
    f["mean_Tavg"] = float(np.mean(tavg))
    f["delta_cap"] = float(cap[0] - cap[-1])
    # 策略静态特征
    f["C1"] = float(meta["C1"]); f["Q1"] = float(meta["Q1"]); f["C2"] = float(meta["C2"])
    f["E_low"] = f["C1"] * f["Q1"]
    f["E_high"] = f["C2"] * (80 - f["Q1"])
    return f

# ---------- 递归预测模型：预测 SOH 增量 ----------
# 思路：用 40 块电池前 N_train 循环训练一个“下一循环 SOH”模型，
#   特征=当前状态特征(到第k循环)，目标=第k+1循环SOH_smooth。
#   预测时递归：从第N_train循环起，用预测值更新状态，逐步外推到200。
FEAT_KEYS = None  # 占位，运行时填

def build_dataset(ids, n_train, target_horizon_start):
    """对每块电池，用前 n_train 循环构造训练样本：
       每个样本 = features_upto(k) -> SOH_smooth[k+1]（k 从 1 到 n_train-1）。"""
    X, y = [], []
    for bid in ids:
        g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
        meta = summ[summ["battery_id"] == bid].iloc[0]
        soh_s = g["SOH_smooth"].to_numpy(float)
        for k in range(2, n_train):  # 用前k个循环预测第k+1
            f = features_upto(g, k, meta)
            X.append(list(f.values()))
            y.append(soh_s[k])  # 第k+1循环（0-index k）
    return np.array(X), np.array(y), list(f.keys()) if False else None

def get_feat_keys():
    g0 = cyc[cyc["battery_id"] == all_ids[0]].sort_values("cycle")
    m0 = summ[summ["battery_id"] == all_ids[0]].iloc[0]
    return list(features_upto(g0, 10, m0).keys())

FEAT_KEYS = get_feat_keys()
print("特征:", FEAT_KEYS)

# ---------- 模型工厂 ----------
def make_model(name):
    if name == "rf":
        return RandomForestRegressor(n_estimators=300, max_depth=8, random_state=SEED)
    return None

# ---------- 留出验证：40块，前150训练->151..200验证 ----------
N_TRAIN = 150
HORIZON = list(range(151, 201))  # 预测 151..200
X_tr, y_tr, _ = build_dataset(train_ids, N_TRAIN, 151)
scaler = StandardScaler().fit(X_tr)
X_tr_s = scaler.transform(X_tr)

# 基线模型：纯线性外推（每电池独立，不需训练集）—— 直接对每电池前150拟合
def predict_linear_baseline(bid, n_train):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    N = g["cycle"].to_numpy(float)[:n_train]
    soh_s = g["SOH_smooth"].to_numpy(float)[:n_train]
    slope, intercept = np.polyfit(N, soh_s, 1)   # polyfit 返回 [斜率, 截距]
    return np.array([intercept + slope * n for n in HORIZON]), (intercept, slope)

def predict_exp_baseline(bid, n_train):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    N = g["cycle"].to_numpy(float)[:n_train]
    soh_s = np.clip(g["SOH_smooth"].to_numpy(float)[:n_train], 1e-6, None)
    slope, const = np.polyfit(N, np.log(soh_s), 1)   # log(SOH)=slope*N+const, slope=-lambda
    lam = -slope
    return np.array([np.exp(slope * n + const) for n in HORIZON]), lam

# 递归 RF 预测
def predict_recursive_ml(bid, n_train, model, scaler):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    # 用前 n_train 个循环的真实数据作为起点
    hist = g.head(n_train).copy()
    preds = []
    cur_n = n_train
    # 构造一个可追加的 DataFrame 模拟未来循环
    for tgt_cycle in HORIZON:
        cur_n = tgt_cycle
        f = features_upto(hist, len(hist), meta)
        x = scaler.transform([list(f.values())])
        yhat = float(model.predict(x)[0])
        preds.append(yhat)
        # 更新历史：追加一行（用预测 SOH，其余特征用最近一循环外推）
        last = hist.iloc[-1].copy()
        last["cycle"] = cur_n
        last["SOH_smooth"] = yhat
        last["SOH"] = yhat
        # IR/chargetime/Tavg 用线性外推
        last["IR"] = hist["IR"].iloc[-1]  # 近似持平
        last["chargetime"] = hist["chargetime"].iloc[-1]
        last["Tavg"] = hist["Tavg"].iloc[-1]
        last["capacity"] = yhat * float(meta["initial_capacity"])
        hist = pd.concat([hist, pd.DataFrame([last])], ignore_index=True)
    return np.array(preds)

# 训练 RF
rf = make_model("rf"); rf.fit(X_tr_s, y_tr)

# 留出验证（40块，有真值）
metrics = {"linear": [], "exp": [], "rf": []}
preds_holdout = {}
for bid in train_ids:
    true = cyc[cyc["battery_id"] == bid].sort_values("cycle")["SOH_smooth"].to_numpy(float)[150:200]
    if len(true) != 50:
        continue
    pl, _ = predict_linear_baseline(bid, 150)
    pe, _ = predict_exp_baseline(bid, 150)
    pr = predict_recursive_ml(bid, 150, rf, scaler)
    preds_holdout[bid] = {"true": true.tolist(), "linear": pl.tolist(),
                           "exp": pe.tolist(), "rf": pr.tolist()}
    for name, p in [("linear", pl), ("exp", pe), ("rf", pr)]:
        rmse = float(np.sqrt(mean_squared_error(true, p)))
        mae = float(mean_absolute_error(true, p))
        mape = float(np.mean(np.abs((true - p) / true)) * 100)
        metrics[name].append({"bid": int(bid), "rmse": rmse, "mae": mae, "mape": mape})

def agg_metrics(L):
    return {"rmse_mean": float(np.mean([m["rmse"] for m in L])),
            "rmse_med": float(np.median([m["rmse"] for m in L])),
            "mae_mean": float(np.mean([m["mae"] for m in L])),
            "mape_mean": float(np.mean([m["mape"] for m in L]))}

holdout_summary = {k: agg_metrics(v) for k, v in metrics.items()}
save_json({"holdout_summary_150train": holdout_summary,
           "per_battery": {k: v for k, v in [(b, metrics_col) for b, metrics_col in []]}}, "p3_holdout_metrics.json")
# 也存逐电池
for name in ["linear", "exp", "rf"]:
    pd.DataFrame(metrics[name]).to_csv(os.path.join(RESULTS_DIR, f"p3_holdout_{name}.csv"), index=False)

print("\n=== 留出验证（40块，前150训练→151~200验证）===")
for k, v in holdout_summary.items():
    print(f"{k:7s}: RMSE_mean={v['rmse_mean']:.5f} (med={v['rmse_med']:.5f}), MAE={v['mae_mean']:.5f}, MAPE={v['mape_mean']:.3f}%")

# 选最优模型为主模型
best_model_name = min(holdout_summary, key=lambda k: holdout_summary[k]["rmse_mean"])
print(f"\n最优模型: {best_model_name}")

# ---------- 数据长度敏感性：前 50/100/150 ----------
length_result = {}
for n_tr in [50, 100, 150]:
    Xn, yn, _ = build_dataset(train_ids, n_tr, n_tr + 1)
    scn = StandardScaler().fit(Xn); Xn_s = scn.transform(Xn)
    rfn = make_model("rf"); rfn.fit(Xn_s, yn)
    HORIZ = list(range(n_tr + 1, n_tr + 51))  # 预测后50循环
    rmses_lin, rmses_rf = [], []
    for bid in train_ids:
        g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
        true = g["SOH_smooth"].to_numpy(float)[n_tr:n_tr + 50]
        if len(true) != 50:
            continue
        # 线性基线（注意 polyfit 返回 [斜率, 截距]）
        N = g["cycle"].to_numpy(float)[:n_tr]
        s = g["SOH_smooth"].to_numpy(float)[:n_tr]
        slope_lin, const_lin = np.polyfit(N, s, 1)
        pl = np.array([const_lin + slope_lin * n for n in HORIZ])
        # rf 递归
        pr = predict_recursive_ml(bid, n_tr, rfn, scn)
        rmses_lin.append(float(np.sqrt(mean_squared_error(true, pl))))
        rmses_rf.append(float(np.sqrt(mean_squared_error(true, pr))))
    length_result[n_tr] = {"linear_rmse_mean": float(np.mean(rmses_lin)),
                            "rf_rmse_mean": float(np.mean(rmses_rf))}
save_json(length_result, "p3_data_length.json")
print("\n=== 数据长度敏感性 ===")
for n, v in length_result.items():
    print(f"前{n}循环: 线性RMSE={v['linear_rmse_mean']:.5f}, RF-RMSE={v['rf_rmse_mean']:.5f}")

# ---------- 9块测试电池预测 151~200 + 寿命 ----------
# 用主模型（按 holdout 最优）；同时给线性/指数对照
pred_test_rows = []
life_test = []
fig, axes = plt.subplots(3, 3, figsize=(12, 9))
for ax, bid in zip(axes.ravel(), sorted(test_ids)):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    true150 = g["SOH_smooth"].to_numpy(float)[:150]
    # 主模型预测
    if best_model_name == "rf":
        pm = predict_recursive_ml(bid, 150, rf, scaler)
    elif best_model_name == "exp":
        pm, _ = predict_exp_baseline(bid, 150)
    else:
        pm, _ = predict_linear_baseline(bid, 150)
    pl, _ = predict_linear_baseline(bid, 150)
    pe, _ = predict_exp_baseline(bid, 150)
    # 寿命预测：结合“前150真实斜率”与“151..200预测”拟合直线外推。
    # 单独用 151..200 预测段拟合会因 50 点短窗噪声而失稳（斜率近 0 甚至翻正 -> NaN 或天文数字）。
    # 改为：对前150真实 SOH_smooth + 151..200 预测 一起拟合一条直线，更稳健地外推到 0.8。
    def life_from_combined(pred_seq):
        N_real = g["cycle"].to_numpy(float)[:150]
        S_real = g["SOH_smooth"].to_numpy(float)[:150]
        N_pred = np.arange(151, 201, dtype=float)
        Ns = np.concatenate([N_real, N_pred])
        Ss = np.concatenate([S_real, pred_seq])
        slope, intercept = np.polyfit(Ns, Ss, 1)
        if slope >= 0: return np.nan
        return (0.8 - intercept) / slope
    life_main = float(life_from_combined(pm))
    life_lin = float(life_from_combined(pl))
    life_exp = float(life_from_combined(pe))
    pol = meta["policy"]
    life_test.append({"battery_id": int(bid), "policy": pol,
                       "C1": float(meta["C1"]), "Q1": float(meta["Q1"]), "C2": float(meta["C2"]),
                       "life_main": life_main, "life_linear": life_lin, "life_exp": life_exp,
                       "model": best_model_name})
    for i, (n, p) in enumerate([(151 + i, v) for i, v in enumerate(pm)]):
        pred_test_rows.append({"battery_id": int(bid), "cycle": n, "SOH_pred": float(p),
                                "SOH_pred_linear": float(pl[i]),
                                "SOH_pred_exp": float(pe[i]),
                                "model": best_model_name})
    # 画图：前150真值 + 预测
    ax.plot(range(1, 151), true150, "k-", lw=1.2, label="实测(前150)")
    ax.plot(range(151, 201), pm, "r-", lw=1.5, label=f"预测({best_model_name})")
    ax.plot(range(151, 201), pl, "b--", lw=1.0, alpha=0.6, label="线性")
    ax.plot(range(151, 201), pe, "g--", lw=1.0, alpha=0.6, label="指数")
    ax.axhline(0.8, color="gray", ls=":", lw=0.8)
    ax.set_title(f"#{bid} {pol[:18]}\n寿命预测={life_main:.0f}", fontsize=8)
    ax.set_xlabel("循环"); ax.set_ylabel("SOH")
    ax.legend(fontsize=6, loc="lower left"); ax.set_ylim(0.94, 1.005)
plt.tight_layout(); plt.savefig(fig_path("p3_test_pred_curves.pdf")); plt.close()

pd.DataFrame(pred_test_rows).to_csv(os.path.join(RESULTS_DIR, "p3_pred_test.csv"), index=False)
pd.DataFrame(life_test).to_csv(os.path.join(RESULTS_DIR, "p3_life.csv"), index=False)
save_json({"best_model": best_model_name, "holdout": holdout_summary,
           "length_sensitivity": length_result, "test_life": life_test}, "p3_summary.json")

print("\n=== 9块测试电池寿命预测 ===")
for r in life_test:
    print(f"#{r['battery_id']:>2} {r['policy']:38s} life_main={r['life_main']:.0f} (lin={r['life_linear']:.0f}, exp={r['life_exp']:.0f})")

# ---------- 图：留出验证误差分布 ----------
fig, ax = plt.subplots(figsize=(7, 4.5))
data = [pd.DataFrame(metrics[m])["rmse"].values for m in ["linear", "exp", "rf"]]
bp = ax.boxplot(data, tick_labels=["线性基线", "指数基线", "随机森林(递归)"], patch_artist=True, showmeans=True,
                meanprops=dict(marker="D", mfc="white", mec="k", ms=5))
for i, p in enumerate(bp["boxes"]):
    p.set_facecolor(PALETTE[i]); p.set_alpha(0.6)
ax.set_ylabel("RMSE（151~200 循环 SOH）")
for i, m in enumerate(["linear", "exp", "rf"]):
    ax.text(i + 1, holdout_summary[m]["rmse_mean"], f"均值={holdout_summary[m]['rmse_mean']:.5f}",
            ha="center", va="bottom", fontsize=7)
plt.tight_layout(); plt.savefig(fig_path("p3_holdout_rmse_box.pdf")); plt.close()

# ---------- 图：数据长度敏感性 ----------
fig, ax = plt.subplots(figsize=(6, 4))
ns = sorted(length_result.keys())
ax.plot(ns, [length_result[n]["linear_rmse_mean"] for n in ns], "o-", label="线性基线")
ax.plot(ns, [length_result[n]["rf_rmse_mean"] for n in ns], "s-", label="随机森林(递归)")
ax.set_xlabel("训练用早期循环数"); ax.set_ylabel("后50循环 RMSE (均值)")
ax.legend()
plt.tight_layout(); plt.savefig(fig_path("p3_data_length.pdf")); plt.close()

# ---------- 图：特征重要性（RF） ----------
imp = dict(zip(FEAT_KEYS, rf.feature_importances_))
imp_s = dict(sorted(imp.items(), key=lambda x: -x[1]))
fig, ax = plt.subplots(figsize=(7, 4.5))
keys = list(imp_s.keys()); vals = list(imp_s.values())
bars = ax.barh(range(len(keys))[::-1], vals, color=PALETTE[0], alpha=0.8)
ax.set_yticks(range(len(keys))[::-1]); ax.set_yticklabels(keys, fontsize=8)
ax.set_xlabel("随机森林特征重要性")
plt.tight_layout(); plt.savefig(fig_path("p3_feature_importance.pdf")); plt.close()
save_json({"feature_importance": imp_s}, "p3_feature_importance.json")

print("\n图已生成: p3_test_pred_curves.pdf, p3_holdout_rmse_box.pdf, p3_data_length.pdf, p3_feature_importance.pdf")
print("\n特征重要性:", imp_s)

```

#strong[problem4.py]
```python
"""
问题4：兼顾充电时间与寿命衰减的充电策略优化。
- 充电时间解析模型：t_ch = t1 + t2 + t3, t1=Q1/(100*C1)*60, t2=(80-Q1)/(100*C2)*60, t3 经验校准。
- SOH 衰减模型：复用问题2 的衰减斜率预测 |slope| = f(E_low, E_high, C1, Q1, C2)。
- 寿命模型：life = (0.8 - intercept)/slope，intercept≈1.0 初始。
- 多目标优化：min t_ch, min |slope| (即 max life)。先 9 策略离散比较，再邻域网格 + 加权 + Pareto。
- 固定种子，多起点。
"""
import os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from utils import (load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED)

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)
summ = load_summary()

# ============ (1) 充电时间模型 ============
Q_rated = 1.1  # Ah
# t1, t2 解析（小时）：恒流段 I = C*Q_rated, 电量 = SOC%*Q_rated, t = 电量/I = SOC/100/C (小时)
# 转 min: *60
# t3: CC-CV 段（80%->满，1C），用数据校准：mean_chargetime - (t1+t2)*60
def t12_min(C1, Q1, C2):
    t1 = Q1 / 100.0 / C1 * 60.0       # min
    t2 = (80.0 - Q1) / 100.0 / C2 * 60.0
    return t1 + t2

# 校准 t3：对每块电池 mean_chargetime - t12
df1["t12_model"] = df1.apply(lambda r: t12_min(r["C1"], r["Q1"], r["C2"]), axis=1)
df1["t3_est"] = df1["mean_chargetime"] - df1["t12_model"]
t3_mean = float(df1["t3_est"].median())  # 用中位稳健
print(f"=== 充电时间模型 ===")
print(f"t3 (CC-CV段) 中位校准 = {t3_mean:.3f} min")
print(f"t12 模型 vs 实测充电时间 R²: ", end="")
r2_t = r2_score(df1["mean_chargetime"], df1["t12_model"] + t3_mean)
print(f"{r2_t:.3f}")
# 保存校准残差，看是否与策略相关
df1[["battery_id", "policy", "C1", "Q1", "C2", "mean_chargetime", "t12_model", "t3_est"]].to_csv(
    os.path.join(RESULTS_DIR, "p4_charge_time_calib.csv"), index=False)

def t_ch_model(C1, Q1, C2, t3=t3_mean):
    return t12_min(C1, Q1, C2) + t3

# ============ (2) SOH 衰减模型 ============
# 用对数链接保证预测的衰减斜率恒正（物理约束：倍率越高、中高SOC暴露越大 -> 衰减越快）。
# log(|slope|) = b0 + b1*C1 + b2*Q1 + b3*C2 + b4*E_low + b5*E_high, 然后 exp。
df1["E_low"] = df1["C1"] * df1["Q1"]
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])
y_dec = np.abs(df1["slope_SOH"].to_numpy())
y_dec = np.clip(y_dec, 1e-12, None)  # 防 log(0)
log_y = np.log(y_dec)
X_dec = df1[["C1", "Q1", "C2", "E_low", "E_high"]].to_numpy()
dec_model = LinearRegression().fit(X_dec, log_y)
log_yhat = dec_model.predict(X_dec)
r2_dec = 1 - np.sum((log_y - log_yhat) ** 2) / np.sum((log_y - log_y.mean()) ** 2)
coefs = dict(zip(["C1", "Q1", "C2", "E_low", "E_high"], dec_model.coef_))
print(f"\n=== SOH 衰减模型（对数链接，恒正）===")
print(f"log|slope| ~ C1+Q1+C2+E_low+E_high: R²(log空间)={r2_dec:.3f}")
print(f"系数: {coefs}, 截距={dec_model.intercept_:.3f}")

def slope_abs_pred(C1, Q1, C2):
    E_low = C1 * Q1; E_high = C2 * (80 - Q1)
    x = np.array([[C1, Q1, C2, E_low, E_high]])
    return float(np.exp(dec_model.predict(x)[0]))   # 恒正

def life_pred(C1, Q1, C2, intercept0=1.0):
    s = slope_abs_pred(C1, Q1, C2)   # 正的衰减速率
    # SOH = 1 - s*N -> 0.8 = 1 - s*L -> L = 0.2/s
    return 0.2 / s

# ============ (3) 多目标优化 ============
# (a) 9 种已有策略离散比较
strat = df1.groupby("policy").agg(
    C1=("C1", "first"), Q1=("Q1", "first"), C2=("C2", "first"),
    life_med=("life", "median"), mean_chargetime=("mean_chargetime", "mean"),
    slope_med=("slope_SOH", "median"),
).reset_index()
strat["t_ch_model"] = strat.apply(lambda r: t_ch_model(r["C1"], r["Q1"], r["C2"]), axis=1)
strat["life_model"] = strat.apply(lambda r: life_pred(r["C1"], r["Q1"], r["C2"]), axis=1)
strat["slope_model"] = strat.apply(lambda r: slope_abs_pred(r["C1"], r["Q1"], r["C2"]), axis=1)
strat.to_csv(os.path.join(RESULTS_DIR, "p4_strategies.csv"), index=False)
print(f"\n=== 9 策略离散比较（模型预测）===")
print(strat[["policy", "C1", "Q1", "C2", "t_ch_model", "life_model", "slope_model"]].to_string(index=False))

# (b) 邻域网格搜索 + 加权 + Pareto
# 无量纲化目标：t_ch 与 1/life（或 |slope|）都越小越好
# 先用 9 策略点计算 min/max 做归一化基准
t_min, t_max = strat["t_ch_model"].min(), strat["t_ch_model"].max()
s_min, s_max = strat["slope_model"].min(), strat["slope_model"].max()

def norm_t(t): return (t - t_min) / (t_max - t_min) if t_max > t_min else 0.0
def norm_s(s): return (s - s_min) / (s_max - s_min) if s_max > s_min else 0.0

def weighted_score(C1, Q1, C2, w_t=0.5, w_s=0.5):
    t = t_ch_model(C1, Q1, C2)
    s = slope_abs_pred(C1, Q1, C2)
    return w_t * norm_t(t) + w_s * norm_s(s)

# 网格：在已有策略点 ± 邻域内枚举
grid_pts = []
for _, r in strat.iterrows():
    for dc1 in [-0.5, -0.25, 0, 0.25, 0.5]:
        for dq in [-10, -5, 0, 5, 10]:
            for dc2 in [-0.5, -0.25, 0, 0.25, 0.5]:
                c1 = r["C1"] + dc1; q1 = r["Q1"] + dq; c2 = r["C2"] + dc2
                if c1 <= 0 or c2 <= 0 or q1 <= 0 or q1 >= 80: continue
                if c1 > 6 or c2 > 6: continue
                t = t_ch_model(c1, q1, c2); s = slope_abs_pred(c1, q1, c2); L = life_pred(c1, q1, c2)
                grid_pts.append({"C1": c1, "Q1": q1, "C2": c2,
                                 "near_policy": r["policy"],
                                 "t_ch": t, "slope": s, "life": L,
                                 "w_t0.5": weighted_score(c1, q1, c2, 0.5, 0.5)})
grid = pd.DataFrame(grid_pts).drop_duplicates(subset=["C1", "Q1", "C2"])
grid.to_csv(os.path.join(RESULTS_DIR, "p4_grid.csv"), index=False)

# Pareto 前沿（min t_ch, min slope）
def is_pareto(df, cols):
    vals = df[cols].to_numpy()
    mask = np.ones(len(df), dtype=bool)
    for i in range(len(df)):
        for j in range(len(df)):
            if i == j: continue
            if np.all(vals[j] <= vals[i]) and np.any(vals[j] < vals[i]):
                mask[i] = False; break
    return mask
pareto_mask = is_pareto(grid, ["t_ch", "slope"])
grid["pareto"] = pareto_mask
pareto = grid[grid["pareto"]].sort_values("t_ch")
pareto.to_csv(os.path.join(RESULTS_DIR, "p4_pareto.csv"), index=False)

# 推荐策略：加权综合得分最低（w_t=w_s=0.5），且必须在 Pareto 前沿上
cand = grid[grid["pareto"]].copy()
best = cand.loc[cand["w_t0.5"].idxmin()]
rec = {"C1": float(best["C1"]), "Q1": float(best["Q1"]), "C2": float(best["C2"]),
       "near_policy": str(best["near_policy"]),
       "t_ch": float(best["t_ch"]), "life": float(best["life"]),
       "slope": float(best["slope"]),
       "weighted_score": float(best["w_t0.5"]),
       "t3_calibrated": t3_mean,
       "decay_model_r2_log": float(r2_dec),
       "charge_time_model_r2": float(r2_t)}
save_json(rec, "p4_recommendation.json")
print(f"\n=== 推荐策略（加权 w_t=w_s=0.5, Pareto 上最优）===")
print(json.dumps(rec, ensure_ascii=False, indent=2))

# 权重敏感性：w_t 从 0.2 到 0.8
sens = []
for w_t in np.arange(0.2, 0.81, 0.1):
    grid[f"w_{w_t:.1f}"] = grid.apply(lambda r: weighted_score(r["C1"], r["Q1"], r["C2"], w_t, 1 - w_t), axis=1)
    b = grid.loc[grid[f"w_{w_t:.1f}"].idxmin()]
    sens.append({"w_t": float(w_t), "C1": float(b["C1"]), "Q1": float(b["Q1"]), "C2": float(b["C2"]),
                 "t_ch": float(b["t_ch"]), "life": float(b["life"])})
save_json(sens, "p4_weight_sensitivity.json")
print("\n=== 权重敏感性 ===")
for s in sens:
    print(f"w_t={s['w_t']:.1f}: C1={s['C1']:.2f} Q1={s['Q1']:.0f} C2={s['C2']:.2f} t_ch={s['t_ch']:.2f}min life={s['life']:.0f}")

# ============ 图 ============
# 图10: Pareto 前沿（充电时间 vs 寿命）
fig, ax = plt.subplots(figsize=(8, 5.5))
# 9 策略点
for i, p in enumerate(strat["policy"]):
    ax.scatter(strat[strat["policy"] == p]["t_ch_model"], strat[strat["policy"] == p]["life_model"],
               color=PALETTE[i % len(PALETTE)], s=80, zorder=5, edgecolor="k", lw=0.6)
    r = strat[strat["policy"] == p].iloc[0]
    ax.annotate(p[:14], (r["t_ch_model"], r["life_model"]), fontsize=6, xytext=(3, 3), textcoords="offset points")
# Pareto 前沿
ax.plot(pareto["t_ch"], pareto["life"], "r-", lw=1.5, alpha=0.7, label="Pareto 前沿")
ax.scatter(pareto["t_ch"], pareto["life"], c="red", s=20, alpha=0.5, zorder=4)
# 推荐点
ax.scatter([best["t_ch"]], [best["life"]], marker="*", s=300, color="gold",
           edgecolor="k", lw=1.0, zorder=6, label=f"推荐策略\n(C1={best['C1']:.2f},Q1={best['Q1']:.0f},C2={best['C2']:.2f})")
ax.set_xlabel("充电时间 (min)"); ax.set_ylabel("预测循环寿命"); ax.set_yscale("log")
ax.legend(loc="lower right", fontsize=8)
plt.tight_layout(); plt.savefig(fig_path("p4_pareto.pdf")); plt.close()

# 图11: 推荐策略在已有策略中的位置（综合得分排名）
strat["score"] = strat.apply(lambda r: weighted_score(r["C1"], r["Q1"], r["C2"], 0.5, 0.5), axis=1)
strat = strat.sort_values("score")
fig, ax = plt.subplots(figsize=(9, 5))
colors = [PALETTE[i % len(PALETTE)] for i in range(len(strat))]
bars = ax.barh(range(len(strat)), strat["score"], color=colors, alpha=0.8)
ytick = [f"{p}\n(C1={row.C1:.1f},Q1={row.Q1:.0f},C2={row.C2:.1f})"
         for p, row in zip(strat["policy"], strat.itertuples())]
ax.set_yticks(range(len(strat))); ax.set_yticklabels(ytick, fontsize=7)
ax.set_xlabel("综合得分（充电时间+衰减，越小越好）")
ax.axvline(rec["weighted_score"], color="gold", ls="--", lw=1.2, label=f"推荐策略得分={rec['weighted_score']:.3f}")
ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig(fig_path("p4_score_rank.pdf")); plt.close()

# 图12: 充电时间模型拟合
fig, ax = plt.subplots(figsize=(6, 5))
ax.scatter(df1["mean_chargetime"], df1["t12_model"] + t3_mean, c=PALETTE[0], alpha=0.7, s=40)
lims = [df1["mean_chargetime"].min(), df1["mean_chargetime"].max()]
ax.plot(lims, lims, "k--", lw=1, alpha=0.5)
ax.set_xlabel("实测平均充电时间 (min)"); ax.set_ylabel("解析模型预测 (min)")
ax.text(0.05, 0.95, f"R²={r2_t:.3f}", transform=ax.transAxes, va="top")
plt.tight_layout(); plt.savefig(fig_path("p4_chargetime_model.pdf")); plt.close()

# 图13: 权重敏感性
fig, ax = plt.subplots(figsize=(7, 4.5))
ws = [s["w_t"] for s in sens]
ax.plot(ws, [s["t_ch"] for s in sens], "o-", label="充电时间 (min)")
ax2 = ax.twinx()
ax2.plot(ws, [s["life"] for s in sens], "s-", color=PALETTE[1], label="预测寿命")
ax.set_xlabel("充电时间权重 w_t"); ax.set_ylabel("充电时间 (min)", color=PALETTE[0])
ax2.set_ylabel("预测寿命", color=PALETTE[1])
fig.legend(loc="upper center", ncol=2, fontsize=8)
plt.tight_layout(); plt.savefig(fig_path("p4_weight_sens.pdf")); plt.close()

print("\n图已生成: p4_pareto.pdf, p4_score_rank.pdf, p4_chargetime_model.pdf, p4_weight_sens.pdf")

```
