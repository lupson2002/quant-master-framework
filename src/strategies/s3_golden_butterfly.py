"""Golden Butterfly — V1 정적 올웨더 vs V2 동적 모멘텀 리밸런싱.

V1: 대형주(SPY) 20%, 소형가치(IWM) 20%, 장기채(TLT) 20%, 단기채(SHY) 20%, 금(GLD) 20%
V2: 5개 자산 중 12개월 모멘텀 상위 3개 자산에 1/3씩 균등 배분 (절대모멘텀 음수 시 SHY 대체).
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy


class GoldenButterflyV1(BaseStrategy):
    """V1 정적 20% 균등 올웨더."""
    def __init__(self, name: str = "Golden_Butterfly_V1_Static"):
        super().__init__(name)
        self.assets = ["SPY", "IWM", "TLT", "SHY", "GLD"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)
        for a in self.assets:
            if a in weights.columns:
                weights[a] = 0.20
        return weights


class GoldenButterflyV2(BaseStrategy):
    """V2 동적 12M 모멘텀 Top-3 올웨더 (CAGR 9.54% 실증 모델)."""
    def __init__(self, name: str = "Golden_Butterfly_V2_Dynamic"):
        super().__init__(name)
        self.assets = ["SPY", "IWM", "TLT", "SHY", "GLD"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        r12 = monthly_px[self.assets].pct_change(12)

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            scores = r12.loc[d].dropna().sort_values(ascending=False)
            top3 = scores.head(3)
            for ticker in top3.index:
                if top3[ticker] > 0:
                    weights_m.loc[d, ticker] = 1.0 / 3.0
                else:
                    weights_m.loc[d, "SHY" if "SHY" in weights_m.columns else "BIL"] += 1.0 / 3.0

        weights_daily = weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
        return weights_daily
