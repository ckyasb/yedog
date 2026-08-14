= 符号说明

#pagebreak()
#align(center)[#text(
  font: ("Heiti SC", "STHeiti", "SimSun", "Songti SC"),
  size: 12pt,
)[表 1 #h(1em) 主要符号说明]]
#align(center)[
  #table(
    columns: (5em, 16em, 5em),
    align: center,
    stroke: none,
    inset: (x: 0.75em, y: 0.6em),
    table.hline(stroke: 0.8pt),
    [#strong[符号]], [#strong[含义]], [#strong[单位/范围]],
    table.hline(stroke: 0.5pt),
    [$"tv_viewers"$], [转播观看人数], [百万人],
    [$T$], [票务收益指标], [USD$arrow$[0,1]],
    [$B$], [转播价值指标], [USD$arrow$[0,1]],
    [$U$], [比赛不确定性=uncertainty_index], [[0,1]],
    [$H$], [比赛吸引力=attractiveness_index/100], [[0,1]],
    [$C$], [组织成本指标], [USD$arrow$[0,1]],
    [$D$], [球队旅行负担指标], [[0,1]],
    [$F$], [资源分配公平性指标], [[0,1]],
    [$R$], [赛事执行风险指标], [[0,1]],
    [$Z_2$], [问题二综合目标函数], [标量],
    [$S_t$], [球队 t 竞技状态], [[0,1]],
    [$h_t$], [球队 t 伤病影响], [[0,3]],
    [$lambda_("i,a")$,$lambda_("i,b")$], [更新进球均值], [[0.15,4.50]],
    [$p_t$], [球队 t 晋级概率], [[0,1]],
    [$Q_i$], [比赛 i 晋级重要性], [[0,1]],
    [$A_i$], [更新后比赛吸引力], [[0,1]],
    [$Ñ_i$], [更新现场需求], [人],
    [$N_i(delta_i)$], [票价调整后现场需求], [人],
    [$"TV"_i$], [票务价值], [USD],
    [$V_i$], [最终预计转播观看人数], [百万人],
    [$"BV"_i$], [转播价值], [USD],
    [$R_("i,noeff")$], [无激励风险], [[0,1]],
    [$R_("i,coll")$], [默契风险], [[0,1]],
    [$d_i$], [动态安保需求得分], [[0,1]],
    [$R_i$], [综合风险暴露], [[0,1]],
    [$C_i$], [资源成本指数], [标量],
    [$delta_i$], [票价调整比例], [[-0.15,0.20]],
    [$Z_3$], [问题三综合目标函数], [标量],
    table.hline(stroke: 0.8pt),
  )
]
