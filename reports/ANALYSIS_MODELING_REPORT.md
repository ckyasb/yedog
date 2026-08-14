# 建模报告 · 策联杯 B 题：海上油田人员直升机运载计划编排

> 本报告基于 `CONTEST_BRIEF.md`（题面/数据/格式整理）与 `plan.md`（用户偏好：纯启发式自包含、Q3 临时增量插入），独立完成假设预检、模型建立、下界推导与算法设计，可直接交付 `3coding-visual` 实现。所有数值结论来自 `data/` 实测验算（见各节"验算"）。

---

## 1. 总体建模框架

### 1.1 题型定位

本题是**带取送货、座位动态复用、续航（加油）约束、时间窗、机队配额的多机场车辆路径问题**，属**优化类**（min 目标 + 整数决策 + 组合约束）。三问是同一基础模型上约束逐级叠加的递进结构：

| 问 | 新增要素 | 模型定位 |
|----|---------|---------|
| Q1 | 仅出海（陆→F），无时间窗，飞机充足 | 多机场 VRP-with-Deliveries + 续航 |
| Q2 | + 海返 + 穿梭（同架次三类混合，座位动态复用） | PDPTW（无时间窗）+ 续航 |
| Q3 | + 时间窗 + 24 架配额 + 周转 + 优先级 + 临时可取消 | 多日 PDPTW + Fleet Scheduling + 续航 |

### 1.2 目标函数（分层/字典序，三问统一）

题面"在最小化总飞机使用时间的基础上尽可能优化其他因素"→ **分层目标**（非加权和）：

- **第一层（主）**：min 总飞机使用时间 $T_{\text{air}} = \sum_{k} (\text{depart}_k^{\text{return}} - \text{depart}_k^{\text{out}})$（向上取整到分钟）。
- **第二层（次）**：在第一层最优（或 gap 可接受）的解集中，依次优化：
  - min 人员总在途时间 $T_{\text{pax}} = \sum_p (\text{arrive}_p - \text{depart}_p)$；
  - max 座位利用率 $\eta = \dfrac{\sum_{\text{seg}} n_{\text{seg}} \cdot \ell_{\text{seg}}}{\sum_{\text{seg}} C_{k} \cdot \ell_{\text{seg}}}$（机上人公里 / 可用座公里）；
  - min 总燃油 $F = \sum_k \sum_{\text{seg}\in k} c_t \cdot \ell_{\text{seg}}$；
  - min 总架次数 $K$（与机型选择联动）。

> 实现口径：第一层用主启发式求近优解 + 下界 gap 论证；第二层在**不增大 $T_{\text{air}}$** 的邻域内做局部搜索（换机型降油耗、合并架次提利用率、调整停靠序降在途时间）。不把多目标揉成单一标量，避免量纲淹没。

### 1.3 全局符号

| 符号 | 含义 |
|------|------|
| $\mathcal{A}=\{A01,A02,A03\}$ | 陆地机场集 |
| $\mathcal{F}=\{F001\dots F052\}$ | 海上设施集 |
| $\mathcal{R}\subset\mathcal{F}$ | 可加油设施集（8 个：F006,011,018,024,031,038,044,050） |
| $\mathcal{N}=\mathcal{A}\cup\mathcal{F}$ | 全部地点（55） |
| $d_{ij}$ | $i,j$ 间飞行距离（km），$d_{ii}=0$，对称 |
| $t$ | 机型 $t\in\{T1,T2,T3\}$，座位 $C_t$、速度 $v_t$、油耗 $c_t$、油箱 $W_t$、安全余油 $s_t$ |
| 机型参数 | T1(12,250,3.4,1000,150)、T2(16,220,2.5,1150,150)、T3(19,190,2.9,1600,200) |
| $\tau_{ij}^{t}=\lceil d_{ij}/v_t \cdot 60\rceil$ | 航段飞行时间（分钟，向上取整） |
| $h_{\text{stop}}$ | 停靠最短时长：不加油 10 min，加油 20 min（可延长以等待） |
| $P$ | 待运人员需求集，$p\in P$ 含 origin/dest（可能为 LAND） |
| $k$ | 一个架次（route），起点终点为同一机场 $a(k)$ |

### 1.4 时间取整约定（全局唯一）

- 飞行时间：$\tau_{ij}^{t}=\lceil 60\,d_{ij}/v_t\rceil$ 分钟（向上取整）。
- 任何累计时长、架次使用时间、人员在途时间均对分钟向上取整。
- 加油决策不改变飞行时间，只改变停靠最短时长（10↔20）与油量状态。
- 实现入口：`utils.ceil_min`、`utils.flight_minutes(d, v)`，禁止各处自造。

---

## 2. 数据处理方案

### 2.1 数据理解（已实测，见文末"数据验算"）

| 文件 | 规模 | 关键统计 |
|------|------|---------|
| `distances.csv` | 55×55 | A-F 距离 153–439 km（中位 245）；F-F 距离 14–579 km（中位 157）；对称、对角 0 |
| `peopleQ1.csv` | 1600 | 全出海；52 个目的设施各 19–51 人；origin: LAND×1353 + A01×79 + A02×82 + A03×86 |
| `peopleQ2.csv` | 4000 | 出海 1600 + 海返 1600 + 穿梭 800（Q1 是 Q2 出海子集） |
| `peopleQ3.csv` | 4000 | shift×3440（窗 7–75h）、production×360（1.4–4.9h）、emergency×40（0.5–3.4h）、temporary×160（32–145h） |

### 2.2 数据清洗与校验（`data_loader.py` 统一实现）

1. 距离矩阵：校验 55×55、首列 `from_id`、列名集合 = 行名集合 = $\mathcal{N}$、对称（$d_{ij}=d_{ji}$）、对角 0、非负整数。
2. peopleQ*：校验列名；`person_id` 唯一；origin/dest 属 $\mathcal{N}\cup\{\text{LAND}\}$；Q1 dest 全为 F；Q3 时间格式 `YYYY-MM-DD HH:MM`、`earliest ≤ latest`、`task_type` ∈ 四类。
3. 模板：`*-routes.csv` 仅表头（保留）；`*-assignments.csv` 已预置全部 `person_id` 空行 → **产出时按模板行序填充，禁止重排**。

### 2.3 派生指标

- 每设施最近机场 `nearest_airport(f)`（A01×32、A03×12、A02×8，实测）。
- 续航可达性矩阵：$R_t(i,j)$=机型 $t$ 从 $i$ 到 $j$ 是否可不加油直飞（$c_t d_{ij}\le W_t-s_t$）。
- 加油策略：在 8 个 $\mathcal{R}$ 中选点加满。

### 2.4 总体路线

```
题面 → 数据加载校验(data_loader) → 续航可达预处理 →
Q1模型(出海VRP) → Q2模型(PDPTW) → Q3模型(多日调度+临时增量) →
结果校验(validate) → 指标计算 → 图表 → 论文
```

---

## 3. 续航（加油）子模型（三问共用，核心约束）

这是本题最大隐雷，单独成节，`utils.fuel_feasible` 单一实现，routes 生成与 validate 共用。

### 3.1 油量状态转移

架次 $k$ 机型 $t$ 从机场 $a$ 满油起飞，停靠序列 $s_0=a, s_1, \dots, s_m, s_{m+1}=a$（$s_1..s_m\in\mathcal{F}$，$m\le5$）。加油决策 $r_i\in\{0,1\}$（$r_0=r_{m+1}=0$；$r_i=1$ 仅当 $s_i\in\mathcal{R}$）。

油量递推：
$$F_0 = W_t$$
$$F_i = \begin{cases} W_t & r_i=1 \\ F_{i-1} - c_t\,d_{s_{i-1},s_i} & r_i=0 \end{cases},\quad \forall i=1..m+1$$

可行性（每段到达时余油 ≥ 安全余油）：
$$F_i - c_t\,d_{s_{i-1},s_i} \;\ge\; s_t \quad \forall i=1..m+1 \;\text{（含返场最后一段）}$$

### 3.2 续航可达性实测（已验算，**修正**）

可用燃油 $W_t-s_t$，不加油最大飞行路径 $= (W_t-s_t)/c_t$；往返不加油要求单程 $\le$ 最大路径/2。

| 机型 | 可用燃油 | 不加油最大路径 | 往返不加油最大单程 | 往返不加油可达设施数 |
|------|-----|-----|-----|-----|
| T1 | 850 kg | 250 km | 125 km | **0/52**（min A-F=153>125，T1 往返必加油） |
| T2 | 1000 kg | 400 km | 200 km | 13/52 |
| T3 | 1400 kg | 482.8 km | 241.4 km | 34/52 |

**修正结论**：续航是**强约束**，并非可忽略：
- **T1 几乎每次往返都需加油**（仅 36 个设施单程可达，往返无一可达不加油）；
- T2 从最近机场往返 39/52 设施需加油；T3 仅 18/52 需加油。
- 因此**机型选择与加油点插入是一阶决策**：T1 虽快（250）但每次加油 +20min 停靠与绕路，综合时间未必占优；T3 慢（190）但座位多（19）、航程长（少加油），架次数少。需按路线实测比较。
- `fuel_feasible` 在构造与优化时作为硬门控；`plan_refuels` 负责在固定停靠序上贪心插入加油点（优先在已停靠的可加油设施加油，否则插入最近可达可加油设施，受 5 次着陆上限约束）。

### 3.3 加油点选择策略

当一趟 5 站路线油量不足时，按"最小代价"插入加油点：
1. 在已停靠的可加油设施（若路线含 $\mathcal{R}$）直接置 $r_i=1$（多 10 min 停靠，免绕路）。
2. 否则在路径上插入最近可加油设施（绕路代价 vs 换大机型代价权衡）。
3. 实在不可行 → 降站数拆分架次。

---

## 4. 问题一模型：单向出海运输

### 4.1 问题目标

1600 条出海需求（origin∈$\mathcal{A}\cup\{\text{LAND}\}$，dest∈$\mathcal{F}$），无时间窗，飞机充足。min 总飞机使用时间，次优化在途/利用率/油耗/架次数。

### 4.2 决策变量

- $x_{p,k}\in\{0,1\}$：人员 $p$ 是否分配到架次 $k$（每人恰好一个 $k$）。
- 架次 $k$：机型 $t_k$、起降机场 $a_k$、停靠序列 $\sigma_k=(a_k, s_1, \dots, s_m, a_k)$、加油决策 $r^k$（$m\le5$）。
- LAND 人员的实际机场 = $a_k$（即"可任选"由架次机场决定）。

### 4.3 约束

1. **人员全覆盖**：$\sum_k x_{p,k}=1\;\forall p$。
2. **单架次单机型**：$k$ 全程机型不变。
3. **架次结构**：首末为同一机场 $a_k\in\mathcal{A}$；中间海上设施 $m\le5$；同一人员不换乘。
4. **起降点一致**：$p$ 的 origin∈$\{a_k\}\cup\{\text{LAND}\}$ 且 dest∈$\sigma_k$；`pickup_stop_order` < `delivery_stop_order`，delivery 为上机后首次到达 dest 的序号。
5. **座位容量**：任一航段机上人数 $\le C_{t_k}$（同站先下后上，座位即时复用）。
6. **续航**：`fuel_feasible`（§3）。
7. **加油合法性**：$r_i=1\Rightarrow s_i\in\mathcal{R}$；机场行 $r=0$。

### 4.4 目标函数（分层）

- L1：$\min T_{\text{air}}=\sum_k [\sum_{i=0}^{m}\tau_{s_i s_{i+1}}^{t_k} + \sum_{i=1}^{m} h_{\text{stop}}(r_i)]$（$h_{\text{stop}}$=10/20）。
- L2（在 L1 不增前提下）：min $T_{\text{pax}}$；max $\eta$；min $F=\sum_k c_{t_k}\sum_i d_{s_i s_{i+1}}$；min $K$。

### 4.5 下界推导（L1 总飞机使用时间）

- **架次数下界 $K_{\text{lb}}$**：每个架次最多 5 站、座位 $C_t$，最多服务 $5 C_t$ 人（满载理想）。但更紧的下界来自目的设施分散度：1600 人分布到 52 个设施（每设施 19–51 人），单架次最多覆盖 5 个不同设施。
  - 按设施覆盖：至少 $\lceil 52/5\rceil = 11$ 架次（仅按设施数，很松）。
  - 按座位容量：$\lceil 1600/C_t\rceil$（T2: 100 架次满载）。**但每架次通常只服务同一目的设施附近的人**，实际架次数受设施分散度主导。
- **单架次使用时间下界**：至少 $\min_t [2\min_{a,f} d_{a,f}/v_t\cdot60 + 10]$。实测 T2 单程 42–120 min，直飞往返 94–250 min。
- **总下界 $T_{\text{lb}}$**：$K_{\text{lb}}\times \bar{\tau}_{\text{rt}}$，其中 $\bar{\tau}_{\text{rt}}$ 取按目的设施聚类后的平均最短往返时间。
- **gap**：$T_{\text{air}}^{\text{heur}}/T_{\text{lb}}-1$，作为接近最优的证据。

### 4.6 算法设计（聚类 + 节约构造 + ALNS + 续航门控）

1. **聚类**：按 `dest` 设施分组；LAND 人员机场待定。同 dest 的人必上同一架次（delivery 点唯一），按 $C_t$ 分批。
2. **初始构造（节约算法/Sweep）**：
   - 对每个机场 $a$，取 dest 最近机场 = $a$ 的设施簇，按方位角 sweep 生成候选架次。
   - 贪心合并近邻目的设施簇到同一架次，直到 $m=5$ 或座位满或续航受限（`fuel_feasible` 门控）。
   - 机型选择：簇人数 ≤12 选 T1，≤16 选 T2，否则 T3；若续航不足则升档。
3. **优化（ALNS）**：
   - **destroy**：随机移除若干架次/站点（related removal by 设施邻近；worst removal by 使用时间低效）。
   - **repair**：regret-k 贪心重插入 + 续航可行性修复（插加油点/拆架次）。
   - 接受准则：模拟退火式（$\Delta T_{\text{air}}\le0$ 必接受；否则以 $e^{-\Delta/\theta}$ 概率接受）。
   - L2 阶段：在 $T_{\text{air}}$ 不增邻域内做换机型（降油耗）、合并架次（提 $\eta$ 降 $K$）、调停靠序（降 $T_{\text{pax}}$）。
4. **停止**：迭代上限或 $T_{\text{air}}$ 连续 $N$ 轮无改进。

### 4.7 输入输出

- 输入：`data/peopleQ1.csv`、`data/distances.csv`。
- 输出：覆写 `data/q1-routes.csv`、`data/q1-assignments.csv`（按模板列序，保留 assignments 行序）。
- 指标：五项（$T_{\text{air}}, T_{\text{pax}}, K, F, \eta$）写入 `results/q1_metrics.json` 与 `RESULTS_REPORT.md`。

### 4.8 校验

`validate.py` 对 q1：首末同机场、$m\le5$、refuel 合法、pickup<delivery 与起终点一致、座位不超载、续航可行、全员已分配。

---

## 5. 问题二模型：出海+海返+穿梭联合运输

### 5.1 问题目标

4000 条需求（出海 1600 / 海返 1600 / 穿梭 800），无时间窗，飞机充足。同架次内三类人员混合上下机，座位动态复用。目标分层同 Q1。

### 5.2 新增难点与决策变量

- 同一架次可同时载出海（陆→F）、海返（F→陆）、穿梭（F→F）三类人员。
- **机上人数时序** $n_i$：在航段 $s_i\to s_{i+1}$ 上，$n_i = n_{i-1} - \text{下机}_i + \text{上机}_i$（同站先下后上），须 $\le C_{t_k}$。
- **LAND 配对**：出海人员 origin=LAND 与海返人员 dest=LAND 可共用同一机场（架次机场 $a_k$），形成"往返环"。
- **穿梭嵌入**：穿梭人员 origin∈$\mathcal{F}$、dest∈$\mathcal{F}$，其 origin 须为架次某停靠 $s_i$，dest 为其后某停靠 $s_j$（$i<j$）。

决策变量新增：
- $u_{p,i}\in\{0,1\}$：人员 $p$ 在停靠 $s_i$ 上机；$v_{p,i}\in\{0,1\}$：在 $s_i$ 下机。
- 架次停靠序列 $\sigma_k$、机型 $t_k$、加油 $r^k$。

### 5.3 约束（在 Q1 基础上新增）

8. **三类人员起终点匹配**：
   - 出海 $p$：origin∈$\{a_k,\text{LAND}\}$，dest∈$\sigma_k$，pickup=0（机场），delivery=首次到 dest。
   - 海返 $p$：origin∈$\sigma_k$，dest∈$\{a_k,\text{LAND}\}$，pickup=origin 停靠，delivery=末（机场）。
   - 穿梭 $p$：origin、dest∈$\sigma_k$，pickup=origin 停靠，delivery=其后首次到 dest。
9. **先下后上**：同停靠 $s_i$ 先处理下机再上机，释放座位即时复用。
10. **座位容量时序**：$n_i\le C_{t_k}\;\forall i$。
11. **续航**：`fuel_feasible`（同 Q1）。

### 5.4 目标函数

分层同 §1.2。注意穿梭增加绕行可能增大 $T_{\text{pax}}$，需在 L2 平衡。

### 5.5 算法设计（PDPTW 构造 + ALNS）

1. **需求配对**：
   - 出海（陆→F）与海返（F→陆）若 F 相同或邻近，拼成"往返环" $a\to F\to a$，座位往返复用。
   - 穿梭（F→F）嵌入已有环的中间段，或与出海/海返共架。
2. **构造**：以"往返环"为单位，按机上人数时序贪心填充三类人员，校验座位容量与续航。
3. **优化（ALNS）**，邻域：
   - **换机场**：LAND 任选，重新匹配往返环机场（降绕行）。
   - **调整停靠序**：重排 $\sigma_k$ 中设施顺序（TSP 式局部 2-opt），降 $T_{\text{air}}$/$T_{\text{pax}}$。
   - **穿梭嵌入位置**：移动穿梭人员的 pickup/delivery 停靠。
   - **合并/拆分架次**：座位利用率低则合并，座位不足或续航受限则拆分。
4. **续航门控**：每次邻域移动后调 `fuel_feasible`，必要时插加油点。

### 5.6 下界

- 架次数下界：$\max(\lceil\text{总人公里}/(C_t\cdot\text{平均架次距离})\rceil, \lceil\text{设施覆盖}/5\rceil)$。
- 单架次往返下界：同 Q1。
- Q2 的 $T_{\text{air}}$ 应**不低于** Q1（需求更多、约束更紧）；若 Q2 显著高于"Q1+独立海返/穿梭"估算，需检查配对是否低效。

### 5.7 输入输出与校验

同 Q1，输出 `data/q2-routes.csv`、`data/q2-assignments.csv`。校验增加：三类人员起终点匹配、座位时序容量、穿梭 pickup<delivery 且都在海上设施。

---

## 6. 问题三模型：带时间窗的多日排班

### 6.1 问题目标

4000 条带时间窗 + task_type 的需求，24 架飞机配额，多日（2026-08-03 ~ 08-10）。先排非临时 3840 条得 $T_0$，再在 $T_{\text{air}}\le T_0$ 下尽量满足 160 条临时，最大化满足数。

### 6.2 新增参数与约束

- **机队**：24 架，编号 `机场-机型-序号`（A01: T1×3,T2×3,T3×2；A02: T1×2,T2×4,T3×2；A03: T1×2,T2×3,T3×3）。
- **运营窗**：起飞 06:00–18:00，返场 ≤20:00，**不过夜**（每日返场）。
- **周转**：架次返场后 ≥30 min 机场周转方可再起飞。
- **时间窗**：人员离开起点 ≥ `earliest_pickup_time`，到终点 ≤ `latest_arrival_time`。
- **优先级**：emergency > production > shift > temporary；临时可取消。
- **时刻链**：$arrival_j = departure_i + \tau_{ij}^t$（向上取整）；首行只填 departure，末行只填 arrival。

### 6.3 决策变量

- 架次 $k$ 绑定**具体飞机** $h_k$（机型 $t(h)$、所属机场 $a(h)$）、日期、起飞时刻。
- 停靠时刻序列 $(arrival_i, departure_i)$。
- 临时人员安排变量 $y_p\in\{0,1\}$（是否满足）。

### 6.4 约束（在 Q2 基础上新增）

12. **运营窗**：$06{:}00 \le departure_0 \le 18{:}00$；$arrival_{m+1}\le 20{:}00$；不过夜（同日返场）。
13. **周转**：同一飞机相邻架次间 $departure_{k+1,0}\ge arrival_{k,m+1}+30$ min。
14. **机队配额**：每时刻在飞飞机数 ≤ 该机场该机型可用数（实质是飞机资源占用时序不重叠）。
15. **时间窗**：人员 $p$ 的 $departure_{\text{pickup}}\ge e_p$，$arrival_{\text{delivery}}\le l_p$。
16. **优先级**：emergency/production/shift 必须满足（$y_p=1$）；temporary 可不满足（$y_p\in\{0,1\}$）。
17. **临时预算**：$\sum_k T_{\text{air},k}^{\text{with temp}} \le T_0$（加入临时后总使用时间不超基线）。

### 6.5 目标函数（两阶段）

**阶段 A（非临时基线）**：对 3840 条非临时，min $T_{\text{air}}$（分层同前），得 $T_0$。

**阶段 B（临时增量）**：
$$\max \sum_{p\in\text{temp}} y_p \quad \text{s.t.}\quad T_{\text{air}}^{\text{total}}\le T_0,\;\text{其他约束成立}$$
在满足数最大化的前提下，再优化 $T_{\text{pax}}, \eta, F, K$。

### 6.6 算法设计

#### 阶段 A：非临时多日排班

1. **按日分桶 + 按优先级**：emergency（窗 0.5–3.4h，最紧）优先排，production（1.4–4.9h）次之，shift（7–75h，宽）填充。
2. **时间窗聚类**：同日、同区域、时间窗重叠的需求合并架次。
3. **构造**：对每个 (日期, 机场) 桶，按 Q2 的 PDPTW 构造 + 时间窗可行性（到达不超 latest、起飞不早于 earliest）。
4. **飞机分配**：架次按机型需求 + 机场归属分配具体飞机 $h$，保证周转与配额。
5. **优化（ALNS）**：邻域含换飞机、调起飞时刻、跨日迁移、合并/拆分。

#### 阶段 B：临时增量插入

1. **候选评估**：对每条 temporary（窗 32–145h，宽），计算插入到现有架次的增量代价 $\Delta T_{\text{air}}$ 与可行性（时间窗、座位、续航、周转）。
2. **贪心 + 局部搜索**：按"增量代价/优先级"排序，逐条尝试插入现有架次或新开架次（受配额约束）；每插入一条检查 $T_{\text{air}}\le T_0$。
3. **最大化满足数**：若直接插入代价超 $T_0$ 预算，尝试**置换**——移除一条低效临时以腾出预算给更高价值临时（价值 = 优先级 + 满足数贡献）。
4. **停止**：预算耗尽或无可行插入。

#### 续航与时刻一致性

- 每次 insertion/relocation 后调 `fuel_feasible` 与时刻链校验。
- 时刻向上取整到分钟，`arrival = prev_departure + ceil(60·d/v)`。

### 6.7 下界与论证

- $T_0$ 下界：非临时 3840 条按日桶的架次使用时间下界之和（同 Q1/Q2 方法按日聚合）。
- 临时满足数上界：160（全满足）；实际受 $T_0$ 预算与机队配额约束，报告"已满足 / 160"及未满足原因（预算不足 / 时间窗冲突 / 座位不足）。

### 6.8 输入输出与校验

- 输入：`data/peopleQ3.csv`、`data/distances.csv`、机队表（code 内置）。
- 输出：`data/q3-routes.csv`（带时刻）、`data/q3-assignments.csv`（temporary 未安排保留空行）。
- 校验（validate.py 新增）：时刻链单调、运营窗、周转 ≥30min、不过夜、机队配额、时间窗、续航、temporary 行保留。

---

## 7. 灵敏度分析与检验方案

- **续航敏感性**：扰动安全余油 $s_t$（±20%），观察架次数与总使用时间变化；验证加油点选择鲁棒性。
- **机型选择敏感性**：强制全用 T2 vs 混合机型，对比 $T_{\text{air}}, F, \eta$。
- **Q3 时间窗松紧**：将 emergency/production 窗长 ±20%，观察满足数与 $T_0$ 变化。
- **ALNS 稳定性**：固定 5 个随机种子独立运行，报告 $T_{\text{air}}$ 均值/标准差，证明非偶然。
- **下界 gap**：报告各问 $T_{\text{air}}^{\text{heur}}/T_{\text{lb}}-1$。

---

## 8. 代码实现任务清单

| 任务 | 输入 | 输出 | 方法 | 校验 |
|------|------|------|------|------|
| 公共工具 `utils.py` | distances, 机型表 | `d()`, `flight_minutes()`, `ceil_min()`, `fuel_feasible()`, 机型表 | 纯函数 | 单元自检：对称/对角/取整 |
| 数据加载 `data_loader.py` | data/*.csv | 校验后的 DataFrame + 距离矩阵 | pandas | 行数/列名/集合校验 |
| 问题一 `problem1.py` | peopleQ1, distances | q1-routes/assignments.csv + metrics | 聚类+节约+ALNS+续航门控 | validate.py 全通过 |
| 问题二 `problem2.py` | peopleQ2, distances | q2-routes/assignments.csv + metrics | PDPTW 配对+构造+ALNS | validate.py + 座位时序 |
| 问题三 `problem3.py` | peopleQ3, distances, 机队 | q3-routes/assignments.csv + metrics | 阶段A基线+阶段B临时增量 | validate.py + 时刻/运营窗/周转/配额 |
| 校验 `validate.py` | q*-routes/assignments | PASS/FAIL 报告 | 逐项硬约束检查 | 与 metrics 对账 |
| 指标与图表 | metrics + routes | results/*.json + figures/*.pdf | pandas/matplotlib | 数值与 RESULTS_REPORT 对账 |

---

## 附：数据验算记录（支撑以上假设与下界，3coding 阶段可复跑）

```
网络: 3 机场 + 52 设施; 距离矩阵 55×55 对称对角0
A-F 距离: min=153 max=439 med=245 km
F-F 距离: min=14 max=579 med=157 km
各设施最近机场: A01×32, A03×12, A02×8

续航可用燃油 (W-s) 与不加油最大路径 ((W-s)/c):
  T1=850kg, cons=3.4, max_path=250km, 往返单程≤125 -> 往返可达设施 0/52
  T2=1000kg, cons=2.5, max_path=400km, 往返单程≤200 -> 往返可达设施 13/52
  T3=1400kg, cons=2.9, max_path=482.8km, 往返单程≤241.4 -> 往返可达设施 34/52
T1 从最近机场往返 52/52 需加油; T2 39/52 需加油; T3 18/52 需加油

Q1: 1600 人, 52 目的设施 (每设施19-51人)
Q2: 出海1600 + 海返1600 + 穿梭800 = 4000
Q3 task_type: shift×3440(窗7-75h) production×360(1.4-4.9h) emergency×40(0.5-3.4h) temporary×160(32-145h)

T2 单程飞行时间: 42-120 min
```
