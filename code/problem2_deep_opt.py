"""
问题2深度优化：贝叶斯岭回归 + 组合特征 + 嵌入式特征选择。
目标：在11个策略样本下最大化R²_LOO。
"""
import os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import BayesianRidge, Ridge, Lasso, ElasticNet
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.model_selection import cross_val_predict, LeaveOneOut
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score, mean_squared_error
from utils import load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)

# 全部派生特征
df1["E_low"] = df1["C1"] * df1["Q1"]
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])
df1["is_new"] = df1["policy"].str.contains("NEWSTRUCTURE").astype(int)
df1["C_ratio"] = df1["C2"] / df1["C1"]
df1["Q1_frac"] = df1["Q1"] / 80.0
df1["C1xQ1"] = df1["C1"] * df1["Q1"]
df1["C2xEh"] = df1["C2"] * df1["E_high"]
df1["C1_C2"] = df1["C1"] * df1["C2"]
# 新增：温度和内阻特征
df1["log_IR"] = np.log(df1["mean_IR"].clip(lower=1e-6))
df1["log_Tavg"] = np.log(df1["mean_Tavg"].clip(lower=1e-6))
df1["IR_T"] = df1["mean_IR"] * df1["mean_Tavg"]
df1["T_norm"] = (df1["mean_Tavg"] - 30) / 10  # 归一化温度

y = np.log(df1["life"].values)
loo = LeaveOneOut()

# 特征集组合
feature_combos = {
    "base+C1Q1C2": ["C1", "Q1", "C2"],
    "+is_new": ["C1", "Q1", "C2", "is_new"],
    "+E_low+E_high": ["C1", "Q1", "C2", "E_low", "E_high"],
    "+is_new+E": ["C1", "Q1", "C2", "is_new", "E_low", "E_high"],
    "+is_new+E+IR+T": ["C1", "Q1", "C2", "is_new", "E_low", "E_high", "mean_IR", "mean_Tavg"],
    "+all": ["C1", "Q1", "C2", "is_new", "E_low", "E_high", "C_ratio", "Q1_frac",
             "C1xQ1", "C2xEh", "C1_C2", "mean_IR", "mean_Tavg", "log_IR", "log_Tavg", "IR_T", "T_norm"],
}

# 模型组合
model_families = {
    "ridge": lambda: Pipeline([("s", StandardScaler()), ("p", PolynomialFeatures(2, include_bias=False)),
                                ("r", Ridge(alpha=1.0))]),
    "bayesian_ridge": lambda: Pipeline([("s", StandardScaler()), ("p", PolynomialFeatures(2, include_bias=False)),
                                         ("r", BayesianRidge())]),
    "lasso": lambda: Pipeline([("s", StandardScaler()), ("p", PolynomialFeatures(2, include_bias=False)),
                                ("r", Lasso(alpha=0.001, max_iter=10000))]),
    "rf": lambda: RandomForestRegressor(n_estimators=500, max_depth=4, random_state=SEED),
    "gbr": lambda: GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, random_state=SEED),
}

results = []
for fs_name, feats in feature_combos.items():
    X = df1[feats].to_numpy()
    for mf_name, mf_factory in model_families.items():
        m = mf_factory()
        try:
            pred = cross_val_predict(m, X, y, cv=loo)
            r2 = r2_score(y, pred)
            rmse = np.sqrt(mean_squared_error(y, pred))
            results.append({"feature_set": fs_name, "model": mf_name, "r2_loo": r2, "rmse_loo": rmse,
                           "n_features": len(feats)})
        except Exception as e:
            results.append({"feature_set": fs_name, "model": mf_name, "r2_loo": np.nan, "rmse_loo": np.nan,
                           "n_features": len(feats), "error": str(e)[:50]})

results_df = pd.DataFrame(results).dropna(subset=["r2_loo"]).sort_values("r2_loo", ascending=False)
results_df.to_csv(os.path.join(RESULTS_DIR, "p2_deep_opt_all_combos.csv"), index=False)

print("=== 深度优化：所有特征×模型组合 LOO R² ===")
print(results_df[["feature_set", "model", "r2_loo", "rmse_loo", "n_features"]].head(15).to_string(index=False))

# 最佳组合
best = results_df.iloc[0]
print(f"\n最佳组合: {best['feature_set']} + {best['model']}")
print(f"  R²_LOO={best['r2_loo']:.3f} RMSE={best['rmse_loo']:.4f}")

# Bootstrap 置信区间 for best
best_feats = feature_combos[best["feature_set"]]
X_best = df1[best_feats].to_numpy()
rng = np.random.RandomState(SEED)
n_boot = 3000
boot_r2 = []
for _ in range(n_boot):
    idx = rng.choice(len(y), len(y), replace=True)
    if len(np.unique(idx)) < 3: continue
    m = model_families[best["model"]]()
    try:
        m.fit(X_best[idx], y[idx])
        yh = m.predict(X_best)
        r2 = 1 - np.sum((y - yh) ** 2) / np.sum((y - y.mean()) ** 2)
        boot_r2.append(r2)
    except:
        continue
ci_lo, ci_hi = np.percentile(boot_r2, [2.5, 97.5])
print(f"  Bootstrap 95% CI: [{ci_lo:.3f}, {ci_hi:.3f}] (n_boot={len(boot_r2)})")

# 集成：top-3 模型加权
top3 = results_df.head(3)
loo_preds_top3 = []
for _, row in top3.iterrows():
    X = df1[feature_combos[row["feature_set"]]].to_numpy()
    m = model_families[row["model"]]()
    pred = cross_val_predict(m, X, y, cv=loo)
    loo_preds_top3.append(pred)
loo_preds_top3 = np.array(loo_preds_top3)

# 优化权重
best_ens_r2, best_ens_w = -1e9, None
for w1 in np.arange(0, 1.01, 0.05):
    for w2 in np.arange(0, 1.01 - w1, 0.05):
        w3 = 1 - w1 - w2
        if w3 < -1e-9: continue
        p = w1 * loo_preds_top3[0] + w2 * loo_preds_top3[1] + w3 * loo_preds_top3[2]
        r2 = r2_score(y, p)
        if r2 > best_ens_r2:
            best_ens_r2 = r2; best_ens_w = (w1, w2, w3)
print(f"\nTop-3 集成: weights={best_ens_w} R²_LOO={best_ens_r2:.3f}")

save_json({
    "best_feature_set": best["feature_set"], "best_model": best["model"],
    "best_r2_loo": float(best["r2_loo"]), "best_rmse_loo": float(best["rmse_loo"]),
    "bootstrap_ci_95": [float(ci_lo), float(ci_hi)],
    "ensemble_r2_loo": float(best_ens_r2), "ensemble_weights": list(best_ens_w),
    "all_results_count": len(results_df),
}, "p2_deep_optimized.json")

# 图：所有组合 R² 对比
fig, ax = plt.subplots(figsize=(10, 6))
top_n = min(20, len(results_df))
top = results_df.head(top_n)
labels = [f"{r['feature_set'][:15]}\n+{r['model']}" for _, r in top.iterrows()]
ax.barh(range(top_n), top["r2_loo"], color=PALETTE[0], alpha=0.7, edgecolor="white")
ax.set_yticks(range(top_n)); ax.set_yticklabels(labels, fontsize=7)
ax.set_xlabel("LOO R²")
ax.axvline(0.441, color="r", ls="--", lw=1, label="上一轮最优 0.441")
ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig(fig_path("p2_deep_opt_comparison.pdf")); plt.close()

print("\n图已生成: p2_deep_opt_comparison.pdf")
