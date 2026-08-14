"""公共工具：matplotlib 中文配置、min-max 归一化、clip、CSV 输出。"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
# 注册 Noto CJK ttc（避免 sans-serif 找不到）
for _p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]:
    try:
        fm.fontManager.addfont(_p)
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
OUT = Path(__file__).resolve().parent / "outputs"
FIG.mkdir(exist_ok=True, parents=True)
OUT.mkdir(exist_ok=True, parents=True)

# 中文字体
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans CJK JP", "AR PL UMing CN", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 11
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["figure.dpi"] = 150

SEED = 20260814


def minmax(x, lo=None, hi=None):
    """min-max 归一化到 [0,1]；max==min 记 0（与题面一致）。lo/hi 可外部给定。"""
    x = np.asarray(x, dtype=float)
    if lo is None:
        lo = np.nanmin(x)
    if hi is None:
        hi = np.nanmax(x)
    if hi == lo:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def clip(x, lo, hi):
    return np.clip(x, lo, hi)


def save_fig(name: str, fig_obj=None):
    p = FIG / name
    if fig_obj is not None:
        fig_obj.savefig(p)
        plt.close(fig_obj)
    else:
        plt.savefig(p)
        plt.close()
    print(f"  [fig] {p.name}")
    return p


def dump_json(obj, name: str):
    p = OUT / name
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    print(f"  [json] {p.name}")
    return p


def dump_df(df: pd.DataFrame, name: str):
    p = OUT / name
    df.to_csv(p, index=False, encoding="utf-8-sig")
    print(f"  [csv] {p.name}")
    return p


# 结果输出目录（最终提交 CSV）
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True, parents=True)
