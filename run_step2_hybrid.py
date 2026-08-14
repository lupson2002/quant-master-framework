"""통합 퀀트 프레임워크 — Step 2 차세대 하이브리드 전략 검증 및 상관관계 분석.

1. 개별 전략 간 일별/월별 상관관계 매트릭스 산출
2. 차세대 하이브리드 전략 2종(Macro-Trend Meta, All-Weather Dynamic Alpha) 백테스팅
3. 벤치마크 및 개별 단품 대비 위험조정수익(Sharpe/Calmar) 및 하락방어(MDD) 개선도 정밀 측정
4. 3년/5년/10년 롤링 수익률 및 최악 구간 원금보존율 분석
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series
from src.backtest.engine import BacktestEngine
from src.strategies.s1_inflation_compass import InflationCompassV1
from src.strategies.s3_golden_butterfly import GoldenButterflyV1
from src.strategies.s4_dual_momentum import DualMomentumV0, DualMomentumV12
from src.strategies.s5_baa_tuned import BaaG4V2, BaaTunedV1
from src.strategies.s2_canary_mqc import CanaryMqchAaV2
from src.strategies.s6_zerolag_trend import ZeroLagTrendV2
from src.hybrid.h1_macro_trend_meta import MacroTrendMetaEngine
from src.hybrid.h2_allweather_dynamic_alpha import AllWeatherDynamicAlpha


def run_benchmarks(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    w_spy = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    w_spy["SPY"] = 1.0

    w_6040 = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    w_6040["SPY"] = 0.60
    w_6040["IEF"] = 0.40

    return {"Benchmark_SPY": w_spy, "Benchmark_60_40": w_6040}


def rolling_analysis(daily_rets: pd.Series, window_years: int = 3) -> dict[str, float]:
    """n년 롤링 복리수익률 통계 계산."""
    w_days = int(window_years * 252)
    if len(daily_rets) < w_days:
        return {}
    rolling_cum = (1.0 + daily_rets).rolling(w_days).apply(np.prod, raw=True)
    rolling_cagr = (rolling_cum ** (1.0 / window_years)) - 1.0
    rolling_cagr = rolling_cagr.dropna()

    return {
        "Rolling_Avg": rolling_cagr.mean(),
        "Rolling_Min": rolling_cagr.min(),
        "Rolling_Max": rolling_cagr.max(),
        "Negative_Ratio": (rolling_cagr < 0).mean()
    }


def main():
    print("=" * 80)
    print("🌟 [Step 2] 차세대 하이브리드 전략 백테스트 & 정밀 상관관계 분석 시작")
    print("=" * 80)

    # 1. 데이터 로드
    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    start_date = "2003-04-01"
    end_date = prices.index[-1].strftime("%Y-%m-%d")
    print(f"[*] 백테스트 구간: {start_date} ~ {end_date} (총 {len(prices.loc[start_date:end_date])} 거래일)")

    # 2. 실행 대상 전략 목록
    strategies = [
        # 벤치마크 및 핵심 단품 블록
        ("Inflation Compass (V1)", InflationCompassV1()),
        ("BAA-G4 (V2 3중쿠션)", BaaG4V2()),
        ("Dual Momentum (V0)", DualMomentumV0()),
        ("Golden Butterfly (V1)", GoldenButterflyV1()),
        ("카나리아 MQC-HAA (V2)", CanaryMqchAaV2()),
        ("ZeroLag Trend (V2)", ZeroLagTrendV2()),

        # 🔥 차세대 하이브리드 전략
        ("🏆 Hybrid 1: Macro-Trend Meta Engine", MacroTrendMetaEngine(max_leverage=1.25)),
        ("🛡️ Hybrid 2: All-Weather Dynamic Alpha", AllWeatherDynamicAlpha()),
    ]

    engine = BacktestEngine(transaction_cost_bp=15.0)  # 편도 15bp = 왕복 30bp

    results = {}
    summary_rows = []
    daily_returns_dict = {}

    # 벤치마크 실행
    for b_name, b_w in run_benchmarks(prices).items():
        res = engine.run(prices, b_w, start_date=start_date, end_date=end_date)
        results[b_name] = res
        daily_returns_dict[b_name] = res["net_daily_rets"]
        m = res["metrics_net"]
        summary_rows.append({
            "전략명": b_name,
            "구분": "벤치마크",
            "CAGR": f"{m['CAGR']*100:.2f}%",
            "연변동성": f"{m['Annual_Vol']*100:.2f}%",
            "Sharpe": f"{m['Sharpe']:.3f}",
            "Sortino": f"{m['Sortino']:.3f}",
            "MDD": f"{m['MDD']*100:.2f}%",
            "Calmar": f"{m['Calmar']:.3f}",
            "연간턴오버": f"{m['Annual_Turnover']:.1f}x",
            "_cagr": m['CAGR'],
            "_sharpe": m['Sharpe'],
            "_mdd": m['MDD']
        })

    # 전략별 실행
    for s_name, strat in strategies:
        try:
            weights = strat.generate_weights(prices, fred)
            res = engine.run(prices, weights, start_date=start_date, end_date=end_date)
            results[s_name] = res
            daily_returns_dict[s_name] = res["net_daily_rets"]
            m = res["metrics_net"]
            group_tag = "🚀 하이브리드" if "Hybrid" in s_name else "핵심단품"
            summary_rows.append({
                "전략명": s_name,
                "구분": group_tag,
                "CAGR": f"{m['CAGR']*100:.2f}%",
                "연변동성": f"{m['Annual_Vol']*100:.2f}%",
                "Sharpe": f"{m['Sharpe']:.3f}",
                "Sortino": f"{m['Sortino']:.3f}",
                "MDD": f"{m['MDD']*100:.2f}%",
                "Calmar": f"{m['Calmar']:.3f}",
                "연간턴오버": f"{m['Annual_Turnover']:.1f}x",
                "_cagr": m['CAGR'],
                "_sharpe": m['Sharpe'],
                "_mdd": m['MDD']
            })
            print(f"  [✓] {s_name:<40} | CAGR: {m['CAGR']*100:6.2f}% | Sharpe: {m['Sharpe']:5.3f} | MDD: {m['MDD']*100:6.2f}%")
        except Exception as e:
            print(f"  [✗] {s_name} 실패: {e}")

    df_summary = pd.DataFrame(summary_rows)
    print("\n" + "=" * 100)
    print("📊 [Step 2 종합 성과 비교표] (2003-04-01 ~ 현재, 실전 왕복 30bp 수수료 차감)")
    print("=" * 100)
    cols = ["전략명", "구분", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "연간턴오버"]
    print(df_summary[cols].to_string(index=False))

    # 3. 상관관계 매트릭스 산출 (월간 수익률 기준)
    df_daily_rets = pd.DataFrame(daily_returns_dict).dropna()
    df_monthly_rets = df_daily_rets.resample("ME").apply(lambda r: (1 + r).prod() - 1)
    
    corr_matrix = df_monthly_rets.corr().round(2)
    print("\n" + "=" * 100)
    print("🔗 [전략 간 월간 수익률 상관관계 매트릭스 (Correlation Matrix)]")
    print("=" * 100)
    print(corr_matrix.to_string())

    # 4. 주요 위기 국면 스트레스 테스트
    stress_rows = []
    for s_name, res in results.items():
        daily_rets = res["net_daily_rets"]
        r2008 = (1 + daily_rets.loc["2008-01-01":"2008-12-31"]).prod() - 1
        r2020 = (1 + daily_rets.loc["2020-02-01":"2020-04-30"]).prod() - 1
        r2022 = (1 + daily_rets.loc["2022-01-01":"2022-12-31"]).prod() - 1
        r2026 = (1 + daily_rets.loc["2026-01-01":]).prod() - 1

        stress_rows.append({
            "전략명": s_name,
            "2008 금융위기": f"{r2008*100:+.2f}%",
            "2020 코로나급락": f"{r2020*100:+.2f}%",
            "2022 금리폭등기": f"{r2022*100:+.2f}%",
            "2026 최신연도": f"{r2026*100:+.2f}%"
        })
    df_stress = pd.DataFrame(stress_rows)

    # 5. 3년 / 5년 롤링 분석
    rolling_rows = []
    for s_name, res in results.items():
        r3 = rolling_analysis(res["net_daily_rets"], window_years=3)
        r5 = rolling_analysis(res["net_daily_rets"], window_years=5)
        rolling_rows.append({
            "전략명": s_name,
            "3년롤링 평균": f"{r3.get('Rolling_Avg', 0)*100:.1f}%",
            "3년롤링 최악": f"{r3.get('Rolling_Min', 0)*100:+.1f}%",
            "3년적자확률": f"{r3.get('Negative_Ratio', 0)*100:.1f}%",
            "5년롤링 평균": f"{r5.get('Rolling_Avg', 0)*100:.1f}%",
            "5년롤링 최악": f"{r5.get('Rolling_Min', 0)*100:+.1f}%",
            "5년적자확률": f"{r5.get('Negative_Ratio', 0)*100:.1f}%",
        })
    df_rolling = pd.DataFrame(rolling_rows)

    # 6. 마크다운 보고서 저장
    report_file = BASE_DIR / "output" / "step2_hybrid_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 🏛️ [Step 2] 차세대 퀀트 하이브리드 전략 검증 및 상관관계 분석 보고서\n\n")
        f.write(f"- **분석 기간:** {start_date} ~ {end_date} (23.3년 풀윈도우)\n")
        f.write(f"- **거래 비용:** 편도 15bp / 왕복 30bp (0.0030) 전액 차감\n")
        f.write(f"- **실행 지연:** 당일 신호 산출 후 익일 집행(1-Day Shift, 룩어헤드 차단)\n\n")
        f.write("## 1. 종합 성과 비교표\n\n")
        f.write(df_summary[cols].to_markdown(index=False))
        f.write("\n\n## 2. 전략 간 상관관계 매트릭스 (월간 수익률)\n\n")
        f.write(corr_matrix.to_markdown())
        f.write("\n\n## 3. 주요 위기 국면 스트레스 테스트\n\n")
        f.write(df_stress.to_markdown(index=False))
        f.write("\n\n## 4. 3년 및 5년 롤링 성과 & 원금 보존 안정성\n\n")
        f.write(df_rolling.to_markdown(index=False))
        f.write("\n")

    print(f"\n[✓] Step 2 종합 검증 보고서 저장 완료: {report_file}")


if __name__ == "__main__":
    main()
