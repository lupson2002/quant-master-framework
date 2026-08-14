"""ZeroLag Trend Signal — V1 원형 vs V2 변동성 레짐 다운시프트 개선판.

V1: QQQ >= ZLEMA(105) -> QLD 100% (2배), 미달 시 4대 대안자산(TLT, BIL, USO, GLD) 55일 모멘텀 + 샹들리에 손절
V2: 박스권 횡보장 2배 ETF 변동성 잠식(Decay)을 막기 위한 변동성 레짐 다운시프트 + 방어 분산
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy
from ..indicators.trend import compute_zlema, compute_chandelier_exit


class ZeroLagTrendV1(BaseStrategy):
    """V1 원형: 일간 ZLEMA(105) + QLD 100% 2배 운용."""
    def __init__(self, name: str = "ZeroLag_Trend_V1_QLD"):
        super().__init__(name)
        self.def_assets = ["TLT", "BIL", "USO", "GLD"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        qqq = prices_daily["QQQ"]
        zlema_105 = compute_zlema(qqq, period=105)
        regime_bull = qqq >= zlema_105

        # 4대 방어자산 55일 모멘텀
        mom55 = prices_daily[[c for c in self.def_assets if c in prices_daily.columns]].pct_change(55)

        weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)

        for i in range(105, len(prices_daily)):
            d = prices_daily.index[i]
            if regime_bull.iloc[i]:
                # 공격: QLD(2x)
                if "QLD" in weights.columns:
                    weights.loc[d, "QLD"] = 1.0  # QLD 자체가 2x ETF
                else:
                    weights.loc[d, "QQQ"] = 2.0
            else:
                # 방어: 55일 모멘텀 1위 자산
                scores = mom55.loc[d].dropna()
                if len(scores) > 0 and scores.max() > 0:
                    top1 = scores.idxmax()
                    weights.loc[d, top1] = 1.0
                else:
                    weights.loc[d, "BIL" if "BIL" in weights.columns else "SHY"] = 1.0

        return weights


class ZeroLagTrendV2(BaseStrategy):
    """V2 개선판: 변동성 레짐 기반 QLD/QQQ 동적 스케일링 + 방어 상위 2개 분산."""
    def __init__(self, name: str = "ZeroLag_Trend_V2_VolRegime"):
        super().__init__(name)
        self.def_assets = ["TLT", "BIL", "USO", "GLD"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        qqq = prices_daily["QQQ"]
        zlema_105 = compute_zlema(qqq, period=105)
        regime_bull = qqq >= zlema_105

        # QQQ 20일 실현 변동성 (연율화)
        vol20 = qqq.pct_change().rolling(20).std() * np.sqrt(252)

        mom55 = prices_daily[[c for c in self.def_assets if c in prices_daily.columns]].pct_change(55)

        weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)

        for i in range(105, len(prices_daily)):
            d = prices_daily.index[i]
            if regime_bull.iloc[i]:
                # 변동성이 높으면(25% 이상) QLD(2x) 대신 QQQ(1x)로 다운시프트하여 계좌 보존
                current_vol = vol20.iloc[i]
                if not np.isnan(current_vol) and current_vol > 0.25:
                    weights.loc[d, "QQQ"] = 1.0
                else:
                    if "QLD" in weights.columns:
                        weights.loc[d, "QLD"] = 1.0
                    else:
                        weights.loc[d, "QQQ"] = 2.0
            else:
                # 방어 시 상위 2개 자산에 50:50 분산
                scores = mom55.loc[d].dropna().sort_values(ascending=False)
                valid = scores[scores > 0]
                if len(valid) >= 2:
                    weights.loc[d, valid.index[0]] = 0.5
                    weights.loc[d, valid.index[1]] = 0.5
                elif len(valid) == 1:
                    weights.loc[d, valid.index[0]] = 0.5
                    weights.loc[d, "BIL" if "BIL" in weights.columns else "SHY"] = 0.5
                else:
                    weights.loc[d, "BIL" if "BIL" in weights.columns else "SHY"] = 1.0

        return weights
