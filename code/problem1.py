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
