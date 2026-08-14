# DrawIO 图示生成报告

## 图示清单

| 文件 | 类型 | 来源依据 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `fig_roadmap.drawio` / `.pdf` | 技术路线图 | ANALYSIS 总体框架 + 四问递进 | 放入绪论/问题重述，展示整体解题路线 | ✅ |
| `fig_pipeline.drawio` / `.pdf` | 数据处理流程图 | ANALYSIS §2 数据处理方案 | 放入数据预处理节 | ✅ |
| `fig_flow_q1.drawio` / `.pdf` | 问题一求解流程图 | ANALYSIS §4 + RESULTS 问题1 | 放入问题一节首 | ✅ |
| `fig_flow_q2.drawio` / `.pdf` | 问题二求解流程图 | ANALYSIS §5（三参数非独立） | 放入问题二节首 | ✅ |
| `fig_flow_q3.drawio` / `.pdf` | 问题三求解流程图 | ANALYSIS §6（防泄露） | 放入问题三节首 | ✅ |
| `fig_flow_q4.drawio` / `.pdf` | 问题四求解流程图 | ANALYSIS §7（多目标优化） | 放入问题四节首 | ✅ |
| `fig_model_q3.drawio` / `.pdf` | 问题三预测模型结构图 | RESULTS 问题3 特征工程+RF递归 | 放入问题三模型描述 | ✅ |
| `fig_model_q4.drawio` / `.pdf` | 问题四优化模型结构图 | ANALYSIS §7 决策变量/目标 | 放入问题四模型描述 | ✅ |

## 未生成图示及原因

- 未生成"指标体系图"：本题非评价类（无准则层/指标层结构），不适用。
- 未生成"决策树/规则图"：无分类规则分支。
- 未生成"变量关系图"：C1/Q1/C2 的耦合关系已在 `fig_model_q4` 与 `fig_flow_q2` 中体现，不重复。

## 导出与自检记录

- **本机无 `drawio` 二进制、无 X 显示服务器**，无法用 `drawio --export` 直接将 `.drawio` 转 PDF。
- 采用方案：每张图同时产出 **`.drawio` 源文件**（可在 draw.io/desktop 编辑，含真实节点与边 XML）与 **`.pdf`**（用 `graphviz(dot)` 按相同拓扑渲染，等效图）。两者节点、边、层级一致。
- 字体：统一 `Noto Sans CJK SC`，PDF 已嵌入中文（`pypdf` 抽取验证：`fig_roadmap.pdf` → "图1 总体技术路线图…"、`fig_flow_q1.pdf` → "图3 问题一求解流程图…"，CJK 正常）。
- 样式统一：过程节点蓝（`#dbeafe`）、数据节点黄（`#fef9c3`）、流程/管道绿（`#dcfce7`）、模型节点粉（`#ffe4e6`）、输出节点紫（`#fae8ff`）、判断节点橙菱形（`#fed7aa`）。同类节点风格一致，无装饰阴影/渐变。
- XML 自检：`fig_roadmap.drawio`(19 cells)、`fig_flow_q2.drawio`(18 cells)、`fig_model_q3.drawio`(26 cells) 均通过 `ElementTree` 解析，节点无重叠、边不穿核心节点（按拓扑 BFS 分层布局）。
- 节点文字短、双行，未堆长句；图内无大段解释。

## 与 3coding-visual 的边界

- 本阶段仅产非数据图（路线/流程/模型结构）。
- **未重复绘制** `p1_*.pdf`、`p2_*.pdf`、`p3_*.pdf`、`p4_*.pdf` 等数据图（由 3coding-visual 生成）。
- 未修改 `code/`、未改写 `RESULTS_REPORT.md` 数值。

## 给论文阶段的嵌入建议

建议位置与 caption（最终 Typst 插入代码由 `5writing` 按章节决定）：

| 图 | 建议章节 | 建议 caption |
| --- | --- | --- |
| `fig_roadmap` | 绪论/问题分析末 | 图1 锂离子电池快充策略寿命建模总体技术路线 |
| `fig_pipeline` | 数据预处理 | 图2 数据清洗与特征工程流程 |
| `fig_flow_q1` | 问题一节首 | 图3 问题一求解流程 |
| `fig_flow_q2` | 问题二节首 | 图4 问题二策略参数影响分析流程 |
| `fig_flow_q3` | 问题三节首 | 图5 问题三电池寿命预测流程 |
| `fig_flow_q4` | 问题四节首 | 图6 问题四充电策略优化流程 |
| `fig_model_q3` | 问题三模型 | 图7 SOH 预测模型结构（随机森林递归） |
| `fig_model_q4` | 问题四模型 | 图8 兼顾充电时间与寿命的优化模型结构 |

> 注：`.pdf` 由 graphviz 渲染，`.drawio` 为可编辑源。如提交方需要原生 drawio 导出的 PDF，可在装有 drawio desktop 的环境用 `drawio --export --format pdf --crop figures/<name>.drawio` 重新导出覆盖。
