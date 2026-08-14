"""问题三：带时间窗的多日排班（24 架飞机配额 + 周转 + 优先级 + 临时可取消）。

两阶段：
- 阶段A：排非临时 3840 条（shift+production+emergency），得总飞机使用时间 T0。
- 阶段B：在 T_air <= T0 下，贪心+局部搜索尽量塞入 160 条 temporary，最大化满足数。

约束：
- 24 架飞机（A01:T1×3,T2×3,T3×2; A02:T1×2,T2×4,T3×2; A03:T1×2,T2×3,T3×3），编号 机场-机型-序号。
- 起飞 06:00-18:00，返场 ≤20:00，不过夜；架次返场后 ≥30min 周转。
- 时间窗：pickup 时刻 >= earliest_pickup_time，delivery 时刻 <= latest_arrival_time。
- 时刻链：arrival_j = departure_i + ceil(60*d/v)；首行只 departure，末行只 arrival。
- 续航：满油起飞，余油≥安全余油，可加油点加满。
- 优先级：emergency > production > shift > temporary；temporary 可取消。
"""
from __future__ import annotations
import sys, math, csv, json, time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils
import data_loader
from model import Flight, Solution, seat_load_profile
from routing import make_route, best_route_and_type, tsp_order
from utils import (AIRCRAFT, AIRPORTS, FACILITIES, REFUEL_STATIONS, nearest_airport,
                   flight_time_minutes, fuel_ok, total_fuel_kg, flight_minutes, ceil_min,
                   DWELL_NO_REFUEL, DWELL_REFUEL)

SEED = 20260803
import random
random.seed(SEED)

OUT = Path(__file__).resolve().parent.parent / "data"
RES = Path(__file__).resolve().parent.parent / "results"

FMT = "%Y-%m-%d %H:%M"
DAY0 = datetime(2026, 8, 3)

# 机队表
FLEET = []  # (aircraft_id, airport, atype)
for a in AIRPORTS:
    counts = {"A01": {"T1":3,"T2":3,"T3":2}, "A02": {"T1":2,"T2":4,"T3":2}, "A03": {"T1":2,"T2":3,"T3":3}}[a]
    for t in ["T1","T2","T3"]:
        for k in range(1, counts[t]+1):
            FLEET.append((f"{a}-{t}-H{k:02d}", a, t))

OP_START = 6*60   # 06:00
OP_END = 18*60    # 18:00 takeoff latest
RET_LIMIT = 20*60 # 20:00 return latest
TURNAROUND = 30   # min

def to_min(dt: datetime) -> int:
    """绝对分钟（自 2026-08-03 00:00）。"""
    return int((dt - DAY0).total_seconds() // 60)

def from_min(m: int) -> datetime:
    return DAY0 + timedelta(minutes=m)

def date_of(m: int) -> int:
    return m // 1440  # 第几天（0-based, 8-03 为 0）

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

def plan_trip_timed(airport, facs, atype, D, depart_min):
    """给定机场、设施集、机型、起飞时刻，计算各站到达/离开时刻与可行性。
    返回 (stops, refuels, arrivals, departures) 或 None。
    约束：返场 ≤ 20:00 且不过夜（返场同日）；续航可行。
    """
    res = make_route(airport, facs, atype, D)
    if res is None:
        return None
    stops, refuels = res
    ac = AIRCRAFT[atype]
    n = len(stops)
    arrivals = [None]*n
    departures = [None]*n
    t = depart_min
    departures[0] = t
    for i in range(n-1):
        seg = flight_minutes(D[(stops[i], stops[i+1])], ac["speed"])
        t += seg
        arrivals[i+1] = t
        if i+1 < n-1:
            dwell = DWELL_REFUEL if refuels[i+1] else DWELL_NO_REFUEL
            t += dwell
            departures[i+1] = t
    arrivals[-1] = t  # 末站机场到达
    # 校验：返场同日且 ≤ 20:00
    if date_of(t) != date_of(depart_min):
        return None  # 过夜
    # 返场时刻在 20:00 前（按当日分钟）
    day_ret = t - date_of(depart_min)*1440
    if day_ret > RET_LIMIT:
        return None
    return stops, refuels, arrivals, departures

def schedule_non_temp(people, D):
    """阶段A：排非临时需求，按时间优先 + 设施聚合。
    按 (pickup 时间, 优先级) 全局排序需求，逐个尝试安排到已有架次或新开架次。
    """
    non_temp = [p for p in people if p["task_type"] != "temporary"]
    out, ret, shu = classify(non_temp)
    out_by_dest = defaultdict(list)
    for p in out: out_by_dest[p["destination_id"]].append(p)
    ret_by_origin = defaultdict(list)
    for p in ret: ret_by_origin[p["origin_id"]].append(p)
    shu_pairs = defaultdict(list)
    for p in shu: shu_pairs[(p["origin_id"], p["destination_id"])].append(p)

    plane_avail = {}
    for aid, a, t in FLEET:
        plane_avail[aid] = 0*1440 + OP_START
    # 飞机忙区间记录（精确冲突检测，替代单点 plane_avail）
    plane_busy = {aid: [] for aid, _, _ in FLEET}  # aid -> [(start, end), ...]
    trips = []
    served = set()

    def is_plane_free(aid, t_start, t_end):
        """检查飞机 aid 在 [t_start, t_end] 是否无重叠。"""
        for s, e in plane_busy[aid]:
            if not (e <= t_start or s >= t_end):
                return False
        return True

    def try_open_trip(airport, atype, facs, depart, pax_spec, D):
        """尝试新开一架次。pax_spec: list of (pid, pickup_fac, delivery_fac, p).
        返回 trip dict 或 None。用区间冲突检测替代单点 plane_avail。"""
        res = plan_trip_timed(airport, facs, atype, D, depart)
        if res is None:
            return None
        stops, refuels, arrs, deps = res
        # 校验 pickup/delivery 序与时间窗
        pax = []
        for pid, pf, df, p in pax_spec:
            if pf is not None and pf not in stops: return None
            if df is not None and df not in stops: return None
            pi = 0 if pf is None else stops.index(pf)
            di = len(stops)-1 if df is None else stops.index(df)
            if pi >= di: return None
            # pickup 时刻 = deps[pi] (leave origin); delivery = arrs[di]
            ep = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
            la = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
            if deps[pi] < ep: return None
            if arrs[di] > la: return None
            pax.append((pid, pi, di, p))
        # 座位容量
        load = [0]*(len(stops)-1)
        on=[0]*len(stops); off=[0]*len(stops)
        for pid, pi, di, _ in pax:
            on[pi]+=1; off[di]+=1
        cur=0
        for i in range(len(stops)-1):
            cur+=on[i]-off[i]
            if cur > AIRCRAFT[atype]["seats"]: return None
        # 飞机占用区间
        trip_start = depart
        trip_end = arrs[-1] + TURNAROUND
        # 找飞机：用区间冲突检测（不再依赖单点 plane_avail）
        cands = [(aid2, plane_avail[aid2]) for aid2, ap, t2 in FLEET if ap==airport and t2==atype]
        # 优先选 plane_avail <= depart 且区间无冲突的
        aid_chosen = None; real_depart = depart
        for aid2, avail in cands:
            if avail <= depart and is_plane_free(aid2, trip_start, trip_end):
                aid_chosen = aid2; break
        if aid_chosen is None:
            # 尝试延后起飞（取最早可用）
            cands2 = sorted(cands, key=lambda x: x[1])
            for aid2, avail in cands2:
                rd = max(depart, avail)
                if rd > date_of(depart)*1440 + OP_END:
                    continue
                res2 = plan_trip_timed(airport, facs, atype, D, rd)
                if res2 is None: continue
                stops2, refuels2, arrs2, deps2 = res2
                trip_end2 = arrs2[-1] + TURNAROUND
                if not is_plane_free(aid2, rd, trip_end2):
                    continue
                # 重校验时间窗
                pax2 = []
                ok = True
                for pid, pf, df, p in pax_spec:
                    pi = 0 if pf is None else stops2.index(pf)
                    di = len(stops2)-1 if df is None else stops2.index(df)
                    if pi>=di: ok=False; break
                    ep = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
                    la = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
                    if deps2[pi] < ep or arrs2[di] > la: ok=False; break
                    pax2.append((pid, pi, di, p))
                if not ok: continue
                stops, refuels, arrs, deps = stops2, refuels2, arrs2, deps2
                pax = pax2
                load = [0]*(len(stops)-1)
                on=[0]*len(stops); off=[0]*len(stops)
                for pid, pi, di, _ in pax:
                    on[pi]+=1; off[di]+=1
                cur=0
                for i in range(len(stops)-1):
                    cur+=on[i]-off[i]
                    if cur > AIRCRAFT[atype]["seats"]: ok=False; break
                if not ok: continue
                aid_chosen = aid2
                real_depart = rd
                trip_start = rd
                trip_end = trip_end2
                break
        if aid_chosen is None:
            return None
        if date_of(arrs[-1]) != date_of(real_depart): return None
        if arrs[-1] - date_of(real_depart)*1440 > RET_LIMIT: return None
        plane_avail[aid_chosen] = arrs[-1] + TURNAROUND
        plane_busy[aid_chosen].append((trip_start, arrs[-1] + TURNAROUND))
        return dict(aircraft_id=aid_chosen, airport=airport, atype=atype, stops=stops,
                    refuels=refuels, arrivals=arrs, departures=deps, pax=pax)

    # 调度顺序：按 (pickup 时间, 优先级) 排序——时间优先，同级紧急优先。
    # 时间优先使宽窗倒班填入早期架次空位，最大化服务数与座位利用；紧急/生产在同时刻优先占位。
    # 紧窗高优先级若被早高峰机位冲突挤掉，由末轮补漏用任意机场/跨日重试。
    prio = {"emergency":0, "production":1, "shift":2}
    all_req = sorted(non_temp, key=lambda p: (p["earliest_pickup_time"], prio.get(p["task_type"], 3)))

    open_trips = []  # 可继续装人的已开架次

    def can_join(trip, p, D):
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        if oL and d in FACILITIES: pf, df = None, d
        elif o in FACILITIES and dL: pf, df = o, None
        elif o in FACILITIES and d in FACILITIES: pf, df = o, d
        else: return False
        if pf is not None and pf not in stops: return False
        if df is not None and df not in stops: return False
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        if pi >= di: return False
        ep = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
        la = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
        if trip["departures"][pi] < ep: return False
        if trip["arrivals"][di] > la: return False
        on=[0]*len(stops); off=[0]*len(stops)
        for pid2, pi2, di2, _ in trip["pax"]:
            on[pi2]+=1; off[di2]+=1
        on[pi]+=1; off[di]+=1
        cur=0
        for i in range(len(stops)-1):
            cur+=on[i]-off[i]
            if cur > AIRCRAFT[trip["atype"]]["seats"]: return False
        return True

    def join_trip(trip, p, D):
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        pf = None if oL else o
        df = None if dL else d
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        trip["pax"].append((p["person_id"], pi, di, p))

    # 预批处理已移除（会降低覆盖率）；改用 per-person 调度 + 后置整合
    for p in all_req:
        if p["person_id"] in served:
            continue
        joined = False
        # 先尝试加入已有开放架次（按可容纳更多人的优先）
        for trip in open_trips:
            if can_join(trip, p, D):
                join_trip(trip, p, D)
                served.add(p["person_id"])
                joined = True
                break
        if joined:
            continue
        # 新开架次：以 p 为种子，facs 由 p 的起终点定
        o, d = p["origin_id"], p["destination_id"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        if oL and d in FACILITIES:
            facs = [d]; a = nearest_airport(d, D); seed_pf, seed_df = None, d
        elif o in FACILITIES and dL:
            facs = [o]; a = nearest_airport(o, D); seed_pf, seed_df = o, None
        elif o in FACILITIES and d in FACILITIES:
            facs = [o, d]; a = nearest_airport(o, D); seed_pf, seed_df = o, d
        else:
            continue
        ep0 = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
        la0 = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
        # 紧窗高优先级：+2日；倒班宽窗：+8日
        max_doff = 2 if p["task_type"] in ("emergency","production") else 8
        opened = False
        for d_off in range(0, max_doff):
            day = date_of(ep0) + d_off
            depart = max(ep0, day*1440 + OP_START)
            if depart > day*1440 + OP_END:
                continue
            pax_spec = [(p["person_id"], seed_pf, seed_df, p)]
            for atype in ["T2", "T1", "T3"]:
                trip = try_open_trip(a, atype, facs, depart, pax_spec, D)
                if trip is None:
                    continue
                served.add(p["person_id"])
                trips.append(trip)
                open_trips.append(trip)
                opened = True
                break
            if opened:
                break
        if len(open_trips) > 300:
            cur_t = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
            open_trips = [t for t in open_trips if t["arrivals"][-1] + TURNAROUND > cur_t - 1440]
    # 末轮补漏：对仍未服务的需求，尝试强行新开架次（任意机型、多日、任意机场）。
    for p in list(all_req):
        if p["person_id"] in served:
            continue
        o, d = p["origin_id"], p["destination_id"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        if oL and d in FACILITIES:
            facs = [d]; seed_pf, seed_df = None, d
            airports_try = sorted(AIRPORTS, key=lambda a: D[(a, d)])
        elif o in FACILITIES and dL:
            facs = [o]; seed_pf, seed_df = o, None
            airports_try = sorted(AIRPORTS, key=lambda a: D[(a, o)])
        elif o in FACILITIES and d in FACILITIES:
            facs = [o, d]; seed_pf, seed_df = o, d
            airports_try = sorted(AIRPORTS, key=lambda a: D[(a, o)])
        else:
            continue
        ep0 = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
        opened = False
        for a in airports_try:
            for d_off in range(0, 8):
                day = date_of(ep0) + d_off
                depart = max(ep0, day*1440 + OP_START)
                if depart > day*1440 + OP_END:
                    continue
                pax_spec = [(p["person_id"], seed_pf, seed_df, p)]
                for atype in ["T2", "T1", "T3"]:
                    trip = try_open_trip(a, atype, facs, depart, pax_spec, D)
                    if trip is None:
                        continue
                    served.add(p["person_id"])
                    trips.append(trip)
                    open_trips.append(trip)
                    opened = True
                    break
                if opened:
                    break
            if opened:
                break

    # === 合并优化：尝试把 solo 架次的人员合并到其他兼容架次 ===
    # 对每个 solo trip，检查是否有其他 trip 可以接受其人员（同日、路径兼容、座位空、时间窗兼容）
    def can_join_trip(trip, p, D):
        """检查人员 p 能否加入已有 trip（座位有空、时间窗兼容）。"""
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        if oL and d in FACILITIES: pf, df = None, d
        elif o in FACILITIES and dL: pf, df = o, None
        elif o in FACILITIES and d in FACILITIES: pf, df = o, d
        else: return False
        if pf is not None and pf not in stops: return False
        if df is not None and df not in stops: return False
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        if pi >= di: return False
        ep = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
        la = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
        if trip["departures"][pi] < ep: return False
        if trip["arrivals"][di] > la: return False
        # 座位检查
        on=[0]*len(stops); off=[0]*len(stops)
        for pid2, pi2, di2, _ in trip["pax"]:
            on[pi2]+=1; off[di2]+=1
        on[pi]+=1; off[di]+=1
        cur=0
        for i in range(len(stops)-1):
            cur+=on[i]-off[i]
            if cur > AIRCRAFT[trip["atype"]]["seats"]: return False
        return True

    def join_into(trip, p, D):
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        pf = None if oL else o
        df = None if dL else d
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        trip["pax"].append((p["person_id"], pi, di, p))

    # 整合移至 temp 插入后执行（保留原始 trip 供 temp 匹配）
    return trips

def consolidate_trips(trips, all_req, D, AIRCRAFT, AIRPORTS, FACILITIES, FMT,
                       to_min, date_of, datetime):
    """架次整合：把小架次合并到大架次（峰值座位检查，双向尝试）。"""
    def can_join_trip(trip, p, D):
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        if oL and d in FACILITIES: pf, df = None, d
        elif o in FACILITIES and dL: pf, df = o, None
        elif o in FACILITIES and d in FACILITIES: pf, df = o, d
        else: return False
        if pf is not None and pf not in stops: return False
        if df is not None and df not in stops: return False
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        if pi >= di: return False
        ep = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
        la = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
        if trip["departures"][pi] < ep: return False
        if trip["arrivals"][di] > la: return False
        on=[0]*len(stops); off=[0]*len(stops)
        for pid2, pi2, di2, _ in trip["pax"]:
            on[pi2]+=1; off[di2]+=1
        on[pi]+=1; off[di]+=1
        cur=0
        for i in range(len(stops)-1):
            cur+=on[i]-off[i]
            if cur > AIRCRAFT[trip["atype"]]["seats"]: return False
        return True

    def join_into(trip, p, D):
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        pf = None if oL else o
        df = None if dL else d
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        trip["pax"].append((p["person_id"], pi, di, p))

    trips_sorted = sorted(trips, key=lambda t: -len(t["pax"]))
    for small in trips_sorted:
        if small not in trips:
            continue
        if len(small["pax"]) == 0:
            continue
        for big in trips:
            if big is small or big not in trips:
                continue
            if date_of(big["departures"][0]) != date_of(small["departures"][0]):
                continue
            all_fit = True
            for pid, pi, di, p in small["pax"]:
                if not can_join_trip(big, p, D):
                    all_fit = False
                    break
            if all_fit:
                for pid, pi, di, p in small["pax"]:
                    join_into(big, p, D)
                trips.remove(small)
                break
    return trips

def _schedule_non_temp_legacy(people, D):
    """[已弃用] 旧版逐设施调度，保留以备对照。"""
    return [], 0

def trips_total_air_time(trips, D):
    return sum(flight_time_minutes(t["stops"], t["atype"], t["refuels"], D) for t in trips)

def assign_flight_numbers(trips):
    """每架飞机的 flight_no 按起飞时刻从1连续。"""
    by_plane = defaultdict(list)
    for t in trips:
        by_plane[t["aircraft_id"]].append(t)
    for aid, ts in by_plane.items():
        ts.sort(key=lambda t: t["departures"][0])
        for i, t in enumerate(ts, 1):
            t["flight_no"] = i

def write_q3_routes(path, trips):
    lines = ["aircraft_id,flight_no,stop_order,facility_id,arrival_time,departure_time,refuel"]
    for t in trips:
        aid = t["aircraft_id"]; fno = t["flight_no"]
        n = len(t["stops"])
        for so in range(n):
            node = t["stops"][so]
            arr = t["arrivals"][so]
            dep = t["departures"][so]
            arr_s = "" if so == 0 else from_min(arr).strftime(FMT)
            dep_s = "" if so == n-1 else from_min(dep).strftime(FMT)
            lines.append(f"{aid},{fno},{so},{node},{arr_s},{dep_s},{t['refuels'][so]}")
    Path(path).write_text("\n".join(lines)+"\n")

def write_q3_assignments(path, trips, person_order, all_people):
    """q3-assignments.csv: person_id,aircraft_id,flight_no,pickup_stop_order,delivery_stop_order
    temporary 未安排保留空行。"""
    table = {}
    for t in trips:
        for pid, pi, di, _ in t["pax"]:
            table[pid] = (t["aircraft_id"], t["flight_no"], pi, di)
    lines = ["person_id,aircraft_id,flight_no,pickup_stop_order,delivery_stop_order"]
    for pid in person_order:
        if pid in table:
            aid, fno, pi, di = table[pid]
            lines.append(f"{pid},{aid},{fno},{pi},{di}")
        else:
            lines.append(f"{pid},,,,")
    Path(path).write_text("\n".join(lines)+"\n")

def main():
    t0 = time.time()
    D = data_loader.load_distances()
    df = data_loader.load_people("Q3")
    people = df.to_dict("records")
    out, ret, shu = classify(people)
    print(f"Q3: 总{len(people)} = 出海{len(out)} 海返{len(ret)} 穿梭{len(shu)}")
    print(f"  task: shift{sum(1 for p in people if p['task_type']=='shift')} "
          f"production{sum(1 for p in people if p['task_type']=='production')} "
          f"emergency{sum(1 for p in people if p['task_type']=='emergency')} "
          f"temporary{sum(1 for p in people if p['task_type']=='temporary')}")

    # 阶段A
    trips = schedule_non_temp(people, D)
    assign_flight_numbers(trips)
    T0 = trips_total_air_time(trips, D)
    served = sum(len(t["pax"]) for t in trips)
    print(f"\n阶段A(非临时): trips={len(trips)}, T0={T0}min ({T0/60:.1f}h), served={served}/3840")

    # 阶段B：临时增量插入。优先插入现有架次（不增时间），其次新开（受 T<=T0 约束）。
    temp = sorted([p for p in people if p["task_type"] == "temporary"],
                  key=lambda p: p["earliest_pickup_time"])
    temp_served = 0
    temp_trips = []
    # 第一优先：插入现有 trips（不增时间）
    def can_join_trip(trip, p, D):
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        if oL and d in FACILITIES: pf, df = None, d
        elif o in FACILITIES and dL: pf, df = o, None
        elif o in FACILITIES and d in FACILITIES: pf, df = o, d
        else: return False
        if pf is not None and pf not in stops: return False
        if df is not None and df not in stops: return False
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        if pi >= di: return False
        ep = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
        la = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
        if trip["departures"][pi] < ep: return False
        if trip["arrivals"][di] > la: return False
        on=[0]*len(stops); off=[0]*len(stops)
        for pid2, pi2, di2, _ in trip["pax"]:
            on[pi2]+=1; off[di2]+=1
        on[pi]+=1; off[di]+=1
        cur=0
        for i in range(len(stops)-1):
            cur+=on[i]-off[i]
            if cur > AIRCRAFT[trip["atype"]]["seats"]: return False
        return True
    def join_into(trip, p, D):
        o, d = p["origin_id"], p["destination_id"]
        stops = trip["stops"]
        oL = (o == "LAND" or o in AIRPORTS); dL = (d == "LAND" or d in AIRPORTS)
        pf = None if oL else o
        df = None if dL else d
        pi = 0 if pf is None else stops.index(pf)
        di = len(stops)-1 if df is None else stops.index(df)
        trip["pax"].append((p["person_id"], pi, di, p))
    for p in temp:
        for trip in trips:
            if can_join_trip(trip, p, D):
                join_into(trip, p, D)
                temp_served += 1
                break
    # 第二优先：剩余 temp 新开架次（受 T<=T0 约束，用 plane_busy 检查可用性）
    cur_total = trips_total_air_time(trips, D)
    for p in temp:
        if any(pid == p["person_id"] for t in trips for pid, _, _, _ in t["pax"]):
            continue
        o, d = p["origin_id"], p["destination_id"]
        oL = (o=="LAND" or o in AIRPORTS); dL=(d=="LAND" or d in AIRPORTS)
        if oL and d in FACILITIES:
            facs=[d]; a = nearest_airport(d, D); pio=0; dio=None
        elif o in FACILITIES and dL:
            facs=[o]; a = nearest_airport(o, D); pio=1; dio=None
        elif o in FACILITIES and d in FACILITIES:
            facs=[o,d]; a = nearest_airport(o, D); pio=1; dio=None
        else:
            continue
        ep = to_min(datetime.strptime(p["earliest_pickup_time"], FMT))
        la = to_min(datetime.strptime(p["latest_arrival_time"], FMT))
        placed = False
        for d_off in range(0, 8):
            day = date_of(ep) + d_off
            depart = max(ep, day*1440 + OP_START)
            if depart > day*1440 + OP_END:
                continue
            for atype in ["T2","T1","T3"]:
                res = plan_trip_timed(a, facs, atype, D, depart)
                if res is None: continue
                stops, refuels, arrs, deps = res
                if o in FACILITIES and d in FACILITIES and stops.index(o) > stops.index(d): continue
                pi = pio
                di = len(stops)-1 if dio is None else stops.index(d)
                if pi >= di: continue
                if deps[pi] < ep: continue
                if arrs[di] > la: continue
                if date_of(arrs[-1]) != date_of(depart): continue
                if arrs[-1] - date_of(depart)*1440 > RET_LIMIT: continue
                ut = flight_time_minutes(stops, atype, refuels, D)
                if cur_total + ut > T0:
                    continue
                # 用 plane_busy 检查飞机可用性
                trip_start = depart
                trip_end = arrs[-1] + TURNAROUND
                cands = [(aid, ap) for aid, ap, t3 in FLEET if ap == a and t3 == atype]
                aid_chosen = None
                for aid2, _ in cands:
                    if is_plane_free(aid2, trip_start, trip_end):
                        aid_chosen = aid2
                        break
                if aid_chosen is None:
                    continue
                plane_busy[aid_chosen].append((trip_start, trip_end))
                pax = [(p["person_id"], pi, di, p)]
                temp_trips.append(dict(aircraft_id=aid_chosen, airport=a, atype=atype, stops=stops,
                                       refuels=refuels, arrivals=arrs, departures=deps, pax=pax))
                temp_served += 1
                cur_total += ut
                placed = True
                break
            if placed: break
        if placed: break
    all_trips = trips + temp_trips
    # === 后置整合：在 temp 插入后执行架次整合（含 temp 人员）===
    all_trips = consolidate_trips(all_trips, all_req if 'all_req' in dir() else people, D,
                                  AIRCRAFT, AIRPORTS, FACILITIES, FMT, to_min, date_of, datetime)
    T_total = trips_total_air_time(all_trips, D)
    temp_time = T_total - trips_total_air_time(trips, D)
    temp_served = sum(1 for p in temp if any(pid == p["person_id"] for t in all_trips for pid, _, _, _ in t["pax"]))
    print(f"阶段B(临时): 插入现有+新开+后置整合, 满足={temp_served}/160")
    print(f"  T0={T0}min, T_total={T_total}min, 超额={max(0,T_total-T0)}min")
    # 若新开超额，移除最晚的临时新开 trip 直到满足
    if T_total > T0:
        temp_trips.sort(key=lambda t: t["departures"][0], reverse=True)
        removed = 0
        while temp_trips and T_total > T0:
            t = temp_trips.pop(0)
            T_total -= flight_time_minutes(t["stops"], t["atype"], t["refuels"], D)
            temp_served -= len(t["pax"])
            removed += 1
        all_trips = trips + temp_trips
        T_total = trips_total_air_time(all_trips, D)
        print(f"  移除 {removed} 临时新开 trip 以满足 T<=T0，剩余满足={temp_served}/160")

    assign_flight_numbers(all_trips)
    # 指标
    metrics = compute_metrics(all_trips, D, people)
    print(f"\n最终: trips={len(all_trips)}, T_air={metrics['total_air_time_min']}min ({metrics['total_air_time_min']/60:.1f}h)")
    print(f"  temporary 满足: {temp_served}/160")
    print("  metrics:", metrics)
    print(f"elapsed: {time.time()-t0:.1f}s")

    person_order = list(df["person_id"])
    write_q3_routes(OUT / "q3-routes.csv", all_trips)
    write_q3_assignments(OUT / "q3-assignments.csv", all_trips, person_order, people)
    out_json = dict(metrics=metrics, T0_min=T0, T_total_min=T_total,
                    temp_served=temp_served, temp_total=160,
                    seed=SEED, elapsed_s=round(time.time()-t0,1))
    (RES / "q3_metrics.json").write_text(json.dumps(out_json, ensure_ascii=False, indent=2))
    print("written q3 results")

def compute_metrics(trips, D, people):
    total_air = trips_total_air_time(trips, D)
    ntrips = len(trips)
    # 人员在途时间
    total_pax = 0
    pkm = 0.0; skm = 0.0
    fuel = 0.0
    for t in trips:
        atype = t["atype"]; stops = t["stops"]; refuels = t["refuels"]
        ac = AIRCRAFT[atype]
        # 人员 in-flight
        arrs = t["arrivals"]; deps = t["departures"]
        for pid, pi, di, _ in t["pax"]:
            total_pax += (arrs[di] - deps[pi])
        # 座位利用率
        load = [0]*(len(stops)-1)
        on=[0]*len(stops); off=[0]*len(stops)
        for pid, pi, di, _ in t["pax"]:
            on[pi]+=1; off[di]+=1
        cur=0
        for i in range(len(stops)-1):
            cur+=on[i]-off[i]; load[i]=cur
        for i in range(len(stops)-1):
            seg = D[(stops[i], stops[i+1])]
            pkm += load[i]*seg; skm += ac["seats"]*seg
        fuel += total_fuel_kg(stops, atype, D)
    return dict(
        total_air_time_min=total_air,
        total_pax_time_min=total_pax,
        num_flights=ntrips,
        total_fuel_kg=round(fuel,1),
        seat_utilization=round(pkm/skm if skm>0 else 0, 4),
    )

if __name__ == "__main__":
    main()

