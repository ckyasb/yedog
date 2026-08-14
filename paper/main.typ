#let body-font = ("Times New Roman", "SimSun", "NSimSun", "Songti SC", "STSong")
#let song-font = ("SimSun", "NSimSun", "Songti SC", "STSong", "Times New Roman")
#let hei-font = ("Heiti SC", "STHeiti", "Noto Sans CJK SC", "Songti SC", "STSong")
#let kai-font = ("KaiTi", "Kaiti SC", "STKaiti", "SimSun", "Songti SC")

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

#set document(title: "海上油田人员直升机运载计划编排", author: ())
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
#show raw: set text(size: 10pt, font: ("Courier New", "Menlo", "SimSun", "Songti SC"))
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
// 策联杯规范：不要目录页；页码从摘要页开始（已 set numbering: "1"）
#let references-cn() = [
#heading(numbering: none, outlined: true)[参考文献]
#{ set par(first-line-indent: 0pt, spacing: 0.35em); include("references.typ") }
]
// 策联杯规范：参考文献前设"AI 工具使用声明"
#let ai-declaration() = [
#heading(numbering: none, outlined: true)[AI 工具使用声明]
#par(first-line-indent: 2em)[本参赛队在竞赛过程中使用了 AI 工具，主要用于语言润色、代码调试与排版辅助，详细使用情况见支撑材料。]
]
#let appendix-cn(file: "sections/A_code.typ") = [
#heading(numbering: none, outlined: true)[附录 A #h(1em) 核心代码]
#include(file)
]


#counter(page).update(1)

#paper-title([海上油田人员直升机运载计划编排])

#abstract-cn[
  海上油田人员运输由直升机执行，涉及出海、海返与穿梭三类需求，并受架次结构、座位容量、续航（加油）、时间窗与机队配额等多重约束。本文针对 3 座陆地机场与 52 座海上设施（含 8 处可加油点）的网络，建立带取送货、座位动态复用与续航约束的分层优化模型，目标为最小化总飞机使用时间，并依次优化人员总在途时间、座位利用率、油耗与架次数。

  对于问题一（1600 条单向出海需求），按目的设施聚类，以单设施独立解为起点，采用大邻域搜索（ALNS）跨簇迁移设施进行合并优化，并通过续航门控自动插入加油点。求得总飞机使用时间 17612 min（293.5 h），110 架次，座位利用率 0.4305，相对 per-facility 强下界的 gap 为 4.2%。

  对于问题二（4000 条出海、海返与穿梭联合需求），以设施为中心构造往返环，实现出海与海返的座位动态复用，并嵌入穿梭人员。求得总飞机使用时间 28602 min（476.7 h），167 架次，座位利用率 0.5591，gap 为 5.3%，架次数与下界一致。

  对于问题三（4000 条带时间窗与任务类型的多日排班，24 架飞机配额），采用两阶段策略：阶段 A 排非临时 3840 条得总飞机使用时间 $T_0$=53358 min，阶段 B 将 160 条临时任务以零额外时间插入现有架次，阶段 C 空位补客将未排需求塞入已有架次空位。最终临时任务满足 159/160（98.1%），非临时服务 3713/3840（96.7%）。所有结果均经独立校验，续航、时刻链、运营窗与周转约束全部满足。
][
  直升机运载 #h(1em) 车辆路径问题 #h(1em) 续航约束 #h(1em) 大邻域搜索 #h(1em) 座位动态复用
]

// 策联杯规范：第二页起正文，不要目录页

#include "sections/1_restatement.typ"
#include "sections/2_analysis.typ"
#include "sections/3_assumptions.typ"
#include "sections/4_symbols.typ"
#include "sections/5_problem1.typ"
#include "sections/6_problem2.typ"
#include "sections/7_problem3.typ"
#include "sections/8_sensitivity.typ"
#include "sections/9_evaluation.typ"

#pagebreak()
// 策联杯规范：参考文献前设 AI 工具使用声明
#ai-declaration()
#pagebreak()
#references-cn()
#pagebreak()
#appendix-cn()
