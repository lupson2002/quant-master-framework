"""BAA (Bold Asset Allocation) — V1 Tuned 2x vs V2 Soft-Canary & BAA-G4.

V1: SPY, EFA, EEM 3개 모두 > 0 시 2배 공격 (QLD 등 1개 2x), 1개라도 <= 0 시 7대 방어자산 상위 3개 균등
V2: 3개 카나리아 양수 비율에 따른 비례 배분 + 2022 채권 약세장 방어 강화 (BAA-G4 3중 쿠션 방어)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy
from ..indicators.momentum import momentum_13612w_baa, relative_ema_momentum


class BaaTunedV1(BaseStrategy):
    """V1 원형: 3카나리아 All-Positive -> Top 1 공격 (2배 운용)."""
    def __init__(self, name: str = "BAA_Tuned_2x_V1", use_leverage: bool = True):
        super().__init__(name)
        self.use_leverage = use_leverage
        self.canary = ["SPY", "EFA", "EEM"]
        self.offense = ["QQQ", "EFA", "EEM"]
        self.defense = ["TIP", "PDBC", "BIL", "IEF", "TLT", "LQD", "AGG"]
        self.exec_2x = {"QQQ": "QLD"}

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        score_canary = momentum_13612w_baa(monthly_px[self.canary])
        rel_mom = relative_ema_momentum(monthly_px)

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            is_risk_on = (score_canary.loc[d] > 0).all()

            if is_risk_on:
                top1_off = rel_mom.loc[d, self.offense].idxmax()
                chosen = self.exec_2x.get(top1_off, top1_off) if self.use_leverage and top1_off in self.exec_2x else top1_off
                lev = 2.0 if self.use_leverage and chosen in self.exec_2x.values() else 1.0
                weights_m.loc[d, chosen] = lev
            else:
                def_scores = rel_mom.loc[d, [c for c in self.defense if c in rel_mom.columns]]
                top3_def = def_scores.nlargest(3).index.tolist()
                bil_score = rel_mom.loc[d, "BIL"] if "BIL" in rel_mom.columns else 1.0

                for asset in top3_def:
                    if def_scores[asset] < bil_score or def_scores[asset] < 1.0:
                        weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] += 1.0 / 3.0
                    else:
                        weights_m.loc[d, asset] += 1.0 / 3.0

        return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


class BaaG4V2(BaseStrategy):
    """V2 BAA-G4: 35년 최저 MDD(-21.5%)를 달성한 GSPC/DM/EM 카나리아 + CASH/LTB/GOLD 3대 방어."""
    def __init__(self, name: str = "BAA_G4_V2_Balanced"):
        super().__init__(name)
        self.canary = ["SPY", "EFA", "EEM"]
        self.offense = ["QQQ", "EFA", "EEM"]
        self.defense = ["BIL", "TLT", "GLD"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        score_canary = momentum_13612w_baa(monthly_px[self.canary])
        rel_mom = relative_ema_momentum(monthly_px)

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            # 카나리아 양수 개수 (0 ~ 3)
            pos_cnt = (score_canary.loc[d] > 0).sum()

            if pos_cnt >= 2:
                # 공격 비중: 3개 양수면 100%, 2개 양수면 66%
                off_weight = 1.0 if pos_cnt == 3 else 0.66
                def_weight = 1.0 - off_weight

                top1_off = rel_mom.loc[d, self.offense].idxmax()
                weights_m.loc[d, top1_off] = off_weight

                if def_weight > 0:
                    for def_a in self.defense:
                        if def_a in weights_m.columns:
                            weights_m.loc[d, def_a] += def_weight / 3.0
            else:
                # 100% 방어 (BIL, TLT, GLD 3대 자산 균등 배분)
                for def_a in self.defense:
                    if def_a in weights_m.columns:
                        weights_m.loc[d, def_a] = 1.0 / 3.0

        return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
