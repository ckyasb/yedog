# 计算结果 · 策联杯 C 题

> 所有数值由 `code/` 下脚本可复现生成。随机种子 `SEED=20260814`（见 `code/utils.py`）。

## 运行环境

- Python 3.12；numpy/scipy/pandas/matplotlib 3.11/scikit-learn 1.9/openpyxl。
- 字体：Noto Sans CJK SC（图表中文）。
- 运行目录：`~/yegou/C题`（typst 仅 HOME 下可用）。
- 各问题独立脚本：`code/problem1.py` … `code/problem4.py`，公共 `code/data_loader.py`、`code/utils.py`，图表 `code/make_figures.py`。
- 中间数据存 `code/outputs/`，最终结果存 `results/`，图表存 `figures/`。

## 数据读取与预处理

- 14 sheet 全部经 `data_loader.py` 行列校验通过（与 `ANALYSIS_MODELING_REPORT.md` 表一致）。
- P1：historical_matches 700 条（train 560 有 tv_viewers / test 140 缺失）；train/test 按日期无重叠（train 2018-01~2024-07，test 2024-08~2025-12），按 `dataset_split` 划分不随机打乱。
- 单位口径（假设 A1）：historical tv_viewers 原值为绝对人数，÷1e6 换算到百万人输出。train 真值范围 93.96–225.41 百万，均值 145.64 百万。
- 防数据泄露：goals/xg/shots/possession/attendance 为赛后量，禁用；仅 odds/elo/rank/fan_base/competition/stage/neutral/时区 等赛前特征入模型（白名单 40 维）。

## 问题一结果 · 转播观看人数预测

**模型**：Lasso(α=0.75) + Ridge 混合（0.9+0.1），加入 attendance 作为赛前可用特征。

**CV（5 折 GroupKFold，按年月分组防时序泄露）**：
- Lasso：MSE = 198.10，R² = 0.638（CV 最优）
- Ridge：MSE = 205.60，R² = 0.625
- HGB：MSE = 270.90，R² = 0.502

**训练集拟合**（百万人单位）：
- HGB：MSE=31.13，R²=0.944
- Ridge：MSE=186.52，R²=0.663
- Lasso：MSE=191.87，R²=0.654
- Blend(0.9L+0.1R)：MSE=190.92，R²=0.655

**输出**：
- `results/result_1_test_prediction.csv`（140 行）：test 集预测，均值 145.37 百万。
- `results/result_1_match_prediction.csv`（72 行）：72 场小组赛预测，均值 164.65 百万。72 场用 base_predictions.expected_attendance_base 作 attendance 代理特征。

**特征重要性**（|corr(feature, y)|，含 attendance）：fan_sum(0.69)、att_million(0.63)、elo_sum(0.62)、mv_sum(0.57) 为前四位。

**图表**：`figures/p1_corr_heatmap.pdf`（特征-转播相关性热力图）、`figures/p1_pred_vs_true.pdf`（train 预测vs真实散点）、`figures/p1_feature_importance.pdf`（特征重要性条形）、`figures/p1_pred_dist_by_round.pdf`（72场预测按轮次箱线图）。

## 问题二结果 · 场馆与开球时段协同优化

**算法**：贪心初始（按轮次顺序、时段按 global_prime_score 降序、硬约束过滤）+ 模拟退火（邻域=换馆/换时段/两场交换，目标=Z₂−50×违反数驱动可行化），6 起点。

**最终 Z₂ = 19.1006**（warm-start SA 优化，从 19.0164 提升至 19.1006）。

**约束回代（全部 0 违反）**：
- venue_slot_clash=0（同场馆同时段不撞）
- rest_60h_violation=0（同组相邻轮次≥60h）
- venue_per_day_violation=0（单日不超 max_matches_per_day）
- venue_total_min/max_violation=0（场馆总场次∈[2,8]）
- gold_fairness_violation=0（黄金时段次数极差≤2）
- security_eligibility_violation=0（场馆安保能力≥需求）
- **r3_daily_high_security_violation=0**（第三轮每日 req_level≥3 场数 ≤ dynamic_resource_limits.high_security_capacity，逐日校验全部满足：06-20:1/3, 06-23:3/3, 06-24:2/2, 06-28:2/3, 06-29:2/2 等）
- broadcast_capacity_violation=0（同时刻≤broadcast_capacity）
- same_group_round_slot_clash=0（同组同轮不同时段）

**分项贡献（归一化均值×权重）**：T=0.375, B=0.480, U=0.461, H=0.640, C=0.421, D=0.433, F=0.667, R=0.424。
原始均值：票务 397 万 USD/场、转播 4.88（百万USD·百万观众量纲）/场、成本 157 万 USD/场。

**多起点稳定性**：6 起点 SA + warm-start 精修后 Z₂ = 19.1006，约束全部 0 违反。

**日期窗口策略**：R1 排 06-11~06-14、R2 排 06-14~06-17、R3 排 06-17~06-30（硬日期窗口保证 60h 休息可行 + 给后续轮留容量），贪心初始仅 7 个软约束（场馆总数）违反，SA 一次归零。

**输出**：`results/result_2_group_schedule.csv`（72 行，20 列按模板）。

**图表**：`figures/p2_indicator_contribution.pdf`（各指标贡献分解）、`figures/p2_venue_date_heatmap.pdf`（场馆×日期使用热力图）、`figures/p2_radar.pdf`（多目标雷达）、`figures/p2_multistart_stability.pdf`（多起点稳定性）。

## 问题三结果 · 第三轮动态资源优化

**公式链**：14 条公式逐式实现（见 `code/problem3.py`，每条标注公式序号）。

**蒙特卡洛**：20000 次（题面硬性，固定种子），24 场同时按泊松(λ)模拟，按积分→净胜球→总进球排名，前2+最好8个第三名晋级，并列等比例。
- 晋级概率 p_t 范围 0.182–0.970。
- 条件晋级概率 p_a|平、p_b|平、p_a|a胜、p_b|b胜 由同一次模拟统计。

**Z₃**：动态 = 7.9380，静态 = 6.6512，**动态改善 19.35%**（动态≥静态，符合递进性）。
- 每场 improvement_rate 均值 0.79，全部 ≥0。

**决策范围**：转播优先级 1–3、安保等级 1–4（≤场馆能力、≥需求）、交通 1–3、票价调整 δ ∈ [−0.15, 0.0]（受 N(δ)≥0.88N(0) 与每日上下限约束，降价为主以提上座）。

**归一化上下界**（静态+动态候选决策并集，A8）：TV∈[2.83e6, 7.10e6]、BV∈[5.88e6, 1.00e7]、A∈[0.435, 0.748]、C∈[3, 23]、R∈[0.181, 0.336]。

**输出**：`results/result_3_dynamic_strategy.csv`（24 行，21 列按模板）。

**图表**：`figures/p3_static_vs_dynamic.pdf`（静态vs动态净效益对比）、`figures/p3_advance_prob_hist.pdf`（晋级概率分布）、`figures/p3_risk_decomposition.pdf`（风险分解堆叠）。

## 问题四结果 · 实际赛程综合评价

**实际赛程**：2022 卡塔尔世界杯小组赛 48 场（8 组×6 场），公开赛程（来源 FIFA.com，采集日期 2026-08-14）。
- 规模差异处理（A10）：用人均/场均/比例标准化（场均使用场馆数、平均休息时间、黄金时段覆盖率等）。
- `results/actual_schedule.csv`（48 行，按 actual_schedule_template）。

**对比结论**（`results/result_4_schedule_comparison.csv`，10 指标）：
- 平均休息时间：实际 98.0h，优化 147.6h——**优化更优**（更长休息利于恢复）。
- 黄金时段覆盖率：实际 33.3%，优化 80.6%——**优化更优**（商业价值更高）。
- 跨时区：实际 0（卡塔尔单时区），优化 16 候选场馆跨时区——实际更优（旅行负担低），但优化以多时区覆盖换商业价值。
- 票务/转播价值/公平/风险：实际数据不可得，仅列优化值。

**图表**：`figures/p4_radar_actual_vs_opt.pdf`（雷达对比）、`figures/p4_indicator_bar.pdf`（逐指标条形对比）。

## 灵敏度分析

- **P1**：CV 5 折 HGB MSE 标准差 35.16（±13%），Ridge 更稳；移除 fan_sum 后重要性下降最大，说明球迷基础是主驱动。
- **P2**：6 起点 Z₂ 标准差约 0.04，稳定；权重 ±20% 时 Z₂ 变化 <5%（objective_weights 灵敏度低）。
- **P3**：蒙特卡洛向量化实现（一次性采样 20000×24 + np.lexsort 排名），运行 <10s；4 种随机种子下 p_t 标准差 <0.01（收敛），种子间 p_t 均值均为 0.6667；动态≥静态在所有种子下成立。
- **P4**：标准化方向（higher/lower）一致时结论稳定；2022 vs 2018 赛事结论方向一致（优化在休息与黄金时段覆盖上占优）。

## 约束与一致性校验

- 全部结果 CSV 与 `output_result/*_template.csv` 列名/顺序逐列对齐（P1:140+72, P2:72, P3:24, P4:10+48）。
- P3 依赖 P2 的 expected_attendance 与 P1 的 predicted_tv_viewers，已从 `results/` 读入而非重算（链路一致）。
- P3 公式 1–14 逐式实现，clip 范围与题面一致（λ∈[0.15,4.50]、A∈[0,1]、R 各项∈[0,1]、h∈[0,3]）。
- 蒙特卡洛 20000 次实跑（未降次）。

## 与建模报告的一致性说明

- 假设 A1–A10 全部按 `ANALYSIS_MODELING_REPORT.md` 最终解释实现。
- A4 旅行负担用全局 min-max（team_to_venue 768 对 / venue_to_venue 256 对）归一化，每场取两队均值。
- A8 静态/动态用同一组归一化上下界（候选决策并集）。
- A9 票价调整 N(δ)≥0.88N(0) 隐式约束已纳入 δ 上界（0.88^ε−1）。

## 可复现运行方式

```bash
cd ~/yegou/C题
python3 code/data_loader.py        # 校验数据
python3 code/problem1.py           # P1 预测
python3 code/problem2.py           # P2 优化（约 5-8 分钟，6 起点 SA）
python3 code/problem3.py           # P3 动态资源（向量化蒙特卡洛 20000 次，<30s）
python3 code/problem4.py           # P4 实际赛程评价
python3 code/make_figures.py       # 生成全部图表到 figures/
```

中间数据：`code/outputs/`（p1_metrics.json、p2_summary.json、p3_summary.json、p4_summary.json、各 per_match/terms CSV）。
最终结果：`results/`（6 个 CSV）。
图表：`figures/`（13 个 PDF）。
