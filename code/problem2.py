"""问题二：出海、海返与穿梭联合运输。

4000 条需求（出海 1600 / 海返 1600 / 穿梭 800），无时间窗，飞机充足。
同一架次内三类人员混合上下机，座位动态复用（先下后上）。

核心策略（见建模报告 §5）：
- **往返环**：A -> F -> A（或 A -> F1 -> F2 -> ... -> A）。
  在设施 F：先下出海人员（dest=F），再上海返人员（origin=F）与穿梭人员（origin=F, dest=F_next）。
  座位即时复用：seg0 载出海，seg1 载海返+穿梭。
- **配对**：同一设施 F 的出海(dest=F) 与海返(origin=F) 共享同一往返环，座位复用降架次。
- **穿梭嵌入**：穿梭(origin=F1,dest=F2) 嵌入访问 F1 后访问 F2 的架次。
- 机型按 max(seg0_load, seg1_load) 选座位，续航门控 + 加油点插入。
- 分层：先 min 总飞机使用时间，再优化在途/利用率/油耗/架次数。
"""
from __future__ import annotations
import sys, math, csv, json, time
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils
import data_loader
from model import Flight, Solution, write_routes_q12, write_assignments_q12, seat_load_profile
from routing import make_route, best_route_and_type, tsp_order
from utils import (AIRCRAFT, AIRPORTS, FACILITIES, REFUEL_STATIONS, nearest_airport,
                   flight_time_minutes, fuel_ok, total_fuel_kg)

SEED = 20260803
import random
random.seed(SEED)

OUT = Path(__file__).resolve().parent.parent / "data"
RES = Path(__file__).resolve().parent.parent / "results"

def classify(people):
    out, ret, shu = [], [], []
    for p in people:
        o, d = p["origin_id"], p["destination_id"]
        oL = (o == "LAND" or o in AIRPORTS)
        dL = (d == "LAND" or d in AIRPORTS)
        if oL and d in FACILITIES:
            out.append(p)
        elif o in FACILITIES and dL:
            ret.append(p)
        elif o in FACILITIES and d in FACILITIES:
            shu.append(p)
    return out, ret, shu

def facility_airport(fac, D):
    return nearest_airport(fac, D)

def build_round_trips(out, ret, shu, D):
    """以设施为中心构造往返环：A->F->A，服务出海(dest=F)+海返(origin=F)。
    座位复用：seg0 载出海（pickup=0,delivery=F），seg1 载海返（pickup=F,delivery=末）。
    每趟 max(out_batch, ret_batch) <= seats。穿梭单独处理。
    """
    out_by_dest = defaultdict(list)
    for p in out: out_by_dest[p["destination_id"]].append(p["person_id"])
    ret_by_origin = defaultdict(list)
    for p in ret: ret_by_origin[p["origin_id"]].append(p["person_id"])
    shu_by_origin = defaultdict(list)
    for p in shu: shu_by_origin[p["origin_id"]].append((p["person_id"], p["destination_id"]))

    flights = []
    # 第一阶段：每设施 F 的往返环（出海+海返座位复用）
    for f in FACILITIES:
        no = len(out_by_dest.get(f, []))
        nr = len(ret_by_origin.get(f, []))
        if no == 0 and nr == 0:
            continue
        a = facility_airport(f, D)
        # 选机型与趟数：trips = max(ceil(no/s), ceil(nr/s))；每趟出海 x、海返 y，满足 x<=s 且 y<=s
        best_plan = None
        for t in ["T1", "T2", "T3"]:
            s = AIRCRAFT[t]["seats"]
            trips = max(math.ceil(no / s) if no else 1, math.ceil(nr / s) if nr else 1)
            if no == 0 and nr == 0:
                continue
            res = make_route(a, [f], t, D)
            if res is None:
                continue
            stops, r = res
            ut = flight_time_minutes(stops, t, r, D)
            total = trips * ut
            if best_plan is None or total < best_plan[0]:
                best_plan = (total, t, stops, r, s, trips)
        if best_plan is None:
            continue
        _, atype, stops, r, s, trips = best_plan
        out_list = out_by_dest.get(f, [])
        ret_list = ret_by_origin.get(f, [])
        # 均匀分配到 trips 趟，每趟出海 <= ceil(no/trips)，海返 <= ceil(nr/trips)，均 <= s
        for i in range(trips):
            out_batch = out_list[i::trips]
            ret_batch = ret_list[i::trips]
            # 确保不超座位（均匀分配后每趟 <= ceil，可能 == s+? 不，ceil(n/trips)<=s 因 trips>=ceil(n/s)）
            pax = []
            for pid in out_batch:
                pax.append((pid, 0, stops.index(f)))
            for pid in ret_batch:
                pax.append((pid, stops.index(f), len(stops)-1))
            flights.append(Flight(atype=atype, stops=stops, refuels=list(r), pax=pax))

    # 第二阶段：穿梭 origin=F1 -> dest=F2，构造 A->F1->F2->A
    shu_pairs = defaultdict(list)
    for f1 in shu_by_origin:
        for pid, f2 in shu_by_origin[f1]:
            shu_pairs[(f1, f2)].append(pid)
    for (f1, f2), pids in shu_pairs.items():
        if f1 == f2:
            continue
        a = facility_airport(f1, D)
        n = len(pids)
        best_plan = None
        for t in ["T1", "T2", "T3"]:
            s = AIRCRAFT[t]["seats"]
            trips = math.ceil(n / s)
            res = make_route(a, [f1, f2], t, D)
            if res is None:
                continue
            stops, r = res
            if stops.index(f1) > stops.index(f2):
                continue
            ut = flight_time_minutes(stops, t, r, D)
            total = trips * ut
            if best_plan is None or total < best_plan[0]:
                best_plan = (total, t, stops, r, s, trips)
        if best_plan is None:
            # 退化为 T3 + 加油点
            res = make_route(a, [f1, f2], "T3", D)
            if res is None:
                continue
            stops, r = res
            if stops.index(f1) > stops.index(f2):
                continue
            t = "T3"; s = 19; trips = math.ceil(n / s)
            best_plan = (trips * flight_time_minutes(stops, t, r, D), t, stops, r, s, trips)
        _, atype, stops, r, s, trips = best_plan
        for i in range(trips):
            batch = pids[i::trips]
            pax = [(pid, stops.index(f1), stops.index(f2)) for pid in batch]
            flights.append(Flight(atype=atype, stops=stops, refuels=list(r), pax=pax))
    return flights

def total_air_time(flights, D):
    return sum(f.use_time(D) for f in flights)

def refine(flights, people, D, rounds=20):
    """第二层优化：换机型降油耗（总时间不增，且不超座位）。"""
    pid_to = {p["person_id"]: (p["origin_id"], p["destination_id"]) for p in people}
    improved = True; it = 0
    while improved and it < rounds:
        improved = False; it += 1
        for f in flights:
            fac_only = [s for s in f.stops[1:-1] if s in FACILITIES]
            cur_load = seat_load_profile(f)
            cur_max_load = max(cur_load) if cur_load else 0
            for t in ["T1", "T2", "T3"]:
                if t == f.atype:
                    continue
                # 座位必须容纳当前最大机上人数
                if AIRCRAFT[t]["seats"] < cur_max_load:
                    continue
                res = make_route(f.airport, fac_only, t, D)
                if res is None:
                    continue
                stops2, r2 = res
                ut2 = flight_time_minutes(stops2, t, r2, D)
                if ut2 <= f.use_time(D) and total_fuel_kg(stops2, t, D) < f.fuel_kg(D) - 1e-9:
                    new_pax = []
                    ok = True
                    for pid, pi, di in f.pax:
                        o, dest = pid_to[pid]
                        if o in AIRPORTS or o == "LAND":
                            if dest not in stops2: ok = False; break
                            new_pax.append((pid, 0, stops2.index(dest)))
                        elif dest in AIRPORTS or dest == "LAND":
                            if o not in stops2: ok = False; break
                            new_pax.append((pid, stops2.index(o), len(stops2)-1))
                        else:
                            if o not in stops2 or dest not in stops2: ok = False; break
                            new_pax.append((pid, stops2.index(o), stops2.index(dest)))
                    if not ok:
                        continue
                    f.atype, f.stops, f.refuels, f.pax = t, stops2, r2, new_pax
                    improved = True
                    break
    return flights

def reorder_tsp(flights, D):
    """第三层优化：停靠序约束 TSP 重排。对含 ≥2 设施的架次，在满足 pickup-before-delivery
    约束的所有排列中找最短距离序，若续航可行且不增飞机使用时间则采用。
    Q1/Q2 无时间窗，故无需校验时刻链/运营窗；pax 索引重映射。
    修复 tsp_order 只做纯距离 TSP 忽略 pickup-before-delivery 的缺陷。"""
    from itertools import permutations
    reordered = 0; save = 0
    for f in flights:
        stops = f.stops; airport = stops[0]; facs = stops[1:-1]
        if len(facs) < 2:
            continue
        # pickup-before-delivery 约束
        constraints = []
        for pid, pi, di in f.pax:
            if 0 < pi < len(stops)-1 and 0 < di < len(stops)-1 and pi < di:
                constraints.append((stops[pi], stops[di]))
        cur_d = sum(D[(stops[i], stops[i+1])] for i in range(len(stops)-1))
        best = None  # (new_time, new_stops, rf)
        for perm in permutations(facs):
            pos = {fac: i for i, fac in enumerate(perm)}
            if any(pos[pf] >= pos[df] for pf, df in constraints):
                continue
            new_stops = [airport] + list(perm) + [airport]
            d = sum(D[(new_stops[i], new_stops[i+1])] for i in range(len(new_stops)-1))
            if d >= cur_d:
                continue
            ok, rf = fuel_ok(new_stops, f.atype, D)
            if not ok:
                continue
            new_t = flight_time_minutes(new_stops, f.atype, rf, D)
            if new_t >= flight_time_minutes(stops, f.atype, f.refuels, D):
                continue
            if best is None or new_t < best[0]:
                best = (new_t, new_stops, rf)
        if best is not None:
            new_t, new_stops, rf = best
            old_t = flight_time_minutes(stops, f.atype, f.refuels, D)
            # 重映射 pax 索引
            new_idx = {fac: i for i, fac in enumerate(new_stops)}
            new_pax = []
            for pid, pi, di in f.pax:
                npi = 0 if pi == 0 else new_idx[stops[pi]]
                ndi = len(new_stops)-1 if di == len(stops)-1 else new_idx[stops[di]]
                new_pax.append((pid, npi, ndi))
            f.stops = new_stops; f.refuels = rf; f.pax = new_pax
            reordered += 1; save += old_t - new_t
    return flights, reordered, save

def per_facility_lb(people, D):
    out, ret, shu = classify(people)
    out_by_dest = defaultdict(list)
    for p in out: out_by_dest[p["destination_id"]].append(p["person_id"])
    ret_by_origin = defaultdict(list)
    for p in ret: ret_by_origin[p["origin_id"]].append(p["person_id"])
    K = 0; T = 0
    for f in FACILITIES:
        no = len(out_by_dest.get(f, []))
        nr = len(ret_by_origin.get(f, []))
        if no == 0 and nr == 0:
            continue
        trips = max(math.ceil(no / 19) if no else 0, math.ceil(nr / 19) if nr else 0)
        a = nearest_airport(f, D)
        best_t = None
        for at in ["T1", "T2", "T3"]:
            res = make_route(a, [f], at, D)
            if res is None: continue
            ut = flight_time_minutes(res[0], at, res[1], D)
            if best_t is None or ut < best_t: best_t = ut
        K += trips; T += trips * best_t
    # 穿梭下界：每对(F1,F2) 至少 ceil(n/19) 趟访问 F1->F2
    shu_pairs = defaultdict(list)
    for p in shu: shu_pairs[(p["origin_id"], p["destination_id"])].append(p["person_id"])
    for (f1, f2), pids in shu_pairs.items():
        a = nearest_airport(f1, D)
        trips = math.ceil(len(pids) / 19)
        best_t = None
        for at in ["T1", "T2", "T3"]:
            res = make_route(a, [f1, f2], at, D)
            if res is None: continue
            ut = flight_time_minutes(res[0], at, res[1], D)
            if best_t is None or ut < best_t: best_t = ut
        if best_t:
            K += trips; T += trips * best_t
    return K, T

def main():
    t0 = time.time()
    D = data_loader.load_distances()
    df = data_loader.load_people("Q2")
    people = df.to_dict("records")
    out, ret, shu = classify(people)
    print(f"Q2: 总{len(people)} = 出海{len(out)} + 海返{len(ret)} + 穿梭{len(shu)}")

    flights = build_round_trips(out, ret, shu, D)
    flights = refine(flights, people, D, rounds=20)
    flights, reordered, reorder_save = reorder_tsp(flights, D)
    if reordered:
        print(f"停靠序重排: {reordered} 架次（时间-{reorder_save}min）")
    sol = Solution(flights=flights)

    # 校验
    bad = 0
    for f in flights:
        if not f.feasible(D):
            bad += 1; print("INFEASIBLE:", f.stops, f.atype)
        load = seat_load_profile(f)
        if any(l > f.seats() for l in load):
            bad += 1; print("OVERLOAD:", f.stops, load, f.seats(), "pax:", f.pax)
    assigned = sum(len(f.pax) for f in flights)
    print(f"feasible: {len(flights)-bad}/{len(flights)}, assigned: {assigned}/{len(people)}")

    metrics = sol.metrics(D)
    print("metrics:", metrics)
    K_lb, T_lb = per_facility_lb(people, D)
    gap = (metrics["total_air_time_min"] - T_lb) / T_lb * 100 if T_lb > 0 else 0
    print(f"下界: K_lb={K_lb}, T_lb={T_lb}min ({T_lb/60:.1f}h), gap={gap:.1f}%")
    print(f"elapsed: {time.time()-t0:.1f}s")

    person_order = list(df["person_id"])
    write_routes_q12(OUT / "q2-routes.csv", flights)
    write_assignments_q12(OUT / "q2-assignments.csv", flights, person_order)
    out_json = dict(metrics=metrics, K_lb=K_lb, T_lb_min=T_lb, gap_pct=round(gap,2),
                    seed=SEED, elapsed_s=round(time.time()-t0,1))
    (RES / "q2_metrics.json").write_text(json.dumps(out_json, ensure_ascii=False, indent=2))
    print("written q2 results")

if __name__ == "__main__":
    main()
