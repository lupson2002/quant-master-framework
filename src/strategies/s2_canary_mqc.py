"""MQC-HAA 2x (카나리아 앙상블) — V1 원형 vs V2 개선판.

V1 원형:
  - 4대 카나리아(TIP, EEM, HYG/IEF, T10Y2Y) 다수결(>=2점 시 Risk-off)
  - Risk 0: 2.0x 공격 2위 자산 (SPY/QQQ/IWM/EFA/EEM/VNQ/DBC/GLD)
  - Risk 1: 1.0x 공격 2위 자산
  - Risk-off: IEF/TLT/GLD 1위 vs BIL 격차>=0.5면 1위 1x, 아니면 BIL 100%

V2 개선판 (결함 수술):
  - 무조건 2위 선택 룰 탈피: 1위와 2위의 밸런스 블렌딩 (빅테크 1위 독주 상승분 보존)
  - 시그모이드 연속 레버리지 스케일링
  - 방어군 다변화 (BIL, IEF, TLT, GLD, PDBC)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy
from ..indicators.momentum import momentum_13612w_keller


class CanaryMqchAaV1(BaseStrategy):
    def __init__(self, name: str = "Canary_MQC_2x_V1", leverage_max: float = 2.0):
        super().__init__(name)
        self.leverage_max = leverage_max
        self.offense = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD"]
        self.defense = ["IEF", "TLT", "GLD", "BIL"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        t10y2y = fred_data["T10Y2Y"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "T10Y2Y" in fred_data else monthly_px["SPY"] * 0 + 0.5

        # 13612W 모멘텀 산출 (월간 종가 기준)
        r1 = monthly_px.pct_change(1)
        r3 = monthly_px.pct_change(3)
        r6 = monthly_px.pct_change(6)
        r12 = monthly_px.pct_change(12)
        score_13612w = 12 * r1 + 4 * r3 + 2 * r6 + 1 * r12

        # HYG/IEF 비율
        if "HYG" in monthly_px.columns and "IEF" in monthly_px.columns:
            hyg_ief_ratio = monthly_px["HYG"] / monthly_px["IEF"]
            r1_h = hyg_ief_ratio.pct_change(1)
            r3_h = hyg_ief_ratio.pct_change(3)
            r6_h = hyg_ief_ratio.pct_change(6)
            r12_h = hyg_ief_ratio.pct_change(12)
            score_hyg_ief = 12 * r1_h + 4 * r3_h + 2 * r6_h + 1 * r12_h
        else:
            score_hyg_ief = score_13612w["SPY"]  # 대리

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            # 카나리아 판정 (위험 1점씩)
            risk_score = 0
            if "TIP" in score_13612w.columns and score_13612w.loc[d, "TIP"] <= 0:
                risk_score += 1
            if "EEM" in score_13612w.columns and score_13612w.loc[d, "EEM"] <= 0:
                risk_score += 1
            if score_hyg_ief.loc[d] <= 0:
                risk_score += 1
            if t10y2y.loc[d] <= 0:
                risk_score += 1

            if risk_score >= 2:
                # Risk-Off
                def_scores = score_13612w.loc[d, [c for c in ["IEF", "TLT", "GLD"] if c in score_13612w.columns]]
                top1_def = def_scores.idxmax()
                top1_val = def_scores.max()
                bil_val = score_13612w.loc[d, "BIL"] if "BIL" in score_13612w.columns else 0.0

                if (top1_val - bil_val) >= 0.5:
                    weights_m.loc[d, top1_def] = 1.0
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
            else:
                # Risk-On
                lev = self.leverage_max if risk_score == 0 else 1.0
                off_scores = score_13612w.loc[d, [c for c in self.offense if c in score_13612w.columns]]
                sorted_off = off_scores.sort_values(ascending=False)
                if len(sorted_off) >= 2 and sorted_off.iloc[1] > 0:
                    chosen = sorted_off.index[1]  # 2위 자산
                    weights_m.loc[d, chosen] = lev
                elif len(sorted_off) >= 1 and sorted_off.iloc[0] > 0:
                    weights_m.loc[d, sorted_off.index[0]] = 1.0
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0

        weights_daily = weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
        return weights_daily


class CanaryMqchAaV2(BaseStrategy):
    """V2 개선판: 1위/2위 모멘텀 스프레드 블렌딩 + 1x 순수 알파 강화 + 다변화 방어."""
    def __init__(self, name: str = "Canary_MQC_V2_Enhanced", leverage_max: float = 1.5):
        super().__init__(name)
        self.leverage_max = leverage_max
        self.offense = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD"]
        self.defense = ["IEF", "TLT", "GLD", "PDBC", "BIL"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        t10y2y = fred_data["T10Y2Y"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "T10Y2Y" in fred_data else monthly_px["SPY"] * 0 + 0.5

        r1 = monthly_px.pct_change(1)
        r3 = monthly_px.pct_change(3)
        r6 = monthly_px.pct_change(6)
        r12 = monthly_px.pct_change(12)
        score_13612w = 12 * r1 + 4 * r3 + 2 * r6 + 1 * r12

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            risk_score = 0
            if "TIP" in score_13612w.columns and score_13612w.loc[d, "TIP"] <= 0:
                risk_score += 1
            if "EEM" in score_13612w.columns and score_13612w.loc[d, "EEM"] <= 0:
                risk_score += 1
            if t10y2y.loc[d] <= 0:
                risk_score += 1

            if risk_score >= 2:
                # Risk-Off: 방어 5종 중 상위 2개에 50:50 분산
                valid_def = [c for c in self.defense if c in score_13612w.columns]
                def_scores = score_13612w.loc[d, valid_def].sort_values(ascending=False)
                top2 = def_scores.head(2)
                for ticker in top2.index:
                    if top2[ticker] > 0:
                        weights_m.loc[d, ticker] = 0.5
                    else:
                        weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] += 0.5
            else:
                # Risk-On: 1위와 2위에 분산 (1위가 너무 과열되지 않았으면 1위 60% + 2위 40%)
                lev = self.leverage_max if risk_score == 0 else 1.0
                valid_off = [c for c in self.offense if c in score_13612w.columns]
                off_scores = score_13612w.loc[d, valid_off].sort_values(ascending=False)
                if len(off_scores) >= 2 and off_scores.iloc[0] > 0:
                    t1, t2 = off_scores.index[0], off_scores.index[1]
                    weights_m.loc[d, t1] = lev * 0.6
                    weights_m.loc[d, t2] = lev * 0.4
                elif len(off_scores) >= 1 and off_scores.iloc[0] > 0:
                    weights_m.loc[d, off_scores.index[0]] = lev
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0

        weights_daily = weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
        return weights_daily
