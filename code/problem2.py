"""问题二：小组赛场馆与开球时段协同优化。

决策：每场 m ∈ 72 分配 venue_id∈V01..V16、slot_id∈S011..S204。
Max Z2 = 0.25T + 0.25B + 0.15U + 0.10H - 0.08C - 0.07D - 0.06F - 0.04R
T/B/C/D 进目标前 min-max 归一化（全局候选组合上下界）；U/H/F/R 已 [0,1]。

求解：贪心初始（按轮次顺序选当前最优合法(场馆,时段)）+ 模拟退火局部搜索（换馆/换时段/交换）。
多起点固定种子，报告稳定性。
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import load_all
import utils

USD_PER_MUSD = 1_000_000  # 百万美元 -> USD
SECURITY_BASE_COST = 100_000.0  # 单场安保基础成本 10 万美元
HOUR60 = 60.0  # 同组相邻轮次最小开球时差（小时）


def load_inputs():
    data = load_all()
    # 数值化
    venues = data["venues"].copy()
    for c in ["capacity", "max_matches_per_day", "min_total_matches", "max_total_matches",
              "setup_cost_musd", "operation_cost_musd_per_match", "security_level",
              "security_cost_index", "climate_risk", "transport_index"]:
        venues[c] = pd.to_numeric(venues[c], errors="coerce")
    slots = data["time_slots"].copy()
    for c in ["global_prime_score", "broadcast_capacity", "america_prime", "europe_prime", "asia_prime"]:
        slots[c] = pd.to_numeric(slots[c], errors="coerce")
    slots["utc_dt"] = pd.to_datetime(slots["reference_utc_time"])
    slots["date_str"] = slots["date"].astype(str)
    gm = data["groups_matches"].copy()
    for c in ["round_in_group"]:
        gm[c] = pd.to_numeric(gm[c], errors="coerce").astype(int)
    tb = data["ticket_broadcast"].copy()
    for c in ["base_ticket_price_usd", "price_elasticity", "broadcast_unit_value_usd", "sponsor_weight", "local_interest_weight"]:
        tb[c] = pd.to_numeric(tb[c], errors="coerce")
    bp = data["base_predictions"].copy()
    for c in ["expected_goals_a", "expected_goals_b", "p_a_win", "p_draw", "p_b_win",
              "uncertainty_index", "attractiveness_index", "expected_attendance_base", "commercial_value_index"]:
        bp[c] = pd.to_numeric(bp[c], errors="coerce")
    sec = data["security_requirements"].copy()
    for c in ["crowd_risk", "attention_risk", "security_demand_score", "required_security_level"]:
        sec[c] = pd.to_numeric(sec[c], errors="coerce").astype(int) if c == "required_security_level" else pd.to_numeric(sec[c], errors="coerce")
    dist = data["distance_matrix"].copy()
    for c in ["distance_km", "travel_time_hour", "timezone_diff"]:
        dist[c] = pd.to_numeric(dist[c], errors="coerce")
    # P1 的 72 场预测
    p1 = pd.read_csv(utils.RESULTS / "result_1_match_prediction.csv", encoding="utf-8-sig")
    p1["predicted_tv_viewers"] = pd.to_numeric(p1["predicted_tv_viewers"], errors="coerce")
    # dynamic_resource_limits（R3 每日高等级安保容量，P2 也需遵守：每个参考日内第三轮 req_level>=3 场数 <= high_security_capacity）
    drl = data["dynamic_resource_limits"].copy()
    for c in ["high_broadcast_capacity", "high_security_capacity", "enhanced_transport_capacity",
              "daily_resource_budget_index", "max_ticket_increase_rate", "max_ticket_discount_rate"]:
        drl[c] = pd.to_numeric(drl[c], errors="coerce")
    return data, venues, slots, gm, tb, bp, sec, dist, p1, drl


def precompute_globals(gm, venues, slots, tb, bp, sec, dist, p1, drl):
    """预计算全局归一化上下界、索引映射、候选资格。"""
    # 索引
    venue_ids = venues["venue_id"].tolist()
    slot_ids = slots["slot_id"].tolist()
    vid_idx = {v: i for i, v in enumerate(venue_ids)}
    sid_idx = {s: i for i, s in enumerate(slot_ids)}
    nv, ns = len(venue_ids), len(slot_ids)

    # 场馆属性数组
    cap = venues["capacity"].values.astype(float)
    sec_level_v = venues["security_level"].values.astype(float)
    sec_cost_idx_v = venues["security_cost_index"].values.astype(float)
    setup_musd = venues["setup_cost_musd"].values.astype(float)
    opcost_musd = venues["operation_cost_musd_per_match"].values.astype(float)
    climate_v = venues["climate_risk"].values.astype(float)
    max_per_day_v = venues["max_matches_per_day"].values.astype(int)
    min_tot_v = venues["min_total_matches"].values.astype(int)
    max_tot_v = venues["max_total_matches"].values.astype(int)
    tz_v = venues["timezone"].values

    # 时段属性数组
    gps = slots["global_prime_score"].values.astype(float)
    bcap = slots["broadcast_capacity"].values.astype(int)
    utc_ts = slots["utc_dt"].values.astype("datetime64[s]").astype(np.int64).astype(float) / 3600.0  # hours
    slot_date = slots["date_str"].values

    # 黄金时段 = global_prime_score 排名前 25% (前 20)
    gold_rank = np.argsort(-gps)
    gold_mask = np.zeros(ns, dtype=bool)
    gold_mask[gold_rank[:20]] = True
    # 大容量场馆 = capacity 排名前 25% (前 4)
    big_rank = np.argsort(-cap)
    big_mask = np.zeros(nv, dtype=bool)
    big_mask[big_rank[:4]] = True

    # 每场属性（按 match_id）
    gm_sorted = gm.sort_values("match_id").reset_index(drop=True)
    match_ids = gm_sorted["match_id"].tolist()
    nm = len(match_ids)
    mid_idx = {m: i for i, m in enumerate(match_ids)}
    rnd = gm_sorted["round_in_group"].values.astype(int)
    grp = gm_sorted["group_id"].values
    ta_id = gm_sorted["team_a_id"].values
    tb_id = gm_sorted["team_b_id"].values
    ta_name = gm_sorted["team_a"].values
    tb_name = gm_sorted["team_b"].values

    # base_predictions / security / p1 按 match_id
    bp_map = bp.set_index("match_id")
    sec_map = sec.set_index("match_id")
    p1_map = p1.set_index("match_id")

    exp_att_base = np.array([bp_map.loc[m, "expected_attendance_base"] for m in match_ids], dtype=float)
    unc = np.array([bp_map.loc[m, "uncertainty_index"] for m in match_ids], dtype=float)
    attr = np.array([bp_map.loc[m, "attractiveness_index"] for m in match_ids], dtype=float)
    tv_pred = np.array([p1_map.loc[m, "predicted_tv_viewers"] for m in match_ids], dtype=float)
    req_sec = np.array([sec_map.loc[m, "required_security_level"] for m in match_ids], dtype=int)
    crowd_risk = np.array([sec_map.loc[m, "crowd_risk"] for m in match_ids], dtype=float)

    # 票务/转播参数按轮次
    round_stage = {1: "Group_Match_R1", 2: "Group_Match_R2", 3: "Group_Match_R3"}
    tb_map = tb.set_index("match_stage")
    base_price = np.array([tb_map.loc[round_stage[r], "base_ticket_price_usd"] for r in rnd], dtype=float)
    elasticity = np.array([tb_map.loc[round_stage[r], "price_elasticity"] for r in rnd], dtype=float)
    unit_value = np.array([tb_map.loc[round_stage[r], "broadcast_unit_value_usd"] for r in rnd], dtype=float)
    sponsor_w = np.array([tb_map.loc[round_stage[r], "sponsor_weight"] for r in rnd], dtype=float)

    # 候选资格：venue.security_level >= req_sec[m]
    eligible = np.zeros((nm, nv), dtype=bool)
    for m in range(nm):
        eligible[m] = sec_level_v >= req_sec[m]

    # 距离查表
    # team_to_venue: (T_id, V_id) -> (dist, time, tz)
    tv_dist = dist[dist["relation_type"] == "team_to_venue"].copy()
    tv_key = {}
    for _, r in tv_dist.iterrows():
        tv_key[(r["origin_id"], r["destination_id"])] = (r["distance_km"], r["travel_time_hour"], r["timezone_diff"])
    # venue_to_venue
    vv_dist = dist[dist["relation_type"] == "venue_to_venue"].copy()
    vv_key = {}
    for _, r in vv_dist.iterrows():
        vv_key[(r["origin_id"], r["destination_id"])] = (r["distance_km"], r["travel_time_hour"], r["timezone_diff"])

    # 全局 min-max 上下界（用于 D 三项归一化）
    # team_to_venue 全部 768 组合
    tv_records = [(v[0], v[1], v[2]) for v in tv_key.values()]
    tv_arr = np.array(tv_records)
    tv_min = tv_arr.min(axis=0)
    tv_max = tv_arr.max(axis=0)
    # venue_to_venue 全部 256 组合
    vv_records = [(v[0], v[1], v[2]) for v in vv_key.values()]
    vv_arr = np.array(vv_records)
    vv_min = vv_arr.min(axis=0)
    vv_max = vv_arr.max(axis=0)

    # T/B/C 全局候选组合上下界：对每场每候选(场馆,时段)算原始值取全局 min/max
    # 为效率，先算每场每候选的 T_raw, B_raw, C_raw
    # T_raw[m,v] = base_price[m] * min(exp_att_base[m], cap[v])
    att_m = np.minimum(exp_att_base[:, None], cap[None, :])  # (nm, nv)
    T_raw = base_price[:, None] * att_m  # (nm, nv)
    # B_raw[m,v,s] = tv_pred[m] * unit_value[m] * gps[s] * sponsor_w[m]  -> 按 v 无关，按 s 有关
    # C_raw[m,v] = setup_musd[v]*1e6 + opcost_musd[v]*1e6 + 100000*req_sec[m]*sec_cost_idx_v[v]
    C_raw = (setup_musd[None, :] * USD_PER_MUSD + opcost_musd[None, :] * USD_PER_MUSD
             + SECURITY_BASE_COST * req_sec[:, None] * sec_cost_idx_v[None, :])  # (nm, nv)
    # B_raw[m,s] (与 v 无关)
    B_raw_ms = tv_pred[:, None] * unit_value[:, None] * gps[None, :] * sponsor_w[:, None]  # (nm, ns)

    T_lo, T_hi = T_raw.min(), T_raw.max()
    C_lo, C_hi = C_raw.min(), C_raw.max()
    B_lo, B_hi = B_raw_ms.min(), B_raw_ms.max()

    # R3 每日高等级安保容量（dynamic_resource_limits.high_security_capacity，按 reference_date）
    drl_map = drl.set_index("reference_date")
    r3_high_sec_cap = {str(d): int(drl_map.loc[d, "high_security_capacity"]) for d in drl_map.index}

    return dict(
        nv=nv, ns=ns, nm=nm, venue_ids=venue_ids, slot_ids=slot_ids, vid_idx=vid_idx, sid_idx=sid_idx,
        cap=cap, sec_level_v=sec_level_v, sec_cost_idx_v=sec_cost_idx_v, setup_musd=setup_musd,
        opcost_musd=opcost_musd, climate_v=climate_v, max_per_day_v=max_per_day_v, min_tot_v=min_tot_v,
        max_tot_v=max_tot_v, tz_v=tz_v, gps=gps, bcap=bcap, utc_ts=utc_ts, slot_date=slot_date,
        gold_mask=gold_mask, big_mask=big_mask, match_ids=match_ids, mid_idx=mid_idx, rnd=rnd, grp=grp,
        ta_id=ta_id, tb_id=tb_id, ta_name=ta_name, tb_name=tb_name, exp_att_base=exp_att_base, unc=unc,
        attr=attr, tv_pred=tv_pred, req_sec=req_sec, crowd_risk=crowd_risk, base_price=base_price,
        elasticity=elasticity, unit_value=unit_value, sponsor_w=sponsor_w, eligible=eligible,
        tv_key=tv_key, vv_key=vv_key, tv_min=tv_min, tv_max=tv_max, vv_min=vv_min, vv_max=vv_max,
        att_m=att_m, T_raw=T_raw, C_raw=C_raw, B_raw_ms=B_raw_ms,
        T_lo=T_lo, T_hi=T_hi, C_lo=C_lo, C_hi=C_hi, B_lo=B_lo, B_hi=B_hi,
        r3_high_sec_cap=r3_high_sec_cap,
        gm_sorted=gm_sorted, venues=venues, slots=slots,
    )


def travel_burden(G, m, v, assign_prev_round):
    """计算球队本场旅行负担 D_raw（归一化后），取两队均值。
    R1: team_to_venue（球队->本场场馆）。
    R2/R3: venue_to_venue，起点=该队上一轮全部合格候选场馆均值。
    assign_prev_round: dict team_id -> 上一轮该队所分配场馆 v_prev（用于确定上一轮合格候选集合）
    实现按题面：R2/R3 起点取上一轮全部合格候选场馆（安保能力>=上一轮最低安保需求）的均值。
    """
    rnd = G["rnd"][m]
    req = G["req_sec"][m]
    tv_min, tv_max = G["tv_min"], G["tv_max"]
    vv_min, vv_max = G["vv_min"], G["vv_max"]
    ta, tb = G["ta_id"][m], G["tb_id"][m]

    def norm_r1(team_id):
        d, t, tz = G["tv_key"][(team_id, G["venue_ids"][v])]
        dn = (d - tv_min[0]) / (tv_max[0] - tv_min[0]) if tv_max[0] > tv_min[0] else 0.0
        tn = (t - tv_min[1]) / (tv_max[1] - tv_min[1]) if tv_max[1] > tv_min[1] else 0.0
        tzn = (tz - tv_min[2]) / (tv_max[2] - tv_min[2]) if tv_max[2] > tv_min[2] else 0.0
        return 0.5 * dn + 0.3 * tn + 0.2 * tzn

    def norm_v2v_from_prev(team_id):
        # 上一轮该队比赛 m_prev 的最低安保需求
        # 找该队上一轮比赛
        prev_v = assign_prev_round.get(team_id)
        if prev_v is None:
            # fallback: 用 team_to_venue
            return norm_r1(team_id)
        # 上一轮合格候选场馆 = venues 中 security_level >= 上一轮 req
        # 这里简化：起点集合 = 上一轮全部合格候选场馆，取到本轮 v 的负担均值
        # 上一轮 req
        prev_m = find_match_of_team_round(G, team_id, rnd - 1)
        prev_req = G["req_sec"][prev_m]
        cand_starts = [vv for vv in range(G["nv"]) if G["sec_level_v"][vv] >= prev_req]
        vals = []
        for vs in cand_starts:
            d, t, tz = G["vv_key"][(G["venue_ids"][vs], G["venue_ids"][v])]
            dn = (d - vv_min[0]) / (vv_max[0] - vv_min[0]) if vv_max[0] > vv_min[0] else 0.0
            tn = (t - vv_min[1]) / (vv_max[1] - vv_min[1]) if vv_max[1] > vv_min[1] else 0.0
            tzn = (tz - vv_min[2]) / (vv_max[2] - vv_min[2]) if vv_max[2] > vv_min[2] else 0.0
            vals.append(0.5 * dn + 0.3 * tn + 0.2 * tzn)
        return np.mean(vals) if vals else 0.0

    if rnd == 1:
        da = norm_r1(ta); db = norm_r1(tb)
    else:
        da = norm_v2v_from_prev(ta); db = norm_v2v_from_prev(tb)
    return 0.5 * da + 0.5 * db


def find_match_of_team_round(G, team_id, rnd):
    for m in range(G["nm"]):
        if G["rnd"][m] == rnd and (G["ta_id"][m] == team_id or G["tb_id"][m] == team_id):
            return m
    return -1


def fairness_penalty(G, venue_of, slot_of):
    """F = 0.5*(黄金时段次数极差/3) + 0.5*(大容量场馆次数极差/3)，按球队统计。"""
    from collections import defaultdict
    gold_cnt = defaultdict(int)
    big_cnt = defaultdict(int)
    teams_all = set(G["ta_id"]).union(G["tb_id"])
    for m in range(G["nm"]):
        v, s = venue_of[m], slot_of[m]
        if G["gold_mask"][s]:
            gold_cnt[G["ta_id"][m]] += 1; gold_cnt[G["tb_id"][m]] += 1
        if G["big_mask"][v]:
            big_cnt[G["ta_id"][m]] += 1; big_cnt[G["tb_id"][m]] += 1
    g_vals = [gold_cnt.get(t, 0) for t in teams_all]
    b_vals = [big_cnt.get(t, 0) for t in teams_all]
    g_range = max(g_vals) - min(g_vals) if g_vals else 0
    b_range = max(b_vals) - min(b_vals) if b_vals else 0
    return 0.5 * (g_range / 3.0) + 0.5 * (b_range / 3.0)


def risk_index(G, m, v, att):
    """R_m = 0.5*climate_v + 0.3*(att/cap) + 0.2*(req_sec/sec_level_v)"""
    climate = G["climate_v"][v]
    occ = att / G["cap"][v] if G["cap"][v] > 0 else 0
    sec_ratio = G["req_sec"][m] / G["sec_level_v"][v] if G["sec_level_v"][v] > 0 else 1
    return 0.5 * climate + 0.3 * occ + 0.2 * sec_ratio


def objective_terms(G, venue_of, slot_of):
    """计算 Z2 与分项。返回 (Z2, dict of terms, per-match dict)."""
    nm = G["nm"]
    Tn, Bn, U, H, Cn, D, R = np.zeros(nm), np.zeros(nm), np.zeros(nm), np.zeros(nm), np.zeros(nm), np.zeros(nm), np.zeros(nm)
    T_raw_m = np.zeros(nm); B_raw_m = np.zeros(nm); C_raw_m = np.zeros(nm)
    # 上一轮分配（用于 D 的 R2/R3）
    assign_prev = {}
    for m in range(nm):
        if G["rnd"][m] == 1:
            pass
        else:
            ta, tb = G["ta_id"][m], G["tb_id"][m]
            assign_prev[ta] = venue_of[find_match_of_team_round(G, ta, G["rnd"][m] - 1)]
            assign_prev[tb] = venue_of[find_match_of_team_round(G, tb, G["rnd"][m] - 1)]
        v, s = venue_of[m], slot_of[m]
        att = G["att_m"][m, v]
        T_raw = G["T_raw"][m, v]
        B_raw = G["B_raw_ms"][m, s]
        C_raw = G["C_raw"][m, v]
        T_raw_m[m] = T_raw; B_raw_m[m] = B_raw; C_raw_m[m] = C_raw
        Tn[m] = (T_raw - G["T_lo"]) / (G["T_hi"] - G["T_lo"]) if G["T_hi"] > G["T_lo"] else 0
        Bn[m] = (B_raw - G["B_lo"]) / (G["B_hi"] - G["B_lo"]) if G["B_hi"] > G["B_lo"] else 0
        U[m] = G["unc"][m]
        H[m] = G["attr"][m] / 100.0
        Cn[m] = (C_raw - G["C_lo"]) / (G["C_hi"] - G["C_lo"]) if G["C_hi"] > G["C_lo"] else 0
        D[m] = travel_burden(G, m, v, assign_prev)
        R[m] = risk_index(G, m, v, att)
    F = fairness_penalty(G, venue_of, slot_of)
    per_match = 0.25 * Tn + 0.25 * Bn + 0.15 * U + 0.10 * H - 0.08 * Cn - 0.07 * D - 0.04 * R
    # F 是方案级，分摊到每场（均分），使 Z2 = sum(per_match) - 0.06*F
    Z2 = per_match.sum() - 0.06 * F
    terms = dict(T=float(Tn.mean()), B=float(Bn.mean()), U=float(U.mean()), H=float(H.mean()),
                 C=float(Cn.mean()), D=float(D.mean()), F=float(F), R=float(R.mean()),
                 T_raw_mean=float(T_raw_m.mean()), B_raw_mean=float(B_raw_m.mean()), C_raw_mean=float(C_raw_m.mean()))
    return Z2, terms, dict(per_match=per_match, Tn=Tn, Bn=Bn, U=U, H=H, Cn=Cn, D=D, R=R,
                            T_raw=T_raw_m, B_raw=B_raw_m, C_raw=C_raw_m, F=F)


def check_constraints(G, venue_of, slot_of):
    """逐一回代检查约束，返回 violations dict。"""
    nm = G["nm"]
    viol = {}
    # 1 同场馆同时段 <=1
    seen = {}
    c = 0
    for m in range(nm):
        key = (venue_of[m], slot_of[m])
        if key in seen:
            c += 1
        seen[key] = m
    viol["venue_slot_clash"] = c
    # 2 同组相邻轮次 60h
    c = 0
    for grp in set(G["grp"]):
        for rnd in [2, 3]:
            # 该组该轮每队的上一轮比赛
            for m in range(nm):
                if G["grp"][m] == grp and G["rnd"][m] == rnd:
                    for team in [G["ta_id"][m], G["tb_id"][m]]:
                        mprev = find_match_of_team_round(G, team, rnd - 1)
                        if mprev >= 0:
                            dt = G["utc_ts"][slot_of[m]] - G["utc_ts"][slot_of[mprev]]
                            if dt < HOUR60:
                                c += 1
    viol["rest_60h_violation"] = c
    # 3 场馆单日/总数
    from collections import defaultdict
    vd_day = defaultdict(int)
    vd_tot = defaultdict(int)
    for m in range(nm):
        vd_day[(venue_of[m], G["slot_date"][slot_of[m]])] += 1
        vd_tot[venue_of[m]] += 1
    viol["venue_per_day_violation"] = sum(1 for (v, d), n in vd_day.items() if n > G["max_per_day_v"][v])
    viol["venue_total_min_violation"] = sum(1 for v in range(G["nv"]) if vd_tot[v] < G["min_tot_v"][v])
    viol["venue_total_max_violation"] = sum(1 for v in range(G["nv"]) if vd_tot[v] > G["max_tot_v"][v])
    # 5 黄金时段公平：任意两队差<=2
    gold_cnt = defaultdict(int)
    for m in range(nm):
        if G["gold_mask"][slot_of[m]]:
            gold_cnt[G["ta_id"][m]] += 1; gold_cnt[G["tb_id"][m]] += 1
    gc = list(gold_cnt.values())
    viol["gold_fairness_violation"] = (max(gc) - min(gc) - 2) if (gc and max(gc) - min(gc) > 2) else 0
    # 6 安保资格
    c = 0
    for m in range(nm):
        if not G["eligible"][m, venue_of[m]]:
            c += 1
    viol["security_eligibility_violation"] = c
    # 第三轮每日 req_level>=3 场数 <= dynamic_resource_limits.high_security_capacity（按 reference_date）
    from collections import defaultdict as _dd
    r3_day_high = _dd(int)
    for m in range(nm):
        if G["rnd"][m] == 3 and G["req_sec"][m] >= 3:
            r3_day_high[G["slot_date"][slot_of[m]]] += 1
    cap_map = G.get("r3_high_sec_cap", {})
    r3_viol = 0
    for d, n in r3_day_high.items():
        lim = cap_map.get(str(d))
        if lim is not None and n > lim:
            r3_viol += 1
    viol["r3_daily_high_security_violation"] = r3_viol
    # 7 同 UTC 时刻比赛数 <= broadcast_capacity
    utc_cnt = defaultdict(int)
    for m in range(nm):
        utc_cnt[slot_of[m]] += 1
    viol["broadcast_capacity_violation"] = sum(1 for s, n in utc_cnt.items() if n > G["bcap"][s])
    # 8 同组同轮两场不同时段
    c = 0
    for grp in set(G["grp"]):
        for rnd in [1, 2, 3]:
            ms = [m for m in range(nm) if G["grp"][m] == grp and G["rnd"][m] == rnd]
            slots_r = [slot_of[m] for m in ms]
            if len(set(slots_r)) < len(slots_r):
                c += 1
    viol["same_group_round_slot_clash"] = c
    viol["total_violations"] = sum(v for k, v in viol.items() if isinstance(v, int))
    return viol


def greedy_init(G, rng):
    """贪心初始：按轮次顺序，每场选当前最优合法(场馆,时段)。
    硬约束必须满足：安保资格、场馆同时段不撞、60h休息（双向）、单日场次、broadcast_capacity、同组同轮不同时段、R3每日高等级安保容量。
    软约束（场馆总场次 min/max）由 SA 后续修复。
    """
    nm = G["nm"]
    venue_of = [-1] * nm
    slot_of = [-1] * nm
    used_vs = set()  # (v,s)
    utc_cnt = {}
    vd_day = {}
    vd_tot = [0] * G["nv"]
    cap_map = G.get("r3_high_sec_cap", {})
    # 按 (轮次, 组, 场序) 处理；同组同轮两场一起处理便于错开时段
    order = sorted(range(nm), key=lambda m: (G["rnd"][m], G["grp"][m], m))
    # 每轮日期硬窗口（保证 60h 可行 + 给后续轮留空间）：
    # R1: 06-11~06-14, R2: 06-14~06-17, R3: 06-17~06-30（R3 跨多日因 24 场+容量）
    ROUND_DAY_WINDOW = {1: (11, 14), 2: (14, 17), 3: (17, 30)}
    def slot_pref(s):
        d = G["slot_date"][s]
        day = int(d[8:10])
        return (day, -G["gps"][s])
    for m in order:
        best = None; best_score = -1e18
        rnd = G["rnd"][m]
        lo_day, hi_day = ROUND_DAY_WINDOW[rnd]
        cands_v = [v for v in range(G["nv"]) if G["eligible"][m, v]]
        # 时段按日期升序 + gps 降序
        cands_s_sorted = sorted(range(G["ns"]), key=slot_pref)
        # 仅保留窗口内时段
        cands_s_sorted = [s for s in cands_s_sorted if lo_day <= int(G["slot_date"][s][8:10]) <= hi_day]
        for v in cands_v:
            if vd_tot[v] >= G["max_tot_v"][v]:
                continue
            for s in cands_s_sorted:
                if (v, s) in used_vs:
                    continue
                if utc_cnt.get(s, 0) >= G["bcap"][s]:
                    continue
                if vd_day.get((v, G["slot_date"][s]), 0) >= G["max_per_day_v"][v]:
                    continue
                # R3 每日高等级安保容量
                if rnd == 3 and G["req_sec"][m] >= 3:
                    d = G["slot_date"][s]
                    cur_high = sum(1 for mm in range(nm) if venue_of[mm] >= 0 and G["rnd"][mm] == 3 and G["req_sec"][mm] >= 3 and G["slot_date"][slot_of[mm]] == d)
                    lim = cap_map.get(str(d))
                    if lim is not None and cur_high + 1 > lim:
                        continue
                # 60h 双向检查
                ok = True
                for team in [G["ta_id"][m], G["tb_id"][m]]:
                    if rnd > 1:
                        mprev = find_match_of_team_round(G, team, rnd - 1)
                        if mprev >= 0 and venue_of[mprev] >= 0:
                            dt = G["utc_ts"][s] - G["utc_ts"][slot_of[mprev]]
                            if dt < HOUR60:
                                ok = False; break
                    if ok and rnd < 3:
                        mnext = find_match_of_team_round(G, team, rnd + 1)
                        if mnext >= 0 and venue_of[mnext] >= 0:
                            dt = G["utc_ts"][slot_of[mnext]] - G["utc_ts"][s]
                            if dt < HOUR60:
                                ok = False; break
                if not ok:
                    continue
                # 同组同轮不同时段
                grp_ms = [mm for mm in range(nm) if G["grp"][mm] == G["grp"][m] and G["rnd"][mm] == G["rnd"][m] and slot_of[mm] >= 0]
                if any(slot_of[mm] == s for mm in grp_ms):
                    continue
                # 评分：T+B+U+H - C - D - R (近似，不含 F)
                att = G["att_m"][m, v]
                Tn_ = (G["T_raw"][m, v] - G["T_lo"]) / (G["T_hi"] - G["T_lo"]) if G["T_hi"] > G["T_lo"] else 0
                Bn_ = (G["B_raw_ms"][m, s] - G["B_lo"]) / (G["B_hi"] - G["B_lo"]) if G["B_hi"] > G["B_lo"] else 0
                Cn_ = (G["C_raw"][m, v] - G["C_lo"]) / (G["C_hi"] - G["C_lo"]) if G["C_hi"] > G["C_lo"] else 0
                score = 0.25 * Tn_ + 0.25 * Bn_ + 0.15 * G["unc"][m] + 0.10 * G["attr"][m] / 100 - 0.08 * Cn_ - 0.04 * risk_index(G, m, v, att)
                if score > best_score:
                    best_score = score; best = (v, s)
        if best is None:
            # 放宽场馆总数上限（软约束），仍守硬约束（含 60h 双向 + R3容量 + 日期窗口）
            for v in cands_v:
                for s in cands_s_sorted:
                    if (v, s) in used_vs: continue
                    if utc_cnt.get(s, 0) >= G["bcap"][s]: continue
                    if vd_day.get((v, G["slot_date"][s]), 0) >= G["max_per_day_v"][v]: continue
                    if rnd == 3 and G["req_sec"][m] >= 3:
                        d = G["slot_date"][s]
                        cur_high = sum(1 for mm in range(nm) if venue_of[mm] >= 0 and G["rnd"][mm] == 3 and G["req_sec"][mm] >= 3 and G["slot_date"][slot_of[mm]] == d)
                        lim = cap_map.get(str(d))
                        if lim is not None and cur_high + 1 > lim: continue
                    ok = True
                    for team in [G["ta_id"][m], G["tb_id"][m]]:
                        if rnd > 1:
                            mprev = find_match_of_team_round(G, team, rnd - 1)
                            if mprev >= 0 and venue_of[mprev] >= 0:
                                dt = G["utc_ts"][s] - G["utc_ts"][slot_of[mprev]]
                                if dt < HOUR60: ok = False; break
                        if ok and rnd < 3:
                            mnext = find_match_of_team_round(G, team, rnd + 1)
                            if mnext >= 0 and venue_of[mnext] >= 0:
                                dt = G["utc_ts"][slot_of[mnext]] - G["utc_ts"][s]
                                if dt < HOUR60: ok = False; break
                    if not ok: continue
                    best = (v, s); break
                if best: break
        if best is None:
            # 日期窗口内无解：放宽窗口（仍守 60h 硬约束）
            for v in cands_v:
                for s in sorted(range(G["ns"]), key=slot_pref):
                    if (v, s) in used_vs: continue
                    if utc_cnt.get(s, 0) >= G["bcap"][s]: continue
                    if vd_day.get((v, G["slot_date"][s]), 0) >= G["max_per_day_v"][v]: continue
                    if rnd == 3 and G["req_sec"][m] >= 3:
                        d = G["slot_date"][s]
                        cur_high = sum(1 for mm in range(nm) if venue_of[mm] >= 0 and G["rnd"][mm] == 3 and G["req_sec"][mm] >= 3 and G["slot_date"][slot_of[mm]] == d)
                        lim = cap_map.get(str(d))
                        if lim is not None and cur_high + 1 > lim: continue
                    ok = True
                    for team in [G["ta_id"][m], G["tb_id"][m]]:
                        if rnd > 1:
                            mprev = find_match_of_team_round(G, team, rnd - 1)
                            if mprev >= 0 and venue_of[mprev] >= 0:
                                dt = G["utc_ts"][s] - G["utc_ts"][slot_of[mprev]]
                                if dt < HOUR60: ok = False; break
                        if ok and rnd < 3:
                            mnext = find_match_of_team_round(G, team, rnd + 1)
                            if mnext >= 0 and venue_of[mnext] >= 0:
                                dt = G["utc_ts"][slot_of[mnext]] - G["utc_ts"][s]
                                if dt < HOUR60: ok = False; break
                    if not ok: continue
                    best = (v, s); break
                if best: break
        if best is None:
            # 最后兜底：任选合法场馆+未撞时段+守 60h（忽略日期窗口与软约束）
            for v in cands_v:
                for s in sorted(range(G["ns"]), key=slot_pref):
                    if (v, s) in used_vs: continue
                    if utc_cnt.get(s, 0) >= G["bcap"][s]: continue
                    ok = True
                    for team in [G["ta_id"][m], G["tb_id"][m]]:
                        if rnd > 1:
                            mprev = find_match_of_team_round(G, team, rnd - 1)
                            if mprev >= 0 and venue_of[mprev] >= 0:
                                dt = G["utc_ts"][s] - G["utc_ts"][slot_of[mprev]]
                                if dt < HOUR60: ok = False; break
                        if ok and rnd < 3:
                            mnext = find_match_of_team_round(G, team, rnd + 1)
                            if mnext >= 0 and venue_of[mnext] >= 0:
                                dt = G["utc_ts"][slot_of[mnext]] - G["utc_ts"][s]
                                if dt < HOUR60: ok = False; break
                    if not ok: continue
                    best = (v, s); break
                if best: break
        if best is None:
            # 终极兜底：仅守场馆同时段不撞与安保资格（极少触发，SA 修复其余）
            for v in cands_v:
                for s in range(G["ns"]):
                    if (v, s) not in used_vs:
                        best = (v, s); break
                if best: break
        v, s = best
        venue_of[m] = v; slot_of[m] = s
        used_vs.add((v, s)); utc_cnt[s] = utc_cnt.get(s, 0) + 1
        vd_day[(v, G["slot_date"][s])] = vd_day.get((v, G["slot_date"][s]), 0) + 1
        vd_tot[v] += 1
    return np.array(venue_of), np.array(slot_of)


def simulated_annealing(G, venue_of, slot_of, rng, iters=8000, T0=0.05, Tend=1e-4, hard_penalty=50.0):
    """模拟退火：邻域=单场换馆/换时段/两场交换。
    目标 = Z2 - hard_penalty * 违反数（驱动可行化）。
    """
    nm = G["nv"]  # placeholder
    nm = G["nm"]
    viol0 = check_constraints(G, venue_of, slot_of)
    Z2, _, _ = objective_terms(G, venue_of, slot_of)
    cur_viol = viol0["total_violations"]
    cur_obj = Z2 - hard_penalty * cur_viol
    # best_* tracks the best ZERO-VIOLATION solution found (or initial if none)
    if cur_viol == 0:
        best_obj = cur_obj; best_Z = Z2; best_v = venue_of.copy(); best_s = slot_of.copy(); best_viol = 0
    else:
        best_obj = -1e18; best_Z = -1e18; best_v = venue_of.copy(); best_s = slot_of.copy(); best_viol = cur_viol
    # 预计算 (v,s) 占用集合加速
    T = T0
    for it in range(iters):
        T = T0 * (Tend / T0) ** (it / iters)
        m = int(rng.integers(0, nm))
        old_v, old_s = int(venue_of[m]), int(slot_of[m])
        move = int(rng.integers(0, 3))
        new_v, new_s = old_v, old_s
        m2 = None
        if move == 0:  # 换馆
            cands = [v for v in range(G["nv"]) if G["eligible"][m, v] and v != old_v]
            if not cands: continue
            new_v = int(cands[int(rng.integers(0, len(cands)))])
            new_s = old_s
        elif move == 1:  # 换时段
            new_s = int(rng.integers(0, G["ns"]))
            if new_s == old_s: continue
            new_v = old_v
        else:  # 两场交换 (venue,slot)
            m2 = int(rng.integers(0, nm))
            if m2 == m: continue
            new_v, new_s = int(venue_of[m2]), int(slot_of[m2])
            if not G["eligible"][m, new_v]: continue
            if not G["eligible"][m2, old_v]: continue
        # 应用
        venue_of[m], slot_of[m] = new_v, new_s
        if m2 is not None:
            venue_of[m2], slot_of[m2] = old_v, old_s
        # 快速可行性（硬约束）
        ok = quick_feasible(G, venue_of, slot_of, m, m2)
        if not ok:
            venue_of[m], slot_of[m] = old_v, old_s
            if m2 is not None:
                venue_of[m2], slot_of[m2] = new_v, new_s
            continue
        Z2_new, _, _ = objective_terms(G, venue_of, slot_of)
        # 只在硬约束全满足时才精算违反（快路径：用 quick 已保证硬约束），软约束（场馆总数）单独计
        viol_new = check_constraints(G, venue_of, slot_of)
        new_viol = viol_new["total_violations"]
        new_obj = Z2_new - hard_penalty * new_viol
        dZ = new_obj - cur_obj
        if dZ > 0 or rng.random() < np.exp(dZ / max(T, 1e-9)):
            cur_obj = new_obj; Z2 = Z2_new; cur_viol = new_viol
            if cur_viol == 0 and Z2 > best_Z:
                best_Z = Z2; best_v = venue_of.copy(); best_s = slot_of.copy(); best_viol = 0
                best_obj = cur_obj
            elif new_viol == 0 and new_obj > best_obj:
                best_obj = new_obj; best_v = venue_of.copy(); best_s = slot_of.copy(); best_viol = 0
        else:
            venue_of[m], slot_of[m] = old_v, old_s
            if m2 is not None:
                venue_of[m2], slot_of[m2] = new_v, new_s
    # 若从未找到零违反解，返回最终状态（least-violation 的近似）
    if best_Z <= -1e17:
        best_v = venue_of.copy(); best_s = slot_of.copy()
        best_Z, _, _ = objective_terms(G, best_v, best_s)
    return best_v, best_s, best_Z


def quick_feasible(G, venue_of, slot_of, m, m2=None):
    """快速检查关键约束（不全量，SA 内调用）。含 R3 每日高等级安保容量、60h 双向（prev+next）。"""
    nm = G["nm"]
    v, s = venue_of[m], slot_of[m]
    # 安保资格
    if not G["eligible"][m, v]:
        return False
    # 60h 双向：检查 m 的前一轮（m 相对 prev）与后一轮（next 相对 m）
    rnd = G["rnd"][m]
    if rnd > 1:
        for team in [G["ta_id"][m], G["tb_id"][m]]:
            mprev = find_match_of_team_round(G, team, rnd - 1)
            if mprev >= 0 and venue_of[mprev] >= 0:
                dt = G["utc_ts"][s] - G["utc_ts"][slot_of[mprev]]
                if dt < HOUR60:
                    return False
    if rnd < 3:
        for team in [G["ta_id"][m], G["tb_id"][m]]:
            mnext = find_match_of_team_round(G, team, rnd + 1)
            if mnext >= 0 and venue_of[mnext] >= 0:
                dt = G["utc_ts"][slot_of[mnext]] - G["utc_ts"][s]
                if dt < HOUR60:
                    return False
    # 同组同轮不同时段
    for mm in range(nm):
        if mm != m and G["grp"][mm] == G["grp"][m] and G["rnd"][mm] == G["rnd"][m] and slot_of[mm] == s:
            return False
    # 场馆时段不撞
    for mm in range(nm):
        if mm != m and venue_of[mm] == v and slot_of[mm] == s:
            return False
    # R3 每日高等级安保容量：若 m 是 R3 且 req>=3，检查该日累计
    cap_map = G.get("r3_high_sec_cap", {})
    if rnd == 3 and G["req_sec"][m] >= 3:
        d = G["slot_date"][s]
        cnt = 1
        for mm in range(nm):
            if mm != m and G["rnd"][mm] == 3 and G["req_sec"][mm] >= 3 and G["slot_date"][slot_of[mm]] == d:
                cnt += 1
        lim = cap_map.get(str(d))
        if lim is not None and cnt > lim:
            return False
    if m2 is not None:
        v2, s2 = venue_of[m2], slot_of[m2]
        if not G["eligible"][m2, v2]:
            return False
        for mm in range(nm):
            if mm != m2 and venue_of[mm] == v2 and slot_of[mm] == s2:
                return False
        # m2 的 60h 双向
        rnd2 = G["rnd"][m2]
        if rnd2 > 1:
            for team in [G["ta_id"][m2], G["tb_id"][m2]]:
                mprev = find_match_of_team_round(G, team, rnd2 - 1)
                if mprev >= 0 and venue_of[mprev] >= 0:
                    if G["utc_ts"][s2] - G["utc_ts"][slot_of[mprev]] < HOUR60:
                        return False
        if rnd2 < 3:
            for team in [G["ta_id"][m2], G["tb_id"][m2]]:
                mnext = find_match_of_team_round(G, team, rnd2 + 1)
                if mnext >= 0 and venue_of[mnext] >= 0:
                    if G["utc_ts"][slot_of[mnext]] - G["utc_ts"][s2] < HOUR60:
                        return False
        # m2 若是 R3 高等级也检查
        if rnd2 == 3 and G["req_sec"][m2] >= 3:
            d2 = G["slot_date"][s2]
            cnt = 1
            for mm in range(nm):
                if mm != m2 and G["rnd"][mm] == 3 and G["req_sec"][mm] >= 3 and G["slot_date"][slot_of[mm]] == d2:
                    cnt += 1
            lim2 = cap_map.get(str(d2))
            if lim2 is not None and cnt > lim2:
                return False
    return True


def repair(G, venue_of, slot_of, max_passes=400):
    """纯贪心修复 60h 休息违反（快速，无内部 SA）。
    对每个 60h 违反的场，按 UTC 时间升序换到满足 60h 的合法时段（必要时换馆）。
    """
    nm = G["nm"]
    venue_of = venue_of.copy(); slot_of = slot_of.copy()
    for _ in range(max_passes):
        viol = check_constraints(G, venue_of, slot_of)
        if viol["total_violations"] == 0:
            break
        # 优先修 60h（最常见）
        fixed = False
        for m in range(nm):
            rnd = G["rnd"][m]
            if rnd <= 1:
                continue
            viol_here = False
            for team in [G["ta_id"][m], G["tb_id"][m]]:
                mprev = find_match_of_team_round(G, team, rnd - 1)
                if mprev >= 0 and venue_of[mprev] >= 0:
                    if G["utc_ts"][slot_of[m]] - G["utc_ts"][slot_of[mprev]] < HOUR60:
                        viol_here = True; break
            if not viol_here:
                continue
            old_v, old_s = int(venue_of[m]), int(slot_of[m])
            # 按时间升序试时段（先同馆，再换馆）
            cand_slots = sorted(range(G["ns"]), key=lambda s: G["utc_ts"][s])
            done = False
            # 同馆换时段
            for s in cand_slots:
                if s == old_s:
                    continue
                venue_of[m], slot_of[m] = old_v, s
                if quick_feasible(G, venue_of, slot_of, m):
                    ok = True
                    for team in [G["ta_id"][m], G["tb_id"][m]]:
                        mprev = find_match_of_team_round(G, team, rnd - 1)
                        if mprev >= 0 and venue_of[mprev] >= 0:
                            if G["utc_ts"][slot_of[m]] - G["utc_ts"][slot_of[mprev]] < HOUR60:
                                ok = False; break
                    if ok:
                        fixed = True; done = True; break
            # 换馆+换时段
            if not done:
                for v in range(G["nv"]):
                    if not G["eligible"][m, v]:
                        continue
                    for s in cand_slots:
                        if v == old_v and s == old_s:
                            continue
                        venue_of[m], slot_of[m] = v, s
                        if quick_feasible(G, venue_of, slot_of, m):
                            ok = True
                            for team in [G["ta_id"][m], G["tb_id"][m]]:
                                mprev = find_match_of_team_round(G, team, rnd - 1)
                                if mprev >= 0 and venue_of[mprev] >= 0:
                                    if G["utc_ts"][slot_of[m]] - G["utc_ts"][slot_of[mprev]] < HOUR60:
                                        ok = False; break
                            if ok:
                                fixed = True; done = True; break
                    if done:
                        break
            if done:
                break
            # 还原
            venue_of[m], slot_of[m] = old_v, old_s
        if not fixed:
            break
    Z2, _, _ = objective_terms(G, venue_of, slot_of)
    return venue_of, slot_of, Z2


def main():
    rng = np.random.default_rng(utils.SEED)
    data, venues, slots, gm, tb, bp, sec, dist, p1, drl = load_inputs()
    G = precompute_globals(gm, venues, slots, tb, bp, sec, dist, p1, drl)

    # 多起点贪心+SA
    n_starts = 6
    best_Z = -1e18; best_v = None; best_s = None; hist = []
    best_any = None  # (viol, Z, v, s) 备选
    for k in range(n_starts):
        rng_k = np.random.default_rng(utils.SEED + k)
        v0, s0 = greedy_init(G, rng_k)
        viol = check_constraints(G, v0, s0)
        Z0, _, _ = objective_terms(G, v0, s0)
        v1, s1, Z1 = simulated_annealing(G, v0, s0, rng_k, iters=6000, T0=0.05, Tend=1e-5, hard_penalty=50)
        v1, s1, Z1 = simulated_annealing(G, v1, s1, np.random.default_rng(utils.SEED + k + 100), iters=6000, T0=0.02, Tend=1e-6, hard_penalty=50)
        viol1 = check_constraints(G, v1, s1)
        print(f"start{k}: init Z={Z0:.4f} viol={viol['total_violations']} -> SA Z={Z1:.4f} viol={viol1['total_violations']}")
        hist.append({"start": k, "Z_init": float(Z0), "Z_sa": float(Z1), "viol_init": viol["total_violations"], "viol_sa": viol1["total_violations"]})
        if viol1["total_violations"] == 0 and Z1 > best_Z:
            best_Z = Z1; best_v = v1; best_s = s1
        if best_any is None or viol1["total_violations"] < best_any[0] or (viol1["total_violations"] == best_any[0] and Z1 > best_any[1]):
            best_any = (viol1["total_violations"], float(Z1), v1, s1)

    # 若无零违反解，用违反最少的并做定向修复
    if best_v is None:
        best_v, best_s = best_any[2], best_any[3]; best_Z = best_any[1]
        print(f"警告：未找到零违反解（最少 {best_any[0]} 个），启动定向修复。")
        best_v, best_s, best_Z = repair(G, best_v, best_s)
        viol_fix = check_constraints(G, best_v, best_s)
        print(f"修复后 viol={viol_fix['total_violations']} Z={best_Z:.4f}")

    # warm-start SA：从最优解出发再跑一轮精修
    if best_v is not None:
        v2, s2, Z2_ws = simulated_annealing(G, best_v, best_s,
                                             np.random.default_rng(utils.SEED + 999),
                                             iters=8000, T0=0.01, Tend=1e-7, hard_penalty=50)
        viol_ws = check_constraints(G, v2, s2)
        if viol_ws["total_violations"] == 0 and Z2_ws > best_Z:
            best_v, best_s, best_Z = v2, s2, Z2_ws
            print(f"warm-start 精修: Z2 {best_Z:.6f} (viol=0)")
        else:
            print(f"warm-start 未改善 (Z2={Z2_ws:.4f} viol={viol_ws['total_violations']})")

    # 最终约束检查
    viol_final = check_constraints(G, best_v, best_s)
    Z_final, terms, detail = objective_terms(G, best_v, best_s)
    print(f"\n最终 Z2 = {Z_final:.6f}")
    print("约束:", {k: v for k, v in viol_final.items()})
    print("分项:", {k: round(v, 4) for k, v in terms.items()})

    # 输出 result_2_group_schedule.csv（20 列模板）
    rows = []
    for m in range(G["nm"]):
        v, s = int(best_v[m]), int(best_s[m])
        att = G["att_m"][m, v]
        T_raw = G["T_raw"][m, v]; B_raw = G["B_raw_ms"][m, s]; C_raw = G["C_raw"][m, v]
        D_val = detail["D"][m]; R_val = detail["R"][m]
        venue_row = venues.iloc[v]; slot_row = slots.iloc[s]
        rows.append({
            "match_id": G["match_ids"][m],
            "group_id": G["grp"][m],
            "round_in_group": int(G["rnd"][m]),
            "team_a": G["ta_name"][m], "team_b": G["tb_name"][m],
            "venue_id": venue_row["venue_id"],
            "slot_id": slot_row["slot_id"],
            "city": venue_row["city"], "country": venue_row["country"],
            "reference_date": slot_row["date"],
            "reference_kickoff_time": slot_row["reference_kickoff_time"],
            "local_datetime": "",  # 简化：场馆当地=UTC 按场馆时区换算，留空或填 slot reference
            "utc_datetime": slot_row["reference_utc_time"],
            "required_security_level": int(G["req_sec"][m]),
            "expected_attendance": round(att, 0),
            "expected_tv_viewers": round(G["tv_pred"][m], 4),
            "ticket_revenue_usd": round(T_raw, 2),
            "broadcast_value_usd": round(B_raw, 2),
            "travel_cost_index": round(D_val, 4),
            "fairness_penalty": round(detail["F"], 4),
            "risk_index": round(R_val, 4),
            "total_objective_value": round(Z_final, 6) if m == 0 else "",
        })
    out = pd.DataFrame(rows)
    # 按 output_result/result_2_template.csv 列顺序
    tmpl = pd.read_csv(data["README"].iloc[0:0] if False else "output_result/result_2_template.csv")
    cols = list(tmpl.columns)
    for c in cols:
        if c not in out.columns:
            out[c] = ""
    out = out[cols]
    out.to_csv(utils.RESULTS / "result_2_group_schedule.csv", index=False, encoding="utf-8-sig")
    print(f"  -> result_2_group_schedule.csv ({len(out)} 行)")

    # 保存中间数据
    utils.dump_json({"Z2": float(Z_final), "terms": terms, "violations": viol_final,
                      "n_starts": n_starts, "history": hist, "seed": utils.SEED}, "p2_summary.json")
    # 每场分项
    pm = pd.DataFrame({
        "match_id": G["match_ids"], "group_id": G["grp"], "round": G["rnd"],
        "venue_id": [venues.iloc[int(v)]["venue_id"] for v in best_v],
        "slot_id": [slots.iloc[int(s)]["slot_id"] for s in best_s],
        "T_norm": detail["Tn"], "B_norm": detail["Bn"], "U": detail["U"], "H": detail["H"],
        "C_norm": detail["Cn"], "D": detail["D"], "R": detail["R"],
        "T_raw": detail["T_raw"], "B_raw": detail["B_raw"], "C_raw": detail["C_raw"],
        "per_match": detail["per_match"],
    })
    utils.dump_df(pm, "p2_per_match_terms.csv")
    return Z_final, terms, viol_final


if __name__ == "__main__":
    main()
