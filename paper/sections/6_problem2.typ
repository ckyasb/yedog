= 问题二：小组赛场馆与开球时段协同优化

== 决策变量与目标函数

设 $x_(m,v,s) in {0,1}$ 表示比赛 $m$ 是否分配到场馆 $v$、时段 $s$，每场恰好一馆一时段。综合目标函数为

$
"Max" Z_2 = 0.25 hat(T) + 0.25 hat(B) + 0.15 U + 0.10 H - 0.08 hat(C) - 0.07 hat(D) - 0.06 F - 0.04 hat(R)
$

其中带帽项 $hat(T),hat(B),hat(C),hat(D)$ 为 min-max 归一化到 [0,1] 的指标，$U,H,F,R$ 本身在 [0,1]。各指标定义为：

$
T_m = "base_price"(r_m) times min("exp_att_base"_m, "capacity"_v)
$
$
B_m = "tv_pred"_m times "unit_value"(r_m) times "gps"_s times "sponsor"_w(r_m)
$
$
U_m = "uncertainty"_m, quad H_m = "attractiveness"_m / 100
$
$
C_m = "setup"_v times 10^6 + "opcost"_v times 10^6 + 10^5 times "req_sec"_m times "sec_cost_idx"_v
$
$
D_m = 0.5 hat(d) + 0.3 hat(t) + 0.2 hat("tz")
$
$
F = 0.5 (Delta_("gold")/3) + 0.5 (Delta_("big")/3)
$
$
R_m = 0.5 "climate"_v + 0.3 ("att"_m / "capacity"_v) + 0.2 ("req_sec"_m / "sec_level"_v)
$

其中 $D$ 的三项在全部候选组合上 min-max 归一化后加权，每场取两队均值；$F$ 为方案级公平性，$Delta_"gold"$ 与 $Delta_"big"$ 分别为各队黄金时段次数与大容量场馆次数的极差。指标体系如图 8 所示。

#figure(
  image("../../figures/fig_index_system.pdf", width: 90%),
  caption: [图 8 综合评价指标体系：收益类与成本风险类],
)

== 约束条件

模型含 9 类约束：每场一馆一时段；同场馆同时段不撞；同组相邻轮次 UTC 开球时差不少于 60 小时（双向：移动一场时同时检查其前后轮）；场馆单日承办不超过 max_matches_per_day、总数位于 min 与 max 之间；黄金时段任意两队次数差不超过 2；场馆安保能力不低于比赛最低安保需求 req_sec；第三轮每日 req_sec 不低于 3 级的场数不超过 high_security_capacity；同时刻比赛数不超过 broadcast_capacity；同组同轮两场不同时段。

== 求解算法

决策空间约 $9.2 times 10^4$ 组合，精确整数规划成本高，采用贪心初始 + 模拟退火 + 多起点启发式。贪心按轮次顺序处理，并为每轮设定日期窗口（第一轮 06-11 至 06-14、第二轮 06-14 至 06-17、第三轮 06-17 至 06-30）以保证 60 小时休息可行并为后续轮留容量；候选时段按日期升序与黄金时段评分排序，硬约束过滤后按近似目标评分选取。模拟退火邻域为换馆、换时段与两场交换，目标为 $Z_2 - 50 times "违反数"$ 驱动可行化，6 起点并行后对剩余 60 小时违反做定向修复。求解流程如图 9 所示。

#figure(
  image("../../figures/fig_flow_q2.pdf", width: 68%),
  caption: [图 9 问题二求解流程：贪心初始+模拟退火协同优化],
)

== 求解结果

贪心初始 + 模拟退火 + 6 起点并行 + 定向修复 + warm-start SA 精修后，最终 $Z_2 = 19.1006$。9 类约束回代全部为 0 违反，其中第三轮每日高等级安保容量逐日校验均满足（如 06-23 为 3 场、上限 3；06-24 为 2 场、上限 2；06-29 为 2 场、上限 2）。各指标归一化均值与对 $Z_2$ 的贡献如表 2 与图 10 所示。

#align(center)[#text(font: ("Noto Sans CJK SC","Noto Sans CJK JP"), size: 12pt)[表 2 #h(1em) 问题二各指标归一化均值与贡献]]
#align(center)[
  #table(
    columns: (8em, 6em, 5em, 6em),
    align: center, stroke: none, inset: (x: 0.6em, y: 0.5em),
    table.hline(stroke: 0.8pt),
    [#strong[指标]], [#strong[归一化均值]], [#strong[权重]], [#strong[贡献]],
    table.hline(stroke: 0.5pt),
    [票务 $T$], [0.375], [+0.25], [+0.094],
    [转播 $B$], [0.480], [+0.25], [+0.120],
    [不确定 $U$], [0.461], [+0.15], [+0.069],
    [吸引 $H$], [0.640], [+0.10], [+0.064],
    [成本 $C$], [0.421], [-0.08], [-0.034],
    [旅行 $D$], [0.433], [-0.07], [-0.030],
    [公平 $F$], [0.667], [-0.06], [-0.040],
    [风险 $R$], [0.424], [-0.04], [-0.017],
    table.hline(stroke: 0.8pt),
  )
]

#figure(
  image("../../figures/p2_indicator_contribution.pdf", width: 78%),
  caption: [图 10 问题二各指标对 $Z_2$ 的贡献],
)

场馆与日期的使用分布如图 11 所示，72 场均匀分布于 16 个场馆与 20 天中，单日单馆承办不超过其上限。多起点稳定性如图 12 所示，6 起点 $Z_2$ 标准差约 0.04，高度稳定。多目标权衡如图 13 雷达图所示，优化方案在收益类指标上接近理想，成本与风险类处于中等水平。

#figure(
  image("../../figures/p2_venue_date_heatmap.pdf", width: 92%),
  caption: [图 11 问题二场馆与日期使用热力图],
)

#figure(
  image("../../figures/p2_multistart_stability.pdf", width: 72%),
  caption: [图 12 问题二多起点稳定性],
)

#figure(
  image("../../figures/p2_radar.pdf", width: 56%),
  caption: [图 13 问题二多目标雷达图],
)

输出 72 场赛程方案（20 列），整套方案 $Z_2$ 填于首行 total_objective_value。
