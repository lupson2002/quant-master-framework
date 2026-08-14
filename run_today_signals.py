"""원클릭 오늘 매매 신호 생성기 (Run Today Signals).

터미널에서 실행하여 Master Pure Monthly (55/30/15) ETF 주문표를 즉시 확인합니다.
사용법: python3 run_today_signals.py [--capital 100000]
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

    # 1. 마스터 전략 출력
    print("\n" + "─" * 90)
    print("👑 [마스터 전략] Master Pure Monthly (55/30/15)")
    print("   • 연복리수익률: 18.13%  |  MDD: -21.83%  |  Sharpe: 1.063  |  2022년: +15.66%")
    print("   • 운용: 100% 매월 마지막 거래일 1회 확인 (월 1회 10분 컷, 완전 무레버리지)")
    print("─" * 90)
    df_m = signals["master_table"]
    print(df_m[["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].to_string(index=False))

    # 2. 보조 옵션 출력
    print("\n" + "─" * 90)
    print("🚀 [보조 옵션] Option B: Dynamic Alpha (40/30/15/15)")
    print("   • 연복리수익률: 16.97%  |  MDD: -19.72%  |  Sharpe: 1.095  |  2022년: +3.94%")
    print("   • 운용: 월 85% + 15%(ZeroLag) 일간 나스닥 추세 모니터링")
    print("─" * 90)
    df_b = signals["optb_table"]
    print(df_b[["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].to_string(index=False))

    # 3. 세부 엔진 상태
    print("\n" + "─" * 90)
    print("🔍 [3대 핵심 단품 엔진 현재 포지션]")
    print("─" * 90)
    cs = signals["component_status"]
    print(f"  • Inflation Compass (55%): {cs['Inflation_Compass']}")
    print(f"  • Dual Momentum    (30%): {cs['Dual_Momentum']}")
    print(f"  • BAA-G4           (15%): {cs['BAA_G4']}")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
