# 策联杯 C 题 · 赛题与数据摘要（供建模流程参考）

> 本文件由上一次会话整理，汇总题面、数据结构、目标函数与格式约束。新会话 `2analysis-modeling` 阶段可直接参考，但仍需独立完成假设预检与建模报告。

## 一、赛题总览

**题目**：基于大数据驱动的足球世界杯赛事预测与赛程资源协同优化。
**模拟赛事**：48 队 → 12 小组（A–L）→ 每组 4 队单循环 → 共 72 场小组赛。
**核心链路**：历史数据预测转播观看人数 → 排定 72 场的场馆与开球时段 → 第三轮动态资源调整 → 与真实世界杯赛程对比。

四个子问题：

| # | 问题 | 核心任务 | 输出文件 |
|---|------|----------|----------|
| 1 | 赛事数据分析、特征工程与转播观看人数预测 | 用 historical_matches 建模预测 `tv_viewers`（百万人），产出 test 集预测 + 72 场小组赛预测 | result_1_test_prediction.csv, result_1_match_prediction.csv |
| 2 | 小组赛场馆与开球时段协同优化 | 为 72 场比赛分配 16 个候选场馆 + 80 个候选时段，最大化综合目标 Z₂ | result_2_group_schedule.csv |
| 3 | 前两轮反馈下的第三轮动态资源优化 | 第三轮 24 场，重配转播/安保/交通/票价，对比静态 vs 动态方案 | result_3_dynamic_strategy.csv |
| 4 | 实际赛程获取与优化方案综合评价 | 选一届真实世界杯，用 P2 指标对比实际 vs 优化赛程 | result_4_schedule_comparison.csv（可选）+ actual_schedule.csv |

## 二、问题一：转播观看人数预测

- **目标变量**：`tv_viewers`（单位百万人）。historical_matches 共 700 条，`dataset_split` 划分 train=560（有 tv_viewers）/ test=140（tv_viewers 缺失，组委会保留）。
- **评价**：测试集 MSE = (1/n)·Σ(ŷ−y)²。
- **可用特征**（historical_matches 25 列）：date, competition, stage, neutral, goals_a/b, xg_a/b, shots_a/b, possession_a/b, strength_rank_a/b, elo_a/b, odds_a/b/draw, attendance, tv_viewers。
- **外部可用表**：teams（48 队 16 列含 strength_rank, elo_rating, market_value, fan_base_index, style_attack/defense 等）、base_predictions（72 场的 expected_goals、p_a_win/p_draw/p_b_win、uncertainty_index、attractiveness_index、expected_attendance_base、commercial_value_index）。
- **需产出**：① test 集 140 场预测 → result_1_test_prediction.csv（列：match_id_test, predicted_test_tv_viewers）；② 72 场小组赛预测 → result_1_match_prediction.csv（列：match_id, team_a, team_b, predicted_tv_viewers）。
- **注意**：base_predictions 是问题 2/3 的输入，问题 1 的 72 场预测可参考其 uncertainty/attractiveness，但模型必须在 historical_matches 上训练。

## 三、问题二：场馆与开球时段协同优化

**决策变量**：每场比赛的 venue_id ∈ {V01..V16}、slot_id ∈ {S011..}（80 个时段，2026-06-11 ~ 06-30）。

**目标函数**：
```
Max Z₂ = 0.25T + 0.25B + 0.15U + 0.10H − 0.08C − 0.07D − 0.06F − 0.04R
```
- **T 票务收益** = 该轮基础票价 × 观众人数（基础票价见 ticket_broadcast，按 Group_Match_R1/R2/R3 区分）
- **B 转播价值** = 预测转播观看人数 × 单位观看价值 × 时段全球收视价值 × 赞助权重
- **U 不确定性** = uncertainty_index（base_predictions，原值 0–1）
- **H 吸引力** = attractiveness_index / 100
- **C 组织成本** = 场馆启用成本 + 单场运营成本 + 单场安保成本；其中安保成本 = 10 万美元 × 比赛最低安保需求等级 × 场馆安保成本指数
- **D 旅行负担** = 0.5·距离 + 0.3·旅行时间 + 0.2·时区差，三项先在全部候选组合上 min-max 归一化再加权，每场取两队均值。R1 用 team_to_venue；R2/R3 用 venue_to_venue，起点为该队上一轮全部合格候选场馆（安保能力 ≥ 上一轮最低安保需求）的均值。
- **F 公平性** = 0.5×(黄金时段次数极差/3) + 0.5×(大容量场馆次数极差/3)；大容量 = 容量排名前 25% 的场馆。
- **R 执行风险** = 0.5·气候风险 + 0.3·预计上座率 + 0.2·(最低安保需求等级/场馆安保能力等级)。

**约束**（题面"基本规则约束"，需从数据反推）：
- 每组 6 场、每队 3 场对阵已由 groups_matches 固定（match_id GA01..GL06）。
- 场馆 max_matches_per_day、min/max_total_matches（venues 表）。
- 时段 broadcast_capacity（time_slots 表，每日可同时开赛场数）。
- 安保：场馆安保能力等级 ≥ 比赛最低安保需求等级（security_requirements 表 required_security_level）。
- 同组同轮比赛不能撞时段、旅行时区合理等（需在建模时明确）。

**标准化**：所有指标进目标函数前 min-max 归一化到 [0,1]；若某指标 max=min 则标准化结果记 0。
**输出**：result_2_group_schedule.csv（按 result_2_template.csv，20 列含 match_id, venue_id, slot_id, 各分项指标, total_objective_value）。`total_objective_value` 仅第一条记录填整套方案的 Z₂ 值，其余行留空。

## 四、问题三：第三轮动态资源优化

**设定**：第三轮 24 场，赛程固定（P2 已定场馆/时段），仅用前两轮反馈信息重配资源。24 场均基于"第三轮开始前同一信息截面"，互不使用其他第三轮结果。

**关键公式链**（题面给出，需严格按式实现）：
1. **球队竞技状态** Sₜ = 0.45·Pₜ/(3Gₜ) + 0.35·[0.5+0.5·tanh(((xGFₜ−xGAₜ)/Gₜ)/1.25)] + 0.20·exp(−0.55·RCₜ/Gₜ)，Sₜ∈[0,1]。
2. **伤病** hₜ = 前两轮所涉比赛伤病影响等级均值，限制 [0,3]。
3. **更新进球均值** Δᵢ = 0.32(Sₐ−Sᵦ) − 0.055(hₐ−hᵦ)；λᵢ,ₐ = clip[λ₀,ᵢ,ₐ·exp(Δᵢ−0.04hₐ), 0.15, 4.50]，λᵢ,ᵦ 对称。
4. **蒙特卡洛**：按泊松均值同时模拟 24 场 **20000 次**，按积分→净胜球→总进球排名；每组前 2 名 + 12 组中成绩最好的 8 个第三名晋级（指标完全相同时等比例处理）。pₜ = 晋级次数/20000。
5. **晋级重要性** Qᵢ = [4pₐ(1−pₐ)+4pᵦ(1−pᵦ)]/2，Qᵢ∈[0,1]。
6. **反馈系数**：对球队 t 每场前两轮比赛，实际/赛前现场观众比与转播比分别 clip[0.60,1.50]，两场取平均再 clip[0.75,1.25] 得 rₜᵃ、rₜᵇ；fᵢᵃ=√(rₐᵃ·rᵦᵃ)，fᵢᵇ=√(rₐᵇ·rᵦᵇ)。
7. **更新吸引力** Aᵢ = clip[0.50A₀ᵢ+0.25Qᵢ+0.12Fᵢ+0.08Sᵢ+0.05(1−Hᵢ), 0, 1]，其中 Sᵢ=(Sₐ+Sᵦ)/2，Hᵢ=(hₐ+hᵦ)/6，Fᵢ=clip[(0.5fᵢᵃ+0.5fᵢᵇ−0.75)/0.50, 0, 1]。
8. **更新现场需求** Ñᵢ = Nᵢ,pre·fᵢᵃ·(0.88+0.27Qᵢ)·(0.94+0.12Sᵢ)·(1−0.10Hᵢ)。
9. **票价调整** δᵢ（正涨价负降价），选交通等级 mᵢᵈ 后：Nᵢ(δᵢ)=min{Kᵢ, Ñᵢ·mᵢᵈ·(1+δᵢ)^(1/εᵢ)}，TVᵢ=Pᵢ₀(1+δᵢ)Nᵢ(δᵢ)；要求 Nᵢ(δᵢ)≥0.88Nᵢ(0)（同交通等级仅票价不同）。
10. **更新转播需求** Ṽᵢ = Vᵢ,pre·fᵢᵇ·(0.87+0.30Qᵢ)·(0.90+0.20Aᵢ)·(1−0.06Hᵢ)；选转播优先级 mᵢᵇ 后 Vᵢ=Ṽᵢ·mᵢᵇ，BVᵢ=uᵢ·Vᵢ。
11. **无激励风险** Rᵢ,noeff = 0.5(2pₐ−1)² + 0.5(2pᵦ−1)²。
12. **默契风险**：Dᵢ=min(pₐ|平, pᵦ|平)，Gᵢ=0.5max(pₐ|a胜−pₐ|平,0)+0.5max(pᵦ|b胜−pᵦ|平,0)，Rᵢ,coll=clip[Dᵢ·(1−clip(Gᵢ,0,1))·(1−0.35Rᵢ,noeff), 0, 1]。
13. **动态安保需求** dᵢ=clip[0.45dᵢ₀+0.25Oᵢ+0.15Aᵢ+0.15(Rᵢ,noeff+Rᵢ,coll)/2, 0, 1]，Oᵢ=clip(Ñᵢ/Kᵢ,0,1)。
14. **综合风险** Rᵢ=0.40Rᵢ,noeff+0.40Rᵢ,coll+0.20dᵢ·mᵢˢ（选安保等级后读剩余风险系数 mᵢˢ）。

**决策**：每场第三轮比赛确定 转播优先级 + 安保等级 + 交通等级 + 票价调整比例 δ。
**约束**：安保等级 ≥ 最低安保需求且 ≤ 场馆安保能力等级；每日高等级转播/高等级安保/强化交通容量及资源预算 ≤ dynamic_resource_limits 上限（按 reference_date）。
**成本**：Cᵢ = cᵢᵇ + cᵢˢ + cᵢᵈ（各等级单位成本指数，来自 dynamic_resource_costs）。
**目标**：
```
Max Z₃ = Σ_{i∈I₃} [0.35TVᵢ* + 0.35BVᵢ* + 0.10Aᵢ* − 0.10Cᵢ* − 0.10Rᵢ*]
```
（带 * 为 min-max 归一化，max=min 时记 0）。

**静态 vs 动态对比**：静态方案用赛前预测数据定资源并保持不变；赛前风险中无激励风险取 (1−竞技悬念指数)、默契风险取 0。两方案均在"更新信息环境"下用同一组归一化上下界评价。每场 improvement_rate = (dynamic_net_value − static_net_value)/|static_net_value|，分母 0 记空值。
**输出**：result_3_dynamic_strategy.csv（按 result_3_template.csv，21 列含 updated_p_team_a/b_advance、各 net_value、improvement_rate 等）。

## 五、问题四：实际赛程综合评价

- 选一届已结束、四队小组单循环（每队 3 场）的真实世界杯（如 2022 卡塔尔 / 2018 俄罗斯 / 2014 巴西），从官网采集实际赛程。
- 若规模与本题不同（真实世界杯 32 队 8 组 vs 本题 48 队 12 组），需对指标合理标准化并说明。
- 用 P2 相同的指标定义、标准化方法、基准权重计算实际赛程与本队优化赛程的各分项。
- 对比维度：旅行距离、休息时间、跨时区次数、场馆利用率、容量匹配、黄金时段覆盖、预计观众、票务与转播价值、资源公平性、风险。
- 输出 actual_schedule.csv（按 actual_schedule_template.csv，含 match_id, competition, stage, group_id, round, teams, venue, city, country, date, kickoff_time, utc, goals 等）+ result_4_schedule_comparison.csv（可选）。
- 需附数据采集程序与来源说明、稳健性分析。

## 六、数据附件结构（C题_数据附件.xlsx，14 个 sheet）

| Sheet | 行×列 | 用途 |
|-------|-------|------|
| README | 9×2 | 数据包导航 |
| historical_matches | 700×25 | P1 训练/测试（train 560 有 tv_viewers，test 140 无） |
| teams | 48×16 | 球队属性（strength_rank, elo, market_value, fan_base_index, style, 经纬度） |
| groups_matches | 72×7 | 72 场小组赛对阵（match_id GA01.., group_id, round, 双方 id/name） |
| group_membership | 48×4 | 每组 4 队 + 分档 pot |
| venues | 16×16 | 候选场馆（capacity, 时区, max/min 场次, 成本, 安保等级, 气候风险, 交通指数） |
| time_slots | 80×11 | 候选时段（date, 开球/UTC 时间, 各区 prime 标记, global_prime_score, broadcast_capacity） |
| distance_matrix | 1024×8 | T01..T48 × V01..V16 的距离/旅行时间/时区差（relation_type: team_to_venue / venue_to_venue） |
| ticket_broadcast | 9×6 | 各阶段基础票价、价格弹性、转播单位价值、赞助/本地兴趣权重 |
| base_predictions | 72×14 | P2/P3 基准（期望进球、胜平负概率、uncertainty、attractiveness、预计上座、商业价值） |
| security_requirements | 72×9 | 每场最低安保需求等级 + 风险原因 |
| live_group_results | 48×16 | 前两轮 48 场实际结果（比分、xG、红牌、伤病等级、现场观众、转播人数）—P3 输入 |
| dynamic_resource_limits | 20×7 | P3 每日高等级转播/安保/强化交通容量上限、票价调整上下限 |
| dynamic_resource_costs | 10×6 | 转播/安保/交通各等级单位成本指数、需求/风险乘数 |
| objective_weights | 13×7 | P2/P3 指标权重与标准化方法（与题面公式一致，可交叉核对） |

## 七、策联杯论文格式规范（关键，与模板有冲突！）

源文件：`2026年度"策联杯"数学建模精英联赛-论文格式规范.pdf`。要点：

1. **第一页为摘要专用页**：含标题+关键词，**不超过一页**，页码从 1 开始（页脚居中，阿拉伯数字）。
2. **第二页起正文，不要目录，正文 ≤ 30 页**。
3. **正文后附录，页数不限**：含支撑材料文件列表、全部可运行源程序代码、AI 工具使用声明。缺源程序/不能运行/结果与论文不符 → 取消评奖。
4. **任何地方不能显示参赛者身份和学校信息**。
5. **参考文献**按科技论文规范，正文引用处标注。
6. 字号字体行距颜色不统一要求。
7. 提交：参赛论文 PDF（≤20MB，不压缩）+ 支撑材料 RAR/ZIP（≤20MB）。命名 `XXX_参赛论文` / `XXX_支撑材料`（XXX 为三位队号）。

**AI 工具使用规定**（附录）：
- 参考文献之前设"AI 工具使用声明"，二选一：①"本参赛队在竞赛过程中未使用任何 AI 工具。" ②"本参赛队在竞赛过程中使用了 AI 工具，主要用于【用途】，详细使用情况见支撑材料。"
- 用 AI 则支撑材料含 `AI 工具使用详情.pdf`：工具名称版本、使用目的与环节、主要提示方式与过程、对 AI 输出的采纳/人工修改/核验情况。

## 八、模板选择建议（Typst）

5writing 内置 14 套中文 Typst 模板，无"策联杯"专用。最接近的是 **cumcm（国赛）**，但需改两点以符合策联杯规范：

1. **删除目录页**：cumcm 的 `toc-page()` 必须移除（策联杯明确"不要目录"）。
2. **加 AI 工具使用声明**：在 `references-cn()` 之前插入一个 `heading(numbering: none)[AI 工具使用声明]` 小节。
3. 摘要页保持单页、页码从 1 开始（cumcm 已用 `counter(page).update(1)`，符合）。
4. 正文≤30 页需在写作时控制篇幅。

如 5writing 阶段判断 cumcm 不合适，可退用 `default` 模板再按上述三点调整。

## 九、环境就绪状态

- typst 0.15.1（snap，HOME 下可用，/tmp 不可用——工作目录在 ~/yegou/C题 下不受影响）
- python3 3.12 + numpy/scipy/pandas/matplotlib/scikit-learn/openpyxl 全部就绪
- pdftoppm / mutool / convert（6verity 视觉检查就绪）
- drawio 未装（4drawio 阶段 PDF 导出会跳过，不影响核心流程）
- WSL 直连 GitHub 正常（code=200），无需代理
