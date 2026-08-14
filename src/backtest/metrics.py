"""통합 퀀트 성과 지표 계산기.

CAGR, 연간 변동성, 샤프지수, 소르티노지수, MDD, Calmar Ratio, 승률, 턴오버,
연도별 수익률, 롤링 샤프 등을 계산합니다.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def compute_metrics(equity_series: pd.Series, periods_per_year: int = 252, rf: float = 0.0) -> dict[str, float]:
    """자산 가치 시계열(Equity Series)로부터 핵심 성과 지표 계산."""
    equity = equity_series.dropna()
    if len(equity) < 2:
        return {}

    returns = equity.pct_change().dropna()
    n_periods = len(returns)
    years = n_periods / periods_per_year

    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total_return) ** (1.0 / years) - 1.0 if years > 0 and equity.iloc[-1] > 0 else 0.0

    ann_vol = returns.std() * np.sqrt(periods_per_year)
    excess_returns = returns - (rf / periods_per_year)
    sharpe = (excess_returns.mean() / returns.std()) * np.sqrt(periods_per_year) if returns.std() > 0 else 0.0

    # 소르티노 (하방 변동성)
    downside_returns = returns[returns < 0]
    downside_std = downside_returns.std() * np.sqrt(periods_per_year) if len(downside_returns) > 0 else 0.0
    sortino = (excess_returns.mean() * periods_per_year) / downside_std if downside_std > 0 else 0.0

    # Drawdown & MDD
    cummax = equity.cummax()
    drawdowns = (equity - cummax) / cummax
    mdd = drawdowns.min()

    # Calmar Ratio
    calmar = cagr / abs(mdd) if mdd < 0 else 0.0

    # 승률 (양의 수익률 비율)
    win_rate = (returns > 0).mean()

    return {
        "CAGR": cagr,
        "Annual_Vol": ann_vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "MDD": mdd,
        "Calmar": calmar,
        "Win_Rate": win_rate,
        "Total_Return": total_return,
        "Years": years
    }


def compute_yearly_returns(daily_returns: pd.Series) -> pd.Series:
    """일별 수익률 시리즈로부터 연도별 복리 수익률 계산."""
    daily_returns = daily_returns.dropna()
    yearly = daily_returns.groupby(daily_returns.index.year).apply(lambda r: (1 + r).prod() - 1)
    return yearly
