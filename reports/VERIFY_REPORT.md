# 验证和验收报告

## 结论
**PASS**

## 检查项
| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 论文入口存在 | ✅ | `paper/main.typ` 存在，Typst 引擎 |
| 核心正文完整 | ✅ | 8 个章节文件 + A_code 附录，均含一级标题 |
| 入口 include 数量 | ✅ | 8 个 `#include` + references + appendix，匹配 9 个 section 文件 |
| 章节标题顺序 | ✅ | 问题重述→模型假设→符号说明→问题一~四→模型评价 |
| 占位符清除 | ✅ | writing_check.sh PASS，无 TODO/占位符 |
| 内部文件名泄露 | ✅ | writing_check.sh 无内部文件名告警 |
| 图片引用 | ✅ | 24 张图全部在正文引用，PDF 中 18 页含图 |
| 数值一致性 | ✅ | 17/17 关键数值交叉检查通过 |
| Typst 编译 | ✅ | `typst compile` 成功，无 error/warning |
| PDF 非空 | ✅ | 42 页，6.7 MB |
| 摘要专用页 | ✅ | 第 1 页含标题+摘要+关键词 |
| 正文 ≤30 页 | ✅ | 正文 23 页（第 2~24 页） |
| 无目录 | ✅ | 删除了 toc-page |
| AI 声明位置 | ✅ | 在参考文献前（第 24 页） |
| 附录含源码 | ✅ | utils.py + problem1~4.py 全部可运行代码 |
| 无身份信息 | ✅ | 无 ckyasb/学校/姓名/学号，路径已脱敏 |
| CJK 渲染 | ✅ | Noto Sans/Serif CJK SC，已嵌入 |
| 视觉检查 | ✅ | 抽样页：摘要/正文/AI声明/参考文献，版式正常 |

## 章节结构

```
paper/main.typ
├── sections/1_restatement.typ     → 问题重述（含总体技术路线图）
├── sections/2_assumptions.typ     → 模型假设（7 条）
├── sections/3_symbols.typ         → 符号说明（18 项三线表）
├── sections/4_problem1.typ        → 问题一（寿命外推+分布+长/短寿对比）
├── sections/5_problem2.typ        → 问题二（KW+置换+岭回归+偏相关+RF）
├── sections/6_problem3.typ       → 问题三（防泄露+RF递归+寿命预测）
├── sections/7_sensitivity.typ    → 问题四（充电时间模型+多目标优化）
├── sections/8_evaluation.typ     → 模型评价与推广
└── sections/A_code.typ           → 核心代码（5 个 .py 文件）
```

## 图表引用

24 张图（17 数据图 + 8 非数据图，其中 roadmap 含在正文），全部在 `figures/` 目录中存在且在正文中引用。`writing_check.sh` 未报告缺失图片。

## 数值一致性

17 项关键数值交叉检查全部通过（论文 PDF vs `results/*.json`）：

| 检查项 | 论文值 | 结果 |
| --- | --- | --- |
| P1 寿命范围 1106~18109 | ✓ | PASS |
| P1 长寿 3_6C-80PER 18109 | ✓ | PASS |
| P2 KW p=0.0081 | ✓ | PASS |
| P2 置换 p=0.0022 | ✓ | PASS |
| P2 C2 占比 93.9% | ✓ | PASS |
| P2 C2 偏相关 -0.409 | ✓ | PASS |
| P3 RF RMSE 0.00131 | ✓ | PASS |
| P3 MAPE 0.112% | ✓ | PASS |
| P3 last_SOH 88.4% | ✓ | PASS |
| P3 #2 寿命 18995 | ✓ | PASS |
| P3 #16 寿命 1330 | ✓ | PASS |
| P4 推荐 C1=5.8 | ✓ | PASS |
| P4 推荐 Q1=64 | ✓ | PASS |
| P4 推荐 C2=4.5 | ✓ | PASS |
| P4 充电时间 8.98 min | ✓ | PASS |
| P4 寿命 14850 | ✓ | PASS |
| P4 充电时间 R²=0.587 | ✓ | PASS |

## 文本质量门禁

`writing_check.sh` 输出：
```
INFO: section file count: 9
INFO: main include count: 9
INFO: citation markers detected
PASS: writing text gate passed
```

- 章节文件数与 include 数一致（9=9）
- 无占位符（TODO/待补充/示例数据）
- 无内部文件名泄露（reports/、figures/、code/）
- 参考文献 4 篇真实存在（Severson 2019、Attia 2020 等）

## 编译

```bash
cd paper
typst compile --root /home/ckyasb/yegou/A main.typ
```
- 退出码 0
- 无 error，无 warning
- 输出 `main.pdf`，42 页，6.7 MB

## PDF 视觉检查

抽取第 1、6、24、25 页为 PNG 逐页检查：

- **第 1 页（摘要）**：标题"锂离子电池快充策略对寿命衰减的影响建模与优化"居中，"摘 要"标题，摘要内容覆盖四问方法与关键结果，关键词行完整。页码从第 1 页开始。✅
- **第 6 页（正文）**：中文渲染正常，标题/正文/公式/图表无重叠。✅
- **第 24 页（AI 声明）**："AI 工具使用声明"标题位于参考文献之前，内容符合策联杯规范。✅
- **第 25 页（参考文献）**：4 篇参考文献格式规范。✅
- **CJK 字体**：Noto Sans/Serif CJK SC 嵌入，无缺字/乱码。✅

## 仍需处理的问题

无硬错误。以下为可选优化项（不影响提交）：

- **WARN**：章节 2（模型假设）和 8（模型评价）相对较短（623/712 字符），但内容完整，不影响验收。
- **WARN**：`4drawio` 生成的 PDF 由 graphviz 渲染（本机无 drawio 二进制），`.drawio` 源文件可供编辑，如需原生 drawio 导出可在装有 drawio desktop 的环境重新导出。

## 提交就绪

- **参赛论文**：`paper/main.pdf`（42 页，6.7 MB < 20 MB）— 提交就绪 ✅
- **支撑材料**：`code/`（5 个 .py）+ `results/`（22 个 CSV/JSON）+ `figures/`（25 张 PDF + 8 个 .drawio）+ `reports/`（5 份报告）— 需打包为 RAR/ZIP ✅
- **AI 工具使用详情**：声明已在论文中（第 24 页），详细使用情况需补充到支撑材料的 `AI 工具使用详情.pdf`（竞赛要求）— 建议生成
