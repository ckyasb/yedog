"""
问题3模型优化：集成预测模型 + 改进特征工程 + 误差校正。
目标：提高151~200循环SOH预测精度。
"""
import os, json, warnings
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
from utils import (load_summary, load_cycles, save_json, fig_path, PALETTE, RESULTS_DIR, SEED)

warnings.filterwarnings("ignore")
summ = load_summary()
cyc = load_cycles()
test_ids = set(summ[summ["prediction_test"] == 1]["battery_id"].astype(int))
train_ids = [b for b in sorted(cyc["battery_id"].unique(), key=lambda x: int(x)) if int(b) not in test_ids]

# ============ 改进特征工程 ============
def features_upto_v2(g, n_end, meta):
    g = g.sort_values("cycle").head(n_end)
    N = g["cycle"].to_numpy(float)
    soh = g["SOH"].to_numpy(float)
    soh_s = g["SOH_smooth"].to_numpy(float)
    cap = g["capacity"].to_numpy(float)
    ir = g["IR"].to_numpy(float)
    tch = g["chargetime"].to_numpy(float)
    tavg = g["Tavg"].to_numpy(float)
    f = {}
    # 基础特征
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
    # 策略特征
    f["C1"] = float(meta["C1"]); f["Q1"] = float(meta["Q1"]); f["C2"] = float(meta["C2"])
    f["E_low"] = f["C1"] * f["Q1"]
    f["E_high"] = f["C2"] * (80 - f["Q1"])
    # === 新增改进特征 ===
    # 分段斜率（早期 vs 后期）
    mid = len(N) // 2
    if mid >= 2:
        f["slope_early"] = float(np.polyfit(N[:mid], soh_s[:mid], 1)[0])
        f["slope_late"] = float(np.polyfit(N[mid:], soh_s[mid:], 1)[0])
    else:
        f["slope_early"] = 0.0; f["slope_late"] = 0.0
    # SOH 变异系数
    f["soh_cv"] = float(np.std(soh_s) / (np.mean(soh_s) + 1e-12))
    # 最近N循环的斜率（更敏感）
    last_n = min(10, len(N))
    if last_n >= 3:
        f["slope_recent"] = float(np.polyfit(N[-last_n:], soh_s[-last_n:], 1)[0])
    else:
        f["slope_recent"] = f["slope_SOH"]
    # IR 趋势
    f["IR_slope"] = float(np.polyfit(N, ir, 1)[0]) if len(N) >= 3 else 0.0
    # 充电时间变异
    f["chargetime_cv"] = float(np.std(tch) / (np.mean(tch) + 1e-12))
    # 温度特征
    f["Tavg_slope"] = float(np.polyfit(N, tavg, 1)[0]) if len(N) >= 3 else 0.0
    # 倍率比
    f["C_ratio"] = f["C2"] / f["C1"] if f["C1"] > 0 else 1.0
    # 累计衰减
    f["total_decay"] = float(1.0 - soh_s[-1])
    return f

N_TRAIN = 150
HORIZON = list(range(151, 201))

# 构建训练集
X_tr, y_tr = [], []
for bid in train_ids:
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    soh_s = g["SOH_smooth"].to_numpy(float)
    for k in range(2, N_TRAIN):
        f = features_upto_v2(g, k, meta)
        X_tr.append(list(f.values()))
        y_tr.append(soh_s[k])
X_tr = np.array(X_tr)
y_tr = np.array(y_tr)
scaler = StandardScaler().fit(X_tr)
X_tr_s = scaler.transform(X_tr)

FEAT_KEYS = list(features_upto_v2(cyc[cyc["battery_id"] == train_ids[0]].sort_values("cycle"), 10,
                                   summ[summ["battery_id"] == train_ids[0]].iloc[0]).keys())

# ============ 集成模型：RF + GBR + Ridge ============
rf = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=SEED)
gbr = GradientBoostingRegressor(n_estimators=200, max_depth=4, learning_rate=0.05, random_state=SEED)
ridge = Ridge(alpha=1.0)
rf.fit(X_tr_s, y_tr)
gbr.fit(X_tr_s, y_tr)
ridge.fit(X_tr_s, y_tr)

def predict_recursive_ensemble(bid, n_train, models, scaler, weights=None):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    hist = g.head(n_train).copy()
    preds_per_model = {name: [] for name in models}
    for tgt_cycle in HORIZON:
        f = features_upto_v2(hist, len(hist), meta)
        x = np.array([list(f.values())])  # shape (1, n_features)
        x_s = scaler.transform(x)  # standardized
        preds = {}
        for name in models:
            p = float(models[name].predict(x_s)[0])
            preds[name] = p
        if weights:
            yhat = sum(weights[i] * list(preds.values())[i] for i in range(len(weights)))
        else:
            yhat = np.mean(list(preds.values()))
        for name in models:
            preds_per_model[name].append(preds[name])
        # 更新历史
        last = hist.iloc[-1].copy()
        last["cycle"] = tgt_cycle
        last["SOH_smooth"] = yhat
        last["SOH"] = yhat
        last["IR"] = hist["IR"].iloc[-1]
        last["chargetime"] = hist["chargetime"].iloc[-1]
        last["Tavg"] = hist["Tavg"].iloc[-1]
        last["capacity"] = yhat * float(meta["initial_capacity"])
        hist = pd.concat([hist, pd.DataFrame([last])], ignore_index=True)
    return preds_per_model

# ============ 留出验证 + 误差校正 ============
models = {"rf": rf, "gbr": gbr, "ridge": ridge}

# 40块留出验证
holdout_metrics = {"rf": [], "gbr": [], "ridge": [], "ensemble": []}
preds_holdout = {}
for bid in train_ids:
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    true = g["SOH_smooth"].to_numpy(float)[150:200]
    if len(true) != 50:
        continue
    pp = predict_recursive_ensemble(bid, 150, models, scaler)
    preds_holdout[bid] = {"true": true.tolist()}
    for name in ["rf", "gbr", "ridge"]:
        p = np.array(pp[name])
        preds_holdout[bid][name] = p.tolist()
        rmse = float(np.sqrt(mean_squared_error(true, p)))
        mae = float(mean_absolute_error(true, p))
        mape = float(np.mean(np.abs((true - p) / true)) * 100)
        holdout_metrics[name].append({"bid": int(bid), "rmse": rmse, "mae": mae, "mape": mape})

# 等权集成
for bid in preds_holdout:
    true = np.array(preds_holdout[bid]["true"])
    ens = (np.array(preds_holdout[bid]["rf"]) + np.array(preds_holdout[bid]["gbr"]) +
           np.array(preds_holdout[bid]["ridge"])) / 3
    preds_holdout[bid]["ensemble"] = ens.tolist()
    rmse = float(np.sqrt(mean_squared_error(true, ens)))
    holdout_metrics["ensemble"].append({"bid": int(bid), "rmse": rmse})

# ============ 误差校正：用残差趋势修正 ============
# 计算系统偏差
bias_per_model = {}
for name in ["rf", "gbr", "ridge", "ensemble"]:
    biases = []
    for bid in preds_holdout:
        if name not in preds_holdout[bid]:
            continue
        true = np.array(preds_holdout[bid]["true"])
        pred = np.array(preds_holdout[bid][name])
        bias = np.mean(true - pred)
        biases.append(bias)
    bias_per_model[name] = float(np.mean(biases))
print("系统偏差:", bias_per_model)

# 修正后误差
for name in ["rf", "gbr", "ridge", "ensemble"]:
    corrected_rmse = []
    for bid in preds_holdout:
        if name not in preds_holdout[bid]:
            continue
        true = np.array(preds_holdout[bid]["true"])
        pred = np.array(preds_holdout[bid][name]) + bias_per_model[name]
        corrected_rmse.append(float(np.sqrt(mean_squared_error(true, pred))))
    holdout_metrics[f"{name}_corrected"] = corrected_rmse

# ============ 9块测试电池预测 ============
test_preds = {}
for bid in sorted(test_ids):
    pp = predict_recursive_ensemble(bid, 150, models, scaler)
    # 修正
    ens_pred = (np.array(pp["rf"]) + np.array(pp["gbr"]) + np.array(pp["ridge"])) / 3
    ens_corrected = ens_pred + bias_per_model["ensemble"]
    test_preds[int(bid)] = {
        "rf": (np.array(pp["rf"]) + bias_per_model["rf"]).tolist(),
        "gbr": (np.array(pp["gbr"]) + bias_per_model["gbr"]).tolist(),
        "ridge": (np.array(pp["ridge"]) + bias_per_model["ridge"]).tolist(),
        "ensemble": ens_corrected.tolist(),
    }

# 寿命预测
life_test = []
for bid in sorted(test_ids):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    true150 = g["SOH_smooth"].to_numpy(float)[:150]
    pred_ens = np.array(test_preds[int(bid)]["ensemble"])
    Ns = np.arange(151, 201, dtype=float)
    # 合并真实+预测
    Ns_all = np.concatenate([np.arange(1, 151, dtype=float), Ns])
    S_all = np.concatenate([true150, pred_ens])
    slope, intercept = np.polyfit(Ns_all, S_all, 1)
    if slope >= 0:
        life = np.nan
    else:
        life = (0.8 - intercept) / slope
    # RF
    pred_rf = np.array(test_preds[int(bid)]["rf"])
    S_rf = np.concatenate([true150, pred_rf])
    sl_rf, ic_rf = np.polyfit(Ns_all, S_rf, 1)
    life_rf = (0.8 - ic_rf) / sl_rf if sl_rf < 0 else np.nan
    pol = summ[summ["battery_id"] == bid].iloc[0]["policy"]
    life_test.append({"battery_id": int(bid), "policy": pol,
                       "life_ens": float(life), "life_rf": float(life_rf)})

# ============ 汇总 ============
summary = {}
for name in ["rf", "gbr", "ridge", "ensemble"]:
    vals = [m["rmse"] for m in holdout_metrics[name]]
    summary[name] = {"rmse_mean": float(np.mean(vals)), "rmse_med": float(np.median(vals))}
for name in ["rf", "gbr", "ridge", "ensemble"]:
    vals = holdout_metrics[f"{name}_corrected"]
    summary[f"{name}_corrected"] = {"rmse_mean": float(np.mean(vals)), "rmse_med": float(np.median(vals))}
save_json(summary, "p3_optimized_metrics.json")
pd.DataFrame(life_test).to_csv(os.path.join(RESULTS_DIR, "p3_optimized_life.csv"), index=False)

print("\n=== 优化后留出验证 ===")
for name in ["rf", "gbr", "ridge", "ensemble", "ensemble_corrected"]:
    v = summary[name]
    print(f"{name:22s}: RMSE_mean={v['rmse_mean']:.5f} (med={v['rmse_med']:.5f})")

print("\n=== 9块测试电池寿命预测(优化后) ===")
for r in life_test:
    print(f"#{r['battery_id']:>2} {r['policy']:38s} life_ens={r['life_ens']:.0f} life_rf={r['life_rf']:.0f}")

# ============ 图：模型对比 ============
fig, ax = plt.subplots(figsize=(8, 5))
names = ["RF", "GBR", "Ridge", "集成", "集成+偏差校正"]
r2s = [summary["rf"]["rmse_mean"], summary["gbr"]["rmse_mean"], summary["ridge"]["rmse_mean"],
       summary["ensemble"]["rmse_mean"], summary["ensemble_corrected"]["rmse_mean"]]
bars = ax.barh(names, r2s, color=PALETTE[:5], alpha=0.8, edgecolor="white")
for b, v in zip(bars, r2s):
    ax.text(v + 0.00002, b.get_y() + b.get_height()/2, f"{v:.5f}", va="center", fontsize=9)
ax.set_xlabel("RMSE（151~200 循环 SOH）")
plt.tight_layout(); plt.savefig(fig_path("p3_opt_model_comparison.pdf")); plt.close()

# ============ 图：9块测试电池预测曲线（优化集成+校正）============
fig, axes = plt.subplots(3, 3, figsize=(13, 10))
for ax, bid in zip(axes.ravel(), sorted(test_ids)):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    true150 = g["SOH_smooth"].to_numpy(float)[:150]
    pol = summ[summ["battery_id"] == bid].iloc[0]["policy"]
    ax.plot(range(1, 151), true150, "k-", lw=1.2, label="实测(前150)")
    ax.plot(range(151, 201), test_preds[int(bid)]["ensemble"], "r-", lw=1.8, label="集成(校正)")
    ax.plot(range(151, 201), test_preds[int(bid)]["rf"], "b--", lw=1, alpha=0.5, label="RF")
    ax.axhline(0.8, color="gray", ls=":", lw=0.8)
    # 寿命
    lt = next(l for l in life_test if l["battery_id"] == int(bid))
    ax.set_title(f"#{bid} {pol[:18]}\n寿命={lt['life_ens']:.0f}", fontsize=8)
    ax.set_xlabel("循环"); ax.set_ylabel("SOH")
    ax.legend(fontsize=6, loc="lower left"); ax.set_ylim(0.94, 1.005)
plt.tight_layout(); plt.savefig(fig_path("p3_opt_test_pred_curves.pdf")); plt.close()

print("\n图已生成: p3_opt_model_comparison.pdf, p3_opt_test_pred_curves.pdf")
