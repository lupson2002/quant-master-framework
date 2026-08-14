"""공통 모멘텀 지표 라이브러리.

- 13612W 모멘텀: 12*r1 + 4*r3 + 2*r6 + 1*r12 (또는 BAA 가중치 0.15*r1 + 0.50*r3 + 0.35*r12)
- 12-1 모멘텀: r12 - r1
- Dual Momentum Score: ((r12 + r6)/2 - r3) + r1
- 상대 모멘텀 (Price / EMA14)
- 변동성 조정 모멘텀: Return / Volatility
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def trailing_return(prices: pd.DataFrame | pd.Series, periods: int) -> pd.DataFrame | pd.Series:
    """n기간 누적 수익률: P_t / P_{t-n} - 1"""
    return prices.pct_change(periods)


def momentum_13612w_keller(prices: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """켈러 VAA 13612W 모멘텀: 12*r1 + 4*r3 + 2*r6 + 1*r12"""
    r1 = prices.pct_change(1)
    r3 = prices.pct_change(3)
    r6 = prices.pct_change(6)
    r12 = prices.pct_change(12)
    return 12.0 * r1 + 4.0 * r3 + 2.0 * r6 + 1.0 * r12


def momentum_13612w_baa(prices: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """켈러 BAA 13612W 카나리아 점수: 0.15*r1 + 0.50*r3 + 0.35*r12"""
    r1 = prices.pct_change(1)
    r3 = prices.pct_change(3)
    r12 = prices.pct_change(12)
    return 0.15 * r1 + 0.50 * r3 + 0.35 * r12


def momentum_121(prices: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """12-1 모멘텀: r12 - r1"""
    r12 = prices.pct_change(12)
    r1 = prices.pct_change(1)
    return r12 - r1


def dual_momentum_score(prices: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """4자산 듀얼모멘텀 점수: ((r12 + r6)/2 - r3) + r1"""
    r1 = prices.pct_change(1)
    r3 = prices.pct_change(3)
    r6 = prices.pct_change(6)
    r12 = prices.pct_change(12)
    return ((r12 + r6) / 2.0 - r3) + r1


def relative_ema_momentum(prices: pd.DataFrame | pd.Series, span: int = 14) -> pd.DataFrame | pd.Series:
    """상대 모멘텀: 가격 / EMA(span)"""
    ema = prices.ewm(span=span, adjust=False).mean()
    return prices / ema
