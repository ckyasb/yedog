"""
P2优化: 高斯过程回归(GPR) — 适合小样本+不确定性量化。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel, Matern
from sklearn.linear_model import BayesianRidge
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.model_selection import cross_val_predict, LeaveOneOut
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score, mean_squared_error
from utils import load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)
df1["E_low"] = df1["C1"] * df1["Q1"]
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])
df1["is_new"] = df1["policy"].str.contains("NEWSTRUCTURE").astype(int)
y = np.log(df1["life"].values)
loo = LeaveOneOut()

feats = ["C1", "Q1", "C2", "is_new", "E_low", "E_high"]
X = df1[feats].to_numpy()

# GPR with Matern kernel + noise
kernel = ConstantKernel(1.0) * Matern(length_scale=[1]*len(feats), nu=1.5) + WhiteKernel(noise_level=0.1)
gpr = Pipeline([
    ("scaler", StandardScaler()),
    ("gpr", GaussianProcessRegressor(kernel=kernel, alpha=1e-6, n_restarts_optimizer=5, random_state=SEED))
])

# LOO
pred_gpr = cross_val_predict(gpr, X, y, cv=loo)
r2_gpr = r2_score(y, pred_gpr)
rmse_gpr = np.sqrt(mean_squared_error(y, pred_gpr))

# Fit full for uncertainty
gpr.fit(X, y)
yhat_full, std_full = gpr.named_steps["gpr"].predict(gpr.named_steps["scaler"].transform(X), return_std=True)

print("=== P2 高斯过程回归 ===")
print(f"GPR R²_LOO={r2_gpr:.3f} RMSE_LOO={rmse_gpr:.4f}")
print(f"vs BayesRidge+poly2: R²_LOO=0.445")

# Also try with poly features
gpr_poly = Pipeline([
    ("scaler", StandardScaler()),
    ("poly", PolynomialFeatures(2, include_bias=False)),
    ("gpr", GaussianProcessRegressor(kernel=ConstantKernel(1.0) * RBF() + WhiteKernel(0.1),
                                      n_restarts_optimizer=3, random_state=SEED))
])
pred_gpr_poly = cross_val_predict(gpr_poly, X, y, cv=loo)
r2_gpr_poly = r2_score(y, pred_gpr_poly)
print(f"GPR+poly2 R²_LOO={r2_gpr_poly:.3f}")

# Compare all models
models_summary = {
    "gpr_matern": {"r2_loo": float(r2_gpr), "rmse_loo": float(rmse_gpr)},
    "gpr_poly2": {"r2_loo": float(r2_gpr_poly)},
    "bayes_ridge_poly2": {"r2_loo": 0.445},
}
save_json(models_summary, "p2_gpr_optimized.json")

# Plot: predicted vs actual
fig, ax = plt.subplots(figsize=(6, 6))
ax.errorbar(y, yhat_full, yerr=1.96*std_full, fmt="o", color=PALETTE[0], alpha=0.6,
           ecolor="gray", capsize=3, markersize=6, label="GPR预测(95%CI)")
lims = [min(y.min(), yhat_full.min()), max(y.max(), yhat_full.max())]
ax.plot(lims, lims, "k--", lw=1, alpha=0.5)
ax.set_xlabel("实际 log(寿命)"); ax.set_ylabel("GPR预测 log(寿命)")
ax.text(0.05, 0.95, f"R²={r2_gpr:.3f}", transform=ax.transAxes, va="top")
ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(fig_path("p2_gpr_pred_vs_actual.pdf"))
plt.close()

print("\n图已生成: p2_gpr_pred_vs_actual.pdf")
