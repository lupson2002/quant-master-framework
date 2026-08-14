"""원클릭 오늘 매매 신호 생성기 (Run Today Signals).

터미널에서 실행하여 타입 1과 타입 2의 오늘 ETF 주문표를 즉시 확인합니다.
사용법: python3 run_today_signals.py [--capital 50000]
"""

from __future__ import annotations
import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.production.signal_generator import get_latest_signals


def main():
    parser = argparse.ArgumentParser(description="오늘의 퀀트 매매 시그널 생성기")
    parser.add_argument("--capital", type=float, default=100000.0, help="총 운용 자산 (USD, 기본: $100,000)")
    args = parser.parse_args()

    signals = get_latest_signals(capital_usd=args.capital)
    dt = signals["latest_date"]
    cap = signals["capital_usd"]

    print("\n" + "=" * 90)
    print(f"🏛️  [Unified Quant Master] 오늘의 실전 포트폴리오 매매 시그널")
    print(f"📅  기준 종가 일자: {dt}  |  💵  운용 자산: ${cap:,.0f} USD")
    print("=" * 90)

    # 1. 타입 1 출력
    print("\n" + "─" * 90)
    print("🚀 [타입 1] Dynamic Alpha (Option B: 월간 85% + 일간 15%)")
    print("   • 연복리수익률: 18.16%  |  MDD: -20.16%  |  Sharpe: 1.094  |  2022년: +0.70%")
    print("   • 운용: 평소 월 1회 리밸런싱 + 15%(ZeroLag)만 일간 나스닥 추세 모니터링")
    print("─" * 90)
    df_t1 = signals["type1_table"]
    print(df_t1[["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].to_string(index=False))

    # 2. 타입 2 출력
    print("\n" + "─" * 90)
    print("☕ [타입 2] Pure Monthly (100% 완전 월간 전용 포트폴리오)")
    print("   • 연복리수익률: 17.30%  |  MDD: -21.26%  |  Sharpe: 0.960  |  2022년: +2.10%")
    print("   • 운용: 100% 매월 마지막 날 1회만 확인 (월 1회 10분 컷, 매일 신경 끌 때 최적)")
    print("─" * 90)
    df_t2 = signals["type2_table"]
    print(df_t2[["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].to_string(index=False))

    # 3. 세부 엔진 상태
    print("\n" + "─" * 90)
    print("🔍 [4대 단품 엔진별 현재 상태 브리핑]")
    print("─" * 90)
    cs = signals["component_status"]
    print(f"  • Inflation Compass (40%): {cs['Inflation_Compass']}")
    print(f"  • Dual Momentum    (30%): {cs['Dual_Momentum']}")
    print(f"  • ZeroLag Trend    (15%): {cs['ZeroLag_Trend']}")
    print(f"  • BAA-G4           (15%): {cs['BAA_G4']}")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
