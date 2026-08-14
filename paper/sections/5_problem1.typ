#import "../lib.typ": *

= 问题一的模型建立与求解

== 决策变量与目标函数

问题一为单向出海运输，1600 条需求，无时间窗，飞机充足。决策变量包括：人员分配 $x_(p,k) in {0,1}$（每人恰一个架次）；架次 $k$ 的机型 $t_k$、起降机场 $a_k$、停靠序列 $sigma_k = (a_k, s_1, ..., s_m, a_k)$ 与加油决策 $r^k$（$m <= 5$）。`LAND` 人员的实际机场取 $a_k$。

目标函数采用分层（字典序）形式：第一层最小化总飞机使用时间，第二层在该最优解集中依次优化人员总在途时间、座位利用率、油耗与架次数：

$ "第一层: min" T_"air" = sum_k [sum_(i=0)^m tau_(s_i s_(i+1))^(t_k) + sum_(i=1)^m h_"stop"(r_i)] $

$ "第二层: min" T_"pax", quad "max" eta = (sum_"seg" n_"seg" dot.c ell_"seg") / (sum_"seg" C_(t_k) dot.c ell_"seg"), quad "min" F, quad "min" K $

其中 $T_"pax" = sum_p ("arrive"_p - "depart"_p)$ 为各人员离开起点到到达终点的总时长。

== 约束条件

+ #strong[人员全覆盖]：$sum_k x_(p,k) = 1, forall p$。

+ #strong[架次结构]：首末为同一机场 $a_k in cal(A)$；中间海上设施 $m <= 5$；同一人员不换乘。

+ #strong[起降点一致]：人员 $p$ 的 origin $in {a_k} union {"LAND"}$ 且 dest $in sigma_k$；`pickup_stop_order < delivery_stop_order`，delivery 为上机后首次到达终点的序号。

+ #strong[座位容量]：任一航段机上人数 $<= C_(t_k)$（同站先下后上，座位即时复用）。

+ #strong[续航可行性]：满油起飞，到达每点（含返场）余油 $>= s_t$；可在可加油设施加满。

+ #strong[加油合法性]：$r_i = 1 -> s_i in cal(R)$；机场行 $r = 0$。

== 下界推导

架次数硬下界 $K_"lb" = ceil(1600 / 19) = 85$（T3 全用，座位容量）。更紧的#strong[per-facility 强下界]：每座设施 $f$ 至少需 $ceil(n_f / 19)$ 趟访问 $f$ 的架次，每架次用时不少于到 $f$ 的最短可行往返时间 $t_f$，故

$ T_"lb" = sum_(f in cal(F)) ceil(n_f / 19) dot.c t_f $

经计算 $K_"lb"^"strong" = 110$，$T_"lb"^"strong" = 16900$ min（281.7 h）。

== 求解算法

求解流程如图6所示。核心步骤：

#figure(
  image("../../figures/fig_flow_q1.pdf", width: 78%),
  caption: [问题一求解流程],
) <fig:flow1>

+ #strong[聚类]：按目的设施分组，同机场近邻设施聚为不超过 5 个的簇。

+ #strong[构造]：对每簇枚举机型，选最小化簇内总使用时间 $ceil(N / C_t) dot.c tau_"trip"$ 的机型；`make_route` 自动构造 TSP 序并插入加油点（最多 2 个）。

+ #strong[初始解]：单设施独立解（每设施选最优机型分批），得 110 架次、17666 min。

+ #strong[ALNS 优化]：destroy（随机移除簇/重分批）+ repair（regret 贪心重聚类）+ 模拟退火式接受准则，仅在降低总使用时间时接受；每次移动后续航门控校验。

+ #strong[第二层优化]：在不增大 $T_"air"$ 的邻域内换机型降油耗、合并架次提利用率。

== 求解结果

求解得到问题一五项指标如表3所示。

#three-line-table(
  [表3 问题一求解结果],
  (auto, auto, auto),
  ([指标], [数值], [说明]),
  (
    [总飞机使用时间], [17612 min (293.5 h)], [主目标],
    [人员总在途时间], [128271 min (2137.9 h)], [次优化],
    [总架次数], [110], [与强下界一致],
    [总燃油消耗量], [144800.6 kg], [次优化],
    [座位利用率], [0.4305], [次优化],
  ),
)

相对 per-facility 强下界的 gap 为

$ "gap" = (T_"air"^"heur" - T_"lb"^"strong") / T_"lb"^"strong" = (17612 - 16900) / 16900 = 4.2% $

ALNS 相对单设施独立解改进 0.3%，五种子独立运行总使用时间均值 17640 min、标准差 85 min（变异系数 \< 0.5%），结果稳定。ALNS 收敛曲线如图7所示。

#figure(
  image("../../figures/fig7_q1_convergence.pdf", width: 75%),
  caption: [问题一 ALNS 收敛曲线],
) <fig:conv1>

结果表明，问题一启发式解距强下界仅 4.2%，接近最优；单设施独立解已较优（合并收益有限，因座位容量是架次数的硬约束而非设施分散度），ALNS 进一步微调机型与合并使总时间下降 0.3%。
