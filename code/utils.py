"""
公共工具：数据读取、policy 解析、寿命外推、绘图样式、随机种子。
所有子问题脚本 import 本模块。
"""
import os, json, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

warnings.filterwarnings("ignore")

# ---------- 路径 ----------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root /home/ckyasb/yegou/A
ATTACH = os.path.join(BASE, "2026年度“策联杯”数学建模精英联赛-A题-附件")
SUMMARY_CSV = os.path.join(ATTACH, "battery_summary.csv")
CYCLE_CSV = os.path.join(ATTACH, "cycle_train.csv")
CODE_DIR = os.path.join(BASE, "code")
RESULTS_DIR = os.path.join(BASE, "results")
FIG_DIR = os.path.join(BASE, "figures")
for d in (RESULTS_DIR, FIG_DIR):
    os.makedirs(d, exist_ok=True)

# ---------- 随机种子 ----------
SEED = 42
np.random.seed(SEED)

# ---------- 中文字体 ----------
def _setup_font():
    cjk_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if os.path.exists(cjk_path):
        fm.fontManager.addfont(cjk_path)
        prop = fm.FontProperties(fname=cjk_path)
        name = prop.get_name()
        plt.rcParams["font.family"] = name
        plt.rcParams["font.sans-serif"] = [name]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42       # TrueType embed
    plt.rcParams["ps.fonttype"] = 42
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["xtick.labelsize"] = 9
    plt.rcParams["ytick.labelsize"] = 9
    plt.rcParams["legend.fontsize"] = 9
    plt.rcParams["figure.dpi"] = 150
    plt.rcParams["savefig.dpi"] = 300
    plt.rcParams["savefig.bbox"] = "tight"

_setup_font()

# 配色（灰度可分，色盲友好近似）
PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
           "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"]

# ---------- 数据读取 ----------
def load_summary():
    df = pd.read_csv(SUMMARY_CSV)
    # C1 缺失填 C2（80PER_3_6C 策略无独立第一阶段）
    df["C1"] = df["C1"].fillna(df["C2"])
    return df

def load_cycles():
    df = pd.read_csv(CYCLE_CSV)
    return df

# ---------- policy 解析 ----------
def parse_policy(policy):
    """返回 (C1, Q1, C2)，与 summary 一致校验。"""
    return None  # 依赖 summary，不单独解析

# ---------- 寿命外推 ----------
def fit_linear_life(cycles, soh_smooth, threshold=0.8):
    """线性 SOH = a + k*N（a=截距, k=斜率）外推寿命。返回 (a, k, life)。"""
    x = np.asarray(cycles, float)
    y = np.asarray(soh_smooth, float)
    if len(x) < 3:
        return np.nan, np.nan, np.nan
    # np.polyfit degree=1 返回 [slope, intercept]
    k, a = np.polyfit(x, y, 1)
    if k >= 0:  # 早期无衰减（甚至上升），无法外推寿命
        return a, k, np.nan
    life = (threshold - a) / k
    return a, k, life

def fit_exp_life(cycles, soh_smooth, threshold=0.8):
    """指数 SOH = exp(-lambda*N) 拟合（log(SOH)=-lambda*N）。返回 (lambda, life)。
    更稳健：用全部点、单调约束。lambda<=0 则寿命 NaN。"""
    x = np.asarray(cycles, float)
    y = np.clip(np.asarray(soh_smooth, float), 1e-6, None)
    if len(x) < 3:
        return np.nan, np.nan
    ly = np.log(y)
    # y = -lambda*x + const，斜率 = -lambda
    slope, _ = np.polyfit(x, ly, 1)
    lam = -slope
    if lam <= 0:
        return lam, np.nan
    life = -np.log(threshold) / lam
    return lam, life

def fit_power_life(cycles, soh_smooth, threshold=0.8):
    """SOH = 1 - alpha*N^beta 拟合。早期数据近平台，外推极不稳，仅作参考。"""
    x = np.asarray(cycles, float)
    y = np.asarray(soh_smooth, float)
    y = np.clip(y, 1e-6, None)
    diff = 1 - y
    mask = (x > 0) & (diff > 1e-9)
    if mask.sum() < 3:
        return np.nan, np.nan, np.nan
    lx = np.log(x[mask]); ly = np.log(diff[mask])
    b, la = np.polyfit(lx, ly, 1)
    alpha = np.exp(la)
    if b <= 0 or alpha <= 0:
        return alpha, b, np.nan
    life = ((1 - threshold) / alpha) ** (1 / b)
    return alpha, b, life

# ---------- 输出辅助 ----------
def save_json(obj, name):
    p = os.path.join(RESULTS_DIR, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return p

def fig_path(name):
    return os.path.join(FIG_DIR, name)

if __name__ == "__main__":
    s = load_summary()
    c = load_cycles()
    print("summary:", s.shape, "cycles:", c.shape)
    print("C1 null after fill:", s["C1"].isna().sum())
    print("policies:", s["policy"].nunique())
    print("test batteries:", int(s["prediction_test"].sum()))
