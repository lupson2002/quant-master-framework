"""통합 퀀트 백테스팅 엔진 (Vectorized Portfolio Simulation).

자산 비중 시계열(Weights DataFrame)과 자산별 가격(Prices DataFrame)을 결합하여
룩어헤드 방지(1-day shift), 정확한 턴오버 계산, 거래비용(수수료/슬리피지) 차감,
일별 Net Equity 및 성과 지표를 산출합니다.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from .metrics import compute_metrics, compute_yearly_returns


class BacktestEngine:
    def __init__(self, transaction_cost_bp: float = 15.0):
        """
        transaction_cost_bp: 편도 거래비용 (기본 15bp = 왕복 30bp = 0.0030)
        """
        self.cost_rate = transaction_cost_bp / 10000.0

    def run(self, prices: pd.DataFrame, target_weights: pd.DataFrame,
            start_date: str | None = None, end_date: str | None = None) -> dict:
        """
        prices: 일별 종가 DataFrame (컬럼=티커)
        target_weights: 일별/월별 목표 비중 DataFrame (컬럼=티커, 합계<=1.0 또는 레버리지 합계<=2.0)
        """
        # 공통 일자 정렬
        common_idx = prices.index.intersection(target_weights.index).sort_values()
        if start_date:
            common_idx = common_idx[common_idx >= pd.to_datetime(start_date)]
        if end_date:
            common_idx = common_idx[common_idx <= pd.to_datetime(end_date)]

        if len(common_idx) < 5:
            raise ValueError(f"Insufficient overlapping dates between prices and weights: {len(common_idx)}")

        px = prices.reindex(common_idx).ffill()
        asset_rets = px.pct_change().fillna(0.0)

        # 룩어헤드 방지: t일 종가 시그널 -> t+1일 보유 비중 적용
        weights = target_weights.reindex(common_idx).ffill().shift(1).fillna(0.0)

        # 누락된 컬럼 처리
        for col in weights.columns:
            if col not in asset_rets.columns:
                asset_rets[col] = 0.0

        aligned_rets = asset_rets[weights.columns]

        # 일별 원(Gross) 전략 수익률
        gross_daily_rets = (weights * aligned_rets).sum(axis=1)

        # 턴오버 계산 (가중치 변화량 합 / 2)
        weight_diff = weights.diff().abs().sum(axis=1).fillna(0.0)
        trading_cost = weight_diff * self.cost_rate

        # 일별 순(Net) 전략 수익률
        net_daily_rets = gross_daily_rets - trading_cost

        # Equity Curve (기준 100)
        gross_equity = 100.0 * (1.0 + gross_daily_rets).cumprod()
        net_equity = 100.0 * (1.0 + net_daily_rets).cumprod()

        # 성과 지표 산출
        metrics_gross = compute_metrics(gross_equity, periods_per_year=252)
        metrics_net = compute_metrics(net_equity, periods_per_year=252)
        yearly_rets = compute_yearly_returns(net_daily_rets)

        # 연간 턴오버율
        years = metrics_net.get("Years", 1.0)
        annual_turnover = (weight_diff.sum() / 2.0) / max(years, 0.1)

        metrics_net["Annual_Turnover"] = annual_turnover

        return {
            "gross_equity": gross_equity,
            "net_equity": net_equity,
            "gross_daily_rets": gross_daily_rets,
            "net_daily_rets": net_daily_rets,
            "weights": weights,
            "turnover_series": weight_diff,
            "metrics_gross": metrics_gross,
            "metrics_net": metrics_net,
            "yearly_returns": yearly_rets
        }
