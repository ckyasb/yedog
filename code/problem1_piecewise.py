"""
P1优化: 分段SOH拟合 — 前50循环(初期)vs 后100循环(稳态)不同斜率。
捕捉SOH衰减的"初期快速-后期平稳"两阶段特征。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from utils import load_cycles, load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED

cyc = load_cycles()
summ = load_summary()

records = []
for bid, g in cyc.groupby("battery_id"):
    g = g.sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    N = g["cycle"].to_numpy(float)
    soh_s = g["SOH_smooth"].to_numpy(float)
    n = len(soh_s)

    # Overall linear fit
    k_all, a_all = np.polyfit(N, soh_s, 1)
    life_all = (0.8 - a_all) / k_all if k_all < 0 else np.nan

    # Piecewise: first 50 cycles (initial) vs rest (steady-state)
    split = min(50, n - 2)
    if split >= 3 and (n - split) >= 3:
        k_early, a_early = np.polyfit(N[:split], soh_s[:split], 1)
        k_late, a_late = np.polyfit(N[split:], soh_s[split:], 1)
    else:
        k_early, a_early = k_all, a_all
        k_late, a_late = k_all, a_all

    # Use late-stage slope for life extrapolation (more representative of long-term trend)
    life_late = (0.8 - a_late) / k_late if k_late < 0 else np.nan

    # Also try: weighted average of early and late slopes
    # Weight late slope more (90%) since it's the long-term trend
    k_weighted = 0.1 * k_early + 0.9 * k_late
    a_weighted = 0.1 * a_early + 0.9 * a_late
    life_weighted = (0.8 - a_weighted) / k_weighted if k_weighted < 0 else np.nan

    # Bootstrap CI for weighted life
    rng = np.random.RandomState(SEED + int(bid))
    boot_lives = []
    for _ in range(1000):
        idx = rng.choice(n, n, replace=True)
        if len(np.unique(idx)) < 5: continue
        x = N[idx]; y = soh_s[idx]
        order = np.argsort(x)
        x, y = x[order], y[order]
        sp = min(50, len(x) - 2)
        if sp >= 3 and (len(x) - sp) >= 3:
            kw = 0.1 * np.polyfit(x[:sp], y[:sp], 1)[0] + 0.9 * np.polyfit(x[sp:], y[sp:], 1)[0]
            aw = 0.1 * np.polyfit(x[:sp], y[:sp], 1)[1] + 0.9 * np.polyfit(x[sp:], y[sp:], 1)[1]
        else:
            kw, aw = np.polyfit(x, y, 1)
        if kw < 0 and (0.8 - aw) / kw > 200 and (0.8 - aw) / kw < 1e6:
            boot_lives.append((0.8 - aw) / kw)
    boot_lives = np.array(boot_lives)

    records.append({
        "battery_id": int(bid),
        "policy": meta["policy"],
        "slope_all": float(k_all),
        "slope_early": float(k_early),
        "slope_late": float(k_late),
        "life_all": float(life_all) if np.isfinite(life_all) else None,
        "life_late": float(life_late) if np.isfinite(life_late) else None,
        "life_weighted": float(life_weighted) if np.isfinite(life_weighted) else None,
        "boot_ci_lo": float(np.percentile(boot_lives, 2.5)) if len(boot_lives) > 10 else None,
        "boot_ci_hi": float(np.percentile(boot_lives, 97.5)) if len(boot_lives) > 10 else None,
    })

df_pw = pd.DataFrame(records)
df_pw.to_csv(os.path.join(RESULTS_DIR, "p1_piecewise_life.csv"), index=False)

# Strategy-level
agg = df_pw.groupby("policy").agg(
    life_all_med=("life_all", "median"),
    life_late_med=("life_late", "median"),
    life_weighted_med=("life_weighted", "median"),
    slope_early_med=("slope_early", "median"),
    slope_late_med=("slope_late", "median"),
).reset_index().sort_values("life_weighted_med", ascending=False)
agg.to_csv(os.path.join(RESULTS_DIR, "p1_piecewise_policy.csv"), index=False)

print("=== P1 分段拟合寿命 ===")
print(agg[["policy", "life_all_med", "life_late_med", "life_weighted_med",
          "slope_early_med", "slope_late_med"]].to_string(index=False))

# Compare with original
df_orig = pd.read_csv(os.path.join(RESULTS_DIR, "p1_policy_life.csv"))
print("\n=== 与原始寿命对比 ===")
for _, row in agg.iterrows():
    orig = df_orig[df_orig["policy"] == row["policy"]]["life_med"].values
    orig_val = float(orig[0]) if len(orig) > 0 else np.nan
    print(f"{row['policy']:38s} 原始={orig_val:.0f} 分段={row['life_weighted_med']:.0f} 差异={row['life_weighted_med']-orig_val:.0f}")

# Plot: early vs late slope
fig, ax = plt.subplots(figsize=(8, 5))
policies = agg["policy"].tolist()
x = range(len(policies))
ax.bar([i - 0.15 for i in x], agg["slope_early_med"] * 1e5, 0.3, label="初期斜率(前50循环)", color=PALETTE[0], alpha=0.7)
ax.bar([i + 0.15 for i in x], agg["slope_late_med"] * 1e5, 0.3, label="稳态斜率(50循环后)", color=PALETTE[1], alpha=0.7)
ax.set_xticks(list(x))
ax.set_xticklabels([p[:15] for p in policies], rotation=35, ha="right", fontsize=7)
ax.set_ylabel("SOH衰减速率 (×1e5)")
ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(fig_path("p1_piecewise_slope.pdf"))
plt.close()

print("\n图已生成: p1_piecewise_slope.pdf")
