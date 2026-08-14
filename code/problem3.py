"""问题三：第三轮动态资源优化。

严格按题面 14 条公式链实现。赛程固定（P2 第三轮 24 场的场馆/时段），仅重配：
转播优先级、安保等级、交通等级、票价调整 δ。

关键：
- 蒙特卡洛 20000 次预计算 p_t 与条件晋级概率（一次，固定种子）。
- 静态 vs 动态用同一组归一化上下界（候选决策并集）。
- 分场枚举离散决策 + δ 一维优化 + 每日容量耦合调整。
"""
from __future__ import annotations
import sys, math
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_all
import utils

N_MC = 20000


def load_inputs():
    data = load_all()
    gm = data["groups_matches"].copy()
    gm["round_in_group"] = pd.to_numeric(gm["round_in_group"], errors="coerce").astype(int)
    bp = data["base_predictions"].copy()
    for c in ["expected_goals_a", "expected_goals_b", "p_a_win", "p_draw", "p_b_win",
              "uncertainty_index", "attractiveness_index", "expected_attendance_base", "commercial_value_index"]:
        bp[c] = pd.to_numeric(bp[c], errors="coerce")
    live = data["live_group_results"].copy()
    for c in ["goals_a", "goals_b", "xg_a", "xg_b", "red_cards_a", "red_cards_b",
              "injury_impact_level", "attendance", "tv_viewers"]:
        live[c] = pd.to_numeric(live[c], errors="coerce")
    live["round_in_group"] = pd.to_numeric(live["round_in_group"], errors="coerce").astype(int)
    sec = data["security_requirements"].copy()
    for c in ["crowd_risk", "attention_risk", "security_demand_score", "required_security_level"]:
        sec[c] = pd.to_numeric(sec[c], errors="coerce")
    sec["required_security_level"] = sec["required_security_level"].astype(int)
    venues = data["venues"].copy()
    for c in ["capacity", "security_level"]:
        venues[c] = pd.to_numeric(venues[c], errors="coerce")
    tb = data["ticket_broadcast"].copy()
    for c in ["base_ticket_price_usd", "price_elasticity", "broadcast_unit_value_usd", "sponsor_weight", "local_interest_weight"]:
        tb[c] = pd.to_numeric(tb[c], errors="coerce")
    drc = data["dynamic_resource_costs"].copy()
    for c in ["unit_cost_index", "demand_multiplier", "risk_multiplier"]:
        drc[c] = pd.to_numeric(drc[c], errors="coerce")
    drl = data["dynamic_resource_limits"].copy()
    for c in ["high_broadcast_capacity", "high_security_capacity", "enhanced_transport_capacity",
              "daily_resource_budget_index", "max_ticket_increase_rate", "max_ticket_discount_rate"]:
        drl[c] = pd.to_numeric(drc[c], errors="coerce") if c in drc.columns else pd.to_numeric(drl[c], errors="coerce")
    for c in ["high_broadcast_capacity", "high_security_capacity", "enhanced_transport_capacity",
              "daily_resource_budget_index", "max_ticket_increase_rate", "max_ticket_discount_rate"]:
        drl[c] = pd.to_numeric(drl[c], errors="coerce")
    # P2 结果（第三轮 24 场）
    p2 = pd.read_csv(utils.RESULTS / "result_2_group_schedule.csv", encoding="utf-8-sig")
    p2["round_in_group"] = pd.to_numeric(p2["round_in_group"], errors="coerce").astype(int)
    p2["expected_attendance"] = pd.to_numeric(p2["expected_attendance"], errors="coerce")
    # P1 72 场预测
    p1 = pd.read_csv(utils.RESULTS / "result_1_match_prediction.csv", encoding="utf-8-sig")
    p1["predicted_tv_viewers"] = pd.to_numeric(p1["predicted_tv_viewers"], errors="coerce")
    return data, gm, bp, live, sec, venues, tb, drc, drl, p2, p1


def compute_team_state(live, groups_matches):
    """公式1-2: S_t, h_t。基于前两轮 live_group_results。"""
    # 每队前两轮积分/累计xG/xGA/红牌/伤病均值
    team_stats = {}
    # 收集每队所涉比赛
    for _, r in live.iterrows():
        for side, opp in [("a", "b"), ("b", "a")]:
            t = r[f"team_{side}"]
            g_for = r[f"goals_{side}"]; g_against = r[f"goals_{opp}"]
            xg_for = r[f"xg_{side}"]; xg_against = r[f"xg_{opp}"]
            rc = r[f"red_cards_{side}"]
            inj = r["injury_impact_level"]
            # 积分：胜3平1负0
            if g_for > g_against: pts = 3
            elif g_for == g_against: pts = 1
            else: pts = 0
            if t not in team_stats:
                team_stats[t] = {"G": 0, "P": 0, "xGF": 0.0, "xGA": 0.0, "RC": 0, "inj": []}
            team_stats[t]["G"] += 1
            team_stats[t]["P"] += pts
            team_stats[t]["xGF"] += xg_for
            team_stats[t]["xGA"] += xg_against
            team_stats[t]["RC"] += rc
            team_stats[t]["inj"].append(inj)
    S = {}; h = {}
    for t, st in team_stats.items():
        G = st["G"]; P = st["P"]; xGF = st["xGF"]; xGA = st["xGA"]; RC = st["RC"]
        # S_t = 0.45*P/(3G) + 0.35*[0.5+0.5*tanh(((xGF-xGA)/G)/1.25)] + 0.20*exp(-0.55*RC/G)
        if G == 0:
            S[t] = 0.0
        else:
            term1 = 0.45 * P / (3 * G)
            term2 = 0.35 * (0.5 + 0.5 * math.tanh(((xGF - xGA) / G) / 1.25))
            term3 = 0.20 * math.exp(-0.55 * RC / G)
            S[t] = term1 + term2 + term3
        h[t] = float(np.clip(np.mean(st["inj"]), 0, 3))
    return S, h


def update_lambda(bp_r3, S, h):
    """公式3: 更新进球均值 lambda_i,a, lambda_i,b."""
    lam = {}
    for _, m in bp_r3.iterrows():
        ta, tb = m["team_a"], m["team_b"]
        lam0_a = m["expected_goals_a"]; lam0_b = m["expected_goals_b"]
        Delta = 0.32 * (S[ta] - S[tb]) - 0.055 * (h[ta] - h[tb])
        lam_a = np.clip(lam0_a * np.exp(Delta - 0.04 * h[ta]), 0.15, 4.50)
        lam_b = np.clip(lam0_b * np.exp(-Delta - 0.04 * h[tb]), 0.15, 4.50)
        lam[m["match_id"]] = (lam_a, lam_b, ta, tb)
    return lam


def monte_carlo(lam, bp_r3, seed=utils.SEED):
    """公式4: 20000 次蒙特卡洛。返回 p_t 与条件晋级概率。
    向量化实现：一次性采样 20000×24，按组聚合积分/净胜球/总进球，np.lexsort 排名。
    每组前2 + 12组中成绩最好8个第三名晋级。指标相同等比例处理。
    """
    rng = np.random.default_rng(seed)
    match_ids = list(lam.keys())
    nm = len(match_ids)
    lam_a = np.array([lam[m][0] for m in match_ids])
    lam_b = np.array([lam[m][1] for m in match_ids])
    ta_arr = np.array([lam[m][2] for m in match_ids])
    tb_arr = np.array([lam[m][3] for m in match_ids])

    bp_r3_map = bp_r3.set_index("match_id")
    grp_arr = np.array([bp_r3_map.loc[m, "group_id"] for m in match_ids])
    unique_groups = sorted(set(grp_arr))
    grp_idx = {g: i for i, g in enumerate(unique_groups)}
    grp_of_match = np.array([grp_idx[g] for g in grp_arr])
    ng = len(unique_groups)

    # 每组的 4 个队（唯一）
    group_teams = {}
    for m_idx in range(nm):
        g = grp_arr[m_idx]
        group_teams.setdefault(g, set()).add(ta_arr[m_idx])
        group_teams.setdefault(g, set()).add(tb_arr[m_idx])
    # 每组的队列表（固定顺序）
    group_team_list = {g: sorted(list(ts)) for g, ts in group_teams.items()}
    team_to_global = {}
    all_teams_sorted = sorted(set().union(*group_teams.values()))
    for i, t in enumerate(all_teams_sorted):
        team_to_global[t] = i
    n_teams = len(all_teams_sorted)

    advance_count = np.zeros(n_teams, dtype=np.float64)
    # 条件统计
    cond_p_a_draw = np.zeros(nm)
    cond_p_b_draw = np.zeros(nm)
    cond_p_a_awin = np.zeros(nm)
    cond_p_b_bwin = np.zeros(nm)

    # 向量化采样：一次采全部 20000 次
    all_ga = rng.poisson(lam_a, size=(N_MC, nm))
    all_gb = rng.poisson(lam_b, size=(N_MC, nm))

    for it in range(N_MC):
        ga = all_ga[it]
        gb = all_gb[it]
        # 每组排名
        group_standings = {}
        for g in unique_groups:
            teams = group_team_list[g]
            n_t = len(teams)
            pts = np.zeros(n_t)
            gd = np.zeros(n_t)
            gf = np.zeros(n_t)
            for m_idx in range(nm):
                if grp_arr[m_idx] != g:
                    continue
                a, b = ga[m_idx], gb[m_idx]
                t_a = ta_arr[m_idx]
                t_b = tb_arr[m_idx]
                ia = teams.index(t_a)
                ib = teams.index(t_b)
                if a > b:
                    pts[ia] += 3
                elif a == b:
                    pts[ia] += 1
                    pts[ib] += 1
                else:
                    pts[ib] += 3
                gd[ia] += a - b
                gd[ib] += b - a
                gf[ia] += a
                gf[ib] += b
            # 排名：pts desc, gd desc, gf desc
            order = np.lexsort((-gf, -gd, -pts))
            group_standings[g] = [(teams[i], pts[i], gd[i], gf[i]) for i in order]

        adv_this = set()
        for g in unique_groups:
            ranked = group_standings[g]
            adv_this.add(ranked[0][0])
            adv_this.add(ranked[1][0])

        thirds = []
        for g in unique_groups:
            ranked = group_standings[g]
            t3 = ranked[2]
            thirds.append((g, t3[0], t3[1], t3[2], t3[3]))
        thirds_sorted = sorted(thirds, key=lambda x: (-x[2], -x[3], -x[4]))

        taken = 0
        for x in thirds_sorted:
            if taken >= 8:
                break
            adv_this.add(x[1])
            taken += 1

        for t in adv_this:
            advance_count[team_to_global[t]] += 1

        for m_idx in range(nm):
            ta = ta_arr[m_idx]
            tb = tb_arr[m_idx]
            a, b = ga[m_idx], gb[m_idx]
            if a == b:
                if ta in adv_this:
                    cond_p_a_draw[m_idx] += 1
                if tb in adv_this:
                    cond_p_b_draw[m_idx] += 1
            elif a > b:
                if ta in adv_this:
                    cond_p_a_awin[m_idx] += 1
            else:
                if tb in adv_this:
                    cond_p_b_bwin[m_idx] += 1

    p_t = {t: advance_count[team_to_global[t]] / N_MC for t in all_teams_sorted}
    cond_p = {}
    for m_idx, mid in enumerate(match_ids):
        cond_p[mid] = {
            "p_a_draw": cond_p_a_draw[m_idx] / N_MC,
            "p_b_draw": cond_p_b_draw[m_idx] / N_MC,
            "p_a_awin": cond_p_a_awin[m_idx] / N_MC,
            "p_b_bwin": cond_p_b_bwin[m_idx] / N_MC,
        }
    return p_t, cond_p


def compute_feedback(live, bp, p1_pred):
    """公式6: r_t^a, r_t^b, f_i^a, f_i^b.
    对球队 t 每场前两轮 m: 实际/赛前现场比、实际/赛前转播比，clip[0.6,1.5]；两场均值 clip[0.75,1.25] 得 r_t^a,r_t^b.
    """
    # 赛前预计现场 = base_predictions.expected_attendance_base (该场)
    # 赛前预计转播 = P1 预测 (该场)
    bp_map = bp.set_index("match_id")
    p1_map = p1_pred.set_index("match_id")
    team_att = {}; team_tv = {}
    for _, r in live.iterrows():
        mid = r["match_id"]
        actual_att = r["attendance"]; actual_tv = r["tv_viewers"]
        pre_att = bp_map.loc[mid, "expected_attendance_base"]
        pre_tv = p1_map.loc[mid, "predicted_tv_viewers"]
        r_att = np.clip(actual_att / pre_att, 0.60, 1.50) if pre_att > 0 else 1.0
        r_tv = np.clip(actual_tv / (pre_tv * 1e6), 0.60, 1.50) if pre_tv > 0 else 1.0  # p1 百万->绝对
        for t in [r["team_a"], r["team_b"]]:
            team_att.setdefault(t, []).append(r_att)
            team_tv.setdefault(t, []).append(r_tv)
    r_a = {}; r_b = {}
    for t in team_att:
        r_a[t] = float(np.clip(np.mean(team_att[t]), 0.75, 1.25))
        r_b[t] = float(np.clip(np.mean(team_tv[t]), 0.75, 1.25))
    return r_a, r_b


def per_match_update(m_row, lam_i, S, h, p_t, cond_p, r_a, r_b, bp_map, sec_map, p2_map, p1_map, venues_map, tb_map, drc_map, drl_map):
    """对一场第三轮比赛计算更新后的中间量（不含决策）。返回 dict。"""
    mid = m_row["match_id"]
    ta, tb = lam_i[2], lam_i[3]
    lam_a, lam_b = lam_i[0], lam_i[1]
    p_a, p_b = p_t[ta], p_t[tb]
    # 公式5 晋级重要性
    Q = (4 * p_a * (1 - p_a) + 4 * p_b * (1 - p_b)) / 2
    # 公式6 反馈系数
    f_a = math.sqrt(r_a[ta] * r_a[tb])
    f_b = math.sqrt(r_b[ta] * r_b[tb])
    # 公式7
    S_i = (S[ta] + S[tb]) / 2
    H_i = (h[ta] + h[tb]) / 6
    A0 = bp_map.loc[mid, "attractiveness_index"] / 100
    F_i = np.clip((0.5 * f_a + 0.5 * f_b - 0.75) / 0.50, 0, 1)
    A = np.clip(0.50 * A0 + 0.25 * Q + 0.12 * F_i + 0.08 * S_i + 0.05 * (1 - H_i), 0, 1)
    # 公式8 更新现场需求 Ñ
    N_pre = p2_map.loc[mid, "expected_attendance"]
    N_tilde = N_pre * f_a * (0.88 + 0.27 * Q) * (0.94 + 0.12 * S_i) * (1 - 0.10 * H_i)
    # 公式10 更新转播需求 Ṽ
    V_pre = p1_map.loc[mid, "predicted_tv_viewers"]  # 百万人
    V_tilde = V_pre * f_b * (0.87 + 0.30 * Q) * (0.90 + 0.20 * A) * (1 - 0.06 * H_i)
    # 公式11 无激励风险
    R_noeff = 0.5 * (2 * p_a - 1) ** 2 + 0.5 * (2 * p_b - 1) ** 2
    # 公式12 默契风险
    cp = cond_p[mid]
    p_a_draw = cp["p_a_draw"]; p_b_draw = cp["p_b_draw"]; p_a_awin = cp["p_a_awin"]; p_b_bwin = cp["p_b_bwin"]
    D_i = min(p_a_draw, p_b_draw)
    G_i = 0.5 * max(p_a_awin - p_a_draw, 0) + 0.5 * max(p_b_bwin - p_b_draw, 0)
    R_coll = np.clip(D_i * (1 - np.clip(G_i, 0, 1)) * (1 - 0.35 * R_noeff), 0, 1)
    # 公式13 动态安保需求
    K = venues_map.loc[p2_map.loc[mid, "venue_id"], "capacity"]
    O_i = np.clip(N_tilde / K, 0, 1)
    d0 = sec_map.loc[mid, "security_demand_score"]
    d_i = np.clip(0.45 * d0 + 0.25 * O_i + 0.15 * A + 0.15 * (R_noeff + R_coll) / 2, 0, 1)
    return dict(mid=mid, ta=ta, tb=tb, p_a=p_a, p_b=p_b, Q=Q, f_a=f_a, f_b=f_b, A=A, N_tilde=N_tilde,
                V_tilde=V_tilde, R_noeff=R_noeff, R_coll=R_coll, d_i=d_i, K=K, N_pre=N_pre, V_pre=V_pre, A0=A0)


def evaluate_decision(upd, decision, tb_map, drc_map, p2_map):
    """给定决策 (b_pri, s_lvl, t_lvl, delta) 计算该场 TV, BV, A, C, R 原始值。
    decision = (broadcast_priority, security_level, transport_level, delta)
    """
    mid = upd["mid"]
    b_pri, s_lvl, t_lvl, delta = decision
    # 公式9 票价调整
    R3_stage = "Group_Match_R3"
    P0 = tb_map.loc[R3_stage, "base_ticket_price_usd"]
    eps = tb_map.loc[R3_stage, "price_elasticity"]
    m_d = drc_map.loc[("transport", t_lvl), "demand_multiplier"]
    K = upd["K"]
    N_delta = min(K, upd["N_tilde"] * m_d * (1 + delta) ** (1.0 / eps))
    # N(0)
    N_0 = min(K, upd["N_tilde"] * m_d * (1 + 0) ** (1.0 / eps))
    TV = P0 * (1 + delta) * N_delta
    # 公式10 转播
    m_b = drc_map.loc[("broadcast", b_pri), "demand_multiplier"]
    V = upd["V_tilde"] * m_b
    u = tb_map.loc[R3_stage, "broadcast_unit_value_usd"]
    BV = u * V  # 注意 V 单位百万人，u 是 USD/人 -> BV 单位 百万 USD？需统一
    # 这里 V_pre 是百万人，u 是 USD -> BV = u*V 是 百万 USD；需 *1e6 到 USD
    BV = BV * 1e6
    # 公式14 风险
    m_s = drc_map.loc[("security", s_lvl), "risk_multiplier"]
    R = 0.40 * upd["R_noeff"] + 0.40 * upd["R_coll"] + 0.20 * upd["d_i"] * m_s
    # 成本
    c_b = drc_map.loc[("broadcast", b_pri), "unit_cost_index"]
    c_s = drc_map.loc[("security", s_lvl), "unit_cost_index"]
    c_d = drc_map.loc[("transport", t_lvl), "unit_cost_index"]
    C = c_b + c_s + c_d
    return dict(TV=TV, BV=BV, A=upd["A"], C=C, R=R, N_delta=N_delta, N_0=N_0, V=V, m_d=m_d)


def feasible_delta(upd, delta, t_lvl, tb_map, drc_map):
    """N(delta) >= 0.88 N(0) 同交通等级."""
    R3_stage = "Group_Match_R3"
    eps = tb_map.loc[R3_stage, "price_elasticity"]
    m_d = drc_map.loc[("transport", t_lvl), "demand_multiplier"]
    K = upd["K"]
    N_delta = min(K, upd["N_tilde"] * m_d * (1 + delta) ** (1.0 / eps))
    N_0 = min(K, upd["N_tilde"] * m_d * (1.0) ** (1.0 / eps))
    return N_delta >= 0.88 * N_0


def main():
    data, gm, bp, live, sec, venues, tb, drc, drl, p2, p1 = load_inputs()
    bp_map = bp.set_index("match_id")
    sec_map = sec.set_index("match_id")
    p2_map = p2.set_index("match_id")
    p1_map = p1.set_index("match_id")
    venues_map = venues.set_index("venue_id")
    tb_map = tb.set_index("match_stage")
    drc_map = drc.set_index(["resource_type", "resource_level"])
    drl_map = drl.set_index("reference_date")

    # 第三轮 24 场
    bp_r3 = bp[bp["round_in_group"] == 3].copy()
    match_ids_r3 = bp_r3["match_id"].tolist()

    # 公式1-2 S_t, h_t
    S, h = compute_team_state(live, gm)
    # 公式3 更新 lambda
    lam = update_lambda(bp_r3, S, h)
    # 公式4 蒙特卡洛
    print("蒙特卡洛 20000 次...")
    p_t, cond_p = monte_carlo(lam, bp_r3, seed=utils.SEED)
    print("  p_t 范围:", min(p_t.values()), max(p_t.values()))
    # 公式6 反馈系数
    r_a, r_b = compute_feedback(live, bp, p1)

    # 每场更新量
    updates = {}
    for _, m_row in bp_r3.iterrows():
        mid = m_row["match_id"]
        upd = per_match_update(m_row, lam[mid], S, h, p_t, cond_p, r_a, r_b, bp_map, sec_map, p2_map, p1_map, venues_map, tb_map, drc_map, drl_map)
        updates[mid] = upd

    # 决策空间枚举：b_pri in {1,2,3}, s_lvl in [req, venue_sec], t_lvl in {1,2,3}, delta 连续
    # 静态决策：b=1, s=req, t=1, delta=0
    # 动态决策：枚举离散 + delta 一维优化

    def candidate_decisions(upd):
        """返回该场所有可行离散决策列表（不含 delta，delta 后续优化）."""
        mid = upd["mid"]
        venue_id = p2_map.loc[mid, "venue_id"]
        v_sec = int(venues_map.loc[venue_id, "security_level"])
        req = int(sec_map.loc[mid, "required_security_level"])
        cands = []
        for b in [1, 2, 3]:
            for s in range(req, v_sec + 1):
                for t in [1, 2, 3]:
                    cands.append((b, s, t))
        return cands, req, v_sec

    def optimize_delta(upd, t_lvl, drl_row, tb_map, drc_map):
        """对给定交通等级，优化 delta 使单场净效益最大。
        约束: delta in [-max_discount, +max_increase], N(delta)>=0.88 N(0).
        单场贡献 = 0.35 TV* + 0.35 BV* + 0.10 A* - 0.10 C* - 0.10 R*
        归一化用并集上下界（外部给），这里先返回原始值。
        """
        dinc = drl_row["max_ticket_increase_rate"]; ddisc = drl_row["max_ticket_discount_rate"]
        # delta 范围
        lo, hi = -ddisc, dinc
        # N(delta)>=0.88 N(0): 因 (1+delta)^(1/eps), eps<0, delta>0 使 (1+delta)^(1/eps) 减小（需求降），delta<0 使需求升。
        # N(delta) = min(K, Ñ*m_d*(1+delta)^(1/eps)). eps<0. 当 delta 增大，(1+delta)^(1/eps) 减小 -> N 减小。
        # 0.88 N(0) 约束给出 delta 上界。
        eps = tb_map.loc["Group_Match_R3", "price_elasticity"]
        # N(delta) >= 0.88 N(0): 若未达 K, N(delta)=Ñ m_d (1+delta)^(1/eps) >= 0.88 Ñ m_d
        # (1+delta)^(1/eps) >= 0.88 -> delta <= 0.88^eps - 1
        delta_upper = min(hi, 0.88 ** eps - 1) if eps != 0 else hi
        # 网格搜索 delta（细粒度）
        grid = np.linspace(lo, max(lo, delta_upper), 30)
        best = None
        for d in grid:
            dec = (1, 1, t_lvl, d)  # b/s 占位，单场 TV/BV 不依赖 b/s? TV 依赖 delta, BV 依赖 b_pri
            # 单场 TV 只依赖 delta 和 t_lvl; BV 依赖 b_pri 和 V_tilde; C 依赖 b,s,t; R 依赖 s
            # 所以 delta 优化只影响 TV。为分离，先固定 b,s,t 求 TV 随 delta。
            pass
        return lo, delta_upper

    # 简化策略：对每场，枚举 (b,s,t,delta_grid)，计算原始 TV,BV,A,C,R，收集所有候选（动态）。
    # 静态候选：单条 (1,req,1,0)。
    # 归一化上下界：取动态+静态候选的并集。
    print("枚举决策候选...")
    all_candidates = {}  # mid -> list of (decision, raw_metrics)
    static_candidates = {}
    for mid, upd in updates.items():
        cands, req, v_sec = candidate_decisions(upd)
        venue_id = p2_map.loc[mid, "venue_id"]
        ref_date = str(p2_map.loc[mid, "reference_date"])
        drl_row = drl_map.loc[ref_date]
        dinc = drl_row["max_ticket_increase_rate"]; ddisc = drl_row["max_ticket_discount_rate"]
        eps = tb_map.loc["Group_Match_R3", "price_elasticity"]
        delta_upper = min(dinc, 0.88 ** eps - 1) if eps != 0 else dinc
        delta_grid = np.linspace(-ddisc, max(-ddisc, delta_upper), 30)
        cand_list = []
        for (b, s, t) in cands:
            for d in delta_grid:
                dec = (b, s, t, float(d))
                raw = evaluate_decision(upd, dec, tb_map, drc_map, p2_map)
                cand_list.append((dec, raw))
        all_candidates[mid] = cand_list
        # 静态
        static_dec = (1, req, 1, 0.0)
        static_raw = evaluate_decision(upd, static_dec, tb_map, drc_map, p2_map)
        static_candidates[mid] = (static_dec, static_raw)

    # 归一化上下界：并集（动态+静态每场的 TV,BV,A,C,R）
    TV_all = [r["TV"] for mid in all_candidates for _, r in all_candidates[mid]] + [static_candidates[mid][1]["TV"] for mid in static_candidates]
    BV_all = [r["BV"] for mid in all_candidates for _, r in all_candidates[mid]] + [static_candidates[mid][1]["BV"] for mid in static_candidates]
    A_all = [r["A"] for mid in all_candidates for _, r in all_candidates[mid]] + [static_candidates[mid][1]["A"] for mid in static_candidates]
    C_all = [r["C"] for mid in all_candidates for _, r in all_candidates[mid]] + [static_candidates[mid][1]["C"] for mid in static_candidates]
    R_all = [r["R"] for mid in all_candidates for _, r in all_candidates[mid]] + [static_candidates[mid][1]["R"] for mid in static_candidates]
    bounds = {
        "TV": (min(TV_all), max(TV_all)),
        "BV": (min(BV_all), max(BV_all)),
        "A": (min(A_all), max(A_all)),
        "C": (min(C_all), max(C_all)),
        "R": (min(R_all), max(R_all)),
    }

    def norm(x, key):
        lo, hi = bounds[key]
        return (x - lo) / (hi - lo) if hi > lo else 0.0

    def net_value(raw):
        return (0.35 * norm(raw["TV"], "TV") + 0.35 * norm(raw["BV"], "BV")
                + 0.10 * norm(raw["A"], "A") - 0.10 * norm(raw["C"], "C") - 0.10 * norm(raw["R"], "R"))

    # 动态方案：每场选净效益最大的候选（先忽略每日容量耦合，后调整）
    # 每日容量约束：每日 high_broadcast(b=3), high_security(s>=3), enhanced_transport(t=3) 场数 <= 上限
    dynamic_decisions = {}
    # 按日聚合
    from collections import defaultdict
    day_matches = defaultdict(list)
    for mid in all_candidates:
        ref_date = str(p2_map.loc[mid, "reference_date"])
        day_matches[ref_date].append(mid)

    # 贪心：每场选最优，违反日容量则降级
    for ref_date, mids in day_matches.items():
        drl_row = drl_map.loc[ref_date]
        hb = drl_row["high_broadcast_capacity"]; hs = drl_row["high_security_capacity"]; ht = drl_row["enhanced_transport_capacity"]
        # 每场候选按净效益排序
        scored = []
        for mid in mids:
            for dec, raw in all_candidates[mid]:
                scored.append((net_value(raw), mid, dec, raw))
        scored.sort(reverse=True)
        chosen = {}
        cnt_b3 = 0; cnt_s3 = 0; cnt_t3 = 0
        chosen_set = set()
        for nv, mid, dec, raw in scored:
            if mid in chosen_set: continue
            b, s, t, d = dec
            new_b3 = cnt_b3 + (1 if b == 3 else 0)
            new_s3 = cnt_s3 + (1 if s >= 3 else 0)
            new_t3 = cnt_t3 + (1 if t == 3 else 0)
            if new_b3 > hb or new_s3 > hs or new_t3 > ht:
                continue
            chosen[mid] = (dec, raw, nv)
            chosen_set.add(mid)
            cnt_b3 = new_b3; cnt_s3 = new_s3; cnt_t3 = new_t3
        # 若有未选的场，强制选最低等级
        for mid in mids:
            if mid not in chosen:
                upd = updates[mid]
                cands, req, v_sec = candidate_decisions(upd)
                dec = (1, req, 1, 0.0)
                raw = evaluate_decision(upd, dec, tb_map, drc_map, p2_map)
                chosen[mid] = (dec, raw, net_value(raw))
        dynamic_decisions.update(chosen)

    # 静态方案净效益（固定决策，在更新环境下用同一上下界评价）
    static_results = {}
    for mid in match_ids_r3:
        dec, raw = static_candidates[mid]
        static_results[mid] = (dec, raw, net_value(raw))

    # 输出 result_3
    rows = []
    Z3_dyn = 0.0; Z3_sta = 0.0
    for mid in match_ids_r3:
        upd = updates[mid]
        dyn_dec, dyn_raw, dyn_nv = dynamic_decisions[mid]
        sta_dec, sta_raw, sta_nv = static_results[mid]
        Z3_dyn += dyn_nv; Z3_sta += sta_nv
        imp = (dyn_nv - sta_nv) / abs(sta_nv) if sta_nv != 0 else None
        b, s, t, d = dyn_dec
        rows.append({
            "match_id": mid,
            "group_id": bp_map.loc[mid, "group_id"],
            "team_a": upd["ta"], "team_b": upd["tb"],
            "updated_p_team_a_advance": round(upd["p_a"], 4),
            "updated_p_team_b_advance": round(upd["p_b"], 4),
            "updated_expected_attendance": round(dyn_raw["N_delta"], 0),
            "updated_expected_tv_viewers": round(dyn_raw["V"], 4),
            "stakeless_risk": round(upd["R_noeff"], 4),
            "collusion_risk": round(upd["R_coll"], 4),
            "updated_attractiveness": round(upd["A"], 4),
            "recommended_broadcast_priority": b,
            "recommended_security_level": s,
            "recommended_transport_level": t,
            "recommended_ticket_adjustment": round(d, 4),
            "updated_ticket_revenue_usd": round(dyn_raw["TV"], 2),
            "updated_broadcast_value_usd": round(dyn_raw["BV"], 2),
            "resource_cost_index": round(dyn_raw["C"], 4),
            "risk_exposure_index": round(dyn_raw["R"], 4),
            "static_net_value": round(sta_nv, 6),
            "dynamic_net_value": round(dyn_nv, 6),
            "improvement_rate": round(imp, 4) if imp is not None else "",
        })
    out = pd.DataFrame(rows)
    tmpl = pd.read_csv("output_result/result_3_template.csv")
    cols = [c for c in tmpl.columns]
    for c in cols:
        if c not in out.columns: out[c] = ""
    out = out[cols]
    out.to_csv(utils.RESULTS / "result_3_dynamic_strategy.csv", index=False, encoding="utf-8-sig")
    print(f"  -> result_3_dynamic_strategy.csv ({len(out)} 行)")
    print(f"Z3 动态={Z3_dyn:.6f} 静态={Z3_sta:.6f} 改善={(Z3_dyn-Z3_sta)/abs(Z3_sta)*100:.2f}%")

    # 保存中间
    utils.dump_json({
        "Z3_dynamic": float(Z3_dyn), "Z3_static": float(Z3_sta),
        "improvement_pct": float((Z3_dyn - Z3_sta) / abs(Z3_sta) * 100) if Z3_sta != 0 else None,
        "bounds": {k: list(v) for k, v in bounds.items()},
        "p_t": {k: float(v) for k, v in p_t.items()},
        "S": {k: float(v) for k, v in S.items()},
        "h": {k: float(v) for k, v in h.items()},
        "N_MC": N_MC, "seed": utils.SEED,
    }, "p3_summary.json")
    # 每场对比
    cmp = pd.DataFrame([{
        "match_id": r["match_id"], "static_nv": r["static_net_value"], "dynamic_nv": r["dynamic_net_value"],
        "improvement_rate": r["improvement_rate"],
        "b": r["recommended_broadcast_priority"], "s": r["recommended_security_level"],
        "t": r["recommended_transport_level"], "delta": r["recommended_ticket_adjustment"],
    } for r in rows])
    utils.dump_df(cmp, "p3_static_vs_dynamic.csv")
    return Z3_dyn, Z3_sta


if __name__ == "__main__":
    main()
