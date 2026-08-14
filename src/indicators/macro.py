"""공통 거시경제 및 카나리아 지표 라이브러리.

- Inflation Compass: SPY 200SMA, T5YIE 레벨 & 모멘텀, 섹터 바스켓 선형회귀 기울기
- MQC 4대 카나리아: TIP(통화), EEM(자본), HYG/IEF(신용), T10Y2Y(금리차)
- Yield Curve Defense: DGS3MO vs DFF
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def rolling_slope(series: pd.Series, window: int = 60) -> pd.Series:
    """단일 시계열의 rolling 선형회귀 기울기 산출."""
    x = np.arange(window)
    x_mean = x.mean()
    denom = ((x - x_mean) ** 2).sum()

    def _calc_slope(y):
        return ((x - x_mean) * (y - y.mean())).sum() / denom

    return series.rolling(window).apply(_calc_slope, raw=True)


def compute_inflation_compass_signals(prices_daily: pd.DataFrame, t5yie_daily: pd.Series) -> pd.DataFrame:
    """Inflation Compass 성장/인플레이션 4분면 레짐 산출 (일별)."""
    # 1. 성장 신호
    spy_sma200 = prices_daily["SPY"].rolling(200).mean()
    growth_on = prices_daily["SPY"] > spy_sma200

    # 2. 인플레이션 신호 (포지티브 바스켓 vs 네거티브 바스켓 누적수익률 비율 기울기)
    pos_basket = {"XLE": 0.5, "XLI": 1/6, "XLF": 1/6, "XLB": 1/6}
    neg_basket = {"XLU": 1/3, "XLV": 1/3, "XLP": 1/3}

    rets = prices_daily.pct_change()
    pos_ret = sum(rets[t] * w for t, w in pos_basket.items() if t in rets.columns)
    neg_ret = sum(rets[t] * w for t, w in neg_basket.items() if t in rets.columns)

    pos_cum = (1 + pos_ret.fillna(0)).cumprod()
    neg_cum = (1 + neg_ret.fillna(0)).cumprod()
    indicator = pos_cum / neg_cum

    slope = rolling_slope(indicator, window=60)
    asset_mom_on = slope > 0

    t5yie_lvl_on = t5yie_daily > 2.0
    t5yie_mom_on = t5yie_daily > t5yie_daily.shift(60)

    inflation_on = t5yie_lvl_on & (t5yie_mom_on | asset_mom_on)

    df_signals = pd.DataFrame({
        "growth_on": growth_on,
        "inflation_on": inflation_on,
        "t5yie": t5yie_daily,
        "slope": slope
    }, index=prices_daily.index)

    return df_signals
