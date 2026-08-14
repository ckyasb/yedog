"""架次与解的统一表示 + 指标计算 + CSV 输出（Q1/Q2 共用；Q3 扩展时刻）。"""
from __future__ import annotations
import sys, math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
sys.path.insert(0, str(Path(__file__).resolve().parent))
import utils
from utils import (AIRCRAFT, AIRPORTS, FACILITIES, REFUEL_STATIONS, ALL_NODES,
                   flight_minutes, ceil_min, fuel_ok, flight_time_minutes, total_fuel_kg,
                   DWELL_NO_REFUEL, DWELL_REFUEL)

@dataclass
class Flight:
    """一个架次。stops[0]=stops[-1]=机场；refuels 与 stops 等长。"""
    atype: str
    stops: list[str]
    refuels: list[int]
    # 人员分配: list of (person_id, pickup_idx, delivery_idx)
    pax: list = field(default_factory=list)

    @property
    def airport(self):
        return self.stops[0]

    def landings(self) -> int:
        return len(self.stops) - 2  # 海上着陆次数（不含首末机场）

    def feasible(self, D) -> bool:
        if self.stops[0] != self.stops[-1] or self.stops[0] not in AIRPORTS:
            return False
        if self.landings() > 5:
            return False
        ok, _ = fuel_ok(self.stops, self.atype, D)
        if not ok:
            return False
        return True

    def use_time(self, D) -> int:
        return flight_time_minutes(self.stops, self.atype, self.refuels, D)

    def fuel_kg(self, D) -> float:
        return total_fuel_kg(self.stops, self.atype, D)

    def seats(self) -> int:
        return AIRCRAFT[self.atype]["seats"]


def seat_load_profile(flight: Flight) -> list[int]:
    """每段机上人数（len = len(stops)-1）。基于 flight.pax 的 pickup/delivery。"""
    n = len(flight.stops)
    on = [0]*n; off = [0]*n
    for _, pi, di in flight.pax:
        on[pi] += 1; off[di] += 1
    load = []
    cur = 0
    for i in range(n-1):
        cur += on[i]            # 该站上机（首站机场也算）
        cur -= off[i]           # 该站下机（先下后上）
        load.append(cur)
    return load

def seat_util_km(flight: Flight, D) -> tuple[float, float]:
    """返回 (机上人公里, 可用座公里)。"""
    ac = AIRCRAFT[flight.atype]
    load = seat_load_profile(flight)
    pkm = 0.0; skm = 0.0
    for i in range(len(flight.stops)-1):
        seg = D[(flight.stops[i], flight.stops[i+1])]
        pkm += load[i]*seg
        skm += ac["seats"]*seg
    return pkm, skm

def pax_inflight_minutes(flight: Flight, D) -> int:
    """该架次所有人员的在途时间之和（分钟）。
    在途 = 离开起点 -> 到达终点。无时间窗问题时，等于各段飞行+停靠累计。
    对每人：从 pickup_idx 离开 -> 到 delivery_idx 到达 的时刻差。
    """
    # 逐站累计"离开时刻"（相对起飞），中间停靠加 dwell
    ac = AIRCRAFT[flight.atype]
    dep = [0]*len(flight.stops)   # 离开各站时刻
    arr = [0]*len(flight.stops)   # 到达各站时刻
    t = 0
    for i in range(len(flight.stops)-1):
        dep[i] = t
        seg_min = flight_minutes(D[(flight.stops[i], flight.stops[i+1])], ac["speed"])
        t += seg_min
        arr[i+1] = t
        # 在 i+1 停靠
        if i+1 < len(flight.stops)-1:
            dwell = DWELL_REFUEL if flight.refuels[i+1] else DWELL_NO_REFUEL
            t += dwell
    dep[-1] = 0  # 末站机场无离开
    total = 0
    for _, pi, di in flight.pax:
        # 离开 pickup 时刻 = dep[pi]；到达 delivery 时刻 = arr[di]
        total += (arr[di] - dep[pi])
    return total

# ----------------------------------------------------------------解与指标
@dataclass
class Solution:
    flights: list[Flight]
    def total_air_time(self, D) -> int:
        return sum(f.use_time(D) for f in self.flights)
    def total_fuel(self, D) -> float:
        return sum(f.fuel_kg(D) for f in self.flights)
    def num_flights(self) -> int:
        return len(self.flights)
    def total_pax_time(self, D) -> int:
        return sum(pax_inflight_minutes(f, D) for f in self.flights)
    def seat_utilization(self, D) -> float:
        pkm = skm = 0.0
        for f in self.flights:
            p, s = seat_util_km(f, D)
            pkm += p; skm += s
        return pkm/skm if skm > 0 else 0.0
    def metrics(self, D) -> dict:
        return dict(
            total_air_time_min=self.total_air_time(D),
            total_pax_time_min=self.total_pax_time(D),
            num_flights=self.num_flights(),
            total_fuel_kg=round(self.total_fuel(D),1),
            seat_utilization=round(self.seat_utilization(D),4),
        )

# ----------------------------------------------------------------CSV 输出
def write_routes_q12(path, flights: list[Flight]):
    """q1/q2-routes.csv: aircraft_type,flight_no,stop_order,facility_id,refuel"""
    lines = ["aircraft_type,flight_no,stop_order,facility_id,refuel"]
    for fno, f in enumerate(flights, 1):
        for so, (node, rf) in enumerate(zip(f.stops, f.refuels)):
            lines.append(f"{f.atype},{fno},{so},{node},{rf}")
    Path(path).write_text("\n".join(lines)+"\n")

def write_assignments_q12(path, flights: list[Flight], person_order: list[str]):
    """q1/q2-assignments.csv: person_id,aircraft_type,flight_no,pickup_stop_order,delivery_stop_order
    按模板 person_order 行序输出，未分配者留空。"""
    # 建立 person -> (fno, pi, di)
    table = {}
    for fno, f in enumerate(flights, 1):
        for pid, pi, di in f.pax:
            table[pid] = (f.atype, fno, pi, di)
    lines = ["person_id,aircraft_type,flight_no,pickup_stop_order,delivery_stop_order"]
    for pid in person_order:
        if pid in table:
            at, fno, pi, di = table[pid]
            lines.append(f"{pid},{at},{fno},{pi},{di}")
        else:
            lines.append(f"{pid},,,,")
    Path(path).write_text("\n".join(lines)+"\n")
