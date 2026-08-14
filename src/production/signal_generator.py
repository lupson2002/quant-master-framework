"""실전 운영용 실시간 시그널 생성 엔진 (Production Signal Generator).

마스터 전략: Master Pure Monthly (IC 55% + Dual Momentum 30% + BAA-G4 15%)
오늘 날짜 기준 실제 미국 ETF 매수 주문 포트폴리오를 산출합니다.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series
from run_individual_deep_optimization import ic_v1_weights, baa_opt_weights, dm_v0_weights, zerolag_opt_weights


def get_latest_signals(capital_usd: float = 100000.0) -> dict:
    """오늘 날짜 기준 55/30/15 마스터 전략 최신 시그널 및 주문 내역 산출."""
    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    latest_date = prices.index[-1].strftime("%Y-%m-%d")
    latest_prices = prices.iloc[-1]

    # 개별 전략 가중치 시계열 생성
    w_ic = ic_v1_weights(prices, fred)
    w_dm = dm_v0_weights(prices, fred)
    w_baa = baa_opt_weights(prices, fred)
    w_zl = zerolag_opt_weights(prices, fred)

    # ─────────────────────────────────────────────────────────────────────────
    # 마스터 전략 (IC 55% + DM 30% + BAA 15% | 100% 완전 월간)
    # ─────────────────────────────────────────────────────────────────────────
    w_master_series = w_ic * 0.55 + w_dm * 0.30 + w_baa * 0.15
    w_master_latest = w_master_series.iloc[-1].dropna()
    w_master_active = w_master_latest[w_master_latest > 0.001].sort_values(ascending=False)

    df_master = pd.DataFrame({
        "Ticker": w_master_active.index,
        "Target_Weight": w_master_active.values,
        "Weight_Pct": [f"{v*100:.2f}%" for v in w_master_active.values],
        "Current_Price": [latest_prices.get(t, np.nan) for t in w_master_active.index],
        "Target_Value_USD": [v * capital_usd for v in w_master_active.values],
    })
    df_master["Shares_to_Hold"] = (df_master["Target_Value_USD"] / df_master["Current_Price"]).apply(lambda x: int(np.floor(x)) if not np.isnan(x) else 0)

    # ─────────────────────────────────────────────────────────────────────────
    # 보조 옵션: Option B (IC 40% + DM 30% + ZeroLag 15% + BAA 15%)
    # ─────────────────────────────────────────────────────────────────────────
    w_optb_series = w_ic * 0.40 + w_dm * 0.30 + w_zl * 0.15 + w_baa * 0.15
    w_optb_latest = w_optb_series.iloc[-1].dropna()
    w_optb_active = w_optb_latest[w_optb_latest > 0.001].sort_values(ascending=False)

    df_optb = pd.DataFrame({
        "Ticker": w_optb_active.index,
        "Target_Weight": w_optb_active.values,
        "Weight_Pct": [f"{v*100:.2f}%" for v in w_optb_active.values],
        "Current_Price": [latest_prices.get(t, np.nan) for t in w_optb_active.index],
        "Target_Value_USD": [v * capital_usd for v in w_optb_active.values],
    })
    df_optb["Shares_to_Hold"] = (df_optb["Target_Value_USD"] / df_optb["Current_Price"]).apply(lambda x: int(np.floor(x)) if not np.isnan(x) else 0)

    # 개별 엔진별 최신 상태 브리핑
    ic_pos = {k: round(v, 2) for k, v in w_ic.iloc[-1][w_ic.iloc[-1] > 0].items()}
    dm_pos = {k: round(v, 2) for k, v in w_dm.iloc[-1][w_dm.iloc[-1] > 0].items()}
    baa_pos = {k: round(v, 2) for k, v in w_baa.iloc[-1][w_baa.iloc[-1] > 0].items()}
    zl_pos = {k: round(v, 2) for k, v in w_zl.iloc[-1][w_zl.iloc[-1] > 0].items()}

    return {
        "latest_date": latest_date,
        "capital_usd": capital_usd,
        "master_table": df_master,
        "optb_table": df_optb,
        "type1_table": df_master,
        "type2_table": df_optb,
        "component_status": {
            "Inflation_Compass": ic_pos,
            "Dual_Momentum": dm_pos,
            "BAA_G4": baa_pos,
            "ZeroLag_Trend": zl_pos,
        }
    }


if __name__ == "__main__":
    sig = get_latest_signals(capital_usd=100000.0)
    print("=" * 80)
    print(f"📡 [마스터 실전 매매 시그널] 기준일자: {sig['latest_date']} (운용자산: ${sig['capital_usd']:,.0f})")
    print("=" * 80)
    print("\n👑 [Master Pure Monthly (IC 55% + DM 30% + BAA 15%)]")
    print(sig["master_table"][["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].to_string(index=False))
