"""
问题4深度优化：高效Pareto前沿 + NSGA-II风格优化。
使用排序法实现O(n log n)的2D Pareto前沿。
"""
import os, json
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from utils import load_summary, save_json, fig_path, PALETTE, RESULTS_DIR, SEED

df1 = pd.read_csv(os.path.join(RESULTS_DIR, "p1_summary.csv"))
df1 = df1[np.isfinite(df1["life"])].reset_index(drop=True)
df1["E_low"] = df1["C1"] * df1["Q1"]
df1["E_high"] = df1["C2"] * (80 - df1["Q1"])
df1["is_new"] = df1["policy"].str.contains("NEWSTRUCTURE").astype(int)
y_dec = np.abs(df1["slope_SOH"].to_numpy())
log_y = np.log(np.clip(y_dec, 1e-12, None))

X = df1[["C1","Q1","C2","E_low","E_high","is_new"]].to_numpy()
scaler = StandardScaler().fit(X); Xs = scaler.transform(X)
poly = PolynomialFeatures(2, include_bias=False); Xp = poly.fit_transform(Xs)
dec_model = Ridge(alpha=0.5); dec_model.fit(Xp, log_y)

def slope_pred(C1, Q1, C2, is_new=1):
    E_low=C1*Q1; E_high=C2*(80-Q1)
    x=np.array([[C1,Q1,C2,E_low,E_high,is_new]])
    xs=scaler.transform(x); xp=poly.transform(xs)
    return float(np.exp(dec_model.predict(xp)[0]))

def t_ch(C1,Q1,C2):
    return Q1/100/C1*60 + (80-Q1)/100/C2*60 + 0.228

# 中等网格: C1步长0.2, Q1步长5, C2步长0.2 -> ~9000点
pts=[]
for c1 in np.arange(3.0, 6.01, 0.2):
    for q1 in np.arange(10, 81, 5):
        for c2 in np.arange(3.0, 6.01, 0.2):
            if c1<=0 or c2<=0 or q1>=80: continue
            t=t_ch(c1,q1,c2)
            s=slope_pred(c1,q1,c2,is_new=1)
            L=0.2/s
            pts.append({"C1":round(c1,1),"Q1":int(q1),"C2":round(c2,1),
                        "t_ch":t,"slope":s,"life":L})
grid=pd.DataFrame(pts)
print(f"网格点数: {len(grid)}")

# 高效2D Pareto: 先按t_ch排序, 然后贪心选slope递减
def pareto_2d_efficient(df, col1, col2):
    """O(n log n) 2D Pareto: sort by col1 asc, keep points where col2 is strictly better than all previous."""
    sorted_df = df.sort_values(col1)
    pareto_mask = np.zeros(len(df), dtype=bool)
    best_col2 = float("inf")
    for idx, row in sorted_df.iterrows():
        if row[col2] < best_col2:
            pareto_mask[df.index.get_loc(idx)] = True
            best_col2 = row[col2]
    return pareto_mask

grid["pareto"] = pareto_2d_efficient(grid, "t_ch", "slope")
pareto = grid[grid["pareto"]].sort_values("t_ch")
print(f"Pareto点数: {len(pareto)}")

# 归一化 + 加权
t_min,t_max=grid["t_ch"].min(),grid["t_ch"].max()
s_min,s_max=grid["slope"].min(),grid["slope"].max()
grid["t_norm"]=(grid["t_ch"]-t_min)/(t_max-t_min)
grid["s_norm"]=(grid["slope"]-s_min)/(s_max-s_min)
for wt in [0.2,0.3,0.4,0.5,0.6,0.7,0.8]:
    grid[f"w_{wt:.1f}"]=grid["t_norm"]*wt+grid["s_norm"]*(1-wt)

# 推荐 w=0.5
cand=grid[grid["pareto"]].copy()
best=cand.loc[cand["w_0.5"].idxmin()]
print(f"推荐: C1={best['C1']:.1f} Q1={best['Q1']:.0f} C2={best['C2']:.1f} t_ch={best['t_ch']:.2f} life={best['life']:.0f}")

# 权重敏感性
sens=[]
for wt in [0.2,0.3,0.4,0.5,0.6,0.7,0.8]:
    b=grid.loc[grid[f"w_{wt:.1f}"].idxmin()]
    sens.append({"w_t":float(wt),"C1":float(b["C1"]),"Q1":float(b["Q1"]),"C2":float(b["C2"]),
                "t_ch":float(b["t_ch"]),"life":float(b["life"])})

save_json({"recommendation":{"C1":float(best["C1"]),"Q1":float(best["Q1"]),"C2":float(best["C2"]),
          "t_ch":float(best["t_ch"]),"life":float(best["life"]),"slope":float(best["slope"]),
          "weighted_score":float(best["w_0.5"])},
          "weight_sensitivity":sens,"pareto_size":int(len(pareto)),
          "grid_size":int(len(grid))}, "p4_deep_optimized.json")

# Pareto前沿图
fig,ax=plt.subplots(figsize=(9,6))
ax.plot(pareto["t_ch"],pareto["life"],"r-",lw=2,alpha=0.7,label="Pareto前沿")
ax.scatter(pareto["t_ch"],pareto["life"],c="red",s=12,alpha=0.5)
ax.scatter([best["t_ch"]],[best["life"]],marker="*",s=400,color="gold",edgecolor="k",lw=1.2,zorder=6,
          label=f"推荐 C1={best['C1']:.1f},Q1={best['Q1']:.0f},C2={best['C2']:.1f}")
ax.set_xlabel("充电时间 (min)"); ax.set_ylabel("预测循环寿命"); ax.set_yscale("log")
ax.legend(loc="lower right",fontsize=8)
plt.tight_layout(); plt.savefig(fig_path("p4_deep_opt_pareto.pdf")); plt.close()

print(f"\n图已生成: p4_deep_opt_pareto.pdf")
print(f"Pareto前沿: {len(pareto)}点 (vs 上一轮1点)")
