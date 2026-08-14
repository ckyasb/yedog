# 方案

要依次调用这些 skill，按照里面要求完成任务。

用户偏好：
- 排版引擎：Typst（环境就绪 typst 0.15.1，brief 第八节已给策联杯适配方案）
- 竞赛类型：策联杯（2026 年度"策联杯"数学建模精英联赛，C 题；规则近似国赛但**不要目录页**、**附录需含可运行源代码与 AI 工具使用声明**）
- 论文语言：中文
- 子问题数量：已知 4 个（P1 转播观看人数预测 / P2 场馆与开球时段协同优化 / P3 第三轮动态资源优化 / P4 实际赛程综合评价）

## 赛题概要

题目：基于大数据驱动的足球世界杯赛事预测与赛程资源协同优化。
模拟赛事：48 队 → 12 小组（A–L）→ 每组 4 队单循环 → 72 场小组赛。
核心链路：历史数据预测转播观看人数 → 排定 72 场的场馆与开球时段 → 第三轮动态资源调整 → 与真实世界杯赛程对比。

| # | 问题 | 主要产物 |
|---|------|----------|
| 1 | 转播观看人数预测（historical 700 条，train 560/test 140） | result_1_test_prediction.csv, result_1_match_prediction.csv |
| 2 | 72 场场馆+开球时段协同优化 Max Z₂ | result_2_group_schedule.csv |
| 3 | 第三轮 24 场动态资源优化 Max Z₃，静态 vs 动态对比 | result_3_dynamic_strategy.csv |
| 4 | 真实世界杯赛程采集 + P2 指标综合评价 | actual_schedule.csv, result_4_schedule_comparison.csv |

完整题面、数据结构、公式链见 `CONTEST_BRIEF.md`（勿重复整理，直接复用）。

## workflow

   step      skills
1. 赛题分析与建模设计 - `2analysis-modeling`
2. 编程实现和图表生成 - `3coding-visual`
3. 流程与架构图绘制 - `4drawio`
4. 竞赛论文撰写 - `5writing`
5. 验证和验收 - `6verity`

## 阶段产物约定

```
.
├── plan.md                      # 本文件
├── todo.md                      # 待办事项
├── reports/
│   ├── ANALYSIS_MODELING_REPORT.md   # 2analysis-modeling 产出
│   ├── RESULTS_REPORT.md             # 3coding-visual 产出（含各问题数值结论，供论文引用）
│   ├── DRAWIO_REPORT.md              # 4drawio 产出
│   └── VERIFY_REPORT.md             # 6verity 产出
├── code/                        # 3coding-visual 产出
│   ├── problem1.py ~ problem4.py     # 按子问题组织，数量随题目动态调整
│   ├── utils.py                      # 公共数据加载/IO/归一化工具
│   └── data_loader.py                # 14 sheet 加载与校验
├── results/                     # 各 CSV 结果
├── figures/                     # 数据图 + 非数据图 PDF
│   ├── *.pdf
│   └── *.drawio
└── paper/
    ├── main.typ                  # Typst 主文件（cumcm 模板适配策联杯：删目录页 + 加 AI 声明）
    └── sections/                 # 各节 .typ
```

## 关键工程约束（贯穿所有阶段）

- **数据单一来源**：`C题_数据附件.xlsx` 14 个 sheet。所有代码经 `data_loader.py` 统一加载并校验行列数，杜绝列名漂移。
- **结果文件严格按模板**：`output_result/result_*_template.csv` 为列名与顺序的权威定义，产出文件必须逐列对齐。
- **公式严格性**：P3 的 14 条公式链（Sₜ, λ 更新, 蒙特卡洛 20000 次, Aᵢ/Ñᵢ/Ṽᵢ 更新, 风险 Rᵢ 等）必须**逐式实现**，不得近似；每条公式在 RESULTS_REPORT 中标注对应代码行。
- **可复现性**：固定随机种子；蒙特卡洛 20000 次必须实跑（不可降次）；所有数值结论可由代码重新生成。
- **归一化约定**：进目标函数前 min-max 到 [0,1]，max=min 记 0（与 brief 一致）。
- **论文数值不编造**：5writing 的所有数值必须来自 RESULTS_REPORT.md 或已生成图表数据。

## 风险控制

- P2 是组合优化（72 场 × 16 场馆 × 80 时段），可能需启发式（遗传/模拟退火/贪心+局部搜索）；3coding-visual 阶段先评估精确求解可行性，再选算法。
- P4 需采集真实世界杯赛程（官网），若采集受阻则用本地已知数据手工构建并标注来源与采集程序。
- 4drawio 的 PDF 导出受 drawio 未安装影响可跳过，核心流程不依赖。
- typst 仅在 HOME 下可用（/tmp 不可用），编译须在 `~/yegou/C题` 下执行。

## 策联杯格式硬约束（5writing 必须遵守）

1. 第一页摘要专用页（标题+关键词，≤1 页，页码从 1 开始）。
2. 第二页起正文，**不要目录**，正文 ≤ 30 页。
3. 正文后附录页数不限：含支撑材料文件列表、全部可运行源代码、AI 工具使用声明。
4. 全文不得出现参赛者身份与学校信息。
5. 参考文献按科技论文规范，正文引用处标注。
6. 提交：参赛论文 PDF（≤20MB）+ 支撑材料 RAR/ZIP（≤20MB）。
7. 用了 AI 工具：参考文献前设"AI 工具使用声明"，支撑材料含 `AI 工具使用详情.pdf`。
