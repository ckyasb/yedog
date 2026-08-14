# DrawIO 图示生成报告 · 策联杯 B 题

## 图示清单

| 文件 | 类型 | 来源依据 | 用途 | 状态 |
| --- | --- | --- | --- | --- |
| `figures/fig_roadmap.drawio` + `.pdf` | 技术路线图 | ANALYSIS_MODELING_REPORT §1 总体框架 | 问题重述/绪论，展示三问方法串联 | ✅ 源+PDF |
| `figures/fig_flow_q1.drawio` + `.pdf` | 子问题求解流程 | ANALYSIS §4 + problem1.py | 问题一章节，聚类+节约+ALNS+续航门控 | ✅ 源+PDF |
| `figures/fig_flow_q2.drawio` + `.pdf` | 子问题求解流程 | ANALYSIS §5 + problem2.py | 问题二章节，PDPTW配对+座位复用+ALNS | ✅ 源+PDF |
| `figures/fig_flow_q3.drawio` + `.pdf` | 子问题求解流程 | ANALYSIS §6 + problem3.py | 问题三章节，两阶段调度+临时增量 | ✅ 源+PDF |
| `figures/fig_flight_arch.drawio` + `.pdf` | 架次架构示意 | 题面图3 + CONTEST_BRIEF §3 架次规则 | 问题二/模型假设，出海/海返/穿梭座位复用 | ✅ 源+PDF |
| `figures/fig_refuel.drawio` + `.pdf` | 续航加油决策流程 | ANALYSIS §3 续航子模型 | 模型建立，续航可行性决策树 | ✅ 源+PDF |

## 未生成图示及原因

- 未生成"指标体系图"：本题目标为分层 min（总飞机使用时间→在途/利用率/油耗/架次数），非多准则评价，无需 AHP/指标体系层次图。
- 未生成"数据处理流程图"：数据预处理简单（距离校验+分类），已在技术路线图 `fig_roadmap` 的"预处理"节点体现，不单列。
- 未生成"模型结构/变量关系图"：决策变量（架次路径、人员分配、机型、加油、时刻）关系已在 `fig_flight_arch` 与 `fig_refuel` 体现。
- 未重复生成任何数据图：所有数据图（网络分布、机型参数、续航可达性、需求构成、Q3任务类型、三问指标对比、Q1收敛、Q3临时满足、Q3每日架次）由 `3coding-visual` 的 `make_figures.py` 生成（fig1~9.pdf），本阶段不重复。

## 导出与自检记录

- **DrawIO 命令**：`drawio`/`draw.io` 均未安装（系统无 GUI 版 drawio）；`npx @hediet/drawio-cli`、`npx drawio-batch` 均 404 不可用。
- **Fallback**：保留 `.drawio` 源文件（可编辑 mxfile XML，论文阶段可在 drawio 桌面/网页版打开微调），同时用 `graphviz` (`dot`) 渲染等价矢量 PDF（`code/make_drawio_pdf.py`），保证论文可直接引用 PDF。
- **graphviz splines**：`ortho` 在多分支流程图触发 `maze.c` 断言失败，改用 `polyline` 渲染稳定，所有 6 张 PDF 均成功生成（`fig_flow_q2.pdf` 913KB 为多分支节点密集所致，可正常显示）。
- **字体**：`Noto Sans CJK SC`，中文正常显示（与 `3coding-visual` 数据图一致）。
- **自检**：6 个 `.drawio` 源文件均非空（5.2–6.9KB，29–43 个 mxCell）；6 个 PDF 均非空（70–913KB）；节点无明显重叠，箭头方向清晰，样式统一（起点蓝/处理黄/判断红/正常绿/修复橙/终点蓝）。

建议导出命令（若论文阶段安装了 drawio）：
```bash
drawio --export --format pdf --crop --output figures/fig_roadmap.pdf figures/fig_roadmap.drawio
```

## 给论文阶段的嵌入建议

| 图 | 建议章节 | 建议 caption |
| --- | --- | --- |
| `fig_roadmap` | 问题重述与分析 / 总体框架 | 图1 海上油田人员直升机运载计划编排总体技术路线 |
| `fig_flight_arch` | 模型假设 / 问题二模型建立 | 图2 单架次出海、海返与穿梭联合运输及座位动态复用示意 |
| `fig_refuel` | 模型建立 / 续航约束 | 图3 架次续航（加油）可行性决策流程 |
| `fig_flow_q1` | 问题一求解 | 图4 问题一单向出海运输求解流程 |
| `fig_flow_q2` | 问题二求解 | 图5 问题二出海+海返+穿梭联合运输求解流程 |
| `fig_flow_q3` | 问题三求解 | 图6 问题三带时间窗多日排班两阶段求解流程 |

插入代码（Typst）由 `5writing` 按引擎决定，示例：
```typst
#figure(image("../../figures/fig_roadmap.pdf", width: 90%), caption: [图1 总体技术路线])
```

**注意**：`3coding-visual` 已生成 `fig1_network.pdf`~`fig9_q3_daily.pdf`（数据图），与本阶段 `fig_roadmap` 等非数据图命名不冲突，论文阶段两类图分别引用即可。
