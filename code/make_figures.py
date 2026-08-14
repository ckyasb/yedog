"""生成全部数据型图表（PDF）到 figures/。
依赖 code/outputs/ 与 results/ 的中间数据。
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils

OUT = Path(__file__).resolve().parent / "outputs"
FIG = utils.FIG


def fig_p1_corr():
    """P1 特征-转播观看相关性热力图。"""
    data = utils.load_all() if hasattr(utils, "load_all") else None
    from data_loader import load_all
    data = load_all()
    hist = data["historical_matches"]
    teams = data["teams"]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import problem1 as p1m
    for c in ["elo_a", "elo_b", "strength_rank_a", "strength_rank_b", "odds_a", "odds_draw", "odds_b",
              "attendance", "tv_viewers", "goals_a", "goals_b", "xg_a", "xg_b"]:
        hist[c] = pd.to_numeric(hist[c], errors="coerce")
    df, feat_cols = p1m.build_features(hist, teams)
    df["y_million"] = pd.to_numeric(df["tv_viewers"], errors="coerce") / 1e6
    train = df[df["dataset_split"] == "train"]
    num_cols = ["y_million", "elo_a", "elo_b", "strength_rank_a", "strength_rank_b", "elo_gap", "rank_gap",
                "fan_sum", "mv_sum", "suspense", "entropy", "star_index_a", "star_index_b"]
    corr = train[num_cols].corr()
    fig, ax = plt.subplots(figsize=(9, 7.5))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(num_cols))); ax.set_yticks(range(len(num_cols)))
    labels = ["转播观看", "Elo_a", "Elo_b", "排名_a", "排名_b", "Elo差", "排名差", "球迷和", "市值和", "悬念", "熵", "球星_a", "球星_b"]
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)
    for i in range(len(num_cols)):
        for j in range(len(num_cols)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7, color="white" if abs(v) > 0.5 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8, label="相关系数")
    utils.save_fig("p1_corr_heatmap.pdf", fig)


def fig_p1_pred_vs_true():
    """P1 训练集预测 vs 真实散点。"""
    fit = pd.read_csv(OUT / "p1_train_fit.csv")
    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.scatter(fit["y_true"], fit["y_pred"], alpha=0.4, s=18, c="#2E86C1")
    lim = [min(fit["y_true"].min(), fit["y_pred"].min()) - 5, max(fit["y_true"].max(), fit["y_pred"].max()) + 5]
    ax.plot(lim, lim, "r--", lw=1.2, label="y = ŷ")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("真实转播观看人数（百万人）"); ax.set_ylabel("预测值（百万人）")
    ax.legend(); ax.grid(alpha=0.3)
    utils.save_fig("p1_pred_vs_true.pdf", fig)


def fig_p1_importance():
    """P1 特征重要性条形图。"""
    imp = pd.read_csv(OUT / "p1_feature_importance.csv")
    top = imp.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 6))
    ax.barh(top["feature"], top["importance"], color="#2E86C1")
    ax.set_xlabel("置换重要性（MSE 增量）")
    ax.grid(alpha=0.3, axis="x")
    utils.save_fig("p1_feature_importance.pdf", fig)


def fig_p1_pred_dist():
    """P1 72 场预测分布箱线图（按轮次）。"""
    mp = pd.read_csv(utils.RESULTS / "result_1_match_prediction.csv", encoding="utf-8-sig")
    from data_loader import load_all
    gm = load_all()["groups_matches"][["match_id", "round_in_group"]]
    mp = mp.merge(gm, on="match_id", how="left")
    fig, ax = plt.subplots(figsize=(6.5, 5))
    data_by_r = [mp[mp["round_in_group"] == r]["predicted_tv_viewers"].values for r in [1, 2, 3]]
    bp = ax.boxplot(data_by_r, tick_labels=["第一轮", "第二轮", "第三轮"], patch_artist=True, widths=0.5)
    for patch, c in zip(bp["boxes"], ["#5DADE2", "#48C9B0", "#F5B041"]):
        patch.set_facecolor(c); patch.set_alpha(0.7)
    ax.set_ylabel("预测转播观看人数（百万人）")
    ax.grid(alpha=0.3, axis="y")
    utils.save_fig("p1_pred_dist_by_round.pdf", fig)


def fig_p2_contribution():
    """P2 各指标贡献分解（条形）。"""
    terms = json.load(open(OUT / "p2_summary.json"))["terms"]
    # 归一化后均值 × 权重 = 贡献
    weights = {"T": 0.25, "B": 0.25, "U": 0.15, "H": 0.10, "C": -0.08, "D": -0.07, "F": -0.06, "R": -0.04}
    contribs = {k: terms[k] * weights[k] for k in weights}
    items = sorted(contribs.items(), key=lambda x: x[1], reverse=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    names = ["票务T", "转播B", "不确定U", "吸引H", "成本C(−)", "旅行D(−)", "公平F(−)", "风险R(−)"]
    vals = [v for _, v in items]
    colors = ["#27AE60" if v >= 0 else "#E74C3C" for v in vals]
    ax.bar(names, vals, color=colors, alpha=0.8)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("对 Z2 的贡献（归一化均值×权重）")
    ax.grid(alpha=0.3, axis="y")
    utils.save_fig("p2_indicator_contribution.pdf", fig)


def fig_p2_venue_usage():
    """P2 场馆×日期使用热力图。"""
    from data_loader import load_all
    sched = pd.read_csv(utils.RESULTS / "result_2_group_schedule.csv", encoding="utf-8-sig")
    venues = load_all()["venues"]
    dates = sorted(sched["reference_date"].astype(str).unique())
    v_ids = venues["venue_id"].tolist()
    M = np.zeros((len(v_ids), len(dates)))
    for _, r in sched.iterrows():
        vi = v_ids.index(r["venue_id"])
        di = dates.index(str(r["reference_date"]))
        M[vi, di] += 1
    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(M, cmap="YlOrRd", aspect="auto")
    ax.set_yticks(range(len(v_ids))); ax.set_yticklabels(v_ids, fontsize=8)
    ax.set_xticks(range(len(dates))); ax.set_xticklabels([d[5:] for d in dates], rotation=45, fontsize=7)
    ax.set_xlabel("日期（06-xx）"); ax.set_ylabel("场馆编号")
    for i in range(len(v_ids)):
        for j in range(len(dates)):
            if M[i, j] > 0:
                ax.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=8, color="black" if M[i, j] < 2 else "white")
    fig.colorbar(im, ax=ax, shrink=0.7, label="单日承办场次")
    utils.save_fig("p2_venue_date_heatmap.pdf", fig)


def fig_p2_radar():
    """P2 多目标雷达图（归一化指标 vs 理想）。"""
    terms = json.load(open(OUT / "p2_summary.json"))["terms"]
    cats = ["票务T", "转播B", "不确定U", "吸引H", "成本C", "旅行D", "公平F", "风险R"]
    # 正向化：负向指标取 1-值
    vals = [terms["T"], terms["B"], terms["U"], terms["H"], 1 - terms["C"], 1 - terms["D"], 1 - terms["F"], 1 - terms["R"]]
    ideal = [1] * 8
    angles = np.linspace(0, 2 * np.pi, len(cats), endpoint=False).tolist()
    vals_c = vals + [vals[0]]; ideal_c = ideal + [ideal[0]]; angles_c = angles + [angles[0]]
    fig, ax = plt.subplots(figsize=(6.5, 6), subplot_kw=dict(polar=True))
    ax.plot(angles_c, ideal_c, "--", color="gray", lw=1, label="理想（1.0）")
    ax.fill(angles_c, vals_c, color="#2E86C1", alpha=0.25)
    ax.plot(angles_c, vals_c, "-o", color="#2E86C1", label="优化方案")
    ax.set_xticks(angles); ax.set_xticklabels(cats, fontsize=9)
    ax.set_ylim(0, 1); ax.set_yticks([0.25, 0.5, 0.75])
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1))
    utils.save_fig("p2_radar.pdf", fig)


def fig_p2_convergence():
    """P2 多起点收敛/稳定性（条形）。"""
    summ = json.load(open(OUT / "p2_summary.json"))
    hist = summ["history"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    starts = [h["start"] for h in hist]
    z_init = [h["Z_init"] for h in hist]
    z_sa = [h["Z_sa"] for h in hist]
    x = np.arange(len(starts)); w = 0.38
    ax.bar(x - w / 2, z_init, w, label="贪心初始 Z2", color="#AEB6BF")
    ax.bar(x + w / 2, z_sa, w, label="SA 优化后 Z2", color="#2E86C1")
    ax.set_xticks(x); ax.set_xticklabels([f"start{s}" for s in starts])
    ax.set_ylabel("Z2 目标值"); ax.legend(); ax.grid(alpha=0.3, axis="y")
    utils.save_fig("p2_multistart_stability.pdf", fig)


def fig_p3_static_vs_dynamic():
    """P3 静态 vs 动态净效益对比。"""
    df = pd.read_csv(OUT / "p3_static_vs_dynamic.csv")
    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(df)); w = 0.4
    ax.bar(x - w / 2, df["static_nv"], w, label="静态净效益", color="#AEB6BF")
    ax.bar(x + w / 2, df["dynamic_nv"], w, label="动态净效益", color="#E67E22")
    ax.set_xticks(x); ax.set_xticklabels(df["match_id"], rotation=45, fontsize=7)
    ax.set_ylabel("单场净效益（Z3 贡献）"); ax.legend(); ax.grid(alpha=0.3, axis="y")
    utils.save_fig("p3_static_vs_dynamic.pdf", fig)


def fig_p3_advance_prob():
    """P3 晋级概率分布直方图。"""
    summ = json.load(open(OUT / "p3_summary.json"))
    p_t = summ["p_t"]
    vals = list(p_t.values())
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(vals, bins=15, color="#8E44AD", alpha=0.7, edgecolor="white")
    ax.axvline(0.5, color="red", ls="--", lw=1, label="p=0.5 悬念线")
    ax.set_xlabel("球队晋级概率 p_t"); ax.set_ylabel("球队数量")
    ax.legend(); ax.grid(alpha=0.3)
    utils.save_fig("p3_advance_prob_hist.pdf", fig)


def fig_p3_risk_decomp():
    """P3 风险分解堆叠图。"""
    df = pd.read_csv(utils.RESULTS / "result_3_dynamic_strategy.csv", encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(df))
    # 无激励 + 默契 + 动态安保风险部分（risk_exposure = 0.4 noeff + 0.4 coll + 0.2 d*m_s）
    ax.bar(x, df["stakeless_risk"], label="无激励风险", color="#E74C3C", alpha=0.8)
    ax.bar(x, df["collusion_risk"], bottom=df["stakeless_risk"], label="默契风险", color="#F39C12", alpha=0.8)
    ax.set_xticks(x); ax.set_xticklabels(df["match_id"], rotation=45, fontsize=7)
    ax.set_ylabel("风险值"); ax.legend(); ax.grid(alpha=0.3, axis="y")
    utils.save_fig("p3_risk_decomposition.pdf", fig)


def fig_p4_radar():
    """P4 真实 vs 优化赛程雷达对比。"""
    df = pd.read_csv(utils.RESULTS / "result_4_schedule_comparison.csv", encoding="utf-8-sig")
    # 取有双值的指标
    both = df[(df["actual_schedule_value"] != "") & (df["optimized_schedule_value"] != "")].copy()
    both["actual"] = pd.to_numeric(both["actual_schedule_value"])
    both["opt"] = pd.to_numeric(both["optimized_schedule_value"])
    # 归一化到 [0,1]（按每指标 max）
    cats = both["indicator_name"].tolist()
    actual_n = []
    opt_n = []
    for _, r in both.iterrows():
        mx = max(r["actual"], r["opt"]) if max(r["actual"], r["opt"]) > 0 else 1
        # 方向：higher 越大越好；lower 越小越好 -> 反向归一化使"好"=大
        if r["preferred_direction"] == "lower":
            actual_n.append(1 - r["actual"] / mx if mx > 0 else 0)
            opt_n.append(1 - r["opt"] / mx if mx > 0 else 0)
        else:
            actual_n.append(r["actual"] / mx if mx > 0 else 0)
            opt_n.append(r["opt"] / mx if mx > 0 else 0)
    n = len(cats)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    actual_c = actual_n + [actual_n[0]] if n else []
    opt_c = opt_n + [opt_n[0]] if n else []
    angles_c = angles + [angles[0]] if n else []
    fig, ax = plt.subplots(figsize=(6.5, 6), subplot_kw=dict(polar=True))
    if n:
        ax.plot(angles_c, actual_c, "-o", color="#E74C3C", label="2022 实际赛程")
        ax.fill(angles_c, actual_c, color="#E74C3C", alpha=0.15)
        ax.plot(angles_c, opt_c, "-s", color="#2E86C1", label="本队优化赛程")
        ax.fill(angles_c, opt_c, color="#2E86C1", alpha=0.15)
        ax.set_xticks(angles); ax.set_xticklabels(cats, fontsize=8)
        ax.set_ylim(0, 1)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    utils.save_fig("p4_radar_actual_vs_opt.pdf", fig)


def fig_p4_bar():
    """P4 逐指标对比条形图。"""
    df = pd.read_csv(utils.RESULTS / "result_4_schedule_comparison.csv", encoding="utf-8-sig")
    both = df[(df["actual_schedule_value"] != "") & (df["optimized_schedule_value"] != "")].copy()
    both["actual"] = pd.to_numeric(both["actual_schedule_value"])
    both["opt"] = pd.to_numeric(both["optimized_schedule_value"])
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(both)); w = 0.38
    ax.bar(x - w / 2, both["actual"], w, label="2022 实际", color="#E74C3C", alpha=0.8)
    ax.bar(x + w / 2, both["opt"], w, label="本队优化", color="#2E86C1", alpha=0.8)
    ax.set_xticks(x); ax.set_xticklabels(both["indicator_name"], rotation=20, ha="right", fontsize=9)
    ax.legend(); ax.grid(alpha=0.3, axis="y")
    utils.save_fig("p4_indicator_bar.pdf", fig)


def main():
    print("生成 P1 图表...")
    fig_p1_corr()
    fig_p1_pred_vs_true()
    fig_p1_importance()
    fig_p1_pred_dist()
    print("生成 P2 图表...")
    fig_p2_contribution()
    fig_p2_venue_usage()
    fig_p2_radar()
    fig_p2_convergence()
    print("生成 P3 图表...")
    fig_p3_static_vs_dynamic()
    fig_p3_advance_prob()
    fig_p3_risk_decomp()
    print("生成 P4 图表...")
    fig_p4_radar()
    fig_p4_bar()
    print("全部图表生成完成。")


if __name__ == "__main__":
    main()
