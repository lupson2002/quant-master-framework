"""하이브리드 전략 2: All-Weather Dynamic Alpha (현실적 최적 앙상블).

상관관계가 0.4 이하로 낮고 실전 검증된 4대 핵심 블록을 리스크 버짓팅 가중치로 융합:
  1. Inflation Compass V1 (35%) — 거시 레짐/인플레 방어 엔진
  2. BAA-G4 V2 (30%) — 블랙스완 적응형 모멘텀 및 3중 쿠션 방어
  3. Dual Momentum V0 (20%) — 글로벌 자산 모멘텀 회전 엔진
  4. Golden Butterfly V1 (15%) — 영구적 올웨더 밸런스 및 하방 바닥 쿠션
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from ..strategies.base import BaseStrategy
from ..strategies.s1_inflation_compass import InflationCompassV1
from ..strategies.s5_baa_tuned import BaaG4V2
from ..strategies.s4_dual_momentum import DualMomentumV0
from ..strategies.s3_golden_butterfly import GoldenButterflyV1


class AllWeatherDynamicAlpha(BaseStrategy):
    def __init__(self, name: str = "Hybrid_AllWeather_Dynamic_Alpha"):
        super().__init__(name)
        self.strat_ic = InflationCompassV1()
        self.strat_baa = BaaG4V2()
        self.strat_dm = DualMomentumV0()
        self.strat_gb = GoldenButterflyV1()

        # 최적 앙상블 비중
        self.weights_mix = {
            "IC": 0.35,
            "BAA": 0.30,
            "DM": 0.20,
            "GB": 0.15
        }

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        w_ic = self.strat_ic.generate_weights(prices_daily, fred_data)
        w_baa = self.strat_baa.generate_weights(prices_daily, fred_data)
        w_dm = self.strat_dm.generate_weights(prices_daily, fred_data)
        w_gb = self.strat_gb.generate_weights(prices_daily, fred_data)

        # 4개 전략 가중합
        blended_weights = (
            w_ic * self.weights_mix["IC"] +
            w_baa * self.weights_mix["BAA"] +
            w_dm * self.weights_mix["DM"] +
            w_gb * self.weights_mix["GB"]
        )

        return blended_weights.fillna(0.0)
