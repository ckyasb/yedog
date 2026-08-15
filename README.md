# yedog — 锂离子电池快充策略优化建模

> 策联杯数学建模竞赛 · A题：兼顾充电时间与循环寿命的锂电池快充策略优化

本项目以 MIT–Stanford 锂电池循环数据集为基础，建立"充电时间—SOH 衰减—循环寿命"的完整建模链，在四个子问题上给出定量结论与可复现的推荐快充策略。

---

## 一、问题背景与数据

- **电池**：49 块 A123 18650 LFP 电池，9 种两阶段快充策略
- **数据规模**：9 350 条循环记录，含每循环 SOH、温度、内阻、充电时间
- **决策变量**：$C_1$（第一阶段倍率）、$Q_1$（SOC 切换点）、$C_2$（第二阶段倍率）
- **关键阈值**：SOH = 80% 为寿命终点；额定容量 1.1 Ah

> **核心难点**：数据集中无电池在观测窗口内达到 80% SOH，寿命须由 SOH 衰减趋势外推；且 `NEWSTRUCTURE` 标记的未记录结构差异是重要混杂变量（同一参数 (4.8, 80, 4.8) 下 NEWSTRUCTURE 与非 NEWSTRUCTURE 电池寿命相差约 5 倍）。

---

## 二、四个子问题与方法

| 子问题 | 目标 | 核心方法 | 关键指标 |
|---|---|---|---|
| **P1 寿命估计** | 估计各电池/策略循环寿命 | 分段稳态斜率 + 线性/指数/幂律多模型集成 + Bootstrap 95% CI | 稳态寿命中位数 |
| **P2 影响分析** | 量化 $C_1, Q_1, C_2$ 对衰减的影响 | Kruskal–Wallis + 10000 次置换检验 + 岭回归(含交互) + 偏相关 + 随机森林置换重要性 | $H=21.40,\ p=0.0062$；Ridge $R^2=0.621$ |
| **P3 SOH 预测** | 预测 151–200 循环 SOH 并外推寿命 | 递归随机森林（含 `is_new` + `slope_recent` 特征），40 电池留出验证 | RMSE = 0.00128 |
| **P4 策略优化** | 兼顾充电时间与寿命的多目标优化 | 解析充电时间模型 + log 空间衰减模型 + Pareto 前沿 + 加权综合 | $R^2_{\text{log}}=0.805$ |

### 核心结论

1. **$C_2$ 与 NEWSTRUCTURE 是寿命衰减的主导因素**：随机森林置换重要性 $C_2 = 57.3\%$、`is_new` = 36.6%。控制其他变量后 $C_2$ 偏相关 $r = -0.459\ (p = 0.0009)$，表明第二阶段倍率越高寿命越短。
2. **中高 SOC 段高倍率是加速衰减的主因**：`3_7C-31PER-5_9C` 在 31%–80% SOC 段以 5.9C 充电，$E_{\text{high}} = 289$ 为全数据集最大，衰减最快。
3. **推荐快充策略**：$C_1 = 5.56,\ Q_1 = 79,\ C_2 = 4.90$，充电时间 8.87 min，模型预测寿命 16 101 次。该策略将 SOC 切换点后移至 $Q_1 = 79\%$，使中高 SOC 段高倍率暴露 $E_{\text{high}} \approx 4.9$ 极低，符合"降中高 SOC 倍率换长寿命"的机制。

---

## 三、目录结构

```
yedog/
├── code/                       # 全部 Python 脚本
│   ├── utils.py                 # 共享工具（数据加载、字体、寿命外推）
│   ├── problem1.py / problem1_opt.py / problem1_piecewise.py
│   ├── problem2.py / problem2_opt.py / problem2_deep_opt.py
│   ├── problem3.py / problem3_opt.py / problem3_v3.py
│   ├── problem4.py / problem4_opt.py / problem4_deep_opt.py / problem4_bayes.py
│   └── make_drawio.py           # 流程图生成
├── paper/                      # Typst 论文源码
│   ├── main.typ                 # 入口（字体、布局、摘要页）
│   ├── defs.typ                 # 三线表共享函数
│   ├── sections/                # 各章节 .typ
│   └── main.pdf                 # 编译产物（42 页, 6.5 MB）
├── figures/                    # 全部图表（PDF）
├── results/                    # JSON / CSV 结果与中间数据
├── reports/                    # 阶段性分析报告
├── data/                       # 原始数据（未纳入仓库）
└── README.md
```

---

## 四、复现方式

```bash
# 1. 生成全部结果与图表（按顺序执行）
cd code
python3 utils.py
python3 problem1.py && python3 problem1_opt.py && python3 problem1_piecewise.py
python3 problem2.py && python3 problem2_opt.py
python3 problem3.py && python3 problem3_v3.py
python3 problem4.py && python3 problem4_deep_opt.py && python3 problem4_bayes.py

# 2. 编译论文
cd ../paper
typst compile --root .. main.typ
```

依赖：Python 3.10+，`numpy pandas scipy scikit-learn matplotlib`；Typst（论文编译）；Noto Serif/Sans CJK SC 字体。

---

## 五、关键指标速查

| 指标 | 数值 | 来源 |
|---|---|---|
| Kruskal–Wallis $H$ | 21.40 | `results/p2_kw.json` |
| 置换检验 $p$ | 0.0015 | 同上 |
| 岭回归 $R^2$ | 0.621 | `results/p2_regression.json` |
| $C_2$ 偏相关 | −0.459 ($p = 0.0009$) | 同上 |
| 随机森林 $C_2$ 重要性 | 57.3% | 同上 |
| P3 递归 RMSE | 0.00128 | `results/p3_*` |
| P4 衰减模型 $R^2_{\text{log}}$ | 0.805 | `results/p4_bayes_optimized.json` |
| **推荐策略** | $C_1=5.56,\ Q_1=79,\ C_2=4.90$ | 同上 |
| 推荐寿命 / 充电时间 | 16 101 次 / 8.87 min | 同上 |

---

## 六、技术栈

- **建模**：Python（numpy / pandas / scipy / scikit-learn / matplotlib）
- **论文**：Typst（zh 模板，Noto CJK SC 字体）
- **可复现性**：所有数值由脚本生成并写入 `results/*.json`，论文文字与结果一一对应

---

## 七、分支说明

- `A` 分支：完整建模项目（代码 + 论文 + 图表 + 结果）
- `main` 分支：项目说明（本 README）

---

*本项目为竞赛建模作品，推荐策略基于早期线性/对数衰减假设的探索性结论，实际工程应用须经实验验证。*
