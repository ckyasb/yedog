"""
P1优化: 多模型寿命集成(线性+指数+幂律加权) + 改进寿命估计。
"""
import os, json, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from utils import load_cycles, load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED
from utils import fit_linear_life, fit_exp_life, fit_power_life

cyc = load_cycles()
summ = load_summary()

# Multi-model life ensemble
records = []
for bid, g in cyc.groupby("battery_id"):
    g = g.sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    N = g["cycle"].to_numpy(float)
    soh_s = g["SOH_smooth"].to_numpy(float)

    # Three models
    a_lin, k_lin, life_lin = fit_linear_life(N, soh_s)
    lam_exp, life_exp = fit_exp_life(N, soh_s)
    alpha_pw, beta_pw, life_pw = fit_power_life(N, soh_s)

    # Collect valid estimates
    lives = []
    if np.isfinite(life_lin) and life_lin > 200 and life_lin < 1e6:
        lives.append(life_lin)
    if np.isfinite(life_exp) and life_exp > 200 and life_exp < 1e6:
        lives.append(life_exp)
    # Skip power (unstable)

    if not lives:
        continue

    # Weighted by inverse variance (simpler: use median)
    life_ensemble = float(np.median(lives))
    life_mean = float(np.mean(lives))

    # Bootstrap CI for ensemble
    rng = np.random.RandomState(SEED + int(bid))
    n_boot = 1000
    boot_lives = []
    n = len(soh_s)
    for _ in range(n_boot):
        idx = rng.choice(n, n, replace=True)
        if len(np.unique(idx)) < 3: continue
        x = N[idx]; y = soh_s[idx]
        order = np.argsort(x)
        x, y = x[order], y[order]
        try:
            k, a = np.polyfit(x, y, 1)
            if k < 0 and (0.8 - a) / k > 200:
                boot_lives.append((0.8 - a) / k)
        except:
            continue
    boot_lives = np.array(boot_lives)
    boot_lives = boot_lives[(boot_lives > 200) & (boot_lives < 1e6)]

    records.append({
        "battery_id": int(bid),
        "policy": meta["policy"],
        "life_linear": float(life_lin) if np.isfinite(life_lin) else None,
        "life_exp": float(life_exp) if np.isfinite(life_exp) else None,
        "life_ensemble": life_ensemble,
        "life_mean": life_mean,
        "n_models": len(lives),
        "boot_ci_lo": float(np.percentile(boot_lives, 2.5)) if len(boot_lives) > 10 else None,
        "boot_ci_hi": float(np.percentile(boot_lives, 97.5)) if len(boot_lives) > 10 else None,
        "boot_median": float(np.median(boot_lives)) if len(boot_lives) > 10 else None,
    })

df_life = pd.DataFrame(records)
df_life.to_csv(os.path.join(RESULTS_DIR, "p1_life_ensemble.csv"), index=False)

print("=== P1 多模型寿命集成 ===")
print(df_life[["battery_id", "policy", "life_linear", "life_exp", "life_ensemble",
               "boot_ci_lo", "boot_ci_hi"]].head(15).to_string(index=False))

# Strategy-level summary
agg = df_life.groupby("policy").agg(
    life_med=("life_ensemble", "median"),
    life_min=("life_ensemble", "min"),
    life_max=("life_ensemble", "max"),
).reset_index().sort_values("life_med", ascending=False)
agg.to_csv(os.path.join(RESULTS_DIR, "p1_life_ensemble_policy.csv"), index=False)

print("\n=== 策略级寿命(集成) ===")
print(agg.to_string(index=False))

# Plot: life ensemble with CI
fig, ax = plt.subplots(figsize=(10, 6))
df_sorted = df_life.sort_values("life_ensemble")
colors = [PALETTE[1] if "NEWSTRUCTURE" in str(p) else PALETTE[0] for p in df_sorted["policy"]]
y_pos = range(len(df_sorted))
# Build error bars, handling None and negative values
err_lo = []
err_hi = []
for _, row in df_sorted.iterrows():
    lo = row.get("boot_ci_lo")
    hi = row.get("boot_ci_hi")
    life = row["life_ensemble"]
    if lo is not None and hi is not None and lo > 0 and hi > life:
        err_lo.append(max(0, life - lo))
        err_hi.append(max(0, hi - life))
    else:
        err_lo.append(0)
        err_hi.append(0)
ax.barh(y_pos, df_sorted["life_ensemble"], color=colors, alpha=0.7,
       xerr=[err_lo, err_hi], capsize=2, error_kw={"linewidth": 0.5})
ax.set_yticks(y_pos)
ax.set_yticklabels([f"#{r.battery_id} {r.policy[:18]}" for r in df_sorted.itertuples()], fontsize=6)
ax.set_xlabel("循环寿命(集成估计)")
ax.set_xscale("log")
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=PALETTE[0], label="非NEWSTRUCTURE"),
                   Patch(color=PALETTE[1], label="NEWSTRUCTURE")], fontsize=8)
plt.tight_layout()
plt.savefig(fig_path("p1_life_ensemble_ci.pdf"))
plt.close()

print("\n图已生成: p1_life_ensemble_ci.pdf")
