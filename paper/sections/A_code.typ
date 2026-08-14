#v(1.1em)

本附录列出核心源程序代码（完整代码与运行说明见支撑材料）。全部代码以 Python 3.12 实现，依赖 numpy、scipy、pandas、matplotlib、scikit-learn、openpyxl，随机种子 `SEED=20260814`。运行方式：

```bash
cd ~/yegou/C题
python3 code/data_loader.py        # 数据校验
python3 code/problem1.py           # 问题一预测
python3 code/problem2.py           # 问题二优化（约 5-8 分钟）
python3 code/problem3.py           # 问题三动态资源（含 20000 次蒙特卡洛）
python3 code/problem4.py           # 问题四实际赛程评价
python3 code/make_figures.py       # 数据图
python3 code/make_drawio.py       # 非数据图
```

由于篇幅所限，以下仅展示问题一主模型与问题二目标函数核心片段，完整代码（含 data_loader.py、utils.py、problem1-4.py、make_figures.py、make_drawio.py，共约 2600 行）见支撑材料。

== 问题一：特征构造与混合预测（节选）

```python
# code/problem1.py 节选：赛前特征构造与混合预测
def build_features(hist, teams):
    df = hist.copy()
    # join teams 球队属性
    ta = teams.rename(columns={c: c + "_a" for c in [...]})
    df = df.merge(ta, on="team_a", how="left").merge(tb, on="team_b", how="left")
    # 赔率隐含概率（赛前可知）
    inv_a = 1.0 / df["odds_a"]; inv_d = 1.0 / df["odds_draw"]; inv_b = 1.0 / df["odds_b"]
    s = inv_a + inv_d + inv_b
    df["p_a"] = inv_a / s; df["p_draw"] = inv_d / s; df["p_b"] = inv_b / s
    df["suspense"] = 1.0 - np.maximum(df["p_a"], df["p_b"])  # 悬念指标
    df["entropy"] = -(df["p_a"]*np.log(df["p_a"]+1e-12) + df["p_draw"]*np.log(df["p_draw"]+1e-12) + df["p_b"]*np.log(df["p_b"]+1e-12))
    df["elo_gap"] = (df["elo_a"] - df["elo_b"]).abs()
    df["fan_sum"] = df["fan_base_index_a"] + df["fan_base_index_b"]
    # ... 共 40 维赛前特征
    return df, feat_cols

# 5 折 GroupKFold 防时序泄露 + HGB/Ridge 混合
gkf = GroupKFold(n_splits=5)
groups_id = pd.to_datetime(train["date"]).dt.strftime("%Y%m").astype(int).values
# CV: Ridge MSE=208.23 R2=0.620 | HGB MSE=272.55 R2=0.500
hgb = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.1, max_leaf_nodes=15, l2_regularization=2.0)
rg = Ridge(alpha=10.0)
# 混合预测：0.5*HGB + 0.5*Ridge
test_pred = 0.5 * hgb.predict(Xte) + 0.5 * rg.predict(sc_full.transform(Xte))
```

== 问题二：目标函数与约束（节选）

```python
# code/problem2.py 节选：Z2 目标函数与约束回代
def objective_terms(G, venue_of, slot_of):
    # T/B/C/D min-max 归一化；U/H/F/R 已 [0,1]
    Tn[m] = (T_raw - T_lo) / (T_hi - T_lo) if T_hi > T_lo else 0
    Bn[m] = (B_raw - B_lo) / (B_hi - B_lo) if B_hi > B_lo else 0
    Cn[m] = (C_raw - C_lo) / (C_hi - C_lo) if C_hi > C_lo else 0
    D[m] = travel_burden(G, m, v, assign_prev_round)  # 全局 min-max 归一化
    R[m] = 0.5*climate + 0.3*(att/cap) + 0.2*(req_sec/sec_level)
    F = 0.5*(gold_range/3) + 0.5*(big_range/3)  # 方案级公平性
    Z2 = sum(0.25*Tn + 0.25*Bn + 0.15*U + 0.10*H - 0.08*Cn - 0.07*D - 0.04*R) - 0.06*F

def check_constraints(G, venue_of, slot_of):
    # 9 类约束逐一回代：场馆同时段不撞、60h 双向休息、单日/总场次、
    # 黄金时段公平极差≤2、安保资格、R3 每日高等级容量、broadcast_capacity、同组同轮不同时段
```

== 问题三：14 式公式链（节选）

```python
# code/problem3.py 节选：蒙特卡洛与风险公式
def monte_carlo(lam, bp_r3, seed=20260814):
    rng = np.random.default_rng(seed)
    for it in range(20000):  # 题面硬性 20000 次
        ga = rng.poisson(lam_arr); gb = rng.poisson(lam_b_arr)
        # 按积分→净胜球→总进球排名；前2+最好8个第三名晋级；并列等比例
    return p_t, cond_p  # 晋级概率与条件晋级概率

# 公式11-14: 无激励风险、默契风险、动态安保、综合风险
R_noeff = 0.5*(2*p_a-1)**2 + 0.5*(2*p_b-1)**2
R_coll = np.clip(D_i*(1-np.clip(G_i,0,1))*(1-0.35*R_noeff), 0, 1)
d_i = np.clip(0.45*d0 + 0.25*O_i + 0.15*A + 0.15*(R_noeff+R_coll)/2, 0, 1)
R = 0.40*R_noeff + 0.40*R_coll + 0.20*d_i*m_s
# Max Z3 = sum[0.35*TV* + 0.35*BV* + 0.10*A* - 0.10*C* - 0.10*R*]  (* 为 min-max 归一化)
```

== 问题四：实际赛程采集与对比（节选）

```python
# code/problem4.py 节选：2022 卡塔尔世界杯 48 场赛程
WC2022_GROUP = [("A",1,"Qatar","Ecuador","Al Bayt","Al Khor","Qatar","2022-11-20","19:00","2022-11-20 16:00",0,2), ...]
SOURCE_URL = "https://www.fifa.com/fifaplus/en/tournaments/mens/worldcup/qatar2022"
# 规模差异用人均/场均/比例标准化：场均使用场馆数、平均休息时间、黄金时段覆盖率等
```
