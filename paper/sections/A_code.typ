#import "../lib.typ": *

#v(1.1em)

以下为核心代码节选，完整可运行源程序见支撑材料。

== 公共工具 utils.py（续航与取整）

```python
def ceil_min(x): return math.ceil(x - 1e-9)
def flight_minutes(distance_km, speed_kmh): return ceil_min(60.0 * distance_km / speed_kmh)

def fuel_feasible(stops, atype, refuels, D):
    """架次油量可行性：满油起飞，到每点(含返场)余油>=安全余油；可加油设施加满。"""
    ac = AIRCRAFT[atype]
    cons, tank, reserve = ac["consumption"], ac["tank"], ac["reserve"]
    assert stops[0] == stops[-1] and stops[0] in AIRPORTS
    assert refuels[0] == 0 and refuels[-1] == 0
    fuel = float(tank)
    for i in range(len(stops)-1):
        fuel -= cons * D[(stops[i], stops[i+1])]
        if fuel < reserve - 1e-9: return False
        if refuels[i+1]: fuel = float(tank)
    return True
```

== 路线构造 routing.make_route（含加油点插入）

```python
def make_route(airport, facilities, atype, D):
    facs = list(dict.fromkeys(facilities))
    base = tsp_order(airport, facs, D)          # TSP 序(≤7 枚举, 否则最近邻)
    ok, r = fuel_ok(base, atype, D)
    if ok: return base, r
    new = _insert_refuel_stop(base, atype, D)   # 插入1个可加油设施
    if new:
        ok, r = fuel_ok(new, atype, D)
        if ok: return new, r
    # 插入2个加油点(受5次着陆上限约束) ... 略
    return None
```

== 问题一 problem1.py（聚类+ALNS）

```python
def ALNS(people, D, max_iter=50, time_limit=90):
    by_dest = defaultdict(list)
    for p in people: by_dest[p["destination_id"]].append(p["person_id"])
    clusters = [[facility_airport(f, D), [f]] for f in by_dest if by_dest[f]]
    flights = make_flights_from_clusters(clusters, by_dest, D)
    best = list(flights); best_t = total_air_time(best, D)
    for it in range(max_iter):
        clusters2 = [list(c) for c in clusters]
        # destroy: 随机移设施到近邻簇
        for fac in moved:
            cand = [(D[(a, fac)], i) for i,(a,facs) in enumerate(clusters2) if len(facs)<5]
            if cand: clusters2[min(cand)[1]][1].append(fac)
        new_flights = make_flights_from_clusters(clusters2, by_dest, D)
        new_t = total_air_time(new_flights, D)
        if all(f.feasible(D) for f in new_flights) and new_t < best_t:
            best, best_t, clusters = new_flights, new_t, clusters2
    return best, history
```

== 问题三 problem3.py（两阶段：非临时排班+临时增量）

```python
def schedule_non_temp(people, D):
    # 全局按(pickup时间,优先级)排序，逐需求处理
    for p in all_req:
        for trip in open_trips:
            if can_join(trip, p, D):       # 加入已有架次(零成本)
                join_trip(trip, p, D); break
        else:
            try_open_trip(...)              # 新开，多日重试
    return trips

# 阶段B：临时增量
for p in temp:
    for trip in trips:
        if can_join_trip(trip, p, D):       # 优先插入现有(0额外时间)
            join_into(trip, p, D); temp_served += 1; break
# 第二优先：新开架次(受 T<=T0 约束)
```

== 独立校验 validate.py

```python
def check_q12(q):
    # 首末同机场·≤5站·stop_order连续·refuel合法·续航可行
    # assignments pickup<delivery·起终点一致·delivery为首次到终点
    # 座位不超载·全员已分配
def check_q3():
    # 时刻链 arrival=dep+ceil(60*d/v)·运营窗·周转≥30min·不过夜·机队配额·续航
```
