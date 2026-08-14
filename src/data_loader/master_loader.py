"""통합 퀀트 프레임워크 — 마스터 데이터 로더.

야후 파이낸스(가격), FRED(거시경제), Ken French(글로벌 지수/팩터), Shiller(초장기) 시계열을
통합 관리하고 캐시하여 고속으로 로드합니다.
"""

from __future__ import annotations

import os
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
DB_PATH = BASE_DIR / "data" / "quant_master.db"

# 주요 ETF 및 자산군 유니버스
CORE_ETFS = [
    "SPY", "QQQ", "QLD", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD",
    "TIP", "PDBC", "BIL", "IEF", "TLT", "LQD", "AGG", "SHY",
    "XLE", "XLK", "XLU", "XLP", "XLI", "XLF", "XLB", "XLV", "USO", "VTI", "IYR"
]

FRED_SERIES = [
    "T5YIE", "T10Y2Y", "DGS3MO", "DFF", "DGS10", "DFII10", "TP10J07", "ICSA", "SAHM", "CPIAUCSL"
]


def load_yahoo_prices(tickers: list[str] | None = None, start: str = "1990-01-01") -> pd.DataFrame:
    """야후 파이낸스에서 수정종가(Close/Adj Close) 시계열을 로드/캐시."""
    if tickers is None:
        tickers = CORE_ETFS

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = PROCESSED_DIR / f"yahoo_daily_{start}.parquet"
    if cache_file.exists():
        try:
            df = pd.read_parquet(cache_file)
            missing = [t for t in tickers if t not in df.columns]
            # 캐시가 존재하고 모든 티커가 포함되어 있으며 데이터가 충분히 최근인 경우 캐시 사용
            if not missing and len(df) > 100:
                return df[tickers].dropna(how="all")
        except Exception:
            pass

    print(f"[*] Downloading Yahoo Finance data for {len(tickers)} tickers from {start}...")
    data = yf.download(tickers, start=start, auto_adjust=True, progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        close_df = data["Close"] if "Close" in data.columns.levels[0] else data.xs(data.columns.levels[0][0], axis=1, level=0)
    else:
        close_df = data
    close_df = close_df.ffill().dropna(how="all")
    try:
        close_df.to_parquet(cache_file)
    except Exception:
        pass
    return close_df[[t for t in tickers if t in close_df.columns]]


def load_fred_series(series_ids: list[str] | None = None) -> pd.DataFrame:
    """FRED 거시 지표 로드 (data/raw에 캐시된 CSV 우선 활용)."""
    if series_ids is None:
        series_ids = FRED_SERIES

    frames = {}
    for s_id in series_ids:
        csv_path = RAW_DIR / f"{s_id.lower()}.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                date_col = [c for c in df.columns if c.lower() in ("date", "observation_date")][0]
                val_col = [c for c in df.columns if c != date_col][0]
                df[date_col] = pd.to_datetime(df[date_col])
                df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
                frames[s_id] = df.set_index(date_col)[val_col].sort_index()
            except Exception as e:
                print(f"[!] Warning reading {csv_path}: {e}")

    fred_df = pd.DataFrame(frames).sort_index().ffill()
    return fred_df


def load_monthly_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    """월말 리샘플링된 통합 가격 및 거시 지표 DataFrame 반환."""
    daily_prices = load_yahoo_prices()
    daily_fred = load_fred_series()

    monthly_prices = daily_prices.resample("ME").last()
    monthly_fred = daily_fred.resample("ME").last().reindex(monthly_prices.index).ffill()

    return monthly_prices, monthly_fred
