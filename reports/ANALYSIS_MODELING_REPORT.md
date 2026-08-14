# 赛题分析-建模报告 · 策联杯 C 题

> 基于 `2026年度"策联杯"数学建模精英联赛-C题.pdf`、`C题_数据附件.xlsx`（14 sheet）、`论文格式规范.pdf`、`CONTEST_BRIEF.md` 独立整理。题面公式已在 PDF 中逐式核对，与 brief 一致；本报告补充假设预检、变量符号、求解口径与代码任务清单。

根据题目动态调整问题数量

本赛题共 **4 个子问题**。

---

## 1. 总体建模框架

模拟赛事：48 队 → 12 小组（A–L）→ 每组 4 队单循环 → 72 场小组赛（每队 3 场，分三轮，每轮 24 场）。核心链路：

```
P1 历史数据预测转播观看人数 → P2 排定 72 场场馆+开球时段 → P3 第三轮动态资源调整 → P4 与真实世界杯赛程对比
```

四问递进依赖：P2 用 P1 的 72 场预测作为转播价值输入；P3 在 P2 固定的第三轮赛程上重配资源，且需 P1 的赛前转播预测作 Vᵢ,pre；P4 用 P2 同口径指标评价真实赛程。任一环节的数值口径必须前后一致（同一 `data_loader.py`、同一归一化约定、同一随机种子）。

```
题面 → 数据清洗EDA → P1预测模型 → P2协同优化 → P3动态资源优化 → P4实际赛程评价 → 结果检验 → 论文
```

## 2. 数据处理方案

附件 `C题_数据附件.xlsx` 14 sheet，已逐表核验行列与字段（见下表，**实测**而非 brief 转述）：

| Sheet | 实测规模 | 用途 / 关键字段 |
|---|---|---|
| README | 9×2 | 导航 |
| historical_matches | 700×25 | P1：train 560（tv_viewers 全有，9.4e7–2.25e8）、test 140（tv_viewers 缺失）。**train/test 按日期无重叠**（train 2018-01~2024-07，test 2024-08~2025-12），故按 dataset_split 划分，不可随机打乱。 |
| teams | 48×16 | 球队属性：strength_rank/elo_rating/market_value_musd/fan_base_index/style_attack/defense/home_timezone_region/经纬度。team_id T01–T48，team_name 与 historical/72场一致（join key=team_name，已验证无缺失）。 |
| groups_matches | 72×7 | 72 场对阵：match_id GA01–GL06、group_id、round_in_group(1/2/3 各24)、双方 id/name。每组每轮 2 场。 |
| group_membership | 48×4 | 每组 4 队 + 分档 pot。 |
| venues | 16×16 | V01–V16：capacity(45500–94000)、timezone、max_matches_per_day(1–2)、min/max_total_matches(均 2/8)、setup_cost_musd、operation_cost_musd_per_match、security_level(2–4)、security_cost_index、climate_risk、transport_index。 |
| time_slots | 80×11 | S011–S204：20 天×4 时段(12/15/18/21 时)；reference_utc_time、america/europe/asia_prime、global_prime_score、broadcast_capacity(2–3)。 |
| distance_matrix | 1024×8 | team_to_venue 768(48×16) + venue_to_venue 256(16×16)，含 distance_km/travel_time_hour/timezone_diff。 |
| ticket_broadcast | 9×6 | 各阶段 base_ticket_price_usd(80–640)、price_elasticity(−0.85~−0.3)、broadcast_unit_value_usd、sponsor_weight、local_interest_weight。 |
| base_predictions | 72×14 | P2/P3 基准：expected_goals_a/b、p_a_win/p_draw/p_b_win、uncertainty_index(0.26–0.64)、attractiveness_index(48–79)、expected_attendance_base、commercial_value_index。R1/R2/R3 各 24 场。 |
| security_requirements | 72×9 | 每场 crowd_risk/attention_risk/security_demand_score(0.26–0.93)/required_security_level(分布 1:9,2:32,3:26,4:5)。 |
| live_group_results | 48×16 | 前两轮 48 场实际结果：goals/xg/red_cards/injury_impact_level(0–2)/attendance/tv_viewers。**R1+R2 各 24 场**。 |
| dynamic_resource_limits | 20×7 | 每日 high_broadcast_capacity(2–4)/high_security_capacity(2–3)/enhanced_transport_capacity(3–4)/daily_resource_budget_index/max_ticket_increase_rate(0.2)/max_ticket_discount_rate(0.15)。 |
| dynamic_resource_costs | 10×6 | broadcast 3 级/security 4 级/transport 3 级的 unit_cost_index/demand_multiplier/risk_multiplier。 |
| objective_weights | 13×7 | P2 八指标 + P3 五指标权重与标准化方法（与题面公式一致，作交叉核对）。 |

**数据清洗要点**：
- historical tv_viewers 单位百万人（实际值约 9.4e7–2.25e8，按"百万人"即 1.0e8 量级，需除 1e6 换算到"百万"单位；输出 result_1 单位百万人，需统一口径，见假设预检 A1）。
- historical 的 neutral 为 Python bool；odds_a/draw/b 为十进制欧赔（test 也有）。
- distance_matrix 的 timezone_diff 为浮点小时差（如 1.7、4.0）。
- live_group_results 的 injury_impact_level 已实测分布 {0:14,1:14,2:20}，符合 [0,3] 限制。
- 14 sheet 全部经 openpyxl data_only 读取无公式残留。

## 3. 符号说明

| 符号 | 含义 | 单位/范围 |
|---|---|---|
| `tv_viewers` | 转播观看人数 | 百万人（P1 输出）；historical 原值需换算 |
| T | P2 票务收益指标 | USD（归一化前）→[0,1] |
| B | P2 转播价值指标 | USD →[0,1] |
| U | P2 不确定性 = uncertainty_index | [0,1] 原值 |
| H | P2 吸引力 = attractiveness_index/100 | [0,1] |
| C | P2 组织成本（启用+运营+安保） | USD →[0,1] |
| D | P2 旅行负担 = 0.5距+0.3时+0.2时区差（归一化后加权） | [0,1] |
| F | P2 公平性 = 0.5×黄金时段极差/3 + 0.5×大容量场馆极差/3 | [0,1] |
| R | P2 执行风险 = 0.5气候+0.3上座率+0.2(需求等级/安保能力) | [0,1] |
| Sₜ | P3 球队 t 竞技状态 | [0,1] |
| hₜ | P3 球队 t 伤病影响（前两轮均值） | [0,3] |
| λᵢ,ₐ,λᵢ,ᵦ | P3 更新进球均值 | clip[0.15,4.50] |
| pₜ | P3 球队 t 晋级概率（20000 次蒙特卡洛） | [0,1] |
| Qᵢ | P3 晋级重要性 | [0,1] |
| fᵢᵃ, fᵢᵇ | P3 现场/转播反馈系数 | √(rₐ·rᵦ) |
| Aᵢ | P3 更新吸引力 | clip[0,1] |
| Ñᵢ | P3 更新现场需求 | 人 |
| Nᵢ(δᵢ) | P3 票价调整后现场需求 | min(K, Ñ·mᵈ·(1+δ)^(1/ε)) |
| TVᵢ | P3 票务价值 | P₀(1+δ)N(δ) |
| Ṽᵢ,Vᵢ | P3 更新/最终转播需求 | 人 |
| BVᵢ | P3 转播价值 | uᵢ·Vᵢ |
| Rᵢ,noeff | P3 无激励风险 | [0,1] |
| Rᵢ,coll | P3 默契风险 | clip[0,1] |
| dᵢ | P3 动态安保需求得分 | clip[0,1] |
| Rᵢ | P3 综合风险暴露 | [0,1] |
| Cᵢ | P3 资源成本 | cᵢᵇ+cᵢˢ+cᵢᵈ |
| Z₂ | P2 目标函数 | 标量 |
| Z₃ | P3 目标函数 | 标量 |

## 4. 假设敏感性预检

### 模糊表述及解释

**A1 — tv_viewers 单位口径**：historical tv_viewers 实测约 9.4e7–2.25e8，而题面与 result_1 模板要求"百万人"。
- 解释①：原值是绝对人数，输出需 ÷1e6 换算到百万人（1.56 百万 ~ 225 百万）。
- 解释②：原值已是百万人但数量级异常。
- 验算：historical train 均值约 1.46e8，attendance 46081–95000 人（现场几万人），转播远大于现场才合理；若按①换算 1.46e8 人=146 百万人，对应 1.46 亿观众，对世界杯级比赛合理。选 **①**。

**A2 — P2 expected_attendance 口径**：result_2 模板字段说明 `expected_attendance = min(expected_attendance_base, venue.capacity)`。
- 解释①：base 来自 base_predictions.expected_attendance_base，与分配到的场馆容量取 min（场馆容量约束现场人数上限）。
- 解释②：用预测模型重算。
- 验算：模板字段说明明确为①；且 expected_attendance_base 实测 30170–58377，部分场馆容量 45500–94000，min 合理。选 **①**。

**A3 — P2 转播价值 B 的乘积项**：题面"预测转播观看人数 × 单位观看价值 × 时段全球收视价值 × 赞助权重"。
- 解释①：B = predicted_tv_viewers × broadcast_unit_value_usd(按轮次) × global_prime_score(time_slots) × sponsor_weight(按轮次)。
- 解释②：global_prime_score 用是否黄金时段(0/1)。
- 验算：objective_weights 指明 data_source 含 time_slots，且"时段全球收视价值"对应 global_prime_score 连续值（0.30–0.73）。选 **①**。

**A4 — P2 旅行负担 D 的归一化基准**：题面"三项先在全部候选组合上 min-max 归一化再加权"。
- 解释①：对 distance/time/timezone 三项，分别在**该队本轮所有合法候选 (起点,场馆) 组合**上取 min-max；R1 用 team_to_venue 全 16 个，R2/R3 用 venue_to_venue 从上一轮合格候选场馆出发到本轮场馆。
- 解释②：在全部 48×16 或 16×16 组合上全局归一化。
- 验算：题面"在全部候选组合上"且 R2/R3 明确"以该队上一轮全部合格候选场馆为起点取平均"，故归一化范围应为**全局所有候选 (起点,终点) 对**（team_to_venue 768 对 / venue_to_venue 256 对），保证不同方案可比。选 **②全局归一化**，每场取该队两候选起点的均值。代码先用全局 min-max 表，再按场次查表。**风险点**：若用①局部归一化，不同场量纲不可比；用②全局归一化符合"统一评价基础"。

**A5 — P2 黄金时段与大容量场馆阈值**：题面"全球时段价值排名前 25%为黄金时段""场馆容量排名前 25%为大容量"。
- 验算：80 时段×25%=20 个；实测 global_prime_score 排第 20 名=0.67，≥0.67 共 20 个（含并列）。16 场馆×25%=4 个：V03(94000)/V08(87523)/V11(82500)/V06(76416)。阈值取**排名截断**（前 20/前 4），并列时取排名前 N。

**A6 — P3 Nᵢ,pre 与 Vᵢ,pre 来源**：题面"设问题二给出的赛前预计现场观众人数为 Nᵢ,pre""设问题一给出的赛前预计转播观看人数为 Vᵢ,pre"。
- 解释①：Nᵢ,pre = P2 输出的 expected_attendance（min(base,capacity)）；Vᵢ,pre = P1 的 72 场 predicted_tv_viewers（result_1_match_prediction）。
- 解释②：用 base_predictions 原始 expected_attendance_base 和 base_predictions 商业价值反推。
- 验算：题面明确"问题二给出""问题一给出"，必须用上游结果。选 **①**（保证链路一致，也是 P3→P2→P1 依赖的体现）。

**A7 — P3 蒙特卡洛 20000 次与晋级规则**：
- 24 场同时按泊松(λᵢ,ₐ,λᵢ,ᵦ)模拟 20000 次，每次按 积分→净胜球→总进球 排名；每组前 2 + 12 组中成绩最好的 8 个第三名晋级；**指标完全相同时等比例处理**（各计 0.5）。
- 实现：每场从 Poisson(λ) 采样进球数 gₐ,gᵦ；累加各组 3 场得积分/净胜球/总进球；排名时若某第三名与临界第三名指标完全相同，则该晋级名额按等比例分配。pₜ=晋级次数/20000。
- 这一步**不可降次**（题面硬性 20000）。

**A8 — P3 静态 vs 动态评价的归一化上下界**：题面"两方案均在更新信息环境下用同一组归一化上下界评价"。
- 解释①：TV/BV/A/C/R 五项的 min-max 上下界，取自**第三轮 24 场在更新环境下、两方案各自候选决策的并集**。
- 解释②：取动态方案候选决策的 min-max。
- 验算：题面"同一利用信息更新环境下重新评价该固定决策…同一组归一化上下界"，意味着静态与动态用**同一套**上下界。取两方案候选决策的**并集**作上下界最稳妥（避免一方用更优边界压低另一方）。选 **①并集**。

**A9 — P3 票价调整约束 Nᵢ(δᵢ)≥0.88Nᵢ(0)**：同交通等级、仅票价不同。即涨价不能使现场需求跌破零调价时的 88%。这是 δ 上界的隐式约束，需在求解时逐场二分/解析求 δ 的可行上限。

**A10 — P4 真实世界杯规模差异**：真实世界杯 32 队 8 组（如 2022/2018/2014）vs 本题 48 队 12 组。
- 处理：指标用**人均/场均/比例**形式标准化（如场均旅行距离、黄金时段覆盖率、场馆利用率），并在论文说明规模折算方法。actual_schedule.csv 按 actual_schedule_template 采集真实赛程。

### 快速验算与递进性检查

- **P2 可行性**：80 时段 broadcast_capacity 合计 182 ≥ 72 场需求；16 场馆 min 2 / max 8，总容量 16×8=128 ≥72，16×2=32 ≤72（满足下界需恰当分配）；required_level=4 的 5 场需 V03/V07/V08/V09/V11（共 5 个 level≥4 场馆）承办——可行但紧张，5 场 level-4 比赛需分散到不同场馆/日。约束可行域非空。
- **递进性检查**：P3 在更新信息下重优化，目标 Z₃ 应 ≥ 静态净效益（动态利用更多信息）。若动态劣于静态，检查是否约束写反或搜索未收敛（norms 防错：动态方案候选集 ⊇ 静态固定决策，故动态最优 ≥ 静态）。
- **P3→P2 依赖**：Nᵢ,pre、Vᵢ,pre 必须从 P2/P1 结果读入，不得在 P3 重新预测。

### 最终采用的解释

A1=①换算百万；A2=①min(base,cap)；A3=①四乘积；A4=②全局归一化（每场取两队均值）；A5=排名截断前20/前4；A6=①上游结果；A7=20000次蒙特卡洛+等比例；A8=①并集上下界；A9=δ隐式约束；A10=人均/比例标准化。

### 绘制的图像和对比表格

| 图/表 | 类型 | 回答的问题 |
|---|---|---|
| P1 特征-转播观看相关性热力图 | 热力图 | 哪些特征与 tv_viewers 强相关 |
| P1 预测值 vs 真实值（train CV）散点图 | 散点图 | 预测精度 |
| P1 特征重要性条形图 | 条形图 | 模型主要驱动特征 |
| P1 72 场预测分布（按轮次/分组）箱线图 | 箱线图 | 72 场预测分布差异 |
| P2 各指标贡献分解表 | 表 | Z₂ 八项分项贡献 |
| P2 场馆/时段使用热力图（场馆×日期） | 热力图 | 资源分配是否均衡 |
| P2 旅行负担/公平性/风险雷达图 | 雷达图 | 多目标权衡 |
| P2 算法收敛曲线 | 折线图 | 启发式收敛性 |
| P3 静态 vs 动态净效益对比图 | 分组柱状 | 动态改善幅度 |
| P3 蒙特卡洛晋级概率分布 | 直方图 | 晋级形势 |
| P3 风险分解（无激励/默契/综合）堆叠图 | 堆叠柱 | 风险结构 |
| P4 真实 vs 优化赛程指标雷达对比 | 雷达图 | 优化方案优势 |
| P4 旅行/休息/黄金时段覆盖对比表 | 表 | 逐指标差异 |

## 5. 问题一模型 · 转播观看人数预测

**目标**：在 historical_matches train(560) 上训练回归模型预测 tv_viewers（百万人），对 test(140) 输出预测 + 对 72 场小组赛输出预测。

**输入**：historical_matches(train) 全字段 + teams(球队属性 join)。test 集有除 tv_viewers 外全部字段。

**预测对象**：ŷ = tv_viewers（百万人）。

**特征工程**（赛前可获得，防泄露——goals/xg/shots/possession 是赛后，**test 集虽含但属"已知参考"**，需判断）：
- 球队实力类：elo_a/elo_b、strength_rank_a/b、（join teams）market_value/fan_base_index/star_index。
- 比赛类型类：competition、stage、neutral。
- 悬念类：由 odds_a/draw/b 反推隐含概率 p_a=1/odds_a/(Σ1/odds)，悬念 = 1−max(p_a,p_b) 或 entropy；strength_gap=|elo_a−elo_b|。
- 时区区域类：join teams.home_timezone_region，编码 Americas/Europe/Africa/Asia。
- 球迷基础：fan_base_a+b、market_value_a+b。
- 赛前可得性：odds/elo/rank/fan_base/competition/stage/neutral/时区 **赛前可知**；goals/xg/shots/possession/attendance **赛后才知**——**对 test 与 72 场预测只能用赛前特征**（attendance 在 test 有但属赛后，禁用）。这是防数据泄露关键。
  - 注：题面称 test 集这些字段为"组委会保留真实值用于评价"，预测时仍只用赛前特征。72 场小组赛用 base_predictions 的 expected_goals/uncertainty/attractiveness 作赛前代理特征。

**模型选择**：
- 基线：岭回归/Lasso（线性，可解释）。
- 主模型：梯度提升回归（GradientBoosting/XGBoost 或 sklearn HistGradientBoosting），处理非线性、特征交互，R² 通常更高。
- 评估：5 折 CV（按 date 分组防时序泄露）+ train 上拟合优度。test 无真值，仅交预测。
- 超参：网格/随机搜索在 train 内 CV 选；不在 test 调参。
- 随机种子固定。

**目标/评价**：MSE=(1/n)Σ(ŷ−y)²，n=140。最小化 MSE。

**约束**：预测值物理边界 ≥0；不可用赛后特征；train/test 划分固定。

**输入输出**：
- 输入：historical_matches + teams。
- 输出：result_1_test_prediction.csv(match_id_test, predicted_test_tv_viewers)、result_1_match_prediction.csv(match_id, team_a, team_b, predicted_tv_viewers)。

**代码实现要点**：
- 单位换算：tv_viewers ÷1e6 → 百万人（A1）。train MSE 在百万人单位下计算。
- 防泄露特征清单白名单化。
- 72 场预测：用 groups_matches + teams join 构造同口径赛前特征；可参考 base_predictions.uncertainty/attractiveness 作辅助特征但模型主体在 historical 训练。

**结果校验**：CV MSE 与 R²；预测值分布与 train 分布量级一致；72 场预测无负值/异常。

## 6. 问题二模型 · 场馆与开球时段协同优化

**目标**：为 72 场分配 venue_id∈{V01..V16}、slot_id∈{S011..S204}，最大化 Z₂。

**决策变量**：x_{m,v,s}∈{0,1}，比赛 m 分配场馆 v、时段 s（每场恰好一馆一时段）。

**目标函数**：
```
Max Z₂ = 0.25T̂ + 0.25B̂ + 0.15U + 0.10H − 0.08Ĉ − 0.07D̂ − 0.06F − 0.04R̂
```
（带 ^ 为 min-max 归一化到[0,1]的项；U、H 本身在[0,1]不归一化，F、R 本身在[0,1]不归一化；T/B/C/D 需归一化。题面"部分指标转换以统一尺度属于[0,1]"——对 T/B/C/D 四项做 min-max，U/H/F/R 已是[0,1]原值。）

各分项（归一化前）：
- T_m = base_ticket_price(round_m) × expected_attendance_m；expected_attendance_m = min(base_predictions.expected_attendance_base_m, venue.capacity_v)。
- B_m = predicted_tv_viewers_m(P1) × broadcast_unit_value_usd(round_m) × global_prime_score_s × sponsor_weight(round_m)。
- U_m = uncertainty_index_m（base_predictions）。
- H_m = attractiveness_index_m / 100。
- C_m = setup_cost_v + operation_cost_v + (10万 × required_security_level_m × security_cost_index_v)；注 10 万美元=100000 USD（单场安保成本=100000×req_level×cost_idx，单位 USD；setup_cost 表为 musd 百万美元需 ×1e6 统一到 USD，或全程用百万美元统一）。**单位口径**：T/B 为 USD 量级，C 的 setup_cost_musd 是百万美元，需统一（建议全部换算到 USD 或全部百万美元，代码中显式标注）。
- D_m = 0.5·d̂ + 0.3·t̂ + 0.2·tẑ，d̂/t̂/tẑ 为 distance/travel_time/timezone_diff 在全局候选组合上的 min-max 归一化值；R1 用 team_to_venue，R2/R3 用 venue_to_venue（起点=该队上一轮全部合格候选场馆，取均值）。
- F = 0.5×(黄金时段次数极差/3) + 0.5×(大容量场馆次数极差/3)；极差=全队中最大次数−最小次数；除以 3 因每队最多 3 场。**F 是方案级指标**（非单场），归一化基准"方案内 min-max"——但 F 本身已是[0,1]标量，无需再归一化。
- R_m = 0.5·climate_risk_v + 0.3·(expected_attendance_m/venue.capacity_v) + 0.2·(required_security_level_m/venue.security_level_v)。

**归一化**：T/B/C/D 进目标函数前在**全部候选(比赛,场馆,时段)组合**上 min-max；max=min 记 0。F、R、U、H 已[0,1]。

**约束**（题面规则 a–f）：
1. 每场恰好一馆一时段。
2. 同一场馆同一 UTC 时刻 ≤1 场（同场馆同时段不撞）。
3. 同一球队按 R1→R2→R3 顺序参赛；同组相邻两轮 UTC 开球时差 ≥60 小时（前场开球到后场开球）。
4. 场馆单日承办 ≤ max_matches_per_day_v；总承办 ∈ [min_total_matches_v, max_total_matches_v]。
5. 全球黄金时段(前 20 时段)：任意两队获得黄金时段次数差 ≤2（公平）。
6. 安保：venue.security_level_v ≥ match.required_security_level_m（候选资格）；第三轮每个参考日内 required_level≥3 的场次数 ≤ dynamic_resource_limits.high_security_capacity（该日）。
7. 同一开球时刻(UTC)比赛数 ≤ time_slots.broadcast_capacity_s。
8. 同组同轮两场比赛不同时段（隐含：同组同轮 2 场不能撞同时段，因同组球队轮次推进需错开）。

**求解方法**：
- 规模：72 场 × 16 馆 × 80 时段 = 92160 组合，0-1 整数规划。精确 MILP（PuLP/CBC 或 OR-tools CP-SAT）变量约 92160 个二进制 + 约束，**可能可行但内存/时间紧**。
- 策略：优先尝试 **CP-SAT 精确/启发式混合**——用 CP-SAT 设时间限制(如 300s)求较优解；若不行退 **贪心+局部搜索/模拟退火**：
  - 贪心初始：按轮次顺序，每场选当前最优(场馆,时段)满足约束。
  - 邻域：单场换馆/换时段、两场交换(馆,时段)。
  - 目标：Z₂；多起点+固定种子。
- 公平性 F 与全局相关，需在评估完整方案时计算。
- 报告多起点稳定性（≥5 次取最优/均值）。

**输入**：P1 的 result_1_match_prediction + 全部 P2 表（venues/time_slots/distance_matrix/ticket_broadcast/base_predictions/security_requirements/groups_matches/objective_weights）。

**输出**：result_2_group_schedule.csv（20 列按模板：match_id, group_id, round_in_group, team_a, team_b, venue_id, slot_id, city, country, reference_date, reference_kickoff_time, local_datetime, utc_datetime, required_security_level, expected_attendance, expected_tv_viewers, ticket_revenue_usd, broadcast_value_usd, travel_cost_index, fairness_penalty, risk_index, total_objective_value）。**total_objective_value 仅首行填 Z₂，余空。**

**代码实现要点**：
- 统一单位（USD 或百万美元，全程一致并标注）。
- UTC 时差计算用 reference_utc_time（datetime 比较）。
- 60 小时约束按 round_in_group 与 group_id 找同组同队相邻轮次。
- 归一化用全部候选组合预计算 min/max 表。
- 约束回代检查：每条约束输出值/边界/是否违反。

**结果校验**：所有约束逐一回代通过；Z₂ 与分项贡献表；多起点稳定性；与贪心基线对比证明启发式有效。

## 7. 问题三模型 · 第三轮动态资源优化

**目标**：第三轮 24 场赛程固定（P2 已定场馆/时段），仅用前两轮反馈重配资源（转播优先级+安保等级+交通等级+票价调整 δ），最大化 Z₃；并对比静态 vs 动态。

**决策变量**（每场 i∈I₃，24 场）：broadcast_priority∈{1,2,3}、security_level∈[req, venue.security_level]、transport_level∈{1,2,3}、δᵢ∈[−0.15, +0.20]（受 dynamic_resource_limits 日上下限）。

**公式链**（逐式实现，14 条，严格按题面）：

1. **竞技状态** Sₜ = 0.45·Pₜ/(3Gₜ) + 0.35·[0.5+0.5·tanh(((xGFₜ−xGAₜ)/Gₜ)/1.25)] + 0.20·exp(−0.55·RCₜ/Gₜ)，Gₜ=球队 t 前两轮已赛场数(=2)，Pₜ=积分，xGF/xGA=累计预期进球/失球，RC=红牌。Sₜ∈[0,1]。
2. **伤病** hₜ = 球队 t 前两轮所涉比赛 injury_impact_level 均值，clip[0,3]。
3. **更新进球均值** Δᵢ = 0.32(Sₐ−Sᵦ) − 0.055(hₐ−hᵦ)；λᵢ,ₐ=clip[λ₀,ᵢ,ₐ·exp(Δᵢ−0.04hₐ), 0.15, 4.50]，λᵢ,ᵦ 对称（Δ 取负、hᵦ）。λ₀ 来自 base_predictions.expected_goals_a/b。
4. **蒙特卡洛**：24 场同时按 Poisson(λᵢ,ₐ), Poisson(λᵢ,ᵦ) 模拟 **20000 次**；每次按 积分→净胜球→总进球 排名；每组前 2 + 12 组成绩最好 8 个第三名晋级；指标完全相同等比例处理。pₜ=晋级次数/20000。
5. **晋级重要性** Qᵢ = [4pₐ(1−pₐ)+4pᵦ(1−pᵦ)]/2，Qᵢ∈[0,1]。
6. **反馈系数**：对球队 t 每场前两轮 m，r_m^att=clip(实际现场/赛前预计现场,0.60,1.50)、r_m^tv=clip(实际转播/赛前预计转播,0.60,1.50)；球队两场取均值再 clip[0.75,1.25] 得 rₜᵃ、rₜᵇ；fᵢᵃ=√(rₐᵃ·rᵦᵃ)，fᵢᵇ=√(rₐᵇ·rᵦᵇ)。
   - 赛前预计现场=base_predictions.expected_attendance_base（该场前两轮的赛前基准）；赛前预计转播=该场 P1 模型预测（前两轮也是 72 场之一，有 P1 预测）。
7. **更新吸引力** Sᵢ=(Sₐ+Sᵦ)/2、Hᵢ=(hₐ+hᵦ)/6、A₀ᵢ=attractiveness_index/100、Fᵢ=clip[(0.5fᵢᵃ+0.5fᵢᵇ−0.75)/0.50, 0,1]；Aᵢ=clip[0.50A₀ᵢ+0.25Qᵢ+0.12Fᵢ+0.08Sᵢ+0.05(1−Hᵢ), 0, 1]。
8. **更新现场需求** Ñᵢ = Nᵢ,pre·fᵢᵃ·(0.88+0.27Qᵢ)·(0.94+0.12Sᵢ)·(1−0.10Hᵢ)；Nᵢ,pre=P2 expected_attendance。
9. **票价调整** 选交通等级 mᵢᵈ（读 demand_multiplier）；Nᵢ(δᵢ)=min{Kᵢ, Ñᵢ·mᵢᵈ·(1+δᵢ)^(1/εᵢ)}；TVᵢ=Pᵢ₀(1+δᵢ)Nᵢ(δᵢ)；Kᵢ=venue.capacity，Pᵢ₀=base_ticket_price(R3)，εᵢ=price_elasticity(R3)；约束 Nᵢ(δᵢ)≥0.88Nᵢ(0)（同交通等级仅 δ 不同）。
10. **更新转播需求** Ṽᵢ = Vᵢ,pre·fᵢᵇ·(0.87+0.30Qᵢ)·(0.90+0.20Aᵢ)·(1−0.06Hᵢ)；Vᵢ,pre=P1 predicted_tv_viewers；选转播优先级 mᵢᵇ（读 demand_multiplier）；Vᵢ=Ṽᵢ·mᵢᵇ；BVᵢ=uᵢ·Vᵢ，uᵢ=broadcast_unit_value(R3)。
11. **无激励风险** Rᵢ,noeff = 0.5(2pₐ−1)² + 0.5(2pᵦ−1)²。
12. **默契风险** 由同一次模拟统计 pₐ|平=P(a晋级|平局)、pᵦ|平、pₐ|a胜、pᵦ|b胜；Dᵢ=min(pₐ|平, pᵦ|平)；Gᵢ=0.5max(pₐ|a胜−pₐ|平,0)+0.5max(pᵦ|b胜−pᵦ|平,0)；Rᵢ,coll=clip[Dᵢ·(1−clip(Gᵢ,0,1))·(1−0.35Rᵢ,noeff), 0, 1]。
13. **动态安保需求** Oᵢ=clip(Ñᵢ/Kᵢ,0,1)；dᵢ=clip[0.45dᵢ₀+0.25Oᵢ+0.15Aᵢ+0.15(Rᵢ,noeff+Rᵢ,coll)/2, 0, 1]；dᵢ₀=security_demand_score（security_requirements）。选安保等级 mᵢˢ（读 risk_multiplier）；Rᵢ=0.40Rᵢ,noeff+0.40Rᵢ,coll+0.20dᵢ·mᵢˢ。
14. **成本** Cᵢ=cᵢᵇ+cᵢˢ+cᵢᵈ（所选三等级 unit_cost_index 之和）。

**目标**：
```
Max Z₃ = Σ_{i∈I₃} [0.35TVᵢ* + 0.35BVᵢ* + 0.10Aᵢ* − 0.10Cᵢ* − 0.10Rᵢ*]
```
（*为 min-max 归一化，max=min 记 0；上下界取静态+动态候选决策并集，A8）。

**静态 vs 动态**：
- 静态：用赛前预测（Nᵢ,pre、Vᵢ,pre、A₀ᵢ、赛前风险：无激励=1−uncertainty_index、默契=0）定资源并固定；前两轮结束后保持决策不变，但在**更新信息环境**下用同一归一化上下界重新评价得 static_net_value。
- 动态：用更新信息重优化得 dynamic_net_value。
- improvement_rate = (dynamic−static)/|static|，分母 0 记空。

**约束**：
- 安保等级 ∈ [required_security_level, venue.security_level]。
- 每日 high_broadcast_capacity / high_security_capacity / enhanced_transport_capacity / daily_resource_budget_index ≤ dynamic_resource_limits 上限（按 reference_date）。
- δ ∈ [−max_discount, +max_increase]（daily）。
- Nᵢ(δᵢ) ≥ 0.88Nᵢ(0)。

**求解方法**：
- 24 场各自有 4 类决策（b:3×s:4×t:3×δ:连续）。δ 连续使每场是混合整数非线性。
- **分解策略**：因每场目标可加（Z₃=Σ 分场贡献）、约束除每日容量耦合外基本分场独立——对每日容量耦合用 **拉格朗日松弛/贪心+容量调整**，分场枚举离散决策(3×4×3=36 组合)×δ 一维优化（δ 在约束下单调/解析或二分），选分场最优；再跨场调整满足每日容量。
- 静态方案：固定决策=broadcast=1/security=req/transport=1/δ=0 的赛前最优（或赛前优化）。
- 蒙特卡洛 20000 次**预计算一次**（pₜ、pₐ|平 等统计量）供所有场共用，固定种子。

**输入**：P2 result_2（Nᵢ,pre、场馆、时段、reference_date）+ P1 result_1（Vᵢ,pre）+ base_predictions + live_group_results + security_requirements + dynamic_resource_limits/costs + ticket_broadcast。

**输出**：result_3_dynamic_strategy.csv（21 列按模板：match_id, group_id, team_a, team_b, updated_p_team_a_advance, updated_p_team_b_advance, updated_expected_attendance, updated_expected_tv_viewers, stakeless_risk, collusion_risk, updated_attractiveness, recommended_broadcast_priority, recommended_security_level, recommended_transport_level, recommended_ticket_adjustment, updated_ticket_revenue_usd, updated_broadcast_value_usd, resource_cost_index, risk_exposure_index, static_net_value, dynamic_net_value, improvement_rate）。

**代码实现要点**：逐式实现并加注释标注公式序号；蒙特卡洛向量化（numpy 批量采样 20000×24）；clip 用 np.clip；逐场决策枚举+δ 一维优化；每日容量约束回代检查。

**结果校验**：Sₜ∈[0,1]、λ∈[0.15,4.50]、Aᵢ∈[0,1]、R 各项∈[0,1]；蒙特卡洛收敛性（不同种子 pₜ 标准差<0.01）；动态≥静态；约束全通过。

## 8. 问题四模型 · 实际赛程综合评价

**目标**：选一届真实世界杯（2022 卡塔尔，32 队 8 组，每队 3 场小组赛），采集实际赛程，用 P2 同口径指标评价实际 vs 本队优化赛程。

**输入**：真实赛程（官网/可靠来源采集，按 actual_schedule_template）+ P2 指标定义/标准化/权重 + 本队 P2 优化赛程（result_2）。

**指标对比维度**（题面）：旅行距离、休息时间、跨时区次数、场馆利用率、容量匹配、黄金时段覆盖、预计观众、票务与转播价值、资源公平性、风险。

**标准化**（A10）：规模不同（真实 32 队 8 组 48 场 vs 本题 48 队 12 组 72 场），用**人均/场均/比例**：
- 场均旅行距离、场均休息时间、跨时区次数/场、场馆利用率（已用场次/总容量）、容量匹配度（观众/容量均值）、黄金时段覆盖率（黄金时段场数/总场数）、场均预计观众、场均票务/转播价值、公平性极差均值、场均风险。
- 对真实赛程需映射到本题的场馆/时段体系（或用真实场馆/时区重算同定义指标，说明口径）。

**采集**：写采集程序（requests/BeautifulSoup 或手工整理真实赛程数据，标注 source_url、retrieval_date）。2022 卡塔尔世界杯小组赛 48 场赛程为公开数据。若网络受限，用本地已知数据手工构建并附采集程序与来源说明。

**输出**：actual_schedule.csv（按 actual_schedule_template，含 match_id/competition/stage/group_id/round/teams/venue/city/country/date/kickoff/utc/goals/source_url/retrieval_date）+ result_4_schedule_comparison.csv（按 result_4_template：indicator_name, indicator_category, actual_schedule_value, optimized_schedule_value, absolute_difference, relative_improvement, preferred_direction, evaluation_result）。

**可视化**：真实 vs 优化雷达图、逐指标对比表、旅行/休息分布对比。

**结果校验**：实际值来源可追溯；标准化口径说明；稳健性分析（不同真实赛事/不同标准化方向结论是否一致）。

## 9. 灵敏度分析与检验方案

- **P1**：特征重要性稳定性（不同种子）；移除关键特征后 MSE 变化；超参敏感性。
- **P2**：权重灵敏度（objective_weights ±20%）；多起点稳定性（≥5 次 Z₂ 标准差）；约束松弛分析。
- **P3**：蒙特卡洛种子稳定性（pₜ 标准差）；权重灵敏度；静态/动态对比的稳健性。
- **P4**：不同真实赛事（2022 vs 2018）结论一致性；标准化方向敏感性。

## 10. 代码实现任务清单

| 任务 | 输入 | 输出 | 方法 | 校验 |
|---|---|---|---|---|
| 公共 | C题_数据附件.xlsx | data_loader.py(14 sheet DataFrame) | openpyxl/pandas，行列校验 | sheet 数=14，行列数与实测一致 |
| P1 | historical_matches+teams | result_1_test_prediction.csv, result_1_match_prediction.csv | 梯度提升回归(赛前特征白名单)+岭回归基线，5 折时序 CV | CV MSE/R²，预测分布，无泄露 |
| P2 | P1 结果+venues/time_slots/distance_matrix/ticket_broadcast/base_predictions/security_requirements/groups_matches | result_2_group_schedule.csv(20列)+Z₂ | CP-SAT 精确(限时) / 贪心+模拟退火；全局 min-max 归一化 | 约束逐一回代，多起点稳定性，分项贡献表 |
| P3 | P2+P1 结果+base_predictions+live_group_results+security_requirements+dynamic_resource_limits/costs+ticket_broadcast | result_3_dynamic_strategy.csv(21列)+Z₃ | 逐式14条公式+20000次蒙特卡洛+分场枚举δ优化+每日容量耦合调整 | 各量纲范围，MC 收敛，动态≥静态，约束回代 |
| P4 | 真实赛程(采集)+P2 指标定义+result_2 | actual_schedule.csv+result_4_schedule_comparison.csv | 网络采集/手工整理，同口径指标+人均比例标准化 | 来源可追溯，稳健性分析 |
| 可视化 | 各问题结果 | figures/*.pdf | matplotlib（中文支持） | 每图回答一问题，风格统一 |
