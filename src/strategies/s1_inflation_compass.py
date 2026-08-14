"""Inflation Compass — V1 원형 vs V2 추세/손절 필터 개선판 (Conviction Trend-Filtered).

V1 원형:
  - 성장(SPY > 200SMA) x 인플레(T5YIE>2.0% & (60d mom>0 or Pos/Neg 기울기>0)) 4분면
  - Q1(성장↑/인플레↑): XLE 100%
  - Q2(성장↑/인플레↓): XLK 100%
  - Q3(성장↓/인플레↑): XLU 100%
  - Q4(성장↓/인플레↓): XLP 50% + IEF 50%

V2 개선판 (진정한 결함 수술):
  - 무리한 4분면 믹싱(희석) 대신, 선택된 섹터가 자체 200일 SMA(또는 60일 모멘텀) 하회 시 현금(BIL)으로 보호
  - Q4에서 IEF가 200일 SMA 하회 시(2022년 같은 금리인상기) 채권 대신 초단기채(BIL)로 대체
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy
from ..indicators.macro import compute_inflation_compass_signals


class InflationCompassV1(BaseStrategy):
    def __init__(self, name: str = "Inflation_Compass_V1"):
        super().__init__(name)

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        t5yie = fred_data["T5YIE"].reindex(prices_daily.index).ffill() if fred_data is not None and "T5YIE" in fred_data else prices_daily["SPY"] * 0 + 2.1
        signals = compute_inflation_compass_signals(prices_daily, t5yie)

        monthly_dates = prices_daily.resample("ME").last().index
        weights_m = pd.DataFrame(0.0, index=monthly_dates, columns=prices_daily.columns)

        for d in monthly_dates:
            valid_idx = signals.index[signals.index <= d]
            if len(valid_idx) == 0:
                continue
            d_calc = valid_idx[-1]

            row = signals.loc[d_calc]
            g_on = bool(row["growth_on"])
            inf_on = bool(row["inflation_on"])

            if g_on and inf_on:
                weights_m.loc[d, "XLE"] = 1.0
            elif g_on and not inf_on:
                weights_m.loc[d, "XLK"] = 1.0
            elif not g_on and inf_on:
                weights_m.loc[d, "XLU"] = 1.0
            else:
                weights_m.loc[d, "XLP"] = 0.5
                weights_m.loc[d, "IEF"] = 0.5

        weights_daily = weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
        return weights_daily


class InflationCompassV2(BaseStrategy):
    """V2 개선판: 섹터 자체 추세 필터 + 2022 채권 약세장 BIL 대체."""
    def __init__(self, name: str = "Inflation_Compass_V2_TrendFilter"):
        super().__init__(name)

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        t5yie = fred_data["T5YIE"].reindex(prices_daily.index).ffill() if fred_data is not None and "T5YIE" in fred_data else prices_daily["SPY"] * 0 + 2.1
        signals = compute_inflation_compass_signals(prices_daily, t5yie)

        # 각 자산별 200일 SMA 및 60일 모멘텀
        sma200 = prices_daily.rolling(200).mean()
        mom60 = prices_daily.pct_change(60)

        monthly_dates = prices_daily.resample("ME").last().index
        weights_m = pd.DataFrame(0.0, index=monthly_dates, columns=prices_daily.columns)

        cash_ticker = "BIL" if "BIL" in prices_daily.columns else "SHY"

        for d in monthly_dates:
            valid_idx = signals.index[signals.index <= d]
            if len(valid_idx) == 0:
                continue
            d_calc = valid_idx[-1]

            row = signals.loc[d_calc]
            g_on = bool(row["growth_on"])
            inf_on = bool(row["inflation_on"])

            if g_on and inf_on:
                # XLE 선정: XLE가 60일 모멘텀 양수이면 100%, 아니면 현금
                if mom60.loc[d_calc, "XLE"] > 0:
                    weights_m.loc[d, "XLE"] = 1.0
                else:
                    weights_m.loc[d, cash_ticker] = 1.0
            elif g_on and not inf_on:
                # XLK 선정: XLK가 200일 SMA 위이거나 60일 모멘텀 양수이면 100%
                if prices_daily.loc[d_calc, "XLK"] > sma200.loc[d_calc, "XLK"]:
                    weights_m.loc[d, "XLK"] = 1.0
                else:
                    weights_m.loc[d, cash_ticker] = 1.0
            elif not g_on and inf_on:
                # XLU 선정: XLU가 60일 모멘텀 양수이면 XLU, 음수이면 현금/금(GLD)
                if mom60.loc[d_calc, "XLU"] > 0:
                    weights_m.loc[d, "XLU"] = 1.0
                elif "GLD" in prices_daily.columns and mom60.loc[d_calc, "GLD"] > 0:
                    weights_m.loc[d, "GLD"] = 1.0
                else:
                    weights_m.loc[d, cash_ticker] = 1.0
            else:
                # Q4: XLP 50% + IEF 50% (단, IEF가 200SMA 아래면 BIL로 대체)
                if prices_daily.loc[d_calc, "XLP"] > sma200.loc[d_calc, "XLP"]:
                    weights_m.loc[d, "XLP"] = 0.5
                else:
                    weights_m.loc[d, cash_ticker] += 0.5

                if prices_daily.loc[d_calc, "IEF"] > sma200.loc[d_calc, "IEF"]:
                    weights_m.loc[d, "IEF"] = 0.5
                else:
                    weights_m.loc[d, cash_ticker] += 0.5

        weights_daily = weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
        return weights_daily
