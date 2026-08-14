"""Percentile Channels TAA (David Varadi, CSSA).

유니버스: VTI(주식), IYR(부동산), LQD(회사채), DBC(원자재), SHY(현금)
4개 채널(60, 120, 180, 252일)의 75% 백분위수 상향돌파(+1) 및 25% 하향돌파(-1) 복합신호.
신호 양수 자산에 대해 20일 역변동성(1/vol20)으로 비중 배분, 잔여는 SHY 채움.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy
from ..indicators.trend import compute_percentile_channel


class PercentileChannelsStrategy(BaseStrategy):
    def __init__(self, name: str = "Percentile_Channels_TAA"):
        super().__init__(name)
        self.assets = ["VTI", "IYR", "LQD", "DBC"]
        self.cash = "SHY"
        self.channels = [60, 120, 180, 252]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        available_assets = [a for a in self.assets if a in prices_daily.columns]
        if not available_assets:
            return pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)

        # 4개 채널별 일별 신호 산출
        channel_signals = {}
        for a in available_assets:
            sig_sum = pd.Series(0.0, index=prices_daily.index)
            for ch in self.channels:
                sig_sum += compute_percentile_channel(prices_daily[a], window=ch, buy_th=0.75, exit_th=0.25)
            channel_signals[a] = sig_sum / len(self.channels)

        df_composite = pd.DataFrame(channel_signals, index=prices_daily.index)

        # 20일 변동성 역수 (1 / vol20)
        vol20 = prices_daily[available_assets].pct_change().rolling(20).std()
        inv_vol = 1.0 / vol20.replace(0, np.nan)

        monthly_dates = prices_daily.resample("ME").last().index
        weights_m = pd.DataFrame(0.0, index=monthly_dates, columns=prices_daily.columns)

        for d in monthly_dates:
            valid_idx = df_composite.index[df_composite.index <= d]
            if len(valid_idx) == 0:
                continue
            d_calc = valid_idx[-1]

            scores = df_composite.loc[d_calc]
            ivs = inv_vol.loc[d_calc]

            # 양수 신호 자산만 선정
            pos_assets = scores[scores > 0].index.tolist()
            if not pos_assets:
                weights_m.loc[d, self.cash if self.cash in weights_m.columns else "BIL"] = 1.0
            else:
                raw_w = {a: scores[a] * ivs[a] for a in pos_assets if not np.isnan(ivs[a])}
                total_w = sum(raw_w.values())
                if total_w > 0:
                    allocated_sum = 0.0
                    for a, w in raw_w.items():
                        norm_w = w / total_w
                        weights_m.loc[d, a] = norm_w
                        allocated_sum += norm_w
                    residual = max(1.0 - allocated_sum, 0.0)
                    if residual > 0:
                        weights_m.loc[d, self.cash if self.cash in weights_m.columns else "BIL"] += residual
                else:
                    weights_m.loc[d, self.cash if self.cash in weights_m.columns else "BIL"] = 1.0

        return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
