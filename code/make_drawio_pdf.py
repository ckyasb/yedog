"""把 .drawio (mxfile XML) 渲染成 PDF 作为 fallback。
drawio 未安装，用 graphviz 重新构造等价的流程图 PDF（保留 .drawio 源文件用于可编辑）。
只做论文可读的矢量图，不追求与 .drawio 像素一致。
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from graphviz import Digraph

FIG = Path(__file__).resolve().parent.parent / "figures"
FIG.mkdir(exist_ok=True)

CLR = {"start": "#dae8fc", "proc": "#fff2cc", "dec": "#f8cecc", "ok": "#d5e8d4",
       "repair": "#ffe6cc", "end": "#dae8fc", "box": "#f5f5f5"}

def roadmap():
    g = Digraph("roadmap", format="pdf")
    g.attr(rankdir="TB", fontname="Noto Sans CJK SC", fontsize="11", splines="polyline")
    g.attr("node", shape="box", style="rounded,filled", fontname="Noto Sans CJK SC")
    g.node("data", "输入数据\ndistances.csv(55×55) peopleQ1/Q2/Q3.csv", fillcolor=CLR["start"])
    g.node("pre", "预处理\n距离校验·续航可达性(T1/T2/T3往返需加油)·最近机场", fillcolor=CLR["proc"])
    g.node("q1", "问题一 单向出海(1600人)\n聚类+节约+机型选择+ALNS+续航门控", fillcolor=CLR["ok"])
    g.node("q2", "问题二 出海+海返+穿梭(4000人)\nPDPTW配对+座位复用+穿梭嵌入+ALNS", fillcolor=CLR["ok"])
    g.node("q3", "问题三 带时间窗多日(4000人,24架)\n阶段A非临时→T0 · 阶段B临时增量插入", fillcolor=CLR["ok"])
    g.node("lb", "下界推导与gap\nQ1强下界4.2% Q2 5.3% Q3临时满足率", fillcolor=CLR["dec"])
    g.node("val", "独立校验 validate.py\n首末同机场·≤5站·refuel合法·续航·pickup<delivery·时刻链·运营窗", fillcolor="#e1d5e7")
    g.node("out", "输出\nq1/q2/q3-routes+assignments.csv · 五项指标 · figures", fillcolor=CLR["end"])
    g.edge("data", "pre"); g.edge("pre", "q1"); g.edge("pre", "q2"); g.edge("pre", "q3")
    g.edge("q1", "lb"); g.edge("q2", "lb"); g.edge("q3", "lb")
    g.edge("lb", "val"); g.edge("val", "out")
    g.render(FIG / "fig_roadmap", cleanup=True)

def flow_q1():
    g = Digraph("flowq1", format="pdf")
    g.attr(rankdir="TB", fontname="Noto Sans CJK SC", fontsize="10", splines="polyline")
    g.attr("node", shape="box", style="rounded,filled", fontname="Noto Sans CJK SC")
    g.node("s", "开始: peopleQ1.csv(1600出海)", fillcolor=CLR["start"])
    g.node("d1", "按dest分组(52设施,各19-51人)", fillcolor=CLR["proc"])
    g.node("d2", "设施聚类(同机场近邻≤5)", fillcolor=CLR["proc"])
    g.node("d3", "机型选择 min ceil(N/seat)·trip_time", fillcolor=CLR["proc"])
    g.node("d4", "路线构造 make_route: TSP序+加油点插入", fillcolor=CLR["proc"])
    g.node("gate", "续航门控 fuel_feasible?", shape="diamond", fillcolor=CLR["dec"])
    g.node("repair", "换机型/换序/插加油点", fillcolor=CLR["repair"])
    g.node("d5", "初始解:单设施独立(110架,17666min)", fillcolor=CLR["ok"])
    g.node("alns", "ALNS destroy/repair+SA接受", fillcolor=CLR["ok"])
    g.node("ref", "第二层 refine 换机型降油耗", fillcolor=CLR["ok"])
    g.node("end", "输出 q1-routes+assignments\n总时间17612min gap4.2%", fillcolor=CLR["end"])
    for a,b in [("s","d1"),("d1","d2"),("d2","d3"),("d3","d4"),("d4","gate"),
                ("gate","d5"),("gate","repair"),("repair","d4"),
                ("d5","alns"),("alns","ref"),("ref","end")]:
        g.edge(a,b)
    g.render(FIG / "fig_flow_q1", cleanup=True)

def flow_q2():
    g = Digraph("flowq2", format="pdf")
    g.attr(rankdir="TB", fontname="Noto Sans CJK SC", fontsize="10", splines="polyline")
    g.attr("node", shape="box", style="rounded,filled", fontname="Noto Sans CJK SC")
    g.node("s", "开始: peopleQ2.csv(4000:出1600+返1600+穿梭800)", fillcolor=CLR["start"])
    g.node("c", "分类 出海/海返/穿梭", fillcolor=CLR["proc"])
    g.node("pair", "配对: 出海(dest=F)+海返(origin=F)共享A→F→A\n座位复用 seg0出海 seg1海返", fillcolor=CLR["proc"])
    g.node("type", "机型 max(出批,返批)≤seat", fillcolor=CLR["proc"])
    g.node("loop", "构造往返环 A→F→A", fillcolor=CLR["ok"])
    g.node("shu", "穿梭嵌入 A→F1→F2→A", fillcolor=CLR["ok"])
    g.node("gate", "续航+座位门控?", shape="diamond", fillcolor=CLR["dec"])
    g.node("repair", "插加油点/换机型/拆分", fillcolor=CLR["repair"])
    g.node("alns", "ALNS: 换机场·调序·穿梭位置·合并拆分", fillcolor=CLR["ok"])
    g.node("ref", "refine 换机型降油耗", fillcolor=CLR["ok"])
    g.node("end", "输出 q2-routes+assignments\n28602min 167架 利用率0.56 gap5.3%", fillcolor=CLR["end"])
    for a,b in [("s","c"),("c","pair"),("pair","type"),("type","loop"),("type","shu"),
                ("loop","gate"),("shu","gate"),("gate","alns"),("gate","repair"),
                ("repair","loop"),("alns","ref"),("ref","end")]:
        g.edge(a,b)
    g.render(FIG / "fig_flow_q2", cleanup=True)

def flow_q3():
    g = Digraph("flowq3", format="pdf")
    g.attr(rankdir="TB", fontname="Noto Sans CJK SC", fontsize="10", splines="polyline")
    g.attr("node", shape="box", style="rounded,filled", fontname="Noto Sans CJK SC")
    g.node("s", "开始: peopleQ3.csv(4000+时间窗+task_type) 24架飞机", fillcolor=CLR["start"])
    with g.subgraph(name="cluster_A") as a:
        a.attr(label="阶段A 非临时排班(3840)", style="rounded,filled", fillcolor="#fafafa", fontname="Noto Sans CJK SC")
        a.node("a1", "按(pickup,优先级)排序\n紧窗优先占位", fillcolor=CLR["proc"])
        a.node("a2", "① can_join 加入已有架次?", fillcolor=CLR["ok"])
        a.node("a3", "② try_open_trip 新开\n多日重试 机型T3/T2/T1", fillcolor=CLR["ok"])
        a.node("a4", "硬约束:06-18起飞·≤20返·不过夜·周转≥30·配额·时刻链", fillcolor=CLR["dec"])
        a.node("a5", "末轮补漏 任意机场/跨日", fillcolor=CLR["repair"])
        a.node("a6", "T0=69979min", fillcolor=CLR["end"], shape="box", style="rounded,filled,bold")
    with g.subgraph(name="cluster_B") as b:
        b.attr(label="阶段B 临时增量(160)", style="rounded,filled", fillcolor="#fafafa", fontname="Noto Sans CJK SC")
        b.node("b1", "优先 can_join 插入(0时间)", fillcolor=CLR["ok"])
        b.node("b2", "新开架次 受T≤T0", fillcolor=CLR["ok"])
        b.node("b3", "超额移除最晚临时新开", fillcolor=CLR["repair"])
        b.node("b4", "临时满足 157/160(98.1%)", fillcolor=CLR["end"])
    g.node("end", "输出 q3-routes(带时刻)+assignments\ntemporary未安排保留空行", fillcolor=CLR["end"])
    for a,b in [("s","a1"),("a1","a2"),("a2","a3"),("a3","a4"),("a4","a5"),("a5","a6"),
                ("a6","b1"),("b1","b2"),("b2","b3"),("b3","b4"),("b4","end")]:
        g.edge(a,b)
    g.render(FIG / "fig_flow_q3", cleanup=True)

def flight_arch():
    g = Digraph("arch", format="pdf")
    g.attr(rankdir="LR", fontname="Noto Sans CJK SC", fontsize="11", splines="polyline")
    g.attr("node", shape="box", style="rounded,filled", fontname="Noto Sans CJK SC")
    g.node("A", "陆地机场A", fillcolor=CLR["start"], fontsize="12")
    g.node("F1", "设施F001", fillcolor=CLR["ok"], fontsize="12")
    g.node("F2", "设施F002", fillcolor=CLR["ok"], fontsize="12")
    g.node("A2", "陆地机场A", fillcolor=CLR["start"], fontsize="12")
    g.edge("A", "F1", label="seg0 出海4人\n[■■■■]", color="#4C72B0", penwidth="3")
    g.edge("F1", "F2", label="seg1 穿梭1+出海3=4\n[先下后上]", color="#4C72B0", penwidth="3")
    g.edge("F2", "A2", label="seg2 海返3人\n[■■■]", color="#4C72B0", penwidth="3")
    g.render(FIG / "fig_flight_arch", cleanup=True)

def refuel():
    g = Digraph("refuel", format="pdf")
    g.attr(rankdir="TB", fontname="Noto Sans CJK SC", fontsize="10", splines="polyline")
    g.attr("node", shape="box", style="rounded,filled", fontname="Noto Sans CJK SC")
    g.node("s", "架次满油起飞 F₀=W_t", fillcolor=CLR["start"])
    g.node("loop", "对每一航段 i→i+1", fillcolor=CLR["proc"])
    g.node("calc", "F_{i+1}=F_i−c_t·d", fillcolor=CLR["proc"])
    g.node("gate", "F_{i+1}≥安全余油?", shape="diamond", fillcolor=CLR["dec"])
    g.node("arr", "飞到 s_{i+1}", fillcolor=CLR["ok"])
    g.node("isnext", "还有航段?", shape="diamond", fillcolor=CLR["proc"])
    g.node("done", "续航可行 ✓", fillcolor=CLR["end"])
    g.node("need", "需在 s_i 加油", fillcolor=CLR["repair"])
    g.node("isr", "s_i是可加油设施?", shape="diamond", fillcolor=CLR["dec"])
    g.node("rf", "加满 refuel=1 停≥20min", fillcolor=CLR["ok"])
    g.node("ins", "插入最近可加油设施(≤2)", fillcolor=CLR["repair"])
    g.node("inf", "不可行 换大机型/拆分", fillcolor=CLR["dec"])
    for a,b,lbl in [("s","loop",""),("loop","calc",""),("calc","gate",""),
                    ("gate","arr","是"),("gate","need","否"),
                    ("arr","isnext",""),("isnext","loop","是"),("isnext","done","否"),
                    ("need","isr",""),("isr","rf","是"),("isr","ins","否"),
                    ("ins","inf","")]:
        g.edge(a,b,label=lbl)
    g.render(FIG / "fig_refuel", cleanup=True)

def main():
    roadmap(); flow_q1(); flow_q2(); flow_q3(); flight_arch(); refuel()
    print("drawio fallback PDFs rendered via graphviz")

if __name__ == "__main__":
    main()
