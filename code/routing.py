"""路线构造与加油可行性：插入加油点、TSP 序、机型选择。

核心：make_route(airport, facilities, atype, D) -> (stops, refuels) 或 None
保证：首末同机场、中间海上设施 ≤5（含插入的加油点）、refuel 合法、续航可行。
"""
from __future__ import annotations
import sys, math
from itertools import permutations
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils
from utils import (AIRCRAFT, AIRPORTS, FACILITIES, REFUEL_STATIONS,
                   flight_minutes, fuel_ok, fuel_feasible, plan_refuels,
                   flight_time_minutes, total_fuel_kg, nearest_airport)

MAX_LANDINGS = 5  # 每架次最多 5 次海上着陆

def tsp_order(airport: str, facilities: list[str], D) -> list[str]:
    """枚举设施排列（≤7）最小化 A->...->A 距离；否则最近邻。"""
    if len(facilities) == 0:
        return [airport, airport]
    if len(facilities) <= 7:
        best, best_d = None, None
        for perm in permutations(facilities):
            route = [airport] + list(perm) + [airport]
            dd = sum(D[(route[i], route[i+1])] for i in range(len(route)-1))
            if best_d is None or dd < best_d:
                best_d, best = dd, route
        return best
    # 最近邻
    rem = list(facilities); route = [airport]; cur = airport
    while rem:
        nxt = min(rem, key=lambda f: D[(cur, f)])
        route.append(nxt); rem.remove(nxt); cur = nxt
    route.append(airport)
    return route

def _insert_refuel_stop(stops: list[str], atype: str, D) -> list[str] | None:
    """若现有停靠序续航不可行，尝试在最优位置插入一个可加油设施。
    返回新 stops（插入后仍 ≤ MAX_LANDINGS+2 长度）或 None。"""
    n_landings = len(stops) - 2
    if n_landings >= MAX_LANDINGS:
        return None  # 无余量插入
    airport = stops[0]
    # 候选插入位置与加油点：对每个可加油设施 R，尝试插入到使全程可行
    for R in sorted(REFUEL_STATIONS):
        # 尝试把 R 插入到每个位置 i (1..n-1)
        for i in range(1, len(stops)):
            new_stops = stops[:i] + [R] + stops[i:]
            ok, _ = fuel_ok(new_stops, atype, D)
            if ok:
                return new_stops
    return None

def make_route(airport: str, facilities: list[str], atype: str, D,
               order: list[str] | None = None):
    """构造可行架次路线。返回 (stops, refuels) 或 None。
    facilities: 本架次要访问的海上设施（去重）。"""
    facs = list(dict.fromkeys(facilities))  # 去重保序
    if len(facs) == 0:
        return None
    base = order if order else tsp_order(airport, facs, D)
    stops = base
    # 先试现有序
    ok, r = fuel_ok(stops, atype, D)
    if ok:
        return stops, r
    # 插入一个加油点
    new = _insert_refuel_stop(stops, atype, D)
    if new:
        ok, r = fuel_ok(new, atype, D)
        if ok:
            return new, r
    # 插入两个加油点（仅当余量足够）
    if len(stops) - 2 + 2 <= MAX_LANDINGS:
        for R1 in sorted(REFUEL_STATIONS):
            for i in range(1, len(stops)):
                s1 = stops[:i] + [R1] + stops[i:]
                if len(s1) - 2 > MAX_LANDINGS:
                    break
                for R2 in sorted(REFUEL_STATIONS):
                    if R2 == R1:
                        continue
                    for j in range(1, len(s1)):
                        s2 = s1[:j] + [R2] + s1[j:]
                        if len(s2) - 2 > MAX_LANDINGS:
                            break
                        ok, r = fuel_ok(s2, atype, D)
                        if ok:
                            return s2, r
    return None

def best_route_and_type(airport: str, facilities: list[str], D, types=None):
    """对给定设施集，尝试各机型，选总使用时间最小的可行方案。
    返回 (atype, stops, refuels, use_time) 或 None。
    注意：不检查座位容量（由调用方按人数预筛机型 types）。"""
    types = types or ["T3", "T2", "T1"]
    best = None
    for t in types:
        res = make_route(airport, facilities, t, D)
        if res is None:
            continue
        stops, r = res
        ut = flight_time_minutes(stops, t, r, D)
        if best is None or ut < best[3]:
            best = (t, stops, r, ut)
    return best

if __name__ == "__main__":
    D = utils.load_distance_matrix(Path(__file__).resolve().parent.parent / "data" / "distances.csv")
    # 远端设施 F050 (A03, d=403): T3 直接往返 2*403=806>482.8 需加油
    print("F050 from A03:")
    print("  T3:", make_route("A03", ["F050"], "T3", D))
    print("  best:", best_route_and_type("A03", ["F050"], D))
    # 多设施
    print("A01 -> F018,F022,F020:")
    print("  T2:", make_route("A01", ["F018","F022","F020"], "T2", D))
    print("  best:", best_route_and_type("A01", ["F018","F022","F020"], D))
