# 待办事项

- [x] 1. 赛题分析与建模设计 - `2analysis-modeling`
- [x] 2. 编程实现和图表生成 - `3coding-visual`
- [x] 3. 流程与架构图绘制 - `4drawio`
- [x] 4. 竞赛论文撰写 - `5writing`
- [x] 5. 验证和验收 - `6verity`

## 阶段细化（随推进更新）

### 阶段1 赛题分析与建模设计 `2analysis-modeling`
- [ ] 确认四问输入/输出/决策变量/评价指标/约束与递进依赖
- [ ] 列出关键假设（SOH 定义、80% 阈值、放电一致、C1/Q1/C2 关系、静置段忽略等）
- [ ] 问题1：数据整理方案 + 寿命定义（首次 SOH≤0.8 的循环或拟合外推）
- [ ] 问题2：C1/Q1/C2 非独立 → 分组统计 + 显著性检验 + 因子/相关分析框架
- [ ] 问题3：SOH 预测模型选型（防泄露）、特征工程、精度评价方案、早期数据长度敏感性
- [ ] 问题4：充电时间模型 + SOH 衰减模型 + 多目标优化（已有策略优先，外推限制）
- [ ] 产出 `reports/ANALYSIS_MODELING_REPORT.md`

### 阶段2 编程实现和图表生成 `3coding-visual`
- [ ] `code/utils.py`：数据读取、policy 解析、寿命提取、SOH 曲线工具
- [ ] `code/problem1.py`：整理表、SOH 曲线、寿命分布、长/短寿策略
- [ ] `code/problem2.py`：显著性检验、C1/Q1/C2 关系、SOC 区间衰减特征
- [ ] `code/problem3.py`：特征提取、SOH 预测、151~200 预测、寿命预测、精度评价、数据长度敏感性
- [ ] `code/problem4.py`：充电时间模型、SOH 衰减估计、多目标优化、推荐策略对比
- [ ] `results/`：结果表与 JSON，可追溯到论文数值
- [ ] `figures/`：数据图（趋势/分布/对比/关系）
- [ ] `reports/RESULTS_REPORT.md`

### 阶段3 流程与架构图绘制 `4drawio`
- [ ] 总体技术路线图
- [ ] 各子问题求解流程图
- [ ] 模型结构图（预测模型、优化模型）
- [ ] `figures/*.drawio` + 导出 PDF、`reports/DRAWIO_REPORT.md`

### 阶段4 竞赛论文撰写 `5writing`
- [ ] 按策联杯规范裁剪 `zh/default` 模板（摘要专用页、无目录、≤30 页正文、附录、AI 声明）
- [ ] 摘要（覆盖四问方法与关键结果）
- [ ] 各章节按问题展开，插入数据图与非数据图
- [ ] 参考文献、AI 工具使用声明、附录（源码列表 + AI 详情）
- [ ] `paper/main.typ` + `sections/`，typst 编译通过

### 阶段5 验证和验收 `6verity`
- [ ] 可复现性（代码一键运行、随机种子）
- [ ] 数值一致性（论文 vs 结果记录）
- [ ] 格式规范（摘要页、页码、附录、AI 声明、≤30 页正文）
- [ ] 提交就绪（论文单 PDF ≤20MB、支撑材料 RAR/ZIP ≤20MB）
- [ ] `reports/VERIFY_REPORT.md`
