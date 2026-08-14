#set document(title: "锂离子电池快充策略对寿命衰减的影响建模与优化", author: ())
#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 2.5cm, right: 2.5cm),
  numbering: none,
)
#set text(font: ("Noto Serif CJK SC"), size: 12pt, lang: "zh")
#set par(first-line-indent: (amount: 2em, all: true), justify: true, leading: 0.78em, spacing: 0.55em)
#set heading(numbering: "1.1")
#set enum(numbering: "1.")
#show heading.where(level: 1): it => block(above: 1.8em, below: 1.0em)[#align(center)[#text(font: ("Noto Sans CJK SC", "Noto Sans CJK SC", "Noto Serif CJK SC"), size: 16pt, weight: "bold")[#it]]]
#show heading.where(level: 2): it => block(above: 1.25em, below: 0.65em)[#text(font: ("Noto Sans CJK SC", "Noto Sans CJK SC", "Noto Serif CJK SC"), size: 14pt, weight: "bold")[#it]]
#show heading.where(level: 3): it => block(above: 0.9em, below: 0.4em)[#text(font: ("Noto Sans CJK SC", "Noto Sans CJK SC", "Noto Serif CJK SC"), size: 12pt, weight: "bold")[#it]]
#show figure.caption: it => text(size: 9pt)[#it]

#let hei = (body) => text(font: ("Noto Sans CJK SC", "Noto Sans CJK SC", "Noto Serif CJK SC"), weight: "bold", body)
#let tight-title(body, size: 18pt) = align(center)[#text(font: ("Noto Sans CJK SC", "Noto Sans CJK SC", "Noto Serif CJK SC"), size: size, weight: "bold")[#body]]
#let keywords-cn(body) = block(above: 0.65em)[
  #set par(first-line-indent: 0pt)
  #text(font: ("Noto Sans CJK SC", "Noto Sans CJK SC", "Noto Serif CJK SC"), weight: "bold")[关键词：]#body
]
#let running-header = [
  #align(center)[#text(size: 10.5pt)[数学建模竞赛论文]]
  #v(-0.45em)
  #line(length: 100%, stroke: 0.45pt)
]
#let references-cn() = [
#heading(level: 1, numbering: none, outlined: false)[参考文献]
#set par(first-line-indent: 0pt)
#include("references.typ")
]
#let appendix-cn(file: "sections/A_code.typ") = {
  set heading(numbering: "A")
  set par(first-line-indent: 0pt, leading: 0.55em, spacing: 0pt)
  show raw: set text(size: 8.6pt)
  show raw.where(block: true): set block(above: 0.35em, below: 0pt)
  counter(heading).update(0)
  heading(level: 1)[核心代码]
  include(file)
}

#let three-line-table(caption, columns, header, body, inset: (x: 0.35em, y: 0.52em), cell-align: center) = {
  let col-count = header.len()
  let body-rows = calc.floor(body.len() / col-count)
  let bottom-y = body-rows + 1
  let styled-header = header.map(cell => strong(cell))

  block(width: 100%, breakable: false)[
    #align(center)[
      #box[
        #align(center)[#text(font: ("Noto Sans CJK SC", "Noto Sans CJK SC", "Noto Serif CJK SC"), size: 10.5pt, weight: "bold")[#caption]]
        #v(0.6em)
        #table(
          columns: columns,
          align: cell-align,
          stroke: none,
          inset: inset,
          table.hline(y: 0, stroke: 0.8pt),
          table.hline(y: 1, stroke: 0.5pt),
          table.hline(y: bottom-y, stroke: 0.8pt),
          ..styled-header,
          ..body,
        )
      ]
    ]
  ]
}

// ===== 摘要专用页（策联杯规范：第1页，含标题与关键词，不超1页，页码从1起）=====
#v(0.6cm)
#tight-title([锂离子电池快充策略对寿命衰减的影响建模与优化], size: 17pt)

#v(1.4cm)
#align(center)[#hei([摘 #h(2em) 要])]
#v(0.5em)

#set par(first-line-indent: 2em, justify: true)
本文针对锂离子电池快充策略对循环寿命衰减的影响展开建模与优化。基于 MIT–Stanford 公开电池循环老化数据集（49 块 A123 18650 电池，9 种两阶段快充策略），以 80% SOH 为寿命终止阈值，依次完成数据整理、参数影响分析、寿命预测与策略优化四项任务。

#strong[问题一] 对数据集进行整理，采用线性与指数模型对 SOH 平滑序列外推得到各电池循环寿命（取二者中位为主寿命代理）。寿命分布跨度 1106\~18109 次；提取长寿命策略 `3_6C-80PER`（18109 次）与短寿命策略 `3_7C-31PER-5_9C`（1106 次），发现中高 SOC 段持续高倍率是加速衰减的关键。

#strong[问题二] 针对 $C_1$、$Q_1$、$C_2$ 非完全独立的特点，采用 Kruskal–Wallis 检验（$p = 0.0081$，置换 $p = 0.0022$）确认策略间寿命差异显著；岭回归与偏相关显示 $C_2$ 偏相关 $r = -0.41$（$p = 0.0036$），随机森林置换重要性中 $C_2$ 占 93.9%，表明第二阶段倍率是寿命衰减的主导因素。

#strong[问题三] 采用防泄露留出验证设计，对比线性、指数与随机森林递归模型，随机森林最优（RMSE = 0.00131，MAPE = 0.112%）。预测 9 块测试电池第 151\~200 次 SOH 及寿命，寿命排序与问题一一致；数据长度敏感性表明训练循环数从 50 增至 150 时 RMSE 降低约 40%。

#strong[问题四] 建立充电时间解析模型（$R^2 = 0.587$）与对数链接衰减模型，以多目标优化（Pareto 前沿 + 加权和）求得推荐策略 $C_1 = 5.8$、$Q_1 = 64$、$C_2 = 4.5$，充电时间 8.98 min、预测寿命 14850 次，较长寿策略充电时间缩短 33%，较短寿策略寿命提升约 13 倍。

#keywords-cn[锂离子电池、快充策略、循环寿命、SOH 预测、多目标优化]

#pagebreak()
// ===== 正文：第2页起，无目录，页码从1起连续编号于页脚中部 =====
#set page(
  numbering: "1",
  header: running-header,
  footer: context align(center)[#counter(page).display("1")],
)

#include("sections/1_restatement.typ")
#include("sections/2_assumptions.typ")
#include("sections/3_symbols.typ")
#include("sections/4_problem1.typ")
#include("sections/5_problem2.typ")
#include("sections/6_problem3.typ")
#include("sections/7_sensitivity.typ")
#include("sections/8_evaluation.typ")

// ===== AI 工具使用声明（置于参考文献之前，策联杯规范）=====
#heading(level: 1, numbering: none, outlined: false)[AI 工具使用声明]
本参赛队在竞赛过程中使用了 AI 工具，主要用于代码调试、图表脚本辅助与语言润色，详细使用情况见支撑材料。

#references-cn()

// ===== 附录：源代码列表 + AI 使用详情（策联杯规范）=====
#appendix-cn()
