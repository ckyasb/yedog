"""公共数据加载与校验。
统一从 C题_数据附件.xlsx 读取 14 个 sheet，做行列/类型校验，供所有 problem 脚本复用。
"""
from __future__ import annotations
import os
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "C题_数据附件.xlsx"

# 实测的 sheet 规模 (行数据数, 列数)，与 analysis report 一致
EXPECTED = {
    "README": (9, 2),
    "historical_matches": (700, 25),
    "teams": (48, 16),
    "groups_matches": (72, 7),
    "group_membership": (48, 4),
    "venues": (16, 16),
    "time_slots": (80, 11),
    "distance_matrix": (1024, 8),
    "ticket_broadcast": (9, 6),
    "base_predictions": (72, 14),
    "security_requirements": (72, 9),
    "live_group_results": (48, 16),
    "dynamic_resource_limits": (20, 7),
    "dynamic_resource_costs": (10, 6),
    "objective_weights": (13, 7),
}


def _read_sheet(xlsx: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx, sheet_name=sheet, engine="openpyxl")
    # 去掉完全空行
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def load_all(verbose: bool = False) -> dict[str, pd.DataFrame]:
    if not XLSX.exists():
        raise FileNotFoundError(XLSX)
    out: dict[str, pd.DataFrame] = {}
    for sheet, (nr, nc) in EXPECTED.items():
        df = _read_sheet(XLSX, sheet)
        out[sheet] = df
        if verbose:
            print(f"[{sheet}] {len(df)}x{df.shape[1]} (期望 {nr}x{nc})")
        assert len(df) == nr, f"{sheet} 行数 {len(df)} != {nr}"
        assert df.shape[1] == nc, f"{sheet} 列数 {df.shape[1]} != {nc}"
    return out


def to_numeric_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


if __name__ == "__main__":
    data = load_all(verbose=True)
    print("\n全部 sheet 行列校验通过。")
