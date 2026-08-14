"""生成数据驱动图表（PDF）。
图表：网络分布、机型参数对比、Q1/Q2/Q3 指标对比、收敛曲线、座位利用率分布等。
"""
from __future__ import annotations
import sys, json, csv, math
from pathlib import Path
from collections import defaultdict, Counter
sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

# 中文字体
rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Serif CJK SC", "AR PL UMing CN", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False
rcParams["font.size"] = 10

DATA = Path(__file__).resolve().parent.parent / "data"
RES = Path(__file__).resolve().parent.parent / "results"
FIG = Path(__file__).resolve().parent.parent / "figures"
FIG.mkdir(exist_ok=True)
D = utils.load_distance_matrix(DATA / "distances.csv")

def fig_network():
    """图1：机场、设施、可加油点分布示意（按经纬度无关，用距离矩阵 MDS 降维）。"""
    from sklearn.manifold import MDS
    nodes = utils.ALL_NODES
    n = len(nodes)
    dmat = np.zeros((n, n))
    for i, a in enumerate(nodes):
        for j, b in enumerate(nodes):
            dmat[i, j] = D[(a, b)]
    mds = MDS(n_components=2, dissimilarity="precomputed", random_state=42, normalized_stress="auto")
    coords = mds.fit_transform(dmat)
    fig, ax = plt.subplots(figsize=(8, 6))
    for i, nd in enumerate(nodes):
        if nd in utils.AIRPORTS:
            ax.scatter(*coords[i], c="red", s=120, marker="^", zorder=3, edgecolors="k")
            ax.annotate(nd, coords[i], xytext=(5, 5), textcoords="offset points", fontsize=8, fontweight="bold")
        elif nd in utils.REFUEL_STATIONS:
            ax.scatter(*coords[i], c="green", s=40, marker="s", zorder=2, edgecolors="k")
        else:
            ax.scatter(*coords[i], c="steelblue", s=20, marker="o", zorder=1, alpha=0.6)
    ax.scatter([], [], c="red", marker="^", label="陆地机场")
    ax.scatter([], [], c="green", marker="s", label="可加油设施")
    ax.scatter([], [], c="steelblue", marker="o", label="海上设施")
    ax.set_xlabel("MDS 维 1")
    ax.set_ylabel("MDS 维 2")
    ax.legend(loc="best")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(FIG / "fig1_network.pdf")
    plt.close(fig)
    print("saved fig1_network.pdf")

def fig_aircraft():
    """图2：三机型参数对比（座位/速度/油耗/油箱/余油）。"""
    types = ["T1", "T2", "T3"]
    seats = [utils.AIRCRAFT[t]["seats"] for t in types]
    speed = [utils.AIRCRAFT[t]["speed"] for t in types]
    cons = [utils.AIRCRAFT[t]["consumption"] for t in types]
    tank = [utils.AIRCRAFT[t]["tank"] for t in types]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.2))
    for ax, vals, title in zip(axes, [seats, speed, cons, tank],
                                ["座位数", "速度 (km/h)", "油耗 (kg/km)", "油箱 (kg)"]):
        ax.bar(types, vals, color=["#4C72B0", "#55A868", "#C44E52"])
        ax.set_title(title)
        for i, v in enumerate(vals):
            ax.text(i, v, str(v), ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "fig2_aircraft.pdf")
    plt.close(fig)
    print("saved fig2_aircraft.pdf")

def fig_reachability():
    """图3：各机型从最近机场往返不加油可达设施 vs 需加油设施。"""
    types = ["T1", "T2", "T3"]
    reachable = []; need_refuel = []
    for t in types:
        ac = utils.AIRCRAFT[t]
        max_path = (ac["tank"] - ac["reserve"]) / ac["consumption"]
        rt_max = max_path / 2
        r = sum(1 for f in utils.FACILITIES if 2*D[(utils.nearest_airport(f, D), f)] <= rt_max)
        reachable.append(r)
        need_refuel.append(52 - r)
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(types))
    w = 0.35
    ax.bar(x - w/2, reachable, w, label="不加油往返可达", color="#55A868")
    ax.bar(x + w/2, need_refuel, w, label="需加油", color="#C44E52")
    ax.set_xticks(x); ax.set_xticklabels(types)
    ax.set_ylabel("设施数")
    ax.set_title("各机型从最近机场往返续航可达性")
    ax.legend()
    for i in range(len(types)):
        ax.text(i - w/2, reachable[i], str(reachable[i]), ha="center", va="bottom", fontsize=9)
        ax.text(i + w/2, need_refuel[i], str(need_refuel[i]), ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "fig3_reachability.pdf")
    plt.close(fig)
    print("saved fig3_reachability.pdf")

def fig_demand():
    """图4：各问题需求量与构成。"""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    # Q1/Q2/Q3 量
    ax = axes[0]
    qs = ["Q1", "Q2", "Q3"]
    counts = [1600, 4000, 4000]
    ax.bar(qs, counts, color="#4C72B0")
    ax.set_ylabel("需求数")
    ax.set_title("各问题需求规模")
    for i, v in enumerate(counts):
        ax.text(i, v, str(v), ha="center", va="bottom")
    # Q2 构成
    ax = axes[1]
    labels = ["出海", "海返", "穿梭"]
    sizes = [1600, 1600, 800]
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90,
           colors=["#4C72B0", "#55A868", "#C44E52"])
    ax.set_title("Q2 需求构成（出海/海返/穿梭）")
    fig.tight_layout()
    fig.savefig(FIG / "fig4_demand.pdf")
    plt.close(fig)
    print("saved fig4_demand.pdf")

def fig_q3_tasktype():
    """图5：Q3 task_type 分布与时间窗长度。"""
    df = utils
    import csv
    from datetime import datetime
    rows = list(csv.DictReader(open(DATA / "peopleQ3.csv")))
    by_tt = Counter(r["task_type"] for r in rows)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    ax = axes[0]
    labels = ["shift", "production", "emergency", "temporary"]
    vals = [by_tt[t] for t in labels]
    ax.bar(labels, vals, color=["#4C72B0", "#55A868", "#C44E52", "#8172B3"])
    ax.set_ylabel("需求数")
    ax.set_title("Q3 任务类型分布")
    for i, v in enumerate(vals):
        ax.text(i, v, str(v), ha="center", va="bottom")
    # 时间窗长度箱线图
    ax = axes[1]
    wl_by_tt = defaultdict(list)
    for r in rows:
        ep = datetime.strptime(r["earliest_pickup_time"], "%Y-%m-%d %H:%M")
        la = datetime.strptime(r["latest_arrival_time"], "%Y-%m-%d %H:%M")
        wl_by_tt[r["task_type"]].append((la - ep).total_seconds() / 3600)
    data = [wl_by_tt[t] for t in labels]
    bp = ax.boxplot(data, tick_labels=labels, showfliers=False, patch_artist=True)
    for patch, c in zip(bp["boxes"], ["#4C72B0", "#55A868", "#C44E52", "#8172B3"]):
        patch.set_facecolor(c)
    ax.set_ylabel("时间窗长度 (h)")
    ax.set_title("Q3 各任务类型时间窗长度分布")
    fig.tight_layout()
    fig.savefig(FIG / "fig5_q3_tasktype.pdf")
    plt.close(fig)
    print("saved fig5_q3_tasktype.pdf")

def fig_metrics_compare():
    """图6：Q1/Q2/Q3 五项指标对比。"""
    metrics = {}
    for q in [1, 2, 3]:
        j = json.load(open(RES / f"q{q}_metrics.json"))
        metrics[q] = j.get("metrics", j)
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    qs = ["Q1", "Q2", "Q3"]
    # 总飞机使用时间
    ax = axes[0, 0]
    vals = [metrics[q]["total_air_time_min"] / 60 for q in [1, 2, 3]]
    ax.bar(qs, vals, color="#4C72B0")
    ax.set_ylabel("小时"); ax.set_title("总飞机使用时间")
    for i, v in enumerate(vals): ax.text(i, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    # 人员总在途时间
    ax = axes[0, 1]
    vals = [metrics[q]["total_pax_time_min"] / 60 for q in [1, 2, 3]]
    ax.bar(qs, vals, color="#55A868")
    ax.set_ylabel("小时"); ax.set_title("人员总在途时间")
    for i, v in enumerate(vals): ax.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    # 总架次数
    ax = axes[0, 2]
    vals = [metrics[q]["num_flights"] for q in [1, 2, 3]]
    ax.bar(qs, vals, color="#C44E52")
    ax.set_ylabel("架次"); ax.set_title("总架次数")
    for i, v in enumerate(vals): ax.text(i, v, str(v), ha="center", va="bottom", fontsize=8)
    # 总燃油
    ax = axes[1, 0]
    vals = [metrics[q]["total_fuel_kg"] / 1000 for q in [1, 2, 3]]
    ax.bar(qs, vals, color="#8172B3")
    ax.set_ylabel("吨"); ax.set_title("总燃油消耗")
    for i, v in enumerate(vals): ax.text(i, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    # 座位利用率
    ax = axes[1, 1]
    vals = [metrics[q]["seat_utilization"] for q in [1, 2, 3]]
    ax.bar(qs, vals, color="#CCB974")
    ax.set_ylabel("利用率"); ax.set_title("座位利用率")
    ax.set_ylim(0, 1)
    for i, v in enumerate(vals): ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    # 下界 gap（Q1 有）
    ax = axes[1, 2]
    j1 = json.load(open(RES / "q1_metrics.json"))
    gap_w = j1.get("gap_weak_pct", 0)
    gap_s = j1.get("gap_strong_pct", 0)
    ax.bar(["弱下界gap", "强下界gap"], [gap_w, gap_s], color=["#999", "#4C72B0"])
    ax.set_ylabel("%"); ax.set_title("Q1 下界 gap")
    for i, v in enumerate([gap_w, gap_s]): ax.text(i, v, f"{v:.1f}%", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig6_metrics.pdf")
    plt.close(fig)
    print("saved fig6_metrics.pdf")

def fig_q1_convergence():
    """图7：Q1 ALNS 收敛曲线。"""
    j = json.load(open(RES / "q1_metrics.json"))
    hist = j.get("history", [])
    if not hist:
        return
    its = [h[0] for h in hist]
    ts = [h[1] / 60 for h in hist]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(its, ts, "-o", markersize=3, color="#4C72B0")
    ax.set_xlabel("ALNS 迭代")
    ax.set_ylabel("总飞机使用时间 (h)")
    ax.set_title("Q1 ALNS 收敛曲线")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "fig7_q1_convergence.pdf")
    plt.close(fig)
    print("saved fig7_q1_convergence.pdf")

def fig_q3_temp():
    """图8：Q3 临时任务满足情况。"""
    j = json.load(open(RES / "q3_metrics.json"))
    served = j.get("temp_served", 0)
    total = j.get("temp_total", 160)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(["已满足", "未满足"], [served, total - served], color=["#55A868", "#C44E52"])
    ax.set_ylabel("人数")
    ax.set_title(f"Q3 临时任务满足情况 ({served}/{total})")
    for i, v in enumerate([served, total - served]):
        ax.text(i, v, str(v), ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(FIG / "fig8_q3_temp.pdf")
    plt.close(fig)
    print("saved fig8_q3_temp.pdf")

def fig_q3_daily():
    """图9：Q3 每日架次数与机位利用。"""
    import csv
    from datetime import datetime
    routes = list(csv.DictReader(open(DATA / "q3-routes.csv")))
    # 每个 aircraft_id+flight_no 一架次，取首行 departure_time
    trips = {}
    for r in routes:
        key = (r["aircraft_id"], r["flight_no"])
        if key not in trips:
            trips[key] = r
    by_day = Counter()
    for key, r in trips.items():
        dep = r["departure_time"]
        if dep:
            d = datetime.strptime(dep, "%Y-%m-%d %H:%M").strftime("%m-%d")
            by_day[d] += 1
    days = sorted(by_day.keys())
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(days, [by_day[d] for d in days], color="#4C72B0")
    ax.set_ylabel("架次数")
    ax.set_xlabel("日期")
    ax.set_title("Q3 每日架次分布")
    for i, d in enumerate(days):
        ax.text(i, by_day[d], str(by_day[d]), ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "fig9_q3_daily.pdf")
    plt.close(fig)
    print("saved fig9_q3_daily.pdf")

def main():
    fig_network()
    fig_aircraft()
    fig_reachability()
    fig_demand()
    fig_q3_tasktype()
    fig_metrics_compare()
    fig_q1_convergence()
    fig_q3_temp()
    fig_q3_daily()
    print("\n所有图表已生成到 figures/")

if __name__ == "__main__":
    main()
