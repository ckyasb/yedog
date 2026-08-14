"""
P3修正优化：回退到原始递归逻辑 + 改进特征 + is_new。
保持递归预测框架不变，只改进特征工程。
"""
import os, json, warnings
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
from utils import load_summary, load_cycles, save_json, fig_path, PALETTE, RESULTS_DIR, SEED

warnings.filterwarnings("ignore")
summ = load_summary()
cyc = load_cycles()
test_ids = set(summ[summ["prediction_test"] == 1]["battery_id"].astype(int))
train_ids = [b for b in sorted(cyc["battery_id"].unique(), key=lambda x: int(x)) if int(b) not in test_ids]

# 改进特征：在原始15维基础上加入 is_new 和分段斜率
def features_v3(g, n_end, meta):
    g = g.sort_values("cycle").head(n_end)
    N = g["cycle"].to_numpy(float)
    soh = g["SOH"].to_numpy(float)
    soh_s = g["SOH_smooth"].to_numpy(float)
    cap = g["capacity"].to_numpy(float)
    ir = g["IR"].to_numpy(float)
    tch = g["chargetime"].to_numpy(float)
    tavg = g["Tavg"].to_numpy(float)
    f = {}
    # 原始特征(保持不变)
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
    f["C1"] = float(meta["C1"]); f["Q1"] = float(meta["Q1"]); f["C2"] = float(meta["C2"])
    f["E_low"] = f["C1"] * f["Q1"]
    f["E_high"] = f["C2"] * (80 - f["Q1"])
    # === 新增(不影响递归) ===
    f["is_new"] = float(1 if "NEWSTRUCTURE" in str(meta["policy"]) else 0)
    mid = len(N) // 2
    f["slope_recent"] = float(np.polyfit(N[-min(10,len(N)):], soh_s[-min(10,len(N)):], 1)[0]) if len(N) >= 3 else f["slope_SOH"]
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
        f = features_v3(g, k, meta)
        X_tr.append(list(f.values()))
        y_tr.append(soh_s[k])
X_tr = np.array(X_tr)
y_tr = np.array(y_tr)
scaler = StandardScaler().fit(X_tr)
X_tr_s = scaler.transform(X_tr)

# 单一RF(与原始一致),但用改进特征
rf = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=SEED)
rf.fit(X_tr_s, y_tr)

# 递归预测(与原始逻辑一致)
def predict_recursive_v3(bid, n_train, model, scaler):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    hist = g.head(n_train).copy()
    preds = []
    for tgt_cycle in HORIZON:
        f = features_v3(hist, len(hist), meta)
        x = np.array([list(f.values())])
        xs = scaler.transform(x)
        yhat = float(model.predict(xs)[0])
        preds.append(yhat)
        last = hist.iloc[-1].copy()
        last["cycle"] = tgt_cycle
        last["SOH_smooth"] = yhat
        last["SOH"] = yhat
        last["IR"] = hist["IR"].iloc[-1]
        last["chargetime"] = hist["chargetime"].iloc[-1]
        last["Tavg"] = hist["Tavg"].iloc[-1]
        last["capacity"] = yhat * float(meta["initial_capacity"])
        hist = pd.concat([hist, pd.DataFrame([last])], ignore_index=True)
    return np.array(preds)

# 40块留出验证
metrics = []
for bid in train_ids:
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    true = g["SOH_smooth"].to_numpy(float)[150:200]
    if len(true) != 50:
        continue
    pred = predict_recursive_v3(bid, 150, rf, scaler)
    rmse = float(np.sqrt(mean_squared_error(true, pred)))
    mae = float(mean_absolute_error(true, pred))
    mape = float(np.mean(np.abs((true - pred) / true)) * 100)
    metrics.append({"bid": int(bid), "rmse": rmse, "mae": mae, "mape": mape})

rmse_mean = float(np.mean([m["rmse"] for m in metrics]))
rmse_med = float(np.median([m["rmse"] for m in metrics]))
mae_mean = float(np.mean([m["mae"] for m in metrics]))
mape_mean = float(np.mean([m["mape"] for m in metrics]))

print("=== P3 修正优化(RF+改进特征, 不改变递归) ===")
print(f"RMSE均值: {rmse_mean:.5f} (原始: 0.001310)")
print(f"RMSE中位: {rmse_med:.5f} (原始: 0.001010)")
print(f"MAE均值:  {mae_mean:.5f} (原始: 0.001104)")
print(f"MAPE均值: {mape_mean:.3f}% (原始: 0.112%)")

# 9测试电池
life_test = []
fig, axes = plt.subplots(3, 3, figsize=(13, 10))
for ax, bid in zip(axes.ravel(), sorted(test_ids)):
    g = cyc[cyc["battery_id"] == bid].sort_values("cycle")
    meta = summ[summ["battery_id"] == bid].iloc[0]
    true150 = g["SOH_smooth"].to_numpy(float)[:150]
    pred = predict_recursive_v3(bid, 150, rf, scaler)
    # 寿命
    Ns = np.arange(1, 201, dtype=float)
    S = np.concatenate([true150, pred])
    slope, intercept = np.polyfit(Ns, S, 1)
    life = (0.8 - intercept) / slope if slope < 0 else np.nan
    pol = meta["policy"]
    life_test.append({"battery_id": int(bid), "policy": pol, "life_v3": float(life)})

    ax.plot(range(1, 151), true150, "k-", lw=1.2, label="实测(前150)")
    ax.plot(range(151, 201), pred, "r-", lw=1.5, label="RF(v3)")
    ax.axhline(0.8, color="gray", ls=":", lw=0.8)
    ax.set_title(f"#{bid} {pol[:18]}\n寿命={life:.0f}", fontsize=8)
    ax.set_xlabel("循环"); ax.set_ylabel("SOH")
    ax.legend(fontsize=6, loc="lower left"); ax.set_ylim(0.94, 1.005)
plt.tight_layout(); plt.savefig(fig_path("p3_v3_test_pred_curves.pdf")); plt.close()

save_json({
    "rmse_mean": rmse_mean, "rmse_med": rmse_med,
    "mae_mean": mae_mean, "mape_mean": mape_mean,
    "feature_count": X_tr.shape[1],
    "life_test": life_test,
}, "p3_v3_metrics.json")

print("\n9块测试电池寿命预测:")
for lt in life_test:
    print(f"  #{lt['battery_id']:>2} {lt['policy']:38s} life={lt['life_v3']:.0f}")

print("\n图已生成: p3_v3_test_pred_curves.pdf")
