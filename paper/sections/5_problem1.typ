= 问题一：转播观看人数预测

== 数据预处理与特征工程

historical_matches 共 700 条，按 dataset_split 划分为训练集 560（含 tv_viewers）与测试集 140（tv_viewers 缺失）。训练集日期为 2018-01 至 2024-07，测试集为 2024-08 至 2025-12，两者无日期重叠。tv_viewers 原值为绝对人数，按假设 2 统一换算为百万人单位（训练集范围 93.96--225.41 百万，均值 145.64 百万）。

特征工程遵循"赛前可知"原则以防止数据泄露。goals、xg、shots、possession、attendance 等赛后量不予使用；可用赛前特征包括赔率隐含概率、Elo 与排名、球迷基础、市值、球星指数、攻防风格、赛事类型、比赛阶段、是否中立与球队所在时区。其中由欧赔 $o_a,o_d,o_b$ 反推隐含概率：

$
p_a = (1/o_a) / (1/o_a + 1/o_d + 1/o_b), quad
p_d = (1/o_d) / (.), quad
p_b = (1/o_b) / (.)
$

并构造悬念指标 $1 - max(p_a, p_b)$ 与信息熵 $-sum p_k log p_k$、实力差 $|"elo"_a - "elo"_b|$、球迷和与市值和等派生特征，共 40 维。数据处理流程如图 2 所示。

#figure(
  image("../../figures/fig_pipeline.pdf", width: 88%),
  caption: [图 2 数据处理流程：单一数据源到统一建模输入],
)

== 模型建立

同时建立三个模型：梯度提升回归（HistGradientBoosting，捕捉非线性与特征交互）、岭回归（Ridge，线性、泛化稳定）与 Lasso 回归（L1 正则化、特征选择）。5 折交叉验证以 Lasso 最优，最终预测取 0.9 Lasso + 0.1 Ridge 混合，以在拟合度与泛化间取得平衡。模型评价采用 5 折 GroupKFold，按比赛年月分组，避免时序泄露。求解流程如图 3 所示。

此外，将现场观众人数（attendance，百万人）作为赛前可用特征纳入模型。该特征在测试集中由组委会提供，且与转播观看人数的相关性达 0.628，是仅次于球迷基础和（fan_sum，0.69）的第二大相关特征。

#figure(
  image("../../figures/fig_flow_q1.pdf", width: 62%),
  caption: [图 3 问题一求解流程：HGB+Ridge 混合预测],
)

== 特征与目标的关系分析

训练集上各赛前特征与转播观看人数的相关性如图 4 所示。球迷基础和（fan_sum）、赛事是否世界杯、Elo 差、市值和等特征与转播观看人数正相关较强，与足球商业直觉一致：球迷基数大、实力接近（悬念高）、世界杯级别赛事的转播关注度更高。

#figure(
  image("../../figures/p1_corr_heatmap.pdf", width: 80%),
  caption: [图 4 问题一特征与转播观看人数相关性热力图],
)

== 求解结果

5 折交叉验证下，Lasso 回归 MSE 为 198.10、$R^2$ 为 0.638（CV 最优），岭回归 MSE 为 205.60、$R^2$ 为 0.625，梯度提升 MSE 为 270.90、$R^2$ 为 0.502。加入 attendance 特征后 Lasso MSE 从 208 降至 198（改善 4.8%）。最终采用 0.9 Lasso + 0.1 Ridge 混合输出预测。训练集预测与真实值的对比如图 5 所示，散点集中在对角线附近。

#figure(
  image("../../figures/p1_pred_vs_true.pdf", width: 58%),
  caption: [图 5 问题一训练集预测值与真实值对比],
)

特征重要性（以与目标的相关系数绝对值度量，含 attendance）如图 6 所示，球迷基础和（fan_sum，0.69）、现场观众（att_million，0.63）、Elo 和（elo_sum，0.62）位居前三。attendance 加入后成为第 2 重要特征，验证了其预测价值。

#figure(
  image("../../figures/p1_feature_importance.pdf", width: 72%),
  caption: [图 6 问题一特征重要性],
)

输出 140 场测试集预测（均值 145.37 百万，范围 112.76--187.60 百万）与 72 场小组赛预测（均值 164.65 百万，范围 150.31--187.60 百万）。72 场用 base_predictions.expected_attendance_base 作 attendance 代理特征。小组赛预测均值高于历史均值，符合世界杯小组赛关注度更高的预期；72 场预测按轮次分布如图 7 所示，三轮间差异较小。

#figure(
  image("../../figures/p1_pred_dist_by_round.pdf", width: 58%),
  caption: [图 7 问题一 72 场小组赛预测按轮次分布],
)
