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
