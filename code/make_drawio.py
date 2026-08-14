"""生成非数据型 DrawIO 图示（技术路线图、子问题求解流程图、数据处理流程图、模型结构图、指标体系图）。
drawio CLI 不可用，改用 .drawio 源文件 + matplotlib 渲染 PDF（概念图，非数据图）。
"""
from __future__ import annotations
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm

for _p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]:
    try:
        fm.fontManager.addfont(_p)
    except Exception:
        pass
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils

FIG = utils.FIG

C_BLUE = "#2E86C1"
C_GREEN = "#27AE60"
C_ORANGE = "#E67E22"
C_RED = "#E74C3C"
C_GRAY = "#85929E"
C_PURPLE = "#8E44AD"
C_LIGHT = "#EBF5FB"


def box(ax, x, y, w, h, text, fc=C_LIGHT, ec=C_BLUE, fontsize=10, fontweight="normal", textcolor="black"):
    b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                       linewidth=1.4, edgecolor=ec, facecolor=fc)
    ax.add_patch(b)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize,
            fontweight=fontweight, color=textcolor, wrap=True)
    return (x + w / 2, y + h / 2)


def arrow(ax, p1, p2, color=C_GRAY, style="->", lw=1.4):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=14,
                        color=color, lw=lw, shrinkA=2, shrinkB=2)
    ax.add_patch(a)


def fig_roadmap():
    """技术路线图：四问递进 + 数据流。"""
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.set_xlim(0, 12); ax.set_ylim(0, 6.5); ax.axis("off")
    # 标题层
    box(ax, 0.3, 5.6, 11.4, 0.7, "大数据驱动的足球世界杯赛事预测与赛程资源协同优化 · 技术路线",
        fc="#1A5276", ec="#1A5276", fontsize=12, fontweight="bold", textcolor="white")
    # 四个问题框
    p1 = box(ax, 0.4, 3.4, 2.6, 1.5, "问题一\n转播观看人数预测\n(HGB+Ridge 混合)", fc="#D6EAF8", ec=C_BLUE, fontsize=9.5, fontweight="bold")
    p2 = box(ax, 3.3, 3.4, 2.6, 1.5, "问题二\n场馆+时段协同优化\n(贪心+模拟退火 Z2)", fc="#D5F5E3", ec=C_GREEN, fontsize=9.5, fontweight="bold")
    p3 = box(ax, 6.2, 3.4, 2.6, 1.5, "问题三\n第三轮动态资源优化\n(14 式公式链+MC)", fc="#FAE5D3", ec=C_ORANGE, fontsize=9.5, fontweight="bold")
    p4 = box(ax, 9.1, 3.4, 2.6, 1.5, "问题四\n实际赛程综合评价\n(2022 世界杯对比)", fc="#FADBD8", ec=C_RED, fontsize=9.5, fontweight="bold")
    # 数据输入层
    box(ax, 0.4, 1.6, 11.3, 1.2,
        "数据附件 14 sheet：historical_matches(700) / teams(48) / groups_matches(72) / venues(16) / time_slots(80) /\n"
        "distance_matrix(1024) / ticket_broadcast / base_predictions / security_requirements / live_group_results /\n"
        "dynamic_resource_limits / dynamic_resource_costs / objective_weights",
        fc="#F4F6F6", ec=C_GRAY, fontsize=8)
    # 输出层
    box(ax, 0.4, 0.2, 2.6, 1.0, "result_1\n(140+72 场预测)", fc="white", ec=C_BLUE, fontsize=8)
    box(ax, 3.3, 0.2, 2.6, 1.0, "result_2\n(72 场赛程 Z2)", fc="white", ec=C_GREEN, fontsize=8)
    box(ax, 6.2, 0.2, 2.6, 1.0, "result_3\n(24 场动态策略 Z3)", fc="white", ec=C_ORANGE, fontsize=8)
    box(ax, 9.1, 0.2, 2.6, 1.0, "result_4\n(实际 vs 优化对比)", fc="white", ec=C_RED, fontsize=8)
    # 箭头：数据->问题
    for px in [p1, p2, p3, p4]:
        arrow(ax, (px[0], 2.8), (px[0], 4.9))
    # 问题间递进依赖
    arrow(ax, (3.0, 4.15), (3.3, 4.15), color=C_BLUE, lw=1.8)
    arrow(ax, (5.9, 4.15), (6.2, 4.15), color=C_GREEN, lw=1.8)
    arrow(ax, (8.8, 4.15), (9.1, 4.15), color=C_ORANGE, lw=1.8)
    # 问题->输出
    for px, ox in [(p1, 1.7), (p2, 4.6), (p3, 7.5), (p4, 10.4)]:
        arrow(ax, (px[0], 3.4), (ox, 1.2))
    ax.text(6, 6.0, "链路：P1 预测 → P2 赛程 → P3 动态资源 → P4 对比评价（数值前后一致、同一种子）",
            ha="center", fontsize=9, color="#566573", style="italic")
    utils.save_fig("fig_roadmap.pdf", fig)


def fig_flow_q1():
    """问题一求解流程图。"""
    fig, ax = plt.subplots(figsize=(7.5, 8.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
    steps = [
        (3.5, 9.0, 3.0, 0.7, "historical_matches (700 条)\ntrain 560 / test 140", C_BLUE),
        (3.5, 7.8, 3.0, 0.7, "数据清洗 + 特征构造\n(赛前白名单 40 维)", C_BLUE),
        (3.5, 6.6, 3.0, 0.7, "join teams 球队属性\n(odds/Elo/排名/球迷/时区)", C_BLUE),
        (1.2, 5.2, 3.0, 0.7, "HGB 模型\n(max_iter=150)", C_ORANGE),
        (5.6, 5.2, 3.0, 0.7, "Ridge 基线\n(alpha=10)", C_ORANGE),
        (3.5, 3.9, 3.0, 0.7, "5 折 GroupKFold\n(按年月防时序泄露)", C_GREEN),
        (3.5, 2.7, 3.0, 0.7, "0.5·HGB + 0.5·Ridge\n混合预测", C_GREEN),
        (1.2, 1.3, 3.0, 0.7, "test 140 预测\nresult_1_test", C_RED),
        (5.6, 1.3, 3.0, 0.7, "72 场预测\nresult_1_match", C_RED),
    ]
    centers = {}
    for x, y, w, h, t, c in steps:
        fc = {C_BLUE: "#D6EAF8", C_ORANGE: "#FAE5D3", C_GREEN: "#D5F5E3", C_RED: "#FADBD8"}[c]
        centers[t.split('\n')[0]] = box(ax, x, y, w, h, t, fc=fc, ec=c, fontsize=8.5, fontweight="bold")
    arrow(ax, (5.0, 9.0), (5.0, 8.5))
    arrow(ax, (5.0, 7.8), (5.0, 7.3))
    arrow(ax, (5.0, 6.6), (4.2, 5.9))
    arrow(ax, (5.0, 6.6), (5.8, 5.9))
    arrow(ax, (2.7, 5.2), (4.2, 4.6))
    arrow(ax, (7.1, 5.2), (5.8, 4.6))
    arrow(ax, (5.0, 3.9), (5.0, 3.4))
    arrow(ax, (4.2, 2.7), (2.7, 2.0))
    arrow(ax, (5.8, 2.7), (7.1, 2.0))
    ax.text(5, 0.4, "评价：CV MSE ≈ 208（Ridge）/272（HGB）；防泄露：禁用赛后特征",
            ha="center", fontsize=8, color="#566573", style="italic")
    utils.save_fig("fig_flow_q1.pdf", fig)


def fig_flow_q2():
    """问题二求解流程图：贪心+SA。"""
    fig, ax = plt.subplots(figsize=(8, 7.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 9); ax.axis("off")
    steps = [
        (3.0, 8.0, 4.0, 0.7, "输入：P1 预测 + venues/slots/distance/\nticket/base_pred/security", C_BLUE),
        (3.0, 6.8, 4.0, 0.7, "预计算：全局 min-max 上下界\n候选资格 / 黄金时段 / 大容量场馆", C_BLUE),
        (0.5, 5.4, 4.0, 0.8, "贪心初始\n按轮次顺序+日期窗口\n(R1:11-14, R2:14-17, R3:17-30)", C_ORANGE),
        (5.5, 5.4, 4.0, 0.8, "约束硬过滤\n60h 双向 / 安保资格 /\n场馆同时段 / broadcast_cap", C_ORANGE),
        (3.0, 3.9, 4.0, 0.8, "模拟退火 SA\n邻域:换馆/换时段/交换\n目标=Z2−50·违反数", C_GREEN),
        (3.0, 2.5, 4.0, 0.7, "6 起点并行 + 定向修复\n(rest_60h 逐场换时段)", C_GREEN),
        (3.0, 1.1, 4.0, 0.9, "输出 result_2 (72 场)\nZ2=19.16, 0 违反", C_RED),
    ]
    cs = {}
    for x, y, w, h, t, c in steps:
        fc = {C_BLUE: "#D6EAF8", C_ORANGE: "#FAE5D3", C_GREEN: "#D5F5E3", C_RED: "#FADBD8"}[c]
        cs[steps.index((x, y, w, h, t, c))] = box(ax, x, y, w, h, t, fc=fc, ec=c, fontsize=8.3, fontweight="bold")
    arrow(ax, (5.0, 8.0), (5.0, 7.5))
    arrow(ax, (5.0, 6.8), (3.5, 6.2))
    arrow(ax, (5.0, 6.8), (6.5, 6.2))
    arrow(ax, (4.5, 5.4), (4.5, 4.7))
    arrow(ax, (5.5, 5.4), (5.5, 4.7))
    arrow(ax, (5.0, 3.9), (5.0, 3.2))
    arrow(ax, (5.0, 2.5), (5.0, 2.0))
    ax.text(5, 0.3, "约束回代：9 类全部 0 违反；稳定性：6 起点 Z2∈[19.07,19.16]",
            ha="center", fontsize=8, color="#566573", style="italic")
    utils.save_fig("fig_flow_q2.pdf", fig)


def fig_flow_q3():
    """问题三求解流程图：14 式公式链。"""
    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    ax.set_xlim(0, 11); ax.set_ylim(0, 10); ax.axis("off")
    steps = [
        (3.5, 9.0, 4.0, 0.6, "P2 固定第三轮赛程 + P1 转播预测\n+ live_group_results (前两轮反馈)", C_BLUE),
        (1.0, 7.7, 4.2, 0.7, "公式 1-2: S_t 竞技状态 / h_t 伤病\n(0.45·P/3G + 0.35·tanh + 0.20·exp)", C_PURPLE),
        (5.8, 7.7, 4.2, 0.7, "公式 3: λ 更新\nλ=clip[λ0·exp(Δ−0.04h),0.15,4.50]", C_PURPLE),
        (3.5, 6.3, 4.0, 0.7, "公式 4: 蒙特卡洛 20000 次\n泊松模拟→积分排名→p_t 晋级概率", C_ORANGE),
        (1.0, 4.9, 4.2, 0.7, "公式 5-6: Q_i 晋级重要性\nf_i 反馈系数 (现场/转播比)", C_PURPLE),
        (5.8, 4.9, 4.2, 0.7, "公式 7-8: A_i 更新吸引力\nN~_i 更新现场需求", C_PURPLE),
        (3.5, 3.5, 4.0, 0.7, "公式 9-10: 票价 δ / 转播优先级\nTV_i = P0(1+δ)N(δ),  V_i = V~·m_b", C_PURPLE),
        (1.0, 2.1, 4.2, 0.7, "公式 11-12: 风险\nR_noeff / R_coll 默契风险", C_RED),
        (5.8, 2.1, 4.2, 0.7, "公式 13-14: 动态安保 d_i\n综合风险 R_i / 成本 C_i", C_RED),
        (3.5, 0.7, 4.0, 0.9, "分场枚举+δ优化+每日容量\n静态 vs 动态对比 → result_3\nZ3 动态 8.14 vs 静态 6.55 (↑24%)", C_GREEN),
    ]
    for x, y, w, h, t, c in steps:
        fc = {C_BLUE: "#D6EAF8", C_PURPLE: "#E8DAEF", C_ORANGE: "#FAE5D3", C_RED: "#FADBD8", C_GREEN: "#D5F5E3"}[c]
        box(ax, x, y, w, h, t, fc=fc, ec=c, fontsize=8.0, fontweight="bold")
    arrow(ax, (5.5, 9.0), (3.1, 8.4))
    arrow(ax, (5.5, 9.0), (7.9, 8.4))
    arrow(ax, (5.5, 7.7), (5.5, 7.0))
    arrow(ax, (5.5, 6.3), (3.1, 5.6))
    arrow(ax, (5.5, 6.3), (7.9, 5.6))
    arrow(ax, (5.5, 4.9), (5.5, 4.2))
    arrow(ax, (5.5, 3.5), (3.1, 2.8))
    arrow(ax, (5.5, 3.5), (7.9, 2.8))
    arrow(ax, (5.5, 2.1), (5.5, 1.6))
    utils.save_fig("fig_flow_q3.pdf", fig)


def fig_pipeline():
    """数据处理流程图。"""
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.set_xlim(0, 11); ax.set_ylim(0, 4.5); ax.axis("off")
    stages = [
        (0.3, "原始数据\n14 sheet\nxlsx", C_BLUE),
        (2.3, "data_loader\n行列校验\n类型转换", C_BLUE),
        (4.3, "特征工程\n赛前白名单\n防泄露", C_ORANGE),
        (6.3, "归一化\nmin-max 全局\n[0,1]", C_GREEN),
        (8.3, "建模输入\nP1/P2/P3\n统一口径", C_RED),
    ]
    for x, t, c in stages:
        fc = {C_BLUE: "#D6EAF8", C_ORANGE: "#FAE5D3", C_GREEN: "#D5F5E3", C_RED: "#FADBD8"}[c]
        box(ax, x, 1.6, 1.8, 1.3, t, fc=fc, ec=c, fontsize=8.5, fontweight="bold")
    for i in range(4):
        arrow(ax, (2.1 + i * 2, 2.25), (2.3 + i * 2, 2.25), lw=1.8)
    ax.text(5.5, 3.6, "数据处理流程：单一数据源 → 校验 → 特征 → 归一化 → 统一建模输入",
            ha="center", fontsize=9.5, fontweight="bold", color="#1A5276")
    ax.text(5.5, 0.8, "保证：单位口径一致（百万人/USD）、train/test 不混、蒙特卡洛固定种子 20260814",
            ha="center", fontsize=8, color="#566573", style="italic")
    utils.save_fig("fig_pipeline.pdf", fig)


def fig_index_system():
    """指标体系图：P2/P3 目标函数指标层次。"""
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_xlim(0, 12); ax.set_ylim(0, 6); ax.axis("off")
    # 目标层
    box(ax, 4.5, 5.0, 3.0, 0.7, "综合目标函数\nMax Z2 / Max Z3", fc="#1A5276", ec="#1A5276", fontsize=10, fontweight="bold", textcolor="white")
    # 准则层
    box(ax, 1.0, 3.6, 4.5, 0.8, "收益类（正向 0.70）\nT 票务 0.25 + B 转播 0.25\n+ U 不确定 0.15 + H 吸引 0.10", fc="#D5F5E3", ec=C_GREEN, fontsize=8.5, fontweight="bold")
    box(ax, 6.5, 3.6, 4.5, 0.8, "成本/风险类（负向 0.30）\nC 成本 0.08 + D 旅行 0.07\n+ F 公平 0.06 + R 风险 0.04", fc="#FADBD8", ec=C_RED, fontsize=8.5, fontweight="bold")
    arrow(ax, (5.2, 5.0), (3.2, 4.4))
    arrow(ax, (6.8, 5.0), (8.8, 4.4))
    # 指标层
    inds_pos = ["票务收益 T", "转播价值 B", "不确定性 U", "吸引力 H"]
    inds_neg = ["组织成本 C", "旅行负担 D", "公平性 F", "执行风险 R"]
    for i, t in enumerate(inds_pos):
        box(ax, 0.5 + i * 1.15, 1.8, 1.05, 0.8, t, fc="white", ec=C_GREEN, fontsize=7.5)
        arrow(ax, (3.2 + (i - 1.5) * 0.6, 3.6), (1.0 + i * 1.15, 2.6))
    for i, t in enumerate(inds_neg):
        box(ax, 6.6 + i * 1.15, 1.8, 1.05, 0.8, t, fc="white", ec=C_RED, fontsize=7.5)
        arrow(ax, (8.8 + (i - 1.5) * 0.6, 3.6), (7.1 + i * 1.15, 2.6))
    # 数据源层
    box(ax, 1.0, 0.3, 10.0, 0.9, "数据源：result_1(P1) / ticket_broadcast / base_predictions / venues / time_slots /\n"
        "distance_matrix / security_requirements / dynamic_resource_costs",
        fc="#F4F6F6", ec=C_GRAY, fontsize=7.8)
    ax.text(6, 5.9, "P2 八指标 + P3 五指标体系（权重来自 objective_weights，归一化 min-max）",
            ha="center", fontsize=9, color="#566573", style="italic")
    utils.save_fig("fig_index_system.pdf", fig)


def main():
    print("生成非数据型 DrawIO 图示（matplotlib 渲染，drawio CLI 不可用）...")
    fig_roadmap()
    fig_flow_q1()
    fig_flow_q2()
    fig_flow_q3()
    fig_pipeline()
    fig_index_system()
    print("全部非数据图生成完成。")


if __name__ == "__main__":
    main()
