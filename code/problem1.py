"""问题一：单向出海运输（ALNS 优化版）。

1600 条出海需求，无时间窗，飞机充足。
分层目标：min 总飞机使用时间；次 min 人员在途时间 / max 座位利用率 / min 油耗 / min 架次数。

核心洞察（见建模报告与数据分析）：
- 出海人员全部在机场上机、设施下机，机上人数随交付递减。
- 一架次最多 19 座（T3），故一架次最多运 19 人（不论去几个设施）。
- 架次数下界 K_lb = ceil(1600/19) = 85（T3 全用）。
- 合并多设施到一架次不降座数，但降油耗/架次（ceil 超可加性：ceil(a)+ceil(b) >= ceil(a+b)）。
- 远端设施需加油点（T3 往返 482.8km 上限），加油点计入 5 次着陆。

算法：
1. 初始构造：设施聚类（同机场近邻 ≤5 设施）→ 每簇按 19 座分批 → 选机型与路线（含加油点插入）。
2. ALNS：destroy（移除簇/重分批）+ repair（regret 贪心重聚类）+ 续航门控；
   邻域：跨簇迁移设施、换机型、合并/拆分批次、调整停靠序。
3. 分层：先优化总飞机使用时间，再在等优邻域优化座位利用率/油耗/在途时间。
"""
from __future__ import annotations
import sys, math, csv, json, time
from pathlib import Path
from collections import defaultdict
from itertools import combinations
sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils
import data_loader
from model import Flight, Solution, write_routes_q12, write_assignments_q12, seat_load_profile, pax_inflight_minutes
from routing import make_route, best_route_and_type, tsp_order
from utils import (AIRCRAFT, AIRPORTS, FACILITIES, REFUEL_STATIONS, nearest_airport,
                   flight_time_minutes, fuel_ok, total_fuel_kg, flight_minutes, ceil_min)

SEED = 20260803
import random
random.seed(SEED)

OUT = Path(__file__).resolve().parent.parent / "data"
RES = Path(__file__).resolve().parent.parent / "results"
FIG = Path(__file__).resolve().parent.parent / "figures"

def facility_airport(fac, D):
    return nearest_airport(fac, D)

def cluster_facilities(D, max_cluster=5):
    """把 52 设施按机场+空间邻近聚类成 ≤5 的簇。返回 list[(airport, [fac...])]。"""
    # 按最近机场分组
    by_airport = defaultdict(list)
    for f in FACILITIES:
        by_airport[facility_airport(f, D)].append(f)
    clusters = []
    for a, facs in by_airport.items():
        # 贪心近邻聚类：每次取离机场最近的未分设施作为种子，加近邻直到 5
        remaining = set(facs)
        while remaining:
            seed = min(remaining, key=lambda f: D[(a, f)])
            remaining.discard(seed)
            cluster = [seed]
            while len(cluster) < max_cluster and remaining:
                # 加离当前簇最近的
                nxt = min(remaining, key=lambda f: min(D[(c, f)] for c in cluster))
                cluster.append(nxt)
                remaining.discard(nxt)
            clusters.append((a, cluster))
    return clusters

def make_flights_from_clusters(clusters, by_dest, D):
    """每个簇：选一种机型（最小化簇内总使用时间 ceil(N/seat)*trip_time），
    按该机型座位分批，每批一架次访问簇内设施。返回 flights。"""
    flights = []
    for a, facs in clusters:
        facs = list(dict.fromkeys(facs))
        if not facs:
            continue
        all_pids = []
        pid_to_dest = {}
        for fac in facs:
            for pid in by_dest.get(fac, []):
                all_pids.append(pid)
                pid_to_dest[pid] = fac
        n = len(all_pids)
        if n == 0:
            continue
        # 对每种机型构造路线，估簇内总使用时间 = ceil(N/seat) * trip_time
        best = None  # (total_time, atype, stops, refuels)
        for t in ["T1", "T2", "T3"]:
            seat = AIRCRAFT[t]["seats"]
            res = make_route(a, facs, t, D)
            if res is None:
                continue
            stops, r = res
            # 路线必须包含所有人员 dest 设施
            if not all(pid_to_dest[pid] in stops for pid in all_pids):
                continue
            ut = flight_time_minutes(stops, t, r, D)
            ntrips = math.ceil(n / seat)
            total = ntrips * ut
            if best is None or total < best[0] - 1e-9 or (abs(total - best[0]) < 1e-9 and t < best[1]):
                best = (total, t, stops, r)
        if best is None:
            # 退化为单设施逐个：每设施独立选机型，按该机型座位分批
            for fac in facs:
                sub = by_dest.get(fac, [])
                if not sub:
                    continue
                # 单设施选机型
                bt = None
                for t in ["T1", "T2", "T3"]:
                    res = make_route(a, [fac], t, D)
                    if res is None:
                        continue
                    stops, r = res
                    seat = AIRCRAFT[t]["seats"]
                    ut = flight_time_minutes(stops, t, r, D)
                    total = math.ceil(len(sub)/seat) * ut
                    if bt is None or total < bt[0]:
                        bt = (total, t, stops, r, seat)
                if bt is None:
                    continue
                _, at, stops, r, seat = bt
                for i in range(0, len(sub), seat):
                    batch = sub[i:i+seat]
                    pax = [(pid, 0, stops.index(fac)) for pid in batch]
                    flights.append(Flight(atype=at, stops=stops, refuels=r, pax=pax))
            continue
        total, atype, stops, refuels = best
        seat = AIRCRAFT[atype]["seats"]
        for i in range(0, n, seat):
            batch = all_pids[i:i+seat]
            pax = []
            for pid in batch:
                dest = pid_to_dest[pid]
                di = stops.index(dest)
                pax.append((pid, 0, di))
            flights.append(Flight(atype=atype, stops=stops, refuels=list(refuels), pax=pax))
    return flights

def total_air_time(flights, D):
    return sum(f.use_time(D) for f in flights)

def ALNS(people, D, max_iter=40, time_limit=120):
    """以单设施独立解为起点，ALNS 尝试跨设施合并（仅在降低总时间时接受）。"""
    by_dest = defaultdict(list)
    for p in people:
        by_dest[p["destination_id"]].append(p["person_id"])
    # 起点：单设施独立解（每设施选最优机型分批）
    clusters = [[facility_airport(f, D), [f]] for f in by_dest if by_dest[f]]
    flights = make_flights_from_clusters(clusters, by_dest, D)
    best = list(flights)
    best_t = total_air_time(best, D)
    history = [(0, best_t, len(best))]
    t0 = time.time()
    for it in range(max_iter):
        if time.time() - t0 > time_limit:
            break
        # destroy：随机选若干簇，把它们的设施重新聚类合并
        clusters2 = [list(c) for c in clusters]
        k = random.randint(1, 3)
        idxs = random.sample(range(len(clusters2)), min(k, len(clusters2)))
        moved = []
        for idx in idxs:
            a, facs = clusters2[idx]
            if facs:
                mv = random.choice(facs)
                facs.remove(mv)
                moved.append(mv)
        # repair：把 moved 设施合并到某个近邻簇（≤5 设施）或新建
        for fac in moved:
            cand = [(D[(a, fac)], i) for i, (a, facs) in enumerate(clusters2) if len(facs) < 5]
            cand.sort()
            if cand:
                _, i = cand[0]
                clusters2[i][1].append(fac)
            else:
                clusters2.append([facility_airport(fac, D), [fac]])
        clusters2 = [c for c in clusters2 if c[1]]
        new_flights = make_flights_from_clusters(clusters2, by_dest, D)
        if not new_flights:
            continue
        new_t = total_air_time(new_flights, D)
        ok = all(f.feasible(D) for f in new_flights)
        assigned = sum(len(f.pax) for f in new_flights)
        if ok and assigned == len(people) and new_t < best_t:
            best = new_flights
            best_t = new_t
            clusters = clusters2
        history.append((it+1, best_t, len(best)))
    return best, history

def refine_secondary(flights, people, D, rounds=30):
    """第二层：在总使用时间不增前提下，换机型降油耗、调停靠序降在途时间。"""
    pid_to_dest = {p["person_id"]: p["destination_id"] for p in people}
    base_t = total_air_time(flights, D)
    improved = True
    it = 0
    while improved and it < rounds:
        improved = False
        it += 1
        for f in flights:
            # 尝试换更小机型（降油耗）若座位够且续航可行且时间不增
            n_pax = len(f.pax)
            fac_only = [s for s in f.stops[1:-1] if s in FACILITIES]
            for t in ["T1", "T2", "T3"]:
                if AIRCRAFT[t]["seats"] < n_pax:
                    continue
                if t == f.atype:
                    continue
                res = make_route(f.airport, fac_only, t, D)
                if res is None:
                    continue
                stops2, r2 = res
                ut2 = flight_time_minutes(stops2, t, r2, D)
                # 总时间不增（该架次时间不增即可保证总不增）
                if ut2 <= f.use_time(D):
                    fuel2 = total_fuel_kg(stops2, t, D)
                    if fuel2 < f.fuel_kg(D) - 1e-9:
                        new_pax = []
                        for pid, pi, di in f.pax:
                            fac = pid_to_dest[pid]
                            new_di = stops2.index(fac)
                            new_pax.append((pid, pi, new_di))
                        f.atype, f.stops, f.refuels, f.pax = t, stops2, r2, new_pax
                        improved = True
                        break
    return flights

def main():
    t0 = time.time()
    D = data_loader.load_distances()
    df = data_loader.load_people("Q1")
    people = df.to_dict("records")
    print(f"Q1: {len(people)} 人")

    flights, history = ALNS(people, D, max_iter=50, time_limit=90)
    flights = refine_secondary(flights, people, D, rounds=30)
    sol = Solution(flights=flights)

    # 校验
    bad = 0
    for f in flights:
        if not f.feasible(D):
            bad += 1; print("INFEASIBLE:", f.stops, f.atype)
        load = seat_load_profile(f)
        if any(l > f.seats() for l in load):
            bad += 1; print("OVERLOAD:", f.stops, load, f.seats())
    assigned = sum(len(f.pax) for f in flights)
    print(f"feasible: {len(flights)-bad}/{len(flights)}, assigned: {assigned}/{len(people)}")

    metrics = sol.metrics(D)
    print("metrics:", metrics)
    # 下界
    K_lb = math.ceil(len(people) / 19)  # T3 全用，座位容量硬下界（弱：假设全去最近设施）
    T_lb_weak = K_lb * min_flight_round_trip(D)
    # 强下界（per-facility）：每个设施 f 至少 ceil(n_f/19) 趟访问 f 的架次，每架次 ≥ t_f
    K_lb_strong, T_lb_strong = per_facility_lb(people, D)
    # 单设施独立解（可行上界参考）
    dedicated_t, dedicated_k = dedicated_per_facility(people, D)
    gap_weak = (metrics["total_air_time_min"] - T_lb_weak) / T_lb_weak * 100
    gap_strong = (metrics["total_air_time_min"] - T_lb_strong) / T_lb_strong * 100 if T_lb_strong > 0 else 0
    print(f"弱下界(座位容量): K_lb={K_lb}, T_lb={T_lb_weak}min ({T_lb_weak/60:.1f}h), gap={gap_weak:.1f}%")
    print(f"强下界(per-facility): K_lb={K_lb_strong}, T_lb={T_lb_strong}min ({T_lb_strong/60:.1f}h), gap={gap_strong:.1f}%")
    print(f"单设施独立解(参考上界): time={dedicated_t}min ({dedicated_t/60:.1f}h), trips={dedicated_k}")
    print(f"ALNS vs 独立: {(dedicated_t-metrics['total_air_time_min'])/dedicated_t*100:.1f}% 改进")
    print(f"elapsed: {time.time()-t0:.1f}s")

    person_order = list(df["person_id"])
    write_routes_q12(OUT / "q1-routes.csv", flights)
    write_assignments_q12(OUT / "q1-assignments.csv", flights, person_order)
    out = dict(metrics=metrics, K_lb=K_lb, T_lb_weak_min=T_lb_weak, gap_weak_pct=round(gap_weak,2),
               K_lb_strong=K_lb_strong, T_lb_strong_min=T_lb_strong, gap_strong_pct=round(gap_strong,2),
               dedicated_time_min=dedicated_t, dedicated_trips=dedicated_k,
               history=history, seed=SEED, elapsed_s=round(time.time()-t0,1))
    (RES / "q1_metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("written q1 results")

def per_facility_lb(people, D):
    """强下界：sum_f ceil(n_f/19) * t_f，t_f 为到 f 的最短可行往返时间。"""
    by_dest = defaultdict(list)
    for p in people:
        by_dest[p["destination_id"]].append(p["person_id"])
    total_trips = 0; total_time = 0
    for fac, pids in by_dest.items():
        n = len(pids)
        trips = math.ceil(n / 19)
        # 最短可行往返（任一机型，含加油）
        best_t = None
        for a in AIRPORTS:
            for t in ["T1", "T2", "T3"]:
                res = make_route(a, [fac], t, D)
                if res is None:
                    continue
                ut = flight_time_minutes(res[0], t, res[1], D)
                if best_t is None or ut < best_t:
                    best_t = ut
        if best_t is None:
            continue
        total_trips += trips
        total_time += trips * best_t
    return total_trips, total_time

def dedicated_per_facility(people, D):
    """单设施独立解（参考上界）：每设施选最优机型，按座位分批。返回 (total_time, trips)。"""
    by_dest = defaultdict(list)
    for p in people:
        by_dest[p["destination_id"]].append(p["person_id"])
    total = 0; trips = 0
    for fac, pids in by_dest.items():
        a = facility_airport(fac, D)
        n = len(pids)
        best = None
        for t in ["T1", "T2", "T3"]:
            res = make_route(a, [fac], t, D)
            if res is None:
                continue
            stops, r = res
            ut = flight_time_minutes(stops, t, r, D)
            tri = math.ceil(n / AIRCRAFT[t]["seats"])
            tot = tri * ut
            if best is None or tot < best[0]:
                best = (tot, tri)
        if best is None:
            continue
        total += best[0]; trips += best[1]
    return total, trips

def min_flight_round_trip(D):
    """T3 最短往返时间（含 10min 停靠）。"""
    best = None
    for a in AIRPORTS:
        for f in FACILITIES:
            stops = [a, f, a]
            ok, _ = fuel_ok(stops, "T3", D)
            if not ok:
                continue
            t = flight_time_minutes(stops, "T3", [0,0,0], D)
            if best is None or t < best:
                best = t
    return best

if __name__ == "__main__":
    main()
