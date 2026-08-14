"""Dual Momentum Rotation — V0/V8 vs V12(Top-2) vs V13(Gold방어) vs V2_Enhanced.

V0: QQQ, EFA, GLD, EEM 중 1위 100% (주식 전부<0 시 금리방어)
V8: QQQ, EFA, EEM 중 1위 + 12M 절대모멘텀
V12: QQQ, EFA, EEM 중 Top-2에 50:50 분산 + 12M 절대모멘텀 (샤프 1.0, 변동성 14%)
V13: 금(GLD)을 방어군(CASH, LTB, GLD)으로 이동
V2_Enhanced: Top-2 분산 + 일간 ZLEMA(105) 이탈 시 조기 방어 전환 (Lag 극복)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseStrategy
from ..indicators.momentum import dual_momentum_score
from ..indicators.trend import compute_zlema


class DualMomentumV0(BaseStrategy):
    def __init__(self, name: str = "Dual_Momentum_V0"):
        super().__init__(name)
        self.assets = ["QQQ", "EFA", "GLD", "EEM"]
        self.stock_assets = ["QQQ", "EFA", "EEM"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        scores = dual_momentum_score(monthly_px[self.assets])
        dgs3mo = fred_data["DGS3MO"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DGS3MO" in fred_data else monthly_px["SPY"] * 0 + 3.0
        dff = fred_data["DFF"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DFF" in fred_data else monthly_px["SPY"] * 0 + 2.8

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            stock_scores = scores.loc[d, self.stock_assets]
            if (stock_scores < 0).all():
                # 방어
                if dgs3mo.loc[d] < dff.loc[d]:
                    weights_m.loc[d, "TLT"] = 1.0
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
            else:
                top1 = scores.loc[d].idxmax()
                weights_m.loc[d, top1] = 1.0

        return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


class DualMomentumV12(BaseStrategy):
    """V12: Top-2 분산(50:50) + 12M 절대모멘텀 (변동성 14% 극저변동성 모델)."""
    def __init__(self, name: str = "Dual_Momentum_V12_Top2"):
        super().__init__(name)
        self.stock_assets = ["QQQ", "EFA", "EEM"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        scores = dual_momentum_score(monthly_px[self.stock_assets])
        r12 = monthly_px[self.stock_assets].pct_change(12)
        dgs3mo = fred_data["DGS3MO"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DGS3MO" in fred_data else monthly_px["SPY"] * 0 + 3.0
        dff = fred_data["DFF"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DFF" in fred_data else monthly_px["SPY"] * 0 + 2.8

        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            sorted_stocks = scores.loc[d].sort_values(ascending=False)
            top2 = sorted_stocks.head(2)

            for ticker in top2.index:
                if r12.loc[d, ticker] > 0:
                    weights_m.loc[d, ticker] = 0.5
                else:
                    if dgs3mo.loc[d] < dff.loc[d]:
                        weights_m.loc[d, "TLT"] += 0.5
                    else:
                        weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] += 0.5

        return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


class DualMomentumV2Enhanced(BaseStrategy):
    """V2_Enhanced: Top-2 분산 + 일간 QQQ ZLEMA(105) 이탈 시 조기 방어 전환 (후행성 제거)."""
    def __init__(self, name: str = "Dual_Momentum_V2_Enhanced"):
        super().__init__(name)
        self.stock_assets = ["QQQ", "EFA", "EEM"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        monthly_px = prices_daily.resample("ME").last()
        scores = dual_momentum_score(monthly_px[self.stock_assets])
        r12 = monthly_px[self.stock_assets].pct_change(12)

        # 일간 QQQ ZLEMA 산출
        qqq_zlema = compute_zlema(prices_daily["QQQ"], period=105)
        qqq_bull = prices_daily["QQQ"] >= qqq_zlema

        weights_daily = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)

        # 기본 월간 비중 생성
        weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
        for i in range(12, len(monthly_px)):
            d = monthly_px.index[i]
            sorted_stocks = scores.loc[d].sort_values(ascending=False)
            top2 = sorted_stocks.head(2)
            for ticker in top2.index:
                if r12.loc[d, ticker] > 0:
                    weights_m.loc[d, ticker] = 0.5
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] += 0.5

        base_weights = weights_m.reindex(prices_daily.index).ffill().fillna(0.0)

        # 일간 ZLEMA 필터 적용: QQQ가 ZLEMA 아래로 추락하면 주식 비중을 50% 현금화(De-risking)
        for d in prices_daily.index:
            w_row = base_weights.loc[d].copy()
            if not qqq_bull.loc[d]:
                # 주식 비중 절반 축소 후 현금 전환
                for t in self.stock_assets:
                    if t in w_row and w_row[t] > 0:
                        reduced = w_row[t] * 0.5
                        w_row[t] -= reduced
                        w_row["BIL" if "BIL" in w_row else "SHY"] += reduced
            weights_daily.loc[d] = w_row

        return weights_daily
