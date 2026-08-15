#let body-font = ("Noto Sans CJK SC", "Noto Serif CJK SC", "DejaVu Sans")
#let song-font = ("Noto Serif CJK SC", "Noto Sans CJK SC")
#let hei-font = ("Noto Sans CJK SC", "Noto Sans CJK JP")
#let kai-font = ("Noto Serif CJK SC", "Noto Sans CJK SC")

#let cn-numbering(..nums) = {
  let ns = nums.pos()
  if ns.len() == 1 {
    numbering("一、", ns.at(0))
  } else if ns.len() == 2 {
    numbering("1.1", ns.at(0), ns.at(1))
  } else {
    numbering("1.1.1", ns.at(0), ns.at(1), ns.at(2))
  }
}

#set document(title: "基于大数据驱动的足球世界杯赛事预测与赛程资源协同优化", author: ())
#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 2.5cm, right: 2.5cm),
  numbering: "1",
)
#set text(font: body-font, size: 12.05pt, lang: "zh")
#set par(
  first-line-indent: (amount: 2em, all: true),
  justify: true,
  leading: 0.72em,
  spacing: 0.35em,
)
#set heading(numbering: cn-numbering)
#set enum(numbering: "1.")
#set table(inset: 0.45em)
#show heading.where(level: 1): set align(center)
#show heading.where(level: 1): set text(size: 17.3pt, weight: "bold")
#show heading.where(level: 1): set block(above: 1.25em, below: 0.82em)
#show heading.where(level: 2): set text(size: 14.45pt, weight: "bold")
#show heading.where(level: 2): set block(above: 1.15em, below: 0.55em)
#show heading.where(level: 3): set text(size: 12.05pt, weight: "bold")
#show heading.where(level: 3): set block(above: 1.15em, below: 0.55em)
#show figure.caption: it => text(size: 12pt, weight: "bold")[#it]
#show raw: set text(size: 10pt, font: ("Noto Sans Mono CJK HK", "Noto Sans CJK SC", "DejaVu Sans Mono"))
#show raw.where(block: true): set block(
  fill: luma(97%),
  stroke: 0.8pt + luma(70%),
  inset: 0.7em,
  above: 0.7em,
  below: 0.7em,
)

#let song = (body) => text(font: song-font, body)
#let hei = (body) => text(font: hei-font, weight: "bold", body)
#let kai = (body) => text(font: kai-font, body)
#let paper-title(body) = {
  align(center)[#text(size: 17.3pt, weight: "bold")[#body]]
  v(1em)
}
#let abstract-title() = align(center)[#text(size: 14pt, weight: "bold")[摘要]]
#let keywords-cn(body) = block(above: 1em)[
  #text(font: hei-font, size: 12pt, weight: "bold")[关键字：] #body
]
#let abstract-cn(body, keywords) = {
  abstract-title()
  block(above: 0.15em)[#body]
  keywords-cn(keywords)
  pagebreak()
}
#let toc-page() = {
  show outline.entry.where(level: 1): it => link(
    it.element.location(),
    block(above: 7pt)[
      #text(font: hei-font, size: 12pt, weight: "bold")[
        #grid(
          columns: (auto, 1fr, auto),
          column-gutter: 0.5em,
          [#it.prefix()#it.body()],
          [#repeat[.]],
          [#it.page()],
        )
      ]
    ],
  )
  outline(
    title: align(center)[#text(font: hei-font, size: 17.3pt, weight: "bold")[目录]],
    depth: 3,
  )
  pagebreak()
}
#let references-cn() = [
#heading(numbering: none, outlined: true)[参考文献]
#{ set par(first-line-indent: 0pt, spacing: 0.35em); include("references.typ") }
]
#let appendix-cn(file: "sections/A_code.typ") = [
#heading(numbering: none, outlined: true)[附录 A #h(1em) 核心代码]
#include(file)
]

#let three-line-table(caption, columns, header, body, inset: (x: 0.35em, y: 0.52em), cell-align: center) = {
  let col-count = header.len()
  let body-rows = calc.floor(body.len() / col-count)
  let bottom-y = body-rows + 1
  let styled-header = header.map(cell => strong(cell))

  block(width: 100%, breakable: false)[
    #align(center)[
      #box[
        #align(center)[#text(font: hei-font, size: 10.5pt, weight: "bold")[#caption]]
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

#counter(page).update(1)

#paper-title[[基于大数据驱动的足球世界杯赛事预测与赛程资源协同优化]]

#abstract-cn[
  [本文围绕"大数据驱动的足球世界杯赛事预测与赛程资源协同优化"问题，构建了涵盖转播观看人数预测、赛程协同优化、动态资源调整与实际赛程评价的完整建模链路，对 48 队 12 组 72 场小组赛模拟赛事进行求解。

  针对问题一，以 historical_matches 中 560 条训练数据为基础，构造赛前可知特征（赔率隐含概率、Elo/排名差、球迷基础和、赛事类型、时区、现场观众等共 41 维），采用 Lasso、HistGradientBoosting 与 Ridge 三模型，其中 Lasso（$alpha=0.75$）CV 最优（MSE=198.10，$R^2=0.638$），最终用 0.9 Lasso + 0.1 Ridge 混合输出。加入 attendance 特征后 MSE 从 208 降至 198（改善 4.8%）。输出 140 场测试集预测（均值 145.37 百万）与 72 场小组赛预测（均值 164.65 百万）。

  针对问题二，建立 $Z_2 = 0.25T+0.25B+0.15U+0.10H-0.08C-0.07D-0.06F-0.04R$ 的综合目标函数，决策变量为 72 场的场馆与开球时段。采用贪心初始（按轮次划分日期窗口保证 60 小时休息可行）+ 模拟退火 + 6 起点并行 + 定向修复 + warm-start SA 精修。最终 $Z_2 = 19.11$，9 类约束全部 0 违反。

  针对问题三，在第三轮 24 场固定赛程上，严格按题面 14 式公式链更新球队竞技状态 $S_t$、进球均值 $lambda_i$、晋级概率 $p_t$（蒙特卡洛 20000 次，向量化实现）、更新吸引力 $A_i$、现场/转播需求与各类风险，再以分场枚举离散决策 + $delta$ 一维优化 + 每日容量耦合调整求解 $Z_3$。动态方案 $Z_3 = 7.94$，静态方案 $Z_3 = 6.65$，动态改善 19.18%，全部场次动态净效益不低于静态。

  针对问题四，采集 2022 卡塔尔世界杯 48 场小组赛实际赛程，采用与问题二相同的指标定义与标准化方法，对规模差异用人均/比例口径处理。对比显示优化方案在平均休息时间（147.6h vs 98.0h）、黄金时段覆盖率（80.6% vs 33.3%）上显著占优，实际方案因单时区在跨时区负担上占优。]
][
  [足球世界杯] #h(1em) [转播观看人数预测] #h(1em) [赛程协同优化] #h(1em) [动态资源调整] #h(1em) [蒙特卡洛] #h(1em) [模拟退火]
]

#pagebreak()

#include("sections/1_restatement.typ")
#include("sections/2_analysis.typ")
#include("sections/3_assumptions.typ")
#include("sections/4_symbols.typ")
#include("sections/5_problem1.typ")
#include("sections/6_problem2.typ")
#include("sections/7_problem3.typ")
#include("sections/8_problem4.typ")
#include("sections/10_sensitivity.typ")
#include("sections/11_evaluation.typ")


#pagebreak()
#heading(numbering: none, outlined: true)[AI 工具使用声明]

本参赛队在竞赛过程中使用了 AI 工具，主要用于语言润色、代码调试与论文排版辅助，详细使用情况见支撑材料。

#pagebreak()
#references-cn()
#pagebreak()
#appendix-cn()
