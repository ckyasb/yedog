"""数据加载与校验：distances + peopleQ* + 结果模板。"""
from __future__ import annotations
import csv
from pathlib import Path
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_distance_matrix, AIRPORTS, FACILITIES, ALL_NODES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_distances():
    return load_distance_matrix(DATA_DIR / "distances.csv")

def load_people(q: str):
    """q in {'Q1','Q2','Q3'}."""
    f = DATA_DIR / f"people{q}.csv"
    df = pd.read_csv(f, dtype=str)
    if q == "Q3":
        assert list(df.columns) == ["person_id", "origin_id", "destination_id",
                                     "earliest_pickup_time", "latest_arrival_time", "task_type"], df.columns
    else:
        assert list(df.columns) == ["person_id", "origin_id", "destination_id"], df.columns
    return df

def load_template_routes(q: str):
    f = DATA_DIR / f"q{q[-1]}-routes.csv"
    with open(f) as fh:
        header = fh.readline().strip()
    return header

def main():
    D = load_distances()
    print("distances: 55x55 OK")
    for q in ["Q1", "Q2", "Q3"]:
        df = load_people(q)
        print(f"people{q}: {len(df)} rows, cols={list(df.columns)}")
    # template headers
    for q in ["1", "2", "3"]:
        print(f"q{q}-routes header:", load_template_routes("Q"+q))

if __name__ == "__main__":
    main()
