"""公共工具：距离/机型/取整/续航可行性/指标。

所有时间一律向上取整到分钟（utils.ceil_min 为唯一入口）。
续航可行性 utils.fuel_feasible 为唯一实现，routes 生成与 validate 共用。
"""
from __future__ import annotations
import math
import csv
from pathlib import Path

# ----------------------------------------------------------------地点集
AIRPORTS = ["A01", "A02", "A03"]
FACILITIES = [f"F{i:03d}" for i in range(1, 53)]
REFUEL_STATIONS = {"F006", "F011", "F018", "F024", "F031", "F038", "F044", "F050"}
ALL_NODES = AIRPORTS + FACILITIES  # 55

def is_airport(x: str) -> bool:
    return x in AIRPORTS

def is_facility(x: str) -> bool:
    return x in FACILITIES

# ----------------------------------------------------------------机型参数（表1）
# seats 不含飞行员/机组；speed km/h；consumption kg/km；tank kg；reserve kg
AIRCRAFT = {
    "T1": dict(seats=12, speed=250, consumption=3.4, tank=1000, reserve=150),
    "T2": dict(seats=16, speed=220, consumption=2.5, tank=1150, reserve=150),
    "T3": dict(seats=19, speed=190, consumption=2.9, tank=1600, reserve=200),
}
AIRCRAFT_TYPES = ["T1", "T2", "T3"]

# 停靠最短时长（分钟）
DWELL_NO_REFUEL = 10
DWELL_REFUEL = 20

# ----------------------------------------------------------------取整
def ceil_min(x: float) -> int:
    """向上取整到整数分钟。"""
    return math.ceil(x - 1e-9)

def flight_minutes(distance_km: float, speed_kmh: float) -> int:
    """航段飞行时间（分钟，向上取整）。"""
    return ceil_min(60.0 * distance_km / speed_kmh)

# ----------------------------------------------------------------距离矩阵
def load_distance_matrix(path) -> dict:
    """加载 distances.csv -> {(i,j): int_km}。校验对称、对角0、55x55。"""
    rows = list(csv.reader(open(path)))
    header = rows[0]
    assert header[0] == "from_id", header[0]
    names = header[1:]
    assert names == ALL_NODES, f"距离矩阵列名与预期不符: {names}"
    D = {}
    for r in rows[1:]:
        assert r[0] in ALL_NODES, r[0]
        for j, col in enumerate(names):
            v = int(r[j + 1])
            D[(r[0], col)] = v
    # 校验
    for a in ALL_NODES:
        assert D[(a, a)] == 0, f"{a} 对角非0"
    for i in range(len(ALL_NODES)):
        for j in range(len(ALL_NODES)):
            a, b = ALL_NODES[i], ALL_NODES[j]
            assert D[(a, b)] == D[(b, a)], f"不对称 {a},{b}"
    return D

def nearest_airport(facility: str, D: dict) -> str:
    return min(AIRPORTS, key=lambda a: D[(a, facility)])

# ----------------------------------------------------------------续航可行性
def fuel_feasible(stops: list[str], atype: str, refuels: list[int], D: dict) -> bool:
    """检查架次油量可行性。

    stops: [airport, F1..Fm, airport]，首末同机场。
    refuels: 与 stops 等长的 0/1，airport 行必须 0；F 行 1 仅当 F 属于可加油设施。
    规则：满油起飞；每段扣油耗*c*距离；到达任意点（含返场）余油≥reserve；
          可加油设施停靠可选加满。
    """
    ac = AIRCRAFT[atype]
    cons, tank, reserve = ac["consumption"], ac["tank"], ac["reserve"]
    assert len(stops) == len(refuels), "stops/refuels 长度不一"
    assert len(stops) >= 2, "架次至少首末机场"
    assert stops[0] in AIRPORTS and stops[-1] in AIRPORTS, "首末须为机场"
    assert stops[0] == stops[-1], "首末须为同一机场"
    assert refuels[0] == 0 and refuels[-1] == 0, "机场行 refuel 必须 0"
    for i in range(1, len(stops) - 1):
        assert stops[i] in FACILITIES, f"中间停靠须为设施: {stops[i]}"
        if refuels[i] == 1:
            assert stops[i] in REFUEL_STATIONS, f"非可加油设施标记加油: {stops[i]}"
    fuel = tank
    for i in range(len(stops) - 1):
        seg = D[(stops[i], stops[i + 1])]
        fuel -= cons * seg
        if fuel < reserve - 1e-9:
            return False
        if refuels[i + 1]:
            fuel = tank
    return True

def flight_time_minutes(stops: list[str], atype: str, refuels: list[int], D: dict) -> int:
    """架次总飞机使用时间（分钟）：各航段飞行 + 中间停靠最短时长。"""
    ac = AIRCRAFT[atype]
    t = 0
    for i in range(len(stops) - 1):
        t += flight_minutes(D[(stops[i], stops[i + 1])], ac["speed"])
    for i in range(1, len(stops) - 1):
        t += DWELL_REFUEL if refuels[i] else DWELL_NO_REFUEL
    return t

def total_fuel_kg(stops: list[str], atype: str, D: dict) -> float:
    """架次总燃油消耗（kg）= 各航段油耗之和。"""
    ac = AIRCRAFT[atype]
    return sum(ac["consumption"] * D[(stops[i], stops[i + 1])] for i in range(len(stops) - 1))

# ----------------------------------------------------------------机型选择
def min_type_for_seats(n: int) -> str:
    """能容纳 n 人的最小座位机型（座位数优先，油耗次之）。"""
    cand = [t for t in AIRCRAFT_TYPES if AIRCRAFT[t]["seats"] >= n]
    if not cand:
        return "T3"
    return min(cand, key=lambda t: AIRCRAFT[t]["seats"])

def best_type(stops, people_count, D, prefer="time"):
    """给定架次停靠与人数，选最优机型（时间优先 / 油耗优先）。"""
    cand = []
    for t in AIRCRAFT_TYPES:
        if AIRCRAFT[t]["seats"] < people_count:
            continue
        if not fuel_feasible(stops, t, [0] * len(stops), D):
            continue
        cand.append(t)
    if not cand:
        return None
    if prefer == "time":
        return min(cand, key=lambda t: (flight_time_minutes(stops, t, [0]*len(stops), D), AIRCRAFT[t]["consumption"]))
    return min(cand, key=lambda t: total_fuel_kg(stops, t, D))

# ----------------------------------------------------------------小规模TSP（≤5设施+机场）
def best_order_outbound(airport: str, facilities: list[str], D: dict) -> list[str]:
    """纯出海（载重递减，顺序仅影响距离）：枚举设施排列最小化 A->...->A 距离。"""
    if not facilities:
        return [airport, airport]
    if len(facilities) > 7:
        # 退化为最近邻
        return _nn_order(airport, facilities, D)
    from itertools import permutations
    best, best_d = None, None
    for perm in permutations(facilities):
        route = [airport] + list(perm) + [airport]
        dd = sum(D[(route[i], route[i + 1])] for i in range(len(route) - 1))
        if best_d is None or dd < best_d:
            best_d, best = dd, route
    return best

def _nn_order(airport, facilities, D):
    remaining = list(facilities)
    route = [airport]
    cur = airport
    while remaining:
        nxt = min(remaining, key=lambda f: D[(cur, f)])
        route.append(nxt); remaining.remove(nxt); cur = nxt
    route.append(airport)
    return route

# ----------------------------------------------------------------加油点规划
def plan_refuels(stops: list[str], atype: str, D: dict):
    """在固定停靠序 stops 上求**最少加油**方案（加油站贪心），返回 refuels 或 None。

    经典加油站问题贪心：满油起飞；在沿途每个可加油设施处，判断"当前油量
    能否不加油飞到下一个可加油设施或终点机场（到达各点余油≥安全余油）"；
    若不能，则在此处加满。若加满仍到不了下一个补给点，则该停靠序不可行。
    可行性等价：在所有可加油设施都加油必可行 ⟺ 存在可行加油方案（油多不害）。
    """
    ac = AIRCRAFT[atype]
    cons, tank, reserve = ac["consumption"], ac["tank"], ac["reserve"]
    n = len(stops)
    refuels = [0] * n
    # next_supply[i] = 最小 j>i，使 stops[j] 是可加油设施 或 j==n-1(终点机场)
    next_supply = [n - 1] * n
    nxt = n - 1
    for i in range(n - 2, 0, -1):
        next_supply[i] = nxt
        if stops[i] in REFUEL_STATIONS:
            nxt = i
    fuel = float(tank)
    for i in range(n - 1):
        seg = D[(stops[i], stops[i + 1])]
        # 当前点若是可加油设施：判断是否需要在此加油才能到下一个补给点
        if i > 0 and stops[i] in REFUEL_STATIONS and refuels[i] == 0:
            j = next_supply[i]
            cons_to_next = sum(cons * D[(stops[k], stops[k + 1])] for k in range(i, j))
            if fuel - cons_to_next < reserve - 1e-9:
                fuel = float(tank)
                refuels[i] = 1
        if fuel - cons * seg < reserve - 1e-9:
            return None
        fuel -= cons * seg
        if fuel < reserve - 1e-9:
            return None
    return refuels

def feasible_refuels(stops: list[str], atype: str, D: dict):
    """尝试为 stops 找一组可行 refuels（仅现有停靠打标）。返回 (ok, refuels)。"""
    r = plan_refuels(stops, atype, D)
    if r is None:
        return False, [0] * len(stops)
    return True, r

def fuel_ok(stops: list[str], atype: str, D: dict):
    """综合：自动规划加油点并校验。返回 (是否可行, refuels)。"""
    ok, r = feasible_refuels(stops, atype, D)
    if not ok:
        return False, r
    return fuel_feasible(stops, atype, r, D), r

if __name__ == "__main__":
    D = load_distance_matrix(Path(__file__).resolve().parent.parent / "data" / "distances.csv")
    print("距离矩阵 OK, 55x55, A01-F022 =", D[("A01", "F022")])
    print("nearest_airport F050 =", nearest_airport("F050", D))
    # 续航自检：T1 max_path=(1000-150)/3.4=250km
    # A01-F022 往返 2*194=388>250 -> T1 不加油不可行; T2 max=400 -> 可行
    stops = ["A01", "F022", "A01"]
    print("T1 A01-F022-A01 不加油?", fuel_feasible(stops, "T1", [0,0,0], D), "(应False)")
    print("T2 A01-F022-A01 不加油?", fuel_feasible(stops, "T2", [0,0,0], D), "(应True)")
    # T1 经 F018(可加油, A01->F018=196<=250, F018->F022->A01=225<=250) 加油
    stops2 = ["A01", "F018", "F022", "A01"]
    print("T1 A01-F018(加油)-F022-A01?", fuel_feasible(stops2, "T1", [0,1,0,0], D), "(应True)")
    print("flight_minutes 153km T2 =", flight_minutes(153, 220))
