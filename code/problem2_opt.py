"""
问题2模型优化：交叉验证 + Bootstrap置信区间 + 多项式特征 + 混合效应。
目标：提高寿命预测R²，增强统计推断稳健性。
"""
import os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.linear_model import Ridge, RidgeCV, LassoCV, ElasticNetCV
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.model_selection import cross_val_score, LeaveOneOut, KFold
from sklearn.pipeline import Pipeline
from utils import load_summary, load_cycles, save_json, fig_path, PALETTE, RESULTS_DIR, SEED

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)

# 派生特征
df1["E_low"] = df1["C1"] * df1["Q1"]
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])
# NEWSTRUCTURE 标记（4_8C-80PER_NEWSTRUCTURE 有不同寿命）
df1["is_new"] = df1["policy"].str.contains("NEWSTRUCTURE").astype(int)
# 倍率比与切换点比
df1["C_ratio"] = df1["C2"] / df1["C1"]
df1["Q1_frac"] = df1["Q1"] / 80.0
# 交互项
df1["C1xQ1"] = df1["C1"] * df1["Q1"]
df1["C2xEh"] = df1["C2"] * df1["E_high"]
df1["C1_C2"] = df1["C1"] * df1["C2"]

y = np.log(df1["life"].values)  # log 寿命

# ============ 1. 多项式特征 + 岭回归交叉验证 ============
feature_sets = {
    "base": ["C1", "Q1", "C2"],
    "extended": ["C1", "Q1", "C2", "E_low", "E_high", "is_new", "C_ratio", "Q1_frac"],
    "full": ["C1", "Q1", "C2", "E_low", "E_high", "is_new", "C_ratio", "Q1_frac",
             "C1xQ1", "C2xEh", "C1_C2"],
}

results = {}
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
for ax_idx, (name, feats) in enumerate(feature_sets.items()):
    X = df1[feats].to_numpy()
    # Pipeline: 标准化 + 多项式(2阶) + 岭回归CV
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False, interaction_only=False)),
        ("ridge", RidgeCV(alphas=[0.01, 0.1, 1.0, 10, 100], cv=5)),
    ])
    # LOO 交叉验证
    loo = LeaveOneOut()
    scores = cross_val_score(pipe, X, y, cv=loo, scoring="r2")
    pipe.fit(X, y)
    yhat = pipe.predict(X)
    r2_full = 1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2)
    # Bootstrap 置信区间
    rng = np.random.RandomState(SEED)
    n_boot = 2000
    boot_r2 = []
    n = len(y)
    for _ in range(n_boot):
        idx = rng.choice(n, n, replace=True)
        if len(np.unique(idx)) < 3:
            continue
        pipe_b = Pipeline([
            ("scaler", StandardScaler()),
            ("poly", PolynomialFeatures(degree=2, include_bias=False)),
            ("ridge", Ridge(alpha=1.0)),
        ])
        pipe_b.fit(X[idx], y[idx])
        yh = pipe_b.predict(X)
        boot_r2.append(1 - np.sum((y - yh) ** 2) / np.sum((y - y.mean()) ** 2))
    ci_lo, ci_hi = np.percentile(boot_r2, [2.5, 97.5])
    results[name] = {
        "features": feats,
        "n_features": len(feats),
        "r2_full": float(r2_full),
        "r2_loo_mean": float(np.mean(scores)),
        "r2_loo_std": float(np.std(scores)),
        "r2_boot_median": float(np.median(boot_r2)),
        "r2_ci_95": [float(ci_lo), float(ci_hi)],
    }
    ax = axes[ax_idx]
    ax.hist(boot_r2, bins=40, color=PALETTE[ax_idx], alpha=0.7, edgecolor="white")
    ax.axvline(r2_full, color="k", ls="--", lw=1.5, label=f"R²={r2_full:.3f}")
    ax.axvline(ci_lo, color="r", ls=":", lw=1)
    ax.axvline(ci_hi, color="r", ls=":", lw=1, label=f"95%CI=[{ci_lo:.3f},{ci_hi:.3f}]")
    ax.set_xlabel("Bootstrap R²"); ax.set_ylabel("频次")
    ax.set_title(f"{name} ({len(feats)}特征+2阶多项式)", fontsize=10)
    ax.legend(fontsize=7)
plt.tight_layout(); plt.savefig(fig_path("p2_opt_bootstrap_r2.pdf")); plt.close()

print("=== 多项式+岭回归CV Bootstrap ===")
for k, v in results.items():
    print(f"{k:10s}: R²_full={v['r2_full']:.3f} LOO={v['r2_loo_mean']:.3f}±{v['r2_loo_std']:.3f} "
          f"Boot_median={v['r2_boot_median']:.3f} 95%CI=[{v['r2_ci_95'][0]:.3f},{v['r2_ci_95'][1]:.3f}]")

# ============ 2. ElasticNet 特征选择 ============
best_name = max(results, key=lambda k: results[k]["r2_loo_mean"])
feats = feature_sets[best_name]
X = df1[feats].to_numpy()
scaler = StandardScaler()
Xs = scaler.fit_transform(X)
en = ElasticNetCV(l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9, 1.0], cv=5, random_state=SEED, max_iter=10000)
en.fit(Xs, y)
# 多项式版本
poly = PolynomialFeatures(degree=2, include_bias=False)
Xp = poly.fit_transform(Xs)
en_poly = ElasticNetCV(l1_ratio=[0.3, 0.5, 0.7, 0.9], cv=5, random_state=SEED, max_iter=10000)
en_poly.fit(Xp, y)
yhat_en = en_poly.predict(Xp)
r2_en = 1 - np.sum((y - yhat_en) ** 2) / np.sum((y - y.mean()) ** 2)
# LOO
scores_en = cross_val_score(
    Pipeline([("s", StandardScaler()), ("p", PolynomialFeatures(2, include_bias=False)),
              ("en", ElasticNetCV(cv=5, random_state=SEED, max_iter=10000))]),
    X, y, cv=LeaveOneOut(), scoring="r2")
print(f"\nElasticNet(poly2): R²_full={r2_en:.3f} LOO={np.mean(scores_en):.3f}±{np.std(scores_en):.3f} "
      f"l1_ratio={en_poly.l1_ratio_:.2f}")

# ============ 3. 梯度提升回归 + 特征重要性 ============
gbr = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=SEED)
gbr.fit(X, y)
yhat_gbr = gbr.predict(X)
r2_gbr = 1 - np.sum((y - yhat_gbr) ** 2) / np.sum((y - y.mean()) ** 2)
scores_gbr = cross_val_score(gbr, X, y, cv=LeaveOneOut(), scoring="r2")
imp_gbr = dict(zip(feats, gbr.feature_importances_))
print(f"GBR: R²_full={r2_gbr:.3f} LOO={np.mean(scores_gbr):.3f}±{np.std(scores_gbr):.3f}")
print(f"GBR重要性: {dict(sorted(imp_gbr.items(), key=lambda x:-x[1]))}")

# ============ 4. 集成：岭+RF+GBR 加权平均 ============
rf = RandomForestRegressor(n_estimators=500, max_depth=6, random_state=SEED)
rf.fit(X, y)
scores_rf = cross_val_score(rf, X, y, cv=LeaveOneOut(), scoring="r2")

ridge_pipe = Pipeline([("s", StandardScaler()), ("p", PolynomialFeatures(2, include_bias=False)),
                        ("r", Ridge(alpha=1.0))])
scores_ridge = cross_val_score(ridge_pipe, X, y, cv=LeaveOneOut(), scoring="r2")

# LOO 权重优化
loo_preds = {"ridge": [], "rf": [], "gbr": []}
loo = LeaveOneOut()
for tr, te in loo.split(X):
    ridge_pipe.fit(X[tr], y[tr])
    rf.fit(X[tr], y[tr])
    gbr.fit(X[tr], y[tr])
    loo_preds["ridge"].append(ridge_pipe.predict(X[te])[0])
    loo_preds["rf"].append(rf.predict(X[te])[0])
    loo_preds["gbr"].append(gbr.predict(X[te])[0])

for k in loo_preds:
    loo_preds[k] = np.array(loo_preds[k])

# 网格搜索权重
best_w, best_err = None, 1e9
for w1 in np.arange(0, 1.01, 0.05):
    for w2 in np.arange(0, 1.01 - w1, 0.05):
        w3 = 1 - w1 - w2
        if w3 < 0: continue
        pred = w1 * loo_preds["ridge"] + w2 * loo_preds["rf"] + w3 * loo_preds["gbr"]
        err = np.mean((pred - y) ** 2)
        if err < best_err:
            best_err = err; best_w = (w1, w2, w3)
ensemble_pred = best_w[0] * loo_preds["ridge"] + best_w[1] * loo_preds["rf"] + best_w[2] * loo_preds["gbr"]
r2_ens = 1 - np.sum((y - ensemble_pred) ** 2) / np.sum((y - y.mean()) ** 2)
print(f"\n集成(LOO加权): weights={best_w} R²_LOO={r2_ens:.3f}")

# ============ 5. Bootstrap 寿命预测区间 ============
rng = np.random.RandomState(SEED)
n_boot = 2000
n = len(y)
boot_life = {"ridge": [], "rf": [], "gbr": [], "ensemble": []}
for _ in range(n_boot):
    idx = rng.choice(n, n, replace=True)
    if len(np.unique(idx)) < 5: continue
    ridge_b = Pipeline([("s", StandardScaler()), ("p", PolynomialFeatures(2, include_bias=False)),
                        ("r", Ridge(alpha=1.0))])
    ridge_b.fit(X[idx], y[idx])
    rf_b = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=rng.randint(99999))
    rf_b.fit(X[idx], y[idx])
    gbr_b = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=rng.randint(99999))
    gbr_b.fit(X[idx], y[idx])
    boot_life["ridge"].append(ridge_b.predict(X))
    boot_life["rf"].append(rf_b.predict(X))
    boot_life["gbr"].append(gbr_b.predict(X))

# 预测区间
for k in boot_life:
    arr = np.array(boot_life[k])
    boot_life[k] = {
        "pred_mean": np.mean(arr, axis=0).tolist(),
        "pred_lo": np.percentile(arr, 2.5, axis=0).tolist(),
        "pred_hi": np.percentile(arr, 97.5, axis=0).tolist(),
    }

# ============ 汇总 ============
opt_summary = {
    "best_feature_set": best_name,
    "ridge_poly2": results[best_name],
    "elasticnet_poly2": {"r2_full": float(r2_en), "r2_loo": float(np.mean(scores_en)),
                          "l1_ratio": float(en_poly.l1_ratio_)},
    "gbr": {"r2_full": float(r2_gbr), "r2_loo": float(np.mean(scores_gbr)),
            "importance": imp_gbr},
    "rf_extended": {"r2_loo": float(np.mean(scores_rf)), "r2_loo_std": float(np.std(scores_rf))},
    "ensemble": {"weights": list(best_w), "r2_loo": float(r2_ens)},
    "ridge_baseline_loo": float(np.mean(scores_ridge)),
}
save_json(opt_summary, "p2_optimized.json")

# ============ 图：模型对比 ============
fig, ax = plt.subplots(figsize=(8, 5))
models = ["线性基线", "岭回归(2阶)", "ElasticNet(2阶)", "随机森林", "GBR", "集成"]
r2_loos = [results["base"]["r2_loo_mean"] if "base" in results else 0,
           np.mean(scores_ridge), np.mean(scores_en), np.mean(scores_rf), np.mean(scores_gbr), r2_ens]
colors = PALETTE[:6]
bars = ax.barh(models, r2_loos, color=colors, alpha=0.8, edgecolor="white")
for b, v in zip(bars, r2_loos):
    ax.text(v + 0.005, b.get_y() + b.get_height()/2, f"{v:.3f}", va="center", fontsize=9)
ax.set_xlabel("留一交叉验证 R²（LOO）")
ax.set_xlim(0, max(r2_loos) * 1.2)
plt.tight_layout(); plt.savefig(fig_path("p2_opt_model_comparison.pdf")); plt.close()

# ============ 图：预测 vs 实际（集成模型）============
fig, ax = plt.subplots(figsize=(6, 6))
ax.scatter(y, ensemble_pred, c=PALETTE[0], s=50, alpha=0.7, edgecolor="white")
lims = [min(y.min(), ensemble_pred.min()), max(y.max(), ensemble_pred.max())]
ax.plot(lims, lims, "k--", lw=1, alpha=0.5)
ax.set_xlabel("实际 log(寿命)"); ax.set_ylabel("集成预测 log(寿命)")
ax.text(0.05, 0.95, f"R²_LOO={r2_ens:.3f}", transform=ax.transAxes, va="top", fontsize=11)
plt.tight_layout(); plt.savefig(fig_path("p2_opt_pred_vs_actual.pdf")); plt.close()

print("\n=== 优化汇总 ===")
print(json.dumps(opt_summary, ensure_ascii=False, indent=2, default=str)[:1500])
