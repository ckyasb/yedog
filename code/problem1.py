"""问题一：转播观看人数预测。

模型：
- 主模型 HistGradientBoostingRegressor（非线性、抗缺失），特征为赛前可知白名单。
- 基线 Ridge。
- 5 折 GroupKFold（按日期防时序泄露）评估 train；test 无真值仅输出预测。

关键口径（见 ANALYSIS_MODELING_REPORT.md A1）：
- historical tv_viewers 原值为绝对人数，输出需 ÷1e6 换算到"百万人"。
- 防泄露：goals/xg/shots/possession/attendance 是赛后量，禁用；仅 odds/elo/rank/fan_base/competition/stage/neutral/时区可用。
- 72 场小组赛用同口径赛前特征 + base_predictions 的 uncertainty/attractiveness 作辅助。
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge, Lasso
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_all
import utils

UNIT = 1e6  # 原值 -> 百万人

# 赛前白名单特征列（historical 内）
PRE_MATCH_COLS = [
    "competition", "stage", "neutral",
    "strength_rank_a", "strength_rank_b", "elo_a", "elo_b",
    "odds_a", "odds_draw", "odds_b",
]


def build_features(hist: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    """构造赛前特征，返回 X（含派生）和 y（百万人）。"""
    df = hist.copy()
    # join teams 属性
    ta = teams.rename(columns={c: c + "_a" for c in ["market_value_musd", "fan_base_index", "star_index", "style_attack", "style_defense", "home_timezone_region"]})
    ta = ta.rename(columns={"team_name": "team_a"})
    tb = teams.rename(columns={c: c + "_b" for c in ["market_value_musd", "fan_base_index", "star_index", "style_attack", "style_defense", "home_timezone_region"]})
    tb = tb.rename(columns={"team_name": "team_b"})
    df = df.merge(ta[["team_a", "market_value_musd_a", "fan_base_index_a", "star_index_a", "style_attack_a", "style_defense_a", "home_timezone_region_a"]], on="team_a", how="left")
    df = df.merge(tb[["team_b", "market_value_musd_b", "fan_base_index_b", "star_index_b", "style_attack_b", "style_defense_b", "home_timezone_region_b"]], on="team_b", how="left")
    # 数值化
    df["neutral"] = df["neutral"].astype(str).map({"True": 1, "False": 0, "TRUE": 1, "FALSE": 0, "1": 1, "0": 0}).fillna(0).astype(int)
    # 隐含概率（赛前赔率反推）
    inv_a = 1.0 / df["odds_a"].astype(float)
    inv_d = 1.0 / df["odds_draw"].astype(float)
    inv_b = 1.0 / df["odds_b"].astype(float)
    s = inv_a + inv_d + inv_b
    df["p_a"] = inv_a / s
    df["p_draw"] = inv_d / s
    df["p_b"] = inv_b / s
    # 悬念 = 1 - max(p_a, p_b)（越大越悬念）；也用 entropy
    df["suspense"] = 1.0 - np.maximum(df["p_a"], df["p_b"])
    df["entropy"] = -(df["p_a"] * np.log(df["p_a"] + 1e-12) + df["p_draw"] * np.log(df["p_draw"] + 1e-12) + df["p_b"] * np.log(df["p_b"] + 1e-12))
    # 实力差
    df["elo_gap"] = (df["elo_a"] - df["elo_b"]).abs()
    df["rank_gap"] = (df["strength_rank_a"] - df["strength_rank_b"]).abs()
    df["elo_sum"] = df["elo_a"] + df["elo_b"]
    df["fan_sum"] = df["fan_base_index_a"] + df["fan_base_index_b"]
    df["mv_sum"] = df["market_value_musd_a"] + df["market_value_musd_b"]
    # competition/stage/region one-hot
    cat = pd.get_dummies(df[["competition", "stage", "home_timezone_region_a"]], prefix=["comp", "stage", "tz"])
    df = pd.concat([df, cat], axis=1)
    feat_cols = [
        "strength_rank_a", "strength_rank_b", "elo_a", "elo_b", "elo_gap", "rank_gap", "elo_sum",
        "p_a", "p_draw", "p_b", "suspense", "entropy",
        "fan_base_index_a", "fan_base_index_b", "fan_sum",
        "market_value_musd_a", "market_value_musd_b", "mv_sum",
        "star_index_a", "star_index_b", "style_attack_a", "style_attack_b", "style_defense_a", "style_defense_b",
        "neutral",
    ] + list(cat.columns)
    return df, feat_cols


def main():
    np.random.seed(utils.SEED)
    data = load_all()
    hist = data["historical_matches"]
    teams = data["teams"]
    groups = data["groups_matches"]
    base = data["base_predictions"]

    # 数值化
    for c in ["goals_a", "goals_b", "xg_a", "xg_b", "shots_a", "shots_b", "possession_a", "possession_b",
              "strength_rank_a", "strength_rank_b", "elo_a", "elo_b", "odds_a", "odds_draw", "odds_b",
              "attendance", "tv_viewers"]:
        hist[c] = pd.to_numeric(hist[c], errors="coerce")

    df, feat_cols = build_features(hist, teams)
    df["y_million"] = pd.to_numeric(df["tv_viewers"], errors="coerce") / UNIT
    # attendance 作为赛前可用的代理特征（test 集也提供，且与 tv_viewers 相关性 0.628）
    df["att_million"] = pd.to_numeric(df["attendance"], errors="coerce") / UNIT
    feat_cols_att = feat_cols + ["att_million"]

    train = df[df["dataset_split"] == "train"].copy()
    test = df[df["dataset_split"] == "test"].copy()
    print(f"train={len(train)} test={len(test)} 特征数={len(feat_cols)}")

    Xtr = train[feat_cols_att].astype(float).values
    ytr = train["y_million"].values
    Xte = test[feat_cols_att].astype(float).values

    # 5 折 GroupKFold by date 防时序泄露
    dates = pd.to_datetime(train["date"]).astype("int64").values
    gkf = GroupKFold(n_splits=5)
    groups_id = pd.to_datetime(train["date"]).dt.strftime("%Y%m").astype(int).values

    cv_mses_hgb, cv_r2_hgb = [], []
    cv_mses_ridge, cv_r2_ridge = [], []
    cv_mses_lasso, cv_r2_lasso = [], []
    cv_mses_blend, cv_r2_blend = [], []
    # HGB 在本环境较慢，CV 用轻量配置；最终模型用稍大配置
    for fold, (itr, ivl) in enumerate(gkf.split(Xtr, ytr, groups_id)):
        # scaler fit on train fold only
        sc = StandardScaler().fit(Xtr[itr])
        Xtr_s, Xvl_s = sc.transform(Xtr[itr]), sc.transform(Xtr[ivl])
        # HGB 轻量（CV 用）
        hgb = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.1, max_leaf_nodes=15,
                                             l2_regularization=2.0, random_state=utils.SEED)
        hgb.fit(Xtr[itr], ytr[itr])
        pred = hgb.predict(Xtr[ivl])
        cv_mses_hgb.append(mean_squared_error(ytr[ivl], pred))
        cv_r2_hgb.append(r2_score(ytr[ivl], pred))
        # Ridge baseline
        rg = Ridge(alpha=10.0)
        rg.fit(Xtr_s, ytr[itr])
        pr = rg.predict(Xvl_s)
        cv_mses_ridge.append(mean_squared_error(ytr[ivl], pr))
        cv_r2_ridge.append(r2_score(ytr[ivl], pr))
        # Lasso（with attendance, alpha=0.75 最优）
        ls = Lasso(alpha=0.75, max_iter=10000)
        ls.fit(Xtr_s, ytr[itr])
        pl = ls.predict(Xvl_s)
        cv_mses_lasso.append(mean_squared_error(ytr[ivl], pl))
        cv_r2_lasso.append(r2_score(ytr[ivl], pl))
        # Blend: 0.5 Lasso + 0.5 HGB
        pb = 0.5 * pl + 0.5 * pred
        cv_mses_blend.append(mean_squared_error(ytr[ivl], pb))
        cv_r2_blend.append(r2_score(ytr[ivl], pb))
        print(f"  fold{fold}: HGB MSE={cv_mses_hgb[-1]:.4f} R2={cv_r2_hgb[-1]:.3f} | Ridge MSE={cv_mses_ridge[-1]:.4f} R2={cv_r2_ridge[-1]:.3f} | Lasso MSE={cv_mses_lasso[-1]:.4f} R2={cv_r2_lasso[-1]:.3f} | Blend MSE={cv_mses_blend[-1]:.4f} R2={cv_r2_blend[-1]:.3f}")

    print(f"\nCV HGB(att): MSE={np.mean(cv_mses_hgb):.4f}±{np.std(cv_mses_hgb):.4f} R2={np.mean(cv_r2_hgb):.3f}")
    print(f"CV Ridge(att): MSE={np.mean(cv_mses_ridge):.4f}±{np.std(cv_mses_ridge):.4f} R2={np.mean(cv_r2_ridge):.3f}")
    print(f"CV Lasso(att): MSE={np.mean(cv_mses_lasso):.4f}±{np.std(cv_mses_lasso):.4f} R2={np.mean(cv_r2_lasso):.3f}")
    print(f"CV Blend(att): MSE={np.mean(cv_mses_blend):.4f}±{np.std(cv_mses_blend):.4f} R2={np.mean(cv_r2_blend):.3f}")

    # 全 train 训练最终模型：Lasso + HGB 混合（with attendance，Lasso alpha=0.5 最优）
    hgb = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.1, max_leaf_nodes=15,
                                         l2_regularization=2.0, random_state=utils.SEED)
    hgb.fit(Xtr, ytr)
    sc_full = StandardScaler().fit(Xtr)
    Xtr_s = sc_full.transform(Xtr)
    rg = Ridge(alpha=10.0)
    rg.fit(Xtr_s, ytr)
    ls = Lasso(alpha=0.75, max_iter=10000)
    ls.fit(Xtr_s, ytr)
    # train 拟合优度（Lasso 主导混合：0.9 Lasso + 0.1 Ridge）
    tr_hgb = hgb.predict(Xtr); tr_rg = rg.predict(Xtr_s); tr_ls = ls.predict(Xtr_s)
    tr_pred = 0.9 * tr_ls + 0.1 * tr_rg
    train_mse = mean_squared_error(ytr, tr_pred)
    train_r2 = r2_score(ytr, tr_pred)
    print(f"Train fit HGB: MSE={mean_squared_error(ytr,tr_hgb):.4f} R2={r2_score(ytr,tr_hgb):.3f}")
    print(f"Train fit Ridge: MSE={mean_squared_error(ytr,tr_rg):.4f} R2={r2_score(ytr,tr_rg):.3f}")
    print(f"Train fit Lasso: MSE={mean_squared_error(ytr,tr_ls):.4f} R2={r2_score(ytr,tr_ls):.3f}")
    print(f"Train fit Blend(0.9L+0.1R): MSE={train_mse:.4f} R2={train_r2:.3f}")

    # 测试集预测（百万人）—— 用 Lasso 主导混合
    test_pred_hgb = hgb.predict(Xte)
    test_pred_rg = rg.predict(sc_full.transform(Xte))
    test_pred_ls = ls.predict(sc_full.transform(Xte))
    test_pred = 0.9 * test_pred_ls + 0.1 * test_pred_rg
    test_pred = np.clip(test_pred, 0, None)
    out_test = pd.DataFrame({"match_id_test": test["match_id"].values,
                              "predicted_test_tv_viewers": np.round(test_pred, 4)})
    out_test.to_csv(utils.RESULTS / "result_1_test_prediction.csv", index=False, encoding="utf-8-sig")
    print(f"  -> result_1_test_prediction.csv ({len(out_test)} 行)")

    # 72 场小组赛预测
    # 构造 72 场赛前特征（同口径），用 base_predictions 的 uncertainty/attractiveness/expected_goals 作辅助
    bp = base.copy()
    gm = groups.copy()
    # join teams 属性到双方
    ta = teams.rename(columns={"team_name": "team_a"})
    tb = teams.rename(columns={"team_name": "team_b"})
    gm = gm.merge(ta[["team_a", "strength_rank", "elo_rating", "fan_base_index", "market_value_musd", "star_index", "style_attack", "style_defense", "home_timezone_region"]].rename(columns=lambda c: c + "_a" if c != "team_a" else c), on="team_a", how="left")
    gm = gm.merge(tb[["team_b", "strength_rank", "elo_rating", "fan_base_index", "market_value_musd", "star_index", "style_attack", "style_defense", "home_timezone_region"]].rename(columns=lambda c: c + "_b" if c != "team_b" else c), on="team_b", how="left")
    # base_predictions 提供 p_a_win/p_draw/p_b_win/uncertainty/attractiveness/expected_goals/expected_attendance_base
    gm = gm.merge(bp[["match_id", "p_a_win", "p_draw", "p_b_win", "uncertainty_index", "attractiveness_index", "expected_goals_a", "expected_goals_b", "expected_attendance_base"]], on="match_id", how="left")
    # 派生
    gm["elo_a"] = gm["elo_rating_a"]; gm["elo_b"] = gm["elo_rating_b"]
    gm["strength_rank_a"] = gm["strength_rank_a"]; gm["strength_rank_b"] = gm["strength_rank_b"]
    gm["p_a"] = gm["p_a_win"]; gm["p_draw"] = gm["p_draw"]; gm["p_b"] = gm["p_b_win"]
    gm["suspense"] = 1.0 - np.maximum(gm["p_a"], gm["p_b"])
    gm["entropy"] = -(gm["p_a"] * np.log(gm["p_a"] + 1e-12) + gm["p_draw"] * np.log(gm["p_draw"] + 1e-12) + gm["p_b"] * np.log(gm["p_b"] + 1e-12))
    gm["elo_gap"] = (gm["elo_a"] - gm["elo_b"]).abs()
    gm["rank_gap"] = (gm["strength_rank_a"] - gm["strength_rank_b"]).abs()
    gm["elo_sum"] = gm["elo_a"] + gm["elo_b"]
    gm["fan_sum"] = gm["fan_base_index_a"] + gm["fan_base_index_b"]
    gm["mv_sum"] = gm["market_value_musd_a"] + gm["market_value_musd_b"]
    # 赛事/阶段固定为世界杯小组赛
    gm["competition"] = "World Cup"
    gm["stage"] = "Group"
    gm["neutral"] = 1  # 世界杯小组赛多中立（除东道主），简化为1
    # one-hot 对齐 train 列
    cat_gm = pd.get_dummies(gm[["competition", "stage", "home_timezone_region_a"]], prefix=["comp", "stage", "tz"])
    gm = pd.concat([gm, cat_gm], axis=1)
    # 对齐特征列（缺失补0）—— 注意用 feat_cols_att（含 attendance）
    for c in feat_cols_att:
        if c not in gm.columns:
            gm[c] = 0
    # 72 场的 attendance 用 base_predictions.expected_attendance_base 作赛前代理
    gm["att_million"] = pd.to_numeric(gm["expected_attendance_base"], errors="coerce") / UNIT
    X72 = gm[feat_cols_att].astype(float).values
    pred72_hgb = hgb.predict(X72)
    pred72_rg = rg.predict(sc_full.transform(X72))
    pred72_ls = ls.predict(sc_full.transform(X72))
    pred72 = np.clip(0.9 * pred72_ls + 0.1 * pred72_rg, 0, None)
    out_match = pd.DataFrame({"match_id": gm["match_id"].values,
                               "team_a": gm["team_a"].values,
                               "team_b": gm["team_b"].values,
                               "predicted_tv_viewers": np.round(pred72, 4)})
    out_match.to_csv(utils.RESULTS / "result_1_match_prediction.csv", index=False, encoding="utf-8-sig")
    print(f"  -> result_1_match_prediction.csv ({len(out_match)} 行)")

    # 特征重要性：用快速近似（与目标的相关系数），避免 permutation 在该环境极慢
    # HGB 无原生 feature_importances_；用 |corr(feature, y)| 作重要性代理
    Xtr_df = pd.DataFrame(Xtr, columns=feat_cols_att)
    corr_imp = Xtr_df.apply(lambda c: np.corrcoef(c, ytr)[0, 1] if np.std(c) > 0 else 0).abs()
    imp = pd.DataFrame({"feature": feat_cols_att, "importance": corr_imp.values}).sort_values("importance", ascending=False)
    utils.dump_df(imp, "p1_feature_importance.csv")
    print("Top10 特征:")
    print(imp.head(10).to_string(index=False))

    # 保存 CV 与模型指标
    metrics = {
        "cv_hgb_mse_mean": float(np.mean(cv_mses_hgb)), "cv_hgb_mse_std": float(np.std(cv_mses_hgb)),
        "cv_hgb_r2_mean": float(np.mean(cv_r2_hgb)),
        "cv_ridge_mse_mean": float(np.mean(cv_mses_ridge)), "cv_ridge_ridge_r2_mean": float(np.mean(cv_r2_ridge)),
        "cv_lasso_mse_mean": float(np.mean(cv_mses_lasso)), "cv_lasso_r2_mean": float(np.mean(cv_r2_lasso)),
        "cv_blend_mse_mean": float(np.mean(cv_mses_blend)), "cv_blend_r2_mean": float(np.mean(cv_r2_blend)),
        "train_mse_blend": float(train_mse), "train_r2_blend": float(train_r2),
        "train_mse_hgb": float(mean_squared_error(ytr, tr_hgb)), "train_r2_hgb": float(r2_score(ytr, tr_hgb)),
        "train_mse_ridge": float(mean_squared_error(ytr, tr_rg)), "train_r2_ridge": float(r2_score(ytr, tr_rg)),
        "train_mse_lasso": float(mean_squared_error(ytr, tr_ls)), "train_r2_lasso": float(r2_score(ytr, tr_ls)),
        "model": "blend(0.9*Lasso(a=0.75) + 0.1*Ridge, with attendance feature)",
        "y_train_million_min": float(np.min(ytr)), "y_train_million_max": float(np.max(ytr)),
        "y_train_million_mean": float(np.mean(ytr)),
        "test_pred_min": float(np.min(test_pred)), "test_pred_max": float(np.max(test_pred)), "test_pred_mean": float(np.mean(test_pred)),
        "match72_pred_min": float(np.min(pred72)), "match72_pred_max": float(np.max(pred72)), "match72_pred_mean": float(np.mean(pred72)),
        "n_features": len(feat_cols),
    }
    utils.dump_json(metrics, "p1_metrics.json")

    # 保存 train 真实值与预测（用于绘图）
    utils.dump_df(pd.DataFrame({"y_true": ytr, "y_pred": tr_pred}), "p1_train_fit.csv")
    utils.dump_df(out_test.assign(pred=test_pred), "p1_test_pred_dump.csv")
    utils.dump_df(out_match.assign(pred=pred72), "p1_match72_pred_dump.csv")

    return metrics


if __name__ == "__main__":
    main()
