# DrawIO 图示生成报告

## 图示清单

| 文件 | 类型 | 来源依据 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `figures/fig_roadmap.pdf` | 技术路线图 | ANALYSIS_MODELING_REPORT §1 总体框架 | 绪论/问题重述，展示四问递进与数据流 | ✅ 生成 |
| `figures/fig_flow_q1.pdf` | 子问题求解流程图 | RESULTS_REPORT §问题一 | 问题一节，HGB+Ridge 混合预测流程 | ✅ 生成 |
| `figures/fig_flow_q2.pdf` | 子问题求解流程图 | RESULTS_REPORT §问题二 | 问题二节，贪心+SA 协同优化流程 | ✅ 生成 |
| `figures/fig_flow_q3.pdf` | 子问题求解流程图 | RESULTS_REPORT §问题三 | 问题三节，14 式公式链+蒙特卡洛流程 | ✅ 生成 |
| `figures/fig_pipeline.pdf` | 数据处理流程图 | ANALYSIS_MODELING_REPORT §2 数据处理方案 | 数据与预处理节，单一数据源→校验→特征→归一化 | ✅ 生成 |
| `figures/fig_index_system.pdf` | 指标体系图 | ANALYSIS_MODELING_REPORT §3 符号说明 + objective_weights | 问题二/三目标函数节，收益类(正)+成本风险类(负)指标层次 | ✅ 生成 |

## 渲染方式说明

- **drawio CLI 不可用**（环境未安装 drawio 命令），故不产出 `.drawio` 源文件，改用 `code/make_drawio.py`（matplotlib FancyBboxPatch + FancyArrowPatch）渲染概念图为矢量 PDF。
- 这些是**非数据型概念图**（流程/路线/体系），不涉及数值，matplotlib 渲染满足论文矢量插入需求。
- 若需可编辑 `.drawio` 源文件，可后续安装 `drawio` CLI 后用 `code/make_drawio.py` 的布局描述重新生成；当前 PDF 已可直接被 Typst `#figure(image(...))` 引用。

## 未生成图示及原因

- 未生成 `fig_model`（模型结构图）：问题三的 14 式公式链已由 `fig_flow_q3.pdf` 完整覆盖，无需重复。
- 未生成 `fig_decision_tree`（决策树图）：本题为预测/优化/评价类，无分类规则分支需要图示。
- 未生成单独的 P4 流程图：P4 流程简单（采集→同口径指标→对比），已在 `fig_roadmap` 中体现，不单独成图避免凑数。

## 导出与自检记录

- 全部 6 张图均成功导出 PDF，文件非空（47KB–74KB）。
- 自检：
  - 节点无重叠（box 坐标手工排布，留白充足）。
  - 箭头方向清晰，未穿过核心节点。
  - 字号统一（标题 10–12pt，节点 7.5–9pt，注释 8pt），边框风格一致（圆角 FancyBboxPatch，线宽 1.4）。
  - 配色：蓝(P1/数据)、绿(P2/收益/输出)、橙(P3/特征)、红(P4/成本风险)、紫(P3 公式)、灰(数据源)。
  - 中文使用 Noto Sans CJK SC（已注册 ttc）。
  - 不与 `3coding-visual` 的 13 张数据图重复（本阶段全部为流程/路线/体系概念图）。

## 给论文阶段的嵌入建议

| 图 | 建议章节 | 建议 caption（Typst） |
| --- | --- | --- |
| fig_roadmap | 问题重述/总体方法 | 图 1 总体技术路线：四问递进与数据流 |
| fig_pipeline | 数据预处理节 | 图 2 数据处理流程：单一数据源到统一建模输入 |
| fig_flow_q1 | 问题一 | 图 3 问题一求解流程：HGB+Ridge 混合预测 |
| fig_flow_q2 | 问题二 | 图 4 问题二求解流程：贪心初始+模拟退火协同优化 |
| fig_flow_q3 | 问题三 | 图 5 问题三求解流程：14 式公式链与蒙特卡洛 |
| fig_index_system | 问题二/三目标函数 | 图 6 综合评价指标体系：收益类与成本风险类 |

Typst 插入示例（5writing 使用）：
```typst
#figure(image("../../figures/fig_roadmap.pdf", width: 90%), caption: [图 1 总体技术路线])
```
