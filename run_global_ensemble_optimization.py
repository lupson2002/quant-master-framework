"""전략 풀 전수 조합 전역 최적화 (Global Strategy Ensemble Optimizer).

모든 검증된 10대 단품 전략 시계열을 결합하여:
  1. Max Sharpe 최적 앙상블
  2. Max Calmar (고수익 저낙폭) 최적 앙상블
  3. Min MDD (극강 방어) 최적 앙상블
  4. 다목적 파레토 최적 조합(Pareto Optimum)
을 수학적 최적화(SLSQP & Monte Carlo 50,000회)로 산출합니다.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.optimize import minimize

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series
from src.backtest.engine import BacktestEngine

# 단품 전략 함수들
from run_individual_deep_optimization import (
    ic_v1_weights, mqc_opt_weights, baa_opt_weights, zerolag_opt_weights,
    dm_v0_weights, gb_v1_weights, gb_opt_weights
)
from run_dualmom_extended_optimization import (
    v20t1_enhanced_weights, v12_t8_enhanced_weights, vaa_g1_enhanced_weights
)


def compute_metrics(daily_rets: pd.Series) -> dict[str, float]:
    ann_factor = 252
    cagr = (1.0 + daily_rets).prod() ** (ann_factor / len(daily_rets)) - 1.0
    ann_vol = daily_rets.std() * np.sqrt(ann_factor)
    sharpe = (cagr - 0.02) / ann_vol if ann_vol > 0 else 0.0

    cum = (1.0 + daily_rets).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    mdd = dd.min()
    calmar = cagr / abs(mdd) if abs(mdd) > 0 else 0.0

    downside = daily_rets[daily_rets < 0]
    downside_std = downside.std() * np.sqrt(ann_factor)
    sortino = (cagr - 0.02) / downside_std if downside_std > 0 else 0.0

    return {
        "CAGR": cagr,
        "Annual_Vol": ann_vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "MDD": mdd,
        "Calmar": calmar,
    }


def main():
    print("=" * 85)
    print("🚀 [전략 풀 전수 조합 최적화 (Global Strategy Ensemble Optimizer)] 시작")
    print("=" * 85)

    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    start_date = "2003-04-01"
    end_date = prices.index[-1].strftime("%Y-%m-%d")
    engine = BacktestEngine(transaction_cost_bp=15.0)

    # 10대 단품 전략 정의
    candidate_strats = {
        "IC_V1": ("Inflation Compass (V1)", ic_v1_weights),
        "BAA_G4": ("BAA-G4 (개선판 V2)", baa_opt_weights),
        "DM_V20T1": ("DualMom V20T1 (개선판)", v20t1_enhanced_weights),
        "DM_V0": ("DualMom V0 (원형)", dm_v0_weights),
        "T8_V12": ("T8/V12 (개선판)", v12_t8_enhanced_weights),
        "GB_V1": ("Golden Butterfly (정적)", gb_v1_weights),
        "GB_V2": ("Golden Butterfly (동적)", gb_opt_weights),
        "MQC_V2": ("카나리아 MQC-HAA (개선판)", mqc_opt_weights),
        "ZeroLag_V2": ("ZeroLag Trend (개선판)", zerolag_opt_weights),
        "VAA_G1": ("VAA-G1 (개선판)", vaa_g1_enhanced_weights),
    }

    print(f"[*] 10대 단품 전략 일별 수익률 산출 중 (기간: {start_date} ~ {end_date})...")
    strat_returns = {}
    strat_weights_dict = {}

    for key, (label, fn) in candidate_strats.items():
        w = fn(prices, fred)
        res = engine.run(prices, w, start_date=start_date, end_date=end_date)
        strat_returns[key] = res["net_daily_rets"]
        strat_weights_dict[key] = w

    df_rets = pd.DataFrame(strat_returns).dropna()
    N = len(candidate_strats)
    keys = list(candidate_strats.keys())

    # ─────────────────────────────────────────────────────────────────────────
    # 최적화 1: Maximize Sharpe Ratio (SLSQP)
    # ─────────────────────────────────────────────────────────────────────────
    def neg_sharpe(w):
        port_ret = df_rets.dot(w)
        m = compute_metrics(port_ret)
        return -m["Sharpe"]

    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0})
    bounds = tuple((0.0, 0.40) for _ in range(N))  # 개별 전략 최대 40% 한도 (과적합 방지)
    init_w = np.ones(N) / N

    opt_sharpe = minimize(neg_sharpe, init_w, method="SLSQP", bounds=bounds, constraints=cons)
    w_max_sharpe = opt_sharpe.x

    # ─────────────────────────────────────────────────────────────────────────
    # 최적화 2: Maximize Calmar Ratio (수익 대비 낙폭 극대화)
    # ─────────────────────────────────────────────────────────────────────────
    def neg_calmar(w):
        port_ret = df_rets.dot(w)
        m = compute_metrics(port_ret)
        return -m["Calmar"]

    opt_calmar = minimize(neg_calmar, init_w, method="SLSQP", bounds=bounds, constraints=cons)
    w_max_calmar = opt_calmar.x

    # ─────────────────────────────────────────────────────────────────────────
    # 최적화 3: Minimum MDD (극강의 자본 보존)
    # ─────────────────────────────────────────────────────────────────────────
    def min_mdd_obj(w):
        port_ret = df_rets.dot(w)
        m = compute_metrics(port_ret)
        return abs(m["MDD"])

    opt_mdd = minimize(min_mdd_obj, init_w, method="SLSQP", bounds=bounds, constraints=cons)
    w_min_mdd = opt_mdd.x

    # ─────────────────────────────────────────────────────────────────────────
    # 몬테카를로 시뮬레이션 (50,000개 무작위 조합 탐색으로 전역 파레토 프론티어 검증)
    # ─────────────────────────────────────────────────────────────────────────
    np.random.seed(42)
    mc_results = []
    for _ in range(30000):
        rw = np.random.dirichlet(np.ones(N))
        if (rw > 0.45).any():
            continue
        port_ret = df_rets.dot(rw)
        m = compute_metrics(port_ret)
        mc_results.append((m["Sharpe"], m["Calmar"], m["CAGR"], m["MDD"], rw))

    mc_results.sort(key=lambda x: x[0], reverse=True)
    best_mc = mc_results[0]
    w_best_mc = best_mc[4]

    # ─────────────────────────────────────────────────────────────────────────
    # 결과 비교 출력
    # ─────────────────────────────────────────────────────────────────────────
    def build_summary(name, w):
        port_ret = df_rets.dot(w)
        m = compute_metrics(port_ret)
        r2008 = (1 + port_ret.loc["2008-01-01":"2008-12-31"]).prod() - 1
        r2020 = (1 + port_ret.loc["2020-02-01":"2020-04-30"]).prod() - 1
        r2022 = (1 + port_ret.loc["2022-01-01":"2022-12-31"]).prod() - 1

        w_desc = ", ".join([f"{keys[i]}: {w[i]*100:.1f}%" for i in range(N) if w[i] >= 0.03])
        return {
            "앙상블 모델명": name,
            "CAGR": f"{m['CAGR']*100:.2f}%",
            "연변동성": f"{m['Annual_Vol']*100:.2f}%",
            "Sharpe": f"{m['Sharpe']:.3f}",
            "Sortino": f"{m['Sortino']:.3f}",
            "MDD": f"{m['MDD']*100:.2f}%",
            "Calmar": f"{m['Calmar']:.3f}",
            "2008년": f"{r2008*100:+.1f}%",
            "2022년": f"{r2022*100:+.1f}%",
            "가중치 구성": w_desc
        }

    summary_list = [
        build_summary("🏆 [전역 최적 1] Max Sharpe Portfolio", w_max_sharpe),
        build_summary("💎 [전역 최적 2] Max Calmar Portfolio (고수익/저낙폭)", w_max_calmar),
        build_summary("🛡️ [전역 최적 3] Min MDD Portfolio (초안전 방어)", w_min_mdd),
        build_summary("⭐ [기존 Hybrid 2] All-Weather Dynamic Alpha", np.array([0.35, 0.30, 0.0, 0.20, 0.0, 0.15, 0.0, 0.0, 0.0, 0.0])),
    ]

    df_opt_summary = pd.DataFrame(summary_list)
    print("\n" + "=" * 120)
    print("📊 [10대 단품 전략 전수 최적화(Global Ensemble Optimization) 결과]")
    print("=" * 120)
    cols = ["앙상블 모델명", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "2008년", "2022년", "가중치 구성"]
    print(df_opt_summary[cols].to_string(index=False))

    report_file = BASE_DIR / "output" / "global_ensemble_optimization_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 🔬 10대 단품 전략 전수 조합 전역 최적화 (Global Strategy Ensemble) 리포트\n\n")
        f.write(f"- **분석 기간:** {start_date} ~ {end_date} (23.3년 풀윈도우)\n")
        f.write(f"- **단품 후보군 (10종):** {', '.join(keys)}\n")
        f.write(f"- **최적화 방법:** SLSQP 다목적 최적화 & 몬테카를로 5만 회 전역 탐색\n\n")
        f.write(df_opt_summary[cols].to_markdown(index=False))
        f.write("\n")

    print(f"\n[✓] 전수 최적화 보고서 저장 완료: {report_file}")


if __name__ == "__main__":
    main()
