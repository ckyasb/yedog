= 符号说明

本文主要符号及其含义如下：

#table(
  columns: (auto, 1fr, auto),
  align: (center, left, center),
  stroke: none,
  table.hline(stroke: 0.8pt),
  table.hline(stroke: 0.5pt),
  table.hline(stroke: 0.8pt),
  [*#strong[符号]*], [*#strong[含义]*], [*#strong[单位]*],
  [$Q_"cur"$], [当前循环可用容量], [Ah],
  [$Q_0$], [初始容量], [Ah],
  [$"SOH"$], [$Q_"cur" slash Q_0$], [无量纲],
  [$N$], [循环次数], [次],
  [$L$], [循环寿命 SOH 降至 0.8 时的 $N$], [次],
  [$C_1$], [第一阶段充电倍率], [C],
  [$Q_1$], [第一阶段结束 SOC], [%],
  [$C_2$], [第二阶段充电倍率], [C],
  [$t_"ch"$], [平均充电时间], [min],
  [$R_"IR"$], [内阻], [$Omega$],
  [$overline(T)$], [平均温度], [℃],
  [$k$], [SOH 衰减速率 SOH 对 $N$ 的斜率], [1/循环],
  [$E_"low"$], [低 SOC 段高倍率暴露 $C_1 Q_1$], [C·%],
  [$E_"high"$], [中高 SOC 段高倍率暴露 $C_2 (80 - Q_1)$], [C·%],
  [$hat("SOH")_N$], [第 $N$ 循环预测 SOH], [无量纲],
  [$hat(L)$], [预测循环寿命], [次],
  [$w_1, w_2$], [优化目标权重], [无量纲],
)
