"""
生成非数据型图示（技术路线图、流程图、模型结构图）。
- 每张图产出两份：
  1) figures/<name>.drawio  —— 可在 draw.io 编辑的源文件（真实 XML）
  2) figures/<name>.pdf     —— 用 graphviz 渲染的等效 PDF（供 5writing 插入论文）
  本机无 drawio 二进制、无显示服务器，无法直接导出 .drawio->PDF，
  故用 graphviz(dot) 渲染等价图作为 PDF。两者内容一致。
- 节点统一配色与样式；中文标注。
"""
import os
import graphviz
from utils import FIG_DIR, _setup_font  # noqa
import matplotlib
matplotlib.use("Agg")

# 统一样式
NODE_STYLE = dict(fontname="Noto Sans CJK SC", shape="box", style="filled,rounded",
                  fillcolor="#dbeafe", color="#3b6fb6", penwidth="1.2",
                  fontsize="11", margin="0.12,0.07")
DECISION_STYLE = dict(fontnode=None)
PIPE_FILL = "#dcfce7"; PIPE_EDGE = "#16a34a"
PROC_FILL = "#dbeafe"; PROC_EDGE = "#3b6fb6"
DATA_FILL = "#fef9c3"; DATA_EDGE = "#ca8a04"
OUT_FILL = "#fae8ff"; OUT_EDGE = "#9333ea"
MODEL_FILL = "#ffe4e6"; MODEL_EDGE = "#e11d48"

def styled(fill, edge):
    return dict(shape="box", style="filled,rounded", fillcolor=fill, color=edge,
                fontname="Noto Sans CJK SC", fontsize="11", penwidth="1.2", margin="0.12,0.07")

def make_fig(name, title, nodes, edges, rankdir="TB"):
    """nodes: list of (id, label, style_dict). edges: list of (src,dst,label_or_None)."""
    # 1) graphviz PDF
    g = graphviz.Digraph(name=name, format="pdf")
    g.attr(rankdir=rankdir, bgcolor="white", label=title, labelloc="t",
           fontname="Noto Sans CJK SC", fontsize="13", pad="0.2", nodesep="0.35", ranksep="0.45")
    g.attr("node", fontname="Noto Sans CJK SC")
    g.attr("edge", fontname="Noto Sans CJK SC", color="#475569", penwidth="1.1", arrowsize="0.8")
    for nid, lab, st in nodes:
        g.node(nid, lab, **st)
    for e in edges:
        src, dst = e[0], e[1]
        lab = e[2] if len(e) > 2 and e[2] else ""
        g.edge(src, dst, label=lab, fontsize="9")
    pdf_path = os.path.join(FIG_DIR, f"{name}.pdf")
    g.render(filename=os.path.join(FIG_DIR, name), cleanup=True)
    # 2) drawio XML（按拓扑分层手动布局）
    xml = _to_drawio(name, title, nodes, edges, rankdir)
    with open(os.path.join(FIG_DIR, f"{name}.drawio"), "w", encoding="utf-8") as f:
        f.write(xml)
    return pdf_path

def _to_drawio(name, title, nodes, edges, rankdir):
    """把节点按拓扑分层放到 drawio 画布上。"""
    from collections import defaultdict, deque
    ids = [n[0] for n in nodes]
    label = {n[0]: n[1] for n in nodes}
    adj = defaultdict(list)
    indeg = {i: 0 for i in ids}
    for e in edges:
        adj[e[0]].append(e[1]); indeg[e[1]] += 1
    # BFS 分层
    layer = {}
    q = deque([i for i in ids if indeg[i] == 0])
    for i in q: layer[i] = 0
    while q:
        u = q.popleft()
        for v in adj[u]:
            layer[v] = max(layer.get(v, 0), layer[u] + 1)
            indeg[v] -= 1
            if indeg[v] == 0: q.append(v)
    # 未分层（成环）补 0
    for i in ids:
        layer.setdefault(i, 0)
    by_layer = defaultdict(list)
    for i in ids: by_layer[layer[i]].append(i)
    # 颜色按 style 取 fill
    fill_of = {}
    for nid, lab, st in nodes:
        fill_of[nid] = st.get("fillcolor", "#dbeafe")
        edge_of = st.get("color", "#3b6fb6")
    # 坐标
    W, H, dx, dy = 180, 56, 210, 90
    pos = {}
    for L, items in sorted(by_layer.items()):
        n = len(items)
        for j, nid in enumerate(items):
            x = j * dx - (n - 1) * dx / 2
            y = L * dy
            pos[nid] = (x, y)
    # XML
    def cell(nid):
        x, y = pos[nid]
        col = fill_of[nid]
        lab = label[nid].replace('"', '&quot;')
        return (f'<mxCell id="{nid}" value="{lab}" style="rounded=1;whiteSpace=wrap;'
                f'html=1;fillColor={col};strokeColor=#475569;fontFamily=Noto Sans CJK SC;fontSize=12;" '
                f'vertex="1" parent="1"><mxGeometry x="{x:.0f}" y="{y:.0f}" width="{W}" height="{H}" as="geometry"/></mxCell>')
    def edge(eid, src, dst, lab=""):
        lab = (lab or "").replace('"', '&quot;')
        return (f'<mxCell id="{eid}" value="{lab}" style="endArrow=classic;html=1;'
                f'fontFamily=Noto Sans CJK SC;fontSize=10;strokeColor=#475569;" edge="1" parent="1" '
                f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    cells = [f'<mxCell id="0"/>', f'<mxCell id="1" parent="0"/>']
    for n in nodes:
        cells.append(cell(n[0]))
    for i, e in enumerate(edges):
        lab = e[2] if len(e) > 2 and e[2] else ""
        cells.append(edge(f"e{i}", e[0], e[1], lab))
    xml = (f'<mxfile><diagram name="{name}"><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" '
           f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
           f'pageWidth="1100" pageHeight="850" math="0" shadow="0"><root>{"".join(cells)}</root>'
           f'</mxGraphModel></diagram></mxfile>')
    return xml

S_PROC = styled(PROC_FILL, PROC_EDGE)
S_DATA = styled(DATA_FILL, DATA_EDGE)
S_OUT = styled(OUT_FILL, OUT_EDGE)
S_PIPE = styled(PIPE_FILL, PIPE_EDGE)
S_MODEL = styled(MODEL_FILL, MODEL_EDGE)
S_DEC = dict(shape="diamond", style="filled", fillcolor="#fed7aa", color="#ea580c",
             fontname="Noto Sans CJK SC", fontsize="10", penwidth="1.2", margin="0.05,0.03")

# ===================== 图1: 总体技术路线图 =====================
nodes = [
    ("data", "MIT–Stanford 数据集\n49块电池 / 2 CSV", S_DATA),
    ("eda", "数据清洗与EDA\nC1缺失填C2 / policy解析", S_PIPE),
    ("q1", "问题1\n数据整理与寿命影响分析\n(SOH外推寿命)", S_PROC),
    ("q2", "问题2\n策略参数对寿命影响\n(KW+岭回归+RF重要性)", S_PROC),
    ("q3", "问题3\n电池寿命预测\n(防泄露+RF递归)", S_PROC),
    ("q4", "问题4\n充电策略优化\n(充电时间+衰减 多目标)", S_PROC),
    ("paper", "竞赛论文\n(Typst, 四问+图表)", S_OUT),
]
edges = [("data","eda"), ("eda","q1"), ("q1","q2"), ("q2","q3","衰减规律"),
         ("q3","q4","预测模型"), ("q2","q4","影响关系"), ("q4","paper"), ("q1","paper"),
         ("q2","paper"), ("q3","paper")]
make_fig("fig_roadmap", "图1 总体技术路线图", nodes, edges)

# ===================== 图2: 数据处理流程图 =====================
nodes = [
    ("csv1", "battery_summary.csv\n(49行: C1,Q1,C2,...)", S_DATA),
    ("csv2", "cycle_train.csv\n(9350行: cycle,SOH,...)", S_DATA),
    ("clean", "数据清洗\nC1缺失→填C2\n异常值标注(IQR)", S_PIPE),
    ("parse", "policy解析\n(C1,Q1,C2统一)", S_PIPE),
    ("feat", "特征工程\n15维: 容量/充电/老化/策略/滑窗", S_PIPE),
    ("life", "寿命外推\n线性+指数→中位寿命", S_PROC),
    ("out", "整理表 p1_summary.csv\n特征矩阵 p2_features.csv", S_OUT),
]
edges = [("csv1","clean"), ("csv2","clean"), ("clean","parse"), ("parse","feat"),
         ("parse","life"), ("feat","out"), ("life","out")]
make_fig("fig_pipeline", "图2 数据处理流程图", nodes, edges)

# ===================== 图3: 问题1求解流程图 =====================
nodes = [
    ("in", "输入: cycle_train.csv\nbattery_summary.csv", S_DATA),
    ("soh", "按电池提取\nSOH_smooth序列", S_PIPE),
    ("fit", "拟合线性/指数模型\nSOH=a+kN / exp(-λN)", S_PROC),
    ("ext", "外推至 80% SOH\n得循环寿命 L", S_PROC),
    ("dist", "寿命分布统计\n按策略分组(中位/极差)", S_PROC),
    ("ls", "提取长/短寿命策略\ntop2 vs bottom2", S_PROC),
    ("cmp", "差异对比解释\n(倍率/SOC/充电时间/内阻/温度)", S_OUT),
]
edges = [("in","soh"), ("soh","fit"), ("fit","ext"), ("ext","dist"),
         ("dist","ls"), ("ls","cmp")]
make_fig("fig_flow_q1", "图3 问题一求解流程图", nodes, edges)

# ===================== 图4: 问题2求解流程图 =====================
nodes = [
    ("in", "输入: 问题1寿命表\n+ (C1,Q1,C2)", S_DATA),
    ("grp", "分组对比\n(Q1=80族 / C2=4族)", S_PIPE),
    ("kw", "Kruskal-Wallis\n+ 10000次置换检验", S_PROC),
    ("sig", "差异是否显著?", S_DEC),
    ("reg", "岭回归(含交互)\n+ 偏相关系数", S_PROC),
    ("rf", "随机森林\n置换重要性", S_PROC),
    ("soc", "SOC区间高倍率暴露\nE_low=C1·Q1, E_high=C2·(80-Q1)", S_PROC),
    ("mech", "机制讨论与局限性\n(C2主导/中高SOC致伤)", S_OUT),
]
edges = [("in","grp"), ("grp","kw"), ("kw","sig"),
         ("sig","reg","是"), ("sig","mech","否→仍分析"),
         ("reg","rf"), ("rf","soc"), ("soc","mech")]
make_fig("fig_flow_q2", "图4 问题二求解流程图", nodes, edges)

# ===================== 图5: 问题3求解流程图 =====================
nodes = [
    ("in", "输入: 49块电池循环数据", S_DATA),
    ("split", "防泄露划分\n9测试(前150) / 40验证(1-200)", S_PIPE),
    ("feat", "特征提取(15维)\n容量/充电/老化/策略/滑窗", S_PIPE),
    ("model", "模型对比\n线性/指数/RF递归", S_PROC),
    ("hold", "40块留出验证\n前150训→151-200验", S_PROC),
    ("best", "选最优(RF)", S_DEC),
    ("pred", "9测试电池\n预测151-200 SOH", S_PROC),
    ("life", "合并拟合直线\n外推80%寿命", S_PROC),
    ("len", "数据长度敏感性\n前50/100/150", S_PROC),
    ("out", "精度评价 + 寿命\n(无真值,由40块表征)", S_OUT),
]
edges = [("in","split"), ("split","feat"), ("feat","model"), ("model","hold"),
         ("hold","best"), ("best","pred"), ("pred","life"), ("life","out"),
         ("hold","len"), ("len","out")]
make_fig("fig_flow_q3", "图5 问题三求解流程图", nodes, edges)

# ===================== 图6: 问题4求解流程图 =====================
nodes = [
    ("in", "输入: 问题2衰减规律\n问题3预测模型 + 数据", S_DATA),
    ("tmodel", "充电时间模型\nt_ch=t1+t2+t3 (解析+校准)", S_PROC),
    ("dmodel", "SOH衰减模型\nln|slope|=f(C1,Q1,C2,E)", S_PROC),
    ("obj", "多目标优化\nmin t_ch, min |slope|", S_PROC),
    ("disc", "9策略离散比较\n+ 邻域网格枚举", S_PROC),
    ("pareto", "Pareto前沿\n+ 加权综合得分", S_PROC),
    ("rec", "推荐策略\n(C1=5.8,Q1=64,C2=4.5)", S_OUT),
    ("chk", "合理性/适用范围\n外推风险说明", S_OUT),
]
edges = [("in","tmodel"), ("in","dmodel"), ("tmodel","obj"), ("dmodel","obj"),
         ("obj","disc"), ("disc","pareto"), ("pareto","rec"), ("rec","chk")]
make_fig("fig_flow_q4", "图6 问题四求解流程图", nodes, edges)

# ===================== 图7: 问题3预测模型结构图 =====================
nodes = [
    ("in", "前N循环数据\n(SOH/capacity/IR/\nchargetime/Tavg)", S_DATA),
    ("feat", "特征工程模块", S_MODEL),
    ("f1", "容量特征\nlast_SOH,slope,curvature", S_MODEL),
    ("f2", "充电特征\nchargetime,slope", S_MODEL),
    ("f3", "老化特征\nIR,IR_growth,Tavg", S_MODEL),
    ("f4", "策略特征\nC1,Q1,C2,E_low,E_high", S_MODEL),
    ("sc", "标准化(训练段fit)", S_PIPE),
    ("rf", "随机森林回归\n(递归多步)", S_PROC),
    ("out", "第k+1循环 SOH预测", S_OUT),
    ("loop", "递归外推\n151→200", S_PROC),
    ("life", "合并外推\n→80%寿命", S_OUT),
]
edges = [("in","feat"), ("feat","f1"), ("feat","f2"), ("feat","f3"), ("feat","f4"),
         ("f1","sc"), ("f2","sc"), ("f3","sc"), ("f4","sc"), ("sc","rf"),
         ("rf","out"), ("out","loop"), ("loop","life")]
make_fig("fig_model_q3", "图7 问题三预测模型结构图", nodes, edges)

# ===================== 图8: 问题4优化模型结构图 =====================
nodes = [
    ("dec", "决策变量\n(C1, Q1, C2)", S_DATA),
    ("t1", "t1=Q1/(100·C1)·60\n第一阶段时间", S_MODEL),
    ("t2", "t2=(80-Q1)/(100·C2)·60\n第二阶段时间", S_MODEL),
    ("t3", "t3 CC-CV段\n(中位校准0.228min)", S_MODEL),
    ("tch", "充电时间目标\nt_ch=t1+t2+t3", S_PROC),
    ("slo", "衰减目标\nln|slope|=f(C,Q,E)\n→life=0.2/|slope|", S_PROC),
    ("norm", "无量纲化\n(按9策略min/max)", S_PIPE),
    ("obj", "加权综合\nZ=w_t·t̃ + w_s·|slopẽ|", S_PROC),
    ("pareto", "Pareto前沿\n(网格枚举)", S_PROC),
    ("rec", "推荐策略\n(Pareto上最优)", S_OUT),
]
edges = [("dec","t1"), ("dec","t2"), ("dec","t3"), ("t1","tch"), ("t2","tch"), ("t3","tch"),
         ("dec","slo"), ("tch","norm"), ("slo","norm"), ("norm","obj"), ("norm","pareto"),
         ("obj","rec"), ("pareto","rec")]
make_fig("fig_model_q4", "图8 问题四优化模型结构图", nodes, edges)

print("全部图示已生成。")
import subprocess
print(subprocess.run(["ls","-la",FIG_DIR],capture_output=True,text=True).stdout)
