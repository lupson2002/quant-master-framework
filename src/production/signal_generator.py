"""실전 운영용 실시간 시그널 생성 엔진 (Production Signal Generator).

타입 1 (Dynamic Alpha: 월간 85% + 일간 15%) 및
타입 2 (Pure Monthly: 100% 완전 월간 전용)의
오늘 날짜 기준 실제 ETF 매수/매도 주문 포트폴리오를 산출합니다.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series
from run_individual_deep_optimization import ic_v1_weights, baa_opt_weights, zerolag_opt_weights, dm_v0_weights, gb_v1_weights


def get_latest_signals(capital_usd: float = 100000.0) -> dict:
    """오늘 날짜 기준 타입 1 및 타입 2 최신 시그널 및 주문 내역 산출."""
    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    latest_date = prices.index[-1].strftime("%Y-%m-%d")
    latest_prices = prices.iloc[-1]

    # 개별 전략 가중치 시계열 생성
    w_ic = ic_v1_weights(prices, fred)
    w_dm = dm_v0_weights(prices, fred)
    w_zl = zerolag_opt_weights(prices, fred)
    w_baa = baa_opt_weights(prices, fred)
    w_gb = gb_v1_weights(prices, fred)

    # ─────────────────────────────────────────────────────────────────────────
    # 타입 1: Dynamic Alpha (Option B: 40% IC + 30% DM + 15% ZL + 15% BAA)
    # ─────────────────────────────────────────────────────────────────────────
    w_t1_series = w_ic * 0.40 + w_dm * 0.30 + w_zl * 0.15 + w_baa * 0.15
    w_t1_latest = w_t1_series.iloc[-1].dropna()
    w_t1_active = w_t1_latest[w_t1_latest > 0.001].sort_values(ascending=False)

    df_t1 = pd.DataFrame({
        "Ticker": w_t1_active.index,
        "Target_Weight": w_t1_active.values,
        "Weight_Pct": [f"{v*100:.2f}%" for v in w_t1_active.values],
        "Current_Price": [latest_prices.get(t, np.nan) for t in w_t1_active.index],
        "Target_Value_USD": [v * capital_usd for v in w_t1_active.values],
    })
    df_t1["Shares_to_Hold"] = (df_t1["Target_Value_USD"] / df_t1["Current_Price"]).apply(lambda x: int(np.floor(x)) if not np.isnan(x) else 0)

    # ─────────────────────────────────────────────────────────────────────────
    # 타입 2: Pure Monthly (35% IC + 30% BAA + 20% DM + 15% GB)
    # ─────────────────────────────────────────────────────────────────────────
    w_t2_series = w_ic * 0.35 + w_baa * 0.30 + w_dm * 0.20 + w_gb * 0.15
    w_t2_latest = w_t2_series.iloc[-1].dropna()
    w_t2_active = w_t2_latest[w_t2_latest > 0.001].sort_values(ascending=False)

    df_t2 = pd.DataFrame({
        "Ticker": w_t2_active.index,
        "Target_Weight": w_t2_active.values,
        "Weight_Pct": [f"{v*100:.2f}%" for v in w_t2_active.values],
        "Current_Price": [latest_prices.get(t, np.nan) for t in w_t2_active.index],
        "Target_Value_USD": [v * capital_usd for v in w_t2_active.values],
    })
    df_t2["Shares_to_Hold"] = (df_t2["Target_Value_USD"] / df_t2["Current_Price"]).apply(lambda x: int(np.floor(x)) if not np.isnan(x) else 0)

    # 개별 엔진별 최신 상태 브리핑
    ic_pos = w_ic.iloc[-1][w_ic.iloc[-1] > 0].to_dict()
    dm_pos = w_dm.iloc[-1][w_dm.iloc[-1] > 0].to_dict()
    zl_pos = w_zl.iloc[-1][w_zl.iloc[-1] > 0].to_dict()
    baa_pos = w_baa.iloc[-1][w_baa.iloc[-1] > 0].to_dict()

    return {
        "latest_date": latest_date,
        "capital_usd": capital_usd,
        "type1_table": df_t1,
        "type2_table": df_t2,
        "component_status": {
            "Inflation_Compass": ic_pos,
            "Dual_Momentum": dm_pos,
            "ZeroLag_Trend": zl_pos,
            "BAA_G4": baa_pos,
        }
    }


if __name__ == "__main__":
    sig = get_latest_signals(capital_usd=100000.0)
    print("=" * 80)
    print(f"📡 [실전 매매 시그널] 기준일자: {sig['latest_date']} (운용자산: ${sig['capital_usd']:,.0f})")
    print("=" * 80)

    print("\n🚀 [타입 1: Dynamic Alpha (Option B: 월간 85% + 일간 15%)]")
    print(sig["type1_table"][["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].to_string(index=False))

    print("\n☕ [타입 2: Pure Monthly (100% 완전 월간 전용)]")
    print(sig["type2_table"][["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].to_string(index=False))
