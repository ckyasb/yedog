# 方案

要依次调用这些 skill，按照里面要求完成任务。

用户偏好：
- 排版引擎：Typst（环境就绪 typst 0.15.1；与 C 题一致，5writing 用 cumcm 模板删目录页 + 加 AI 工具使用声明以适配策联杯）
- 竞赛类型：策联杯（2026 年度"策联杯"数学建模精英联赛，B 题；格式近似国赛但**不要目录页**、**附录需含可运行源代码与 AI 工具使用声明**）
- 论文语言：中文
- 子问题数量：已知 3 个（Q1 单向出海 / Q2 出海+海返+穿梭联合 / Q3 带时间窗的多日排班）
- 求解算法：**纯启发式、自包含**（不装 OR-Tools；最优性靠下界与 gap 论证）
- Q3 临时任务：**增量插入最大化满足**（先求非临时 3840 条得 T0，再在 ≤T0 下贪心/局部搜索尽量塞入 160 条 temporary）
- 求解强度：**高强度、逼近最优**（ALNS 多起点/多种子，深度局部搜索；单问可放宽到 Q1~3min/Q2~10min/Q3~25min，优先 gap 接近下界，后续阶段进度相应放慢）

## 赛题概要

题目：海上油田人员直升机运载计划编排。
网络：3 机场（A01–A03）+ 52 海上设施（F001–F052，其中 F006/F011/F018/F024/F031/F038/F044/F050 可加油）。
机型：T1(12座/250km·h/3.4kg·km/1000kg/余150)、T2(16/220/2.5/1150/150)、T3(19/190/2.9/1600/200)。
架次：从某机场起飞，连续停靠 1–5 座海上设施后返回**原机场**；人员不得换乘；同站先下后上、座位即时复用；满油起飞，到任意点（含返场）余油 ≥ 安全余油，可在 8 点加满；停靠 ≥10min（加油 ≥20min）；**所有时间向上取整到分钟**。
运输三类：出海（陆→海）、海返（海→陆）、穿梭（海→海）。
优先级：emergency > production > shift > temporary（temporary 可取消）。
数据：distances.csv(55×55 对称，对角 0)、peopleQ1(1600 出海)、peopleQ2(4000=1600出海+1600海返+800穿梭)、peopleQ3(4000 同 Q2 起终点 + 时间窗 + task_type：shift×3440/production×360/temporary×160/emergency×40，时段 2026-08-03~08-10)。
目标（分层/字典序）：先**最小化总飞机使用时间**，再优化人员总在途时间、座位利用率、总燃油、总架次数。

| # | 问题 | 主要产物 |
|---|------|----------|
| 1 | 单向出海运输（1600 条，无时间窗，飞机充足） | data/q1-routes.csv, data/q1-assignments.csv |
| 2 | 出海+海返+穿梭联合（4000 条，无时间窗，飞机充足） | data/q2-routes.csv, data/q2-assignments.csv |
| 3 | 带时间窗多日排班（4000 条 + 24 架飞机配额 + 临时可取消） | data/q3-routes.csv, data/q3-assignments.csv |

完整题面、数据结构、机型参数、架次规则、结果文件格式见 `CONTEST_BRIEF.md`（勿重复整理，直接复用）。

## workflow

   step      skills
1. 赛题分析与建模设计 - `2analysis-modeling`
2. 编程实现和图表生成 - `3coding-visual`
3. 流程与架构图绘制 - `4drawio`
4. 竞赛论文撰写 - `5writing`
5. 验证和验收 - `6verity`

## 阶段产物约定

```
B题/
├── plan.md                      # 本文件
├── todo.md                      # 待办事项
├── reports/
│   ├── ANALYSIS_MODELING_REPORT.md   # 2analysis-modeling 产出
│   ├── RESULTS_REPORT.md             # 3coding-visual 产出（含各问题五项指标，供论文引用）
│   ├── DRAWIO_REPORT.md              # 4drawio 产出
│   └── VERIFY_REPORT.md             # 6verity 产出
├── code/                        # 3coding-visual 产出
│   ├── problem1.py ~ problem3.py     # 按子问题组织
│   ├── utils.py                      # 距离/机型/取整/IO 公共工具
│   ├── data_loader.py                # distances + peopleQ* + 模板加载与校验
│   └── validate.py                   # 结果一致性独立校验（首末同机场、≤5站、refuel合法、pickup<delivery、时刻单调、续航可行、人员全分配）
├── results/                     # 各中间/最终结果快照与指标表
├── figures/                     # 数据图 + 非数据图 PDF
│   ├── *.pdf
│   └── *.drawio
└── paper/
    ├── main.typ                  # Typst 主文件（cumcm 适配策联杯：删目录页 + 加 AI 声明）
    └── sections/                 # 各节 .typ
```

## 关键工程约束（贯穿所有阶段）

- **数据单一来源**：`data/distances.csv` + `peopleQ1/Q2/Q3.csv`。所有代码经 `data_loader.py` 统一加载并校验（行数、列名、地点集合、矩阵对称与对角 0、可加油点集合）。
- **结果文件严格按模板**：`data/q*-routes.csv` / `data/q*-assignments.csv` 为列名与顺序的权威定义。产出时直接覆写模板文件（assignments 已预置全部 person_id 行，需保留行序并填充后四列；temporary 未安排行后四列留空）。
- **取整规则全局一致**：飞行时间 = ceil(距离 / 速度 × 60) 分钟；所有时刻、总时长均向上取整到整数分钟；`utils.py` 提供唯一 `ceil_min`/`flight_minutes` 实现，禁止各处自造。
- **续航可行性**：满油起飞 → 每段扣 `油耗×距离` → 到任意点（含返场）余油 ≥ 安全余油；可在 8 点选 0/1 加满。建模为路径上的"油量资源约束"，`utils.py` 提供 `fuel_feasible(stops, type, refuels)` 单一实现，routes 生成与校验共用。
- **字典序目标**：Q1/Q2 先求总飞机使用时间最优（或接近最优 + gap），再在该解上做座位利用率/油耗/在途时间的局部优化；不把多目标揉成一个标量硬解。
- **可复现性**：固定随机种子；所有数值结论可由代码重新生成；`RESULTS_REPORT.md` 的每个数值标注对应代码/输出文件。
- **论文数值不编造**：5writing 的所有数值必须来自 `RESULTS_REPORT.md`、`results/` 或已生成图表数据。

## 算法路线（纯启发式，自包含）

### Q1 单向出海（无时间窗、飞机充足、每人一程陆→F）
- 抽象：多机场 VRP-with-Deliveries，单边交付，每架次 ≤5 站、单机机型、座位容量、续航约束。
- 流程：
  1. 按"目的设施 + 起飞机场（LAND 用最近机场）"聚类需求。
  2. 构造：对每个簇，用节约算法/sweep 生成候选架次（贪心合并近邻目的设施，直到座位或 5 站或续航受限）。
  3. 机型选择：按簇人数选最小可行机型（座位够 + 续航可行），权衡油耗（kg/km）与使用时间。
  4. 优化：ALNS（destroy: 随机移站/重聚类；repair: 贪心插入 + regret）+ 续航可行性门控（必要时插加油点）。
  5. 下界与 gap：基于"总人公里 / 机型座位数"与"最短返场距离"的下界，报告 gap。

### Q2 出海+海返+穿梭（无时间窗、飞机充足、同架次三类混合）
- 抽象：PDPTW-without-TW（pickup & delivery + transshipment），同架次座位动态复用。
- 流程：
  1. 配对：出海(陆→F) 与海返(F→陆) 若目的/起点相近可拼同一架次往返；穿梭(F→F) 嵌入架次中间段。
  2. 构造：以"往返环"为单位（机场→F1→F2→…→机场），按机上人数时序满足座位容量（先下后上即时复用）。
  3. 优化：ALNS，邻域含"换机场(LAND 任选)""调整停靠序""穿梭嵌入位置"；续航门控同 Q1。
  4. 难点：穿梭人员起点是上一站下机点，强耦合；assignments 的 delivery_stop_order 须为"上机后第一次到终点"序号。

### Q3 带时间窗多日排班（24 架飞机配额 + 周转 + 临时可取消）
- 抽象：多日 PDPTW + Fleet Scheduling + 续航 + 优先级。
- 流程：
  1. **非临时基线**：先排 shift(3440)+production(360)+emergency(40)=3840 条，遵守 06:00–18:00 起飞、≤20:00 返场、不过夜、30min 周转、24 架配额、续航；得总飞机使用时间 **T0**。
  2. **临时增量**：在"总飞机使用时间 ≤ T0"硬约束下，对 160 条 temporary 按"插入增量代价/优先级"贪心 + 局部搜索，逐条评估能否塞入现有架次或新开架次（受配额与时刻约束），最大化满足数。
  3. 时刻建模：每站 arrival/departure 严格满足 `arrival_j = departure_i + ceil(dist/速度)`；首行只填 departure，末行只填 arrival。
  4. 飞机编号：按 `机场-机型-序号`（A01-T2-H03），flight_no 按起飞时刻从 1 连续。

## 下界与最优性论证（2analysis-modeling 须给出，3coding-visual 须计算）

- **总飞机使用时间下界**：
  - 段距下界：每架次至少 A→F→A，贡献 `ceil(2·d(A,F)/v) + 停靠`；按目的设施聚合后求和（考虑一架次最多 5 站与座位的合并节省）。
  - 人次下界：总人公里 /（机型座位数 × 单架次平均距离）给出架次数下界，再乘单架次平均使用时间。
- **gap**：`gap = (启发式解 - 下界)/下界`，作为"接近最优"的证据；不强行宣称全局最优。
- Q3 临时满足数：报告"已满足 / 总数 160"及未满足原因分布。

## 结果校验（3coding-visual 须内置，6verity 复核）

`code/validate.py` 对每个 q*-routes/assignments 逐项检查并打印 PASS/FAIL：
1. routes 首、末记录为同一机场；中间海上设施 ≤5 条；stop_order 从 0 连续。
2. refuel=1 仅出现在 8 个可加油设施；机场行 refuel=0。
3. assignments：pickup_stop_order < delivery_stop_order，同架次；pickup/delivery 与该人员起终点一致（LAND 取架次机场）；delivery 为"上机后首次到终点"序号。
4. 每名人员恰好一行；Q1/Q2 全员已安排；Q3 emergency/production/shift 全填、temporary 保留行（安排或留空）。
5. Q3：arrival_j = departure_i + ceil(dist/速度)；首行只 departure、末行只 arrival；06:00≤起飞≤18:00、返场≤20:00、不过夜、同机架次间周转≥30min；续航可行（余油≥安全余油）。
6. 五项指标：总飞机使用时间、人员总在途时间、总架次数、总燃油消耗量、座位利用率（机上人公里 / 可用座公里），与 RESULTS_REPORT 对账。

## 风险控制

- 规模：Q2/Q3 各 4000 条，纯 Python 启发式需控制单次运行时间（目标 Q1<2min、Q2<5min、Q3<15min，可调参）；必要时先小样本验证再全量。
- 续航可行性是最大隐雷：油量计算错误 → routes 不可行 → 取消评奖。`fuel_feasible` 单一实现 + validate.py 独立复核双重保险。
- 取整一致性：时刻与时长全链路向上取整到分钟，`utils.ceil_min` 唯一入口。
- assignments 行序：保留模板原有 person_id 行序，避免评测脚本按行对齐失败。
- 4drawio 的 PDF 导出受 drawio 未安装影响可跳过，核心流程不依赖。
- typst 仅在 HOME 下可用（/tmp 不可用），编译须在 `~/yegou/B题` 下执行。

## 策联杯格式硬约束（5writing 必须遵守）

1. 第一页摘要专用页（标题+关键词，≤1 页，页码从 1 开始，页脚居中阿拉伯数字）。
2. 第二页起正文，**不要目录**，正文 ≤30 页。
3. 正文后附录页数不限：含支撑材料文件列表、全部可运行源代码、AI 工具使用声明。
4. 全文不得出现参赛者身份与学校信息。
5. 参考文献按科技论文规范，正文引用处标注。
6. 字号字体行距颜色不统一要求。
7. 提交：参赛论文 PDF（≤20MB，不压缩）+ 支撑材料 RAR/ZIP（≤20MB）。命名 `XXX_参赛论文` / `XXX_支撑材料`（XXX 三位队号）。
8. 用了 AI 工具：参考文献前设"AI 工具使用声明"；支撑材料含 `AI 工具使用详情.pdf`（工具名称版本、使用目的与环节、提示方式与过程、对 AI 输出的采纳/修改/核验情况）。
