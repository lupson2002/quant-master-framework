"""VAA-G1 (Vigilant Asset Allocation — Wouter Keller).

공격: QQQ, SPY, EEM, EFA (4자산)
방어: TLT, BIL (2자산)
규칙: 4개 공격 자산 중 최소 2개가 13612W 양수일 때 12-1M 1위에 100% 투자.
     미달 시 13612W가 더 높은 방어자산(TLT vs BIL) 선택.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy
from ..indicators.momentum import momentum_13612w_keller, momentum_121


class VaaG1Strategy(BaseStrategy):
    def __init__(self, name: str = "VAA_G1_Vigilant"):
        super().__init__(name)
        self.offense = ["QQQ", "SPY", "EEM", "EFA"]
        self.defense = ["TLT", "BIL"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        score_13612w = momentum_13612w_keller(monthly_px)
        score_121 = momentum_121(monthly_px)

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            valid_off = [c for c in self.offense if c in score_13612w.columns and not np.isnan(score_13612w.loc[d, c])]
            if not valid_off:
                weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
                continue

            off_scores = score_13612w.loc[d, valid_off]
            pos_count = (off_scores > 0).sum()

            if pos_count >= 2:
                # 12-1 모멘텀 1위에 100%
                valid_121 = [c for c in valid_off if not np.isnan(score_121.loc[d, c])]
                if valid_121:
                    top1_off = score_121.loc[d, valid_121].idxmax()
                    weights_m.loc[d, top1_off] = 1.0
                else:
                    weights_m.loc[d, off_scores.idxmax()] = 1.0
            else:
                # 방어 자산 중 13612W 1위
                valid_def = [c for c in self.defense if c in score_13612w.columns and not np.isnan(score_13612w.loc[d, c])]
                if valid_def:
                    top1_def = score_13612w.loc[d, valid_def].idxmax()
                    weights_m.loc[d, top1_def] = 1.0
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0

        return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
