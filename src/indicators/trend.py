"""공통 추세 및 변동성 지표 라이브러리.

- John Ehlers Zero-Lag EMA (ZLEMA)
- SMA 200 / EMA 14
- Percentile Channels (백분위수 채널 돌파)
- Chandelier Exit (ATR 기반 트레일링 스탑)
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def compute_zlema(series: pd.Series, period: int = 105) -> pd.Series:
    """John Ehlers 정통 Zero-Lag Exponential Moving Average (ZLEMA).
    Lag = (period - 1) // 2
    ZData = 2 * Series - Series.shift(Lag)
    ZLEMA = EMA(ZData, period)
    """
    lag = int((period - 1) / 2)
    zdata = 2 * series - series.shift(lag)
    # 초기 결측치 보정 후 EMA 적용
    zlema = zdata.ewm(span=period, adjust=False).mean()
    return zlema


def compute_chandelier_exit(high: pd.Series, low: pd.Series, close: pd.Series,
                            period: int = 15, mult: float = 4.0) -> pd.Series:
    """Chandelier Exit Trailing Stop.
    ATR = Rolling Mean of True Range(15)
    Exit = Highest High(15) - mult * ATR
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    highest_high = high.rolling(period).max()
    stop_line = highest_high - mult * atr
    return stop_line


def compute_percentile_channel(series: pd.Series, window: int = 60,
                               buy_th: float = 0.75, exit_th: float = 0.25) -> pd.Series:
    """다중 백분위수 채널 돌파 신호 (히스테리시스 유지).
    가격이 window 기간의 상위 buy_th(75%)를 상향돌파하면 +1,
    하위 exit_th(25%)를 하향돌파하면 -1, 그 사이는 직전 상태 유지.
    """
    pct = series.rolling(window).rank(pct=True)
    signal = pd.Series(0.0, index=series.index)
    state = 0.0
    for i in range(len(series)):
        p = pct.iloc[i]
        if np.isnan(p):
            continue
        if p >= buy_th:
            state = 1.0
        elif p <= exit_th:
            state = -1.0
        signal.iloc[i] = state
    return signal
