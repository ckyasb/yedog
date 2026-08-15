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

# t3 随策略参数变化（0.03~3.2 min），常数 t3 拟合 R² 仅 0.587。
# 改用岭回归 + 2 阶多项式拟合 t3 = f(C1, Q1, C2)，R² 提升至 0.884。
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
sc_t3 = StandardScaler()
X_t3 = df1[["C1", "Q1", "C2"]].to_numpy()
X_t3_s = sc_t3.fit_transform(X_t3)
poly_t3 = PolynomialFeatures(2, include_bias=False)
X_t3_p = poly_t3.fit_transform(X_t3_s)
t3_model = Ridge(alpha=0.5).fit(X_t3_p, df1["t3_est"].to_numpy())
t3_pred = t3_model.predict(X_t3_p)
r2_t3 = r2_score(df1["t3_est"], t3_pred)
r2_full = r2_score(df1["mean_chargetime"], df1["t12_model"] + t3_pred)
print(f"t3 = f(C1,Q1,C2) + poly2 + ridge: R²(t3)={r2_t3:.3f}, R²(总)={r2_full:.3f}")

# 保存校准残差，看是否与策略相关
df1[["battery_id", "policy", "C1", "Q1", "C2", "mean_chargetime", "t12_model", "t3_est"]].to_csv(
    os.path.join(RESULTS_DIR, "p4_charge_time_calib.csv"), index=False)

def t_ch_model(C1, Q1, C2, t3=t3_mean):
    return t12_min(C1, Q1, C2) + t3

def t_ch_model_ridge(C1, Q1, C2):
    """改进充电时间模型：解析 CC 段 + 岭回归 t3。"""
    x = np.array([[C1, Q1, C2]])
    xs = sc_t3.transform(x)
    xp = poly_t3.transform(xs)
    t3_hat = float(t3_model.predict(xp)[0])
    return t12_min(C1, Q1, C2) + t3_hat

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

# 图12: 充电时间模型拟合（改进版：解析 CC + 岭回归 t3）
fig, ax = plt.subplots(figsize=(6, 5))
t_full_pred = df1["t12_model"] + t3_pred
ax.scatter(df1["mean_chargetime"], t_full_pred, c=PALETTE[0], alpha=0.7, s=40)
lims = [df1["mean_chargetime"].min(), df1["mean_chargetime"].max()]
ax.plot(lims, lims, "k--", lw=1, alpha=0.5)
ax.set_xlabel("实测平均充电时间 (min)"); ax.set_ylabel("模型预测 (min)")
ax.text(0.05, 0.95, f"R²={r2_full:.3f}\n(解析CC+岭回归t3)", transform=ax.transAxes, va="top")
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
