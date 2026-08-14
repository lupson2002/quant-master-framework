"""전략 기본 인터페이스 (Base Strategy Interface)."""

from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        """
        일별 가격 및 거시 데이터를 입력받아 자산별 목표 가중치(DataFrame, index=날짜, columns=티커)를 반환.
        신호는 리밸런싱 주기에 맞춰 일별 또는 월말로 산출되어 채워집니다.
        """
        pass
