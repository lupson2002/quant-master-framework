"""통합 퀀트 프레임워크 — Step 1 개별 전략 전수 백테스트 & 단품 개선(V1 vs V2) 일대일 검증.

동일한 공통 기간, 동일한 30bp 거래비용, 룩어헤드 방지(1일 시프트) 조건 하에서
개별 전략들의 결함 개선 효과를 정밀하게 측정합니다.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# 경로 설정
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series, CORE_ETFS
from src.backtest.engine import BacktestEngine
from src.strategies.s1_inflation_compass import InflationCompassV1, InflationCompassV2
from src.strategies.s2_canary_mqc import CanaryMqchAaV1, CanaryMqchAaV2
from src.strategies.s3_golden_butterfly import GoldenButterflyV1, GoldenButterflyV2
from src.strategies.s4_dual_momentum import DualMomentumV0, DualMomentumV12, DualMomentumV2Enhanced
from src.strategies.s5_baa_tuned import BaaTunedV1, BaaG4V2
from src.strategies.s6_zerolag_trend import ZeroLagTrendV1, ZeroLagTrendV2
from src.strategies.s7_vaa_g1 import VaaG1Strategy
from src.strategies.s8_pct_channels import PercentileChannelsStrategy


def run_benchmark_strategies(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """기준 벤치마크 (SPY 단독, 60/40) 가중치 생성."""
    weights_spy = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    weights_spy["SPY"] = 1.0

    weights_6040 = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    weights_6040["SPY"] = 0.60
    weights_6040["IEF"] = 0.40

    return {
        "Benchmark_SPY": weights_spy,
        "Benchmark_60_40": weights_6040
    }


def main():
    print("=" * 80)
    print("🚀 [Step 1] 개별 퀀트 전략 단품 개선(V1 vs V2) 및 공통 백테스팅 검증 시작")
    print("=" * 80)

    # 1. 데이터 로드
    print("[1/4] 데이터 로드 및 정제 중...")
    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    # 공통 백테스트 기간 설정 (2003-04-01 ~ 현재)
    start_date = "2003-04-01"
    end_date = prices.index[-1].strftime("%Y-%m-%d")
    print(f"[*] 백테스트 구간: {start_date} ~ {end_date} (총 {len(prices.loc[start_date:end_date])} 거래일)")

    # 2. 전략 인스턴스 생성
    strategies = [
        # 거시 레짐군
        ("Inflation Compass (V1 원형 100%몰빵)", InflationCompassV1()),
        ("Inflation Compass (V2 동적+소프트스무딩)", InflationCompassV2()),
        
        # 카나리아 레버리지군
        ("카나리아 MQC-HAA (V1 2x 고정2위)", CanaryMqchAaV1(leverage_max=2.0)),
        ("카나리아 MQC-HAA (V2 1/2위 블렌딩 1.5x)", CanaryMqchAaV2(leverage_max=1.5)),

        # 올웨더군
        ("Golden Butterfly (V1 정적 20%)", GoldenButterflyV1()),
        ("Golden Butterfly (V2 동적 모멘텀 Top3)", GoldenButterflyV2()),

        # 듀얼모멘텀군
        ("Dual Momentum (V0 원형 100%몰빵)", DualMomentumV0()),
        ("Dual Momentum (V12 Top-2 분산 50:50)", DualMomentumV12()),
        ("Dual Momentum (V2 ZLEMA 조기탈출)", DualMomentumV2Enhanced()),

        # BAA 적응형군
        ("BAA Tuned (V1 2x All-Positive)", BaaTunedV1(use_leverage=True)),
        ("BAA-G4 (V2 3중쿠션 방어 균형형)", BaaG4V2()),

        # 일간 추세/변동성군
        ("ZeroLag Trend (V1 QLD 2x 고정)", ZeroLagTrendV1()),
        ("ZeroLag Trend (V2 변동성 다운시프트)", ZeroLagTrendV2()),

        # 추가 발굴 유망 전략군
        ("VAA-G1 (켈러 Vigilant)", VaaG1Strategy()),
        ("Percentile Channels TAA (Varadi PCT)", PercentileChannelsStrategy()),
    ]

    # 3. 백테스트 실행
    print("[2/4] 개별 전략 가중치 생성 및 벡터화 백테스트 엔진 구동 중...")
    engine = BacktestEngine(transaction_cost_bp=15.0)  # 편도 15bp = 왕복 30bp

    results = {}
    summary_rows = []

    # 벤치마크 실행
    benchmarks = run_benchmark_strategies(prices)
    for b_name, b_w in benchmarks.items():
        res = engine.run(prices, b_w, start_date=start_date, end_date=end_date)
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
        results[b_name] = res

    # 개별 전략들 실행
    for s_name, strat in strategies:
        try:
            weights = strat.generate_weights(prices, fred)
            res = engine.run(prices, weights, start_date=start_date, end_date=end_date)
            m = res["metrics_net"]
            group_tag = "개선판(V2)" if ("V2" in s_name or "V12" in s_name or "G4" in s_name or "VAA" in s_name or "PCT" in s_name) else "원형(V1)"
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
            results[s_name] = res
            print(f"  [✓] {s_name:<42} | CAGR: {m['CAGR']*100:6.2f}% | Sharpe: {m['Sharpe']:5.3f} | MDD: {m['MDD']*100:6.2f}%")
        except Exception as e:
            print(f"  [✗] {s_name} 실패: {e}")

    # 4. 결과 테이블 출력
    df_summary = pd.DataFrame(summary_rows)
    print("\n" + "=" * 100)
    print("📊 [Step 1 종합 검증 결과] (기간: 2003-04-01 ~ 현재, 왕복 30bp 수수료 차감 순수익)")
    print("=" * 100)
    cols_to_print = ["전략명", "구분", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "연간턴오버"]
    print(df_summary[cols_to_print].to_string(index=False))

    # 주요 위기 구간(2008 금융위기, 2022 인플레) 스트레스 테스트 분석
    print("\n" + "=" * 100)
    print("🛡️ [주요 위기 구간 스트레스 테스트 성과]")
    print("=" * 100)
    
    stress_rows = []
    for s_name, res in results.items():
        daily_rets = res["net_daily_rets"]
        # 2008년 (2008-01-01 ~ 2008-12-31)
        r2008 = (1 + daily_rets.loc["2008-01-01":"2008-12-31"]).prod() - 1 if len(daily_rets.loc["2008-01-01":"2008-12-31"]) > 0 else 0
        # 2020 코로나 (2020-02-01 ~ 2020-04-30)
        r2020_covid = (1 + daily_rets.loc["2020-02-01":"2020-04-30"]).prod() - 1 if len(daily_rets.loc["2020-02-01":"2020-04-30"]) > 0 else 0
        # 2022 금리폭등기 (2022-01-01 ~ 2022-12-31)
        r2022 = (1 + daily_rets.loc["2022-01-01":"2022-12-31"]).prod() - 1 if len(daily_rets.loc["2022-01-01":"2022-12-31"]) > 0 else 0
        # 2026년 연초이후 (2026-01-01 ~ 현재)
        r2026 = (1 + daily_rets.loc["2026-01-01":]).prod() - 1 if len(daily_rets.loc["2026-01-01":]) > 0 else 0

        stress_rows.append({
            "전략명": s_name,
            "2008 금융위기": f"{r2008*100:+.2f}%",
            "2020 코로나급락": f"{r2020_covid*100:+.2f}%",
            "2022 금리폭등기": f"{r2022*100:+.2f}%",
            "2026 최신연도": f"{r2026*100:+.2f}%"
        })

    df_stress = pd.DataFrame(stress_rows)
    print(df_stress.to_string(index=False))

    # 결과를 마크다운 파일로 저장
    output_path = BASE_DIR / "output" / "step1_verification_report.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# 🔬 [Step 1] 퀀트 자산배분 개별 전략 전수 백테스트 및 결함 개선(V1 vs V2) 검증 보고서\n\n")
        f.write(f"- **백테스트 구간:** {start_date} ~ {end_date}\n")
        f.write(f"- **거래 비용:** 편도 15bp / 왕복 30bp (0.0030) 차감\n")
        f.write(f"- **실행 지연:** 당일 신호 산출 후 익일 집행(1-Day Shift, 룩어헤드 방지)\n\n")
        f.write("## 1. 전체 핵심 지표 비교표\n\n")
        f.write(df_summary[cols_to_print].to_markdown(index=False))
        f.write("\n\n## 2. 주요 위기 국면 스트레스 테스트\n\n")
        f.write(df_stress.to_markdown(index=False))
        f.write("\n")

    print(f"\n[✓] 검증 리포트 저장 완료: {output_path}")


if __name__ == "__main__":
    main()
