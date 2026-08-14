"""하이브리드 전략 1: Macro-Trend Meta Engine (계층적 4단계 메타 전략).

Layer 1: Macro Canary Gatekeeper (TIP, EEM, T10Y2Y 거시 신용/금리 위험 감지)
Layer 2: Macro Regime Allocator (Inflation Compass 성장/인플레 4분면 타겟팅)
Layer 3: Tactical Momentum Confirmation (BAA-G4 상대강도 교차 검증)
Layer 4: Trailing Risk Management (일간 ZLEMA 105 하회 시 즉시 BIL 조기 탈출)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from ..strategies.base import BaseStrategy
from ..indicators.macro import compute_inflation_compass_signals
from ..indicators.momentum import momentum_13612w_keller, relative_ema_momentum
from ..indicators.trend import compute_zlema


class MacroTrendMetaEngine(BaseStrategy):
    def __init__(self, name: str = "Hybrid_Macro_Trend_Meta", max_leverage: float = 1.25):
        super().__init__(name)
        self.max_leverage = max_leverage
        self.canaries = ["TIP", "EEM"]
        self.def_assets = ["BIL", "TLT", "GLD"]

    def generate_weights(self, prices_daily: pd.DataFrame, fred_data: pd.DataFrame | None = None) -> pd.DataFrame:
        t5yie = fred_data["T5YIE"].reindex(prices_daily.index).ffill() if fred_data is not None and "T5YIE" in fred_data else prices_daily["SPY"] * 0 + 2.1
        t10y2y = fred_data["T10Y2Y"].reindex(prices_daily.index).ffill() if fred_data is not None and "T10Y2Y" in fred_data else prices_daily["SPY"] * 0 + 0.5

        # 1. IC 시그널 (성장 x 인플레 4분면)
        ic_signals = compute_inflation_compass_signals(prices_daily, t5yie)

        # 2. 카나리아 모멘텀 (월간)
        monthly_px = prices_daily.resample("ME").last()
        score_13612w = momentum_13612w_keller(monthly_px)
        rel_mom = relative_ema_momentum(monthly_px)

        # 3. 일간 ZLEMA 필터
        zlema_spy = compute_zlema(prices_daily["SPY"], period=105)
        zlema_qqq = compute_zlema(prices_daily["QQQ"], period=105) if "QQQ" in prices_daily.columns else zlema_spy

        monthly_dates = prices_daily.resample("ME").last().index
        weights_m = pd.DataFrame(0.0, index=monthly_dates, columns=prices_daily.columns)
        cash_ticker = "BIL" if "BIL" in prices_daily.columns else "SHY"

        for d in monthly_dates:
            valid_idx = ic_signals.index[ic_signals.index <= d]
            if len(valid_idx) == 0:
                continue
            d_calc = valid_idx[-1]

            # [Layer 1] 거시 카나리아 위험 점수 판정
            risk_pts = 0
            if "TIP" in score_13612w.columns and score_13612w.loc[d, "TIP"] <= 0:
                risk_pts += 1
            if "EEM" in score_13612w.columns and score_13612w.loc[d, "EEM"] <= 0:
                risk_pts += 1
            if t10y2y.loc[d_calc] <= 0:
                risk_pts += 1

            # [Layer 2] IC 성장 x 인플레이션 국면
            row = ic_signals.loc[d_calc]
            g_on = bool(row["growth_on"])
            inf_on = bool(row["inflation_on"])

            if risk_pts >= 2 or (not g_on and not inf_on):
                # 전면 방어 모드: BIL, TLT, GLD 3중 쿠션 방어 (BAA-G4 로직)
                valid_def = [c for c in self.def_assets if c in weights_m.columns]
                for da in valid_def:
                    weights_m.loc[d, da] = 1.0 / len(valid_def)
            else:
                # 공격 또는 전술 국면: 국면별 최적 자산 선정
                lev = self.max_leverage if risk_pts == 0 and g_on else 1.0

                if g_on and inf_on:
                    # Q1 (리플레이션): XLE (에너지) + DBC (원자재) 50:50
                    weights_m.loc[d, "XLE"] = lev * 0.70
                    weights_m.loc[d, "GLD" if "GLD" in weights_m.columns else "DBC"] = lev * 0.30
                elif g_on and not inf_on:
                    # Q2 (디스인플레 성장): QQQ / XLK (기술주 주도)
                    weights_m.loc[d, "QQQ" if "QQQ" in weights_m.columns else "XLK"] = lev * 0.70
                    weights_m.loc[d, "SPY"] = lev * 0.30
                elif not g_on and inf_on:
                    # Q3 (스태그플레이션): XLU (유틸리티) + GLD (금) 50:50
                    weights_m.loc[d, "XLU"] = lev * 0.50
                    weights_m.loc[d, "GLD"] = lev * 0.50

        # [Layer 4] 일간 ZLEMA 조기 탈출 결합
        base_weights = weights_m.reindex(prices_daily.index).ffill().fillna(0.0)
        final_weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)

        for d in prices_daily.index:
            w_row = base_weights.loc[d].copy()
            # SPY가 ZLEMA 아래로 이탈하면 공격 자산의 50%를 즉시 현금으로 회피
            if prices_daily.loc[d, "SPY"] < zlema_spy.loc[d]:
                for eq in ["SPY", "QQQ", "XLK", "XLE", "XLU"]:
                    if eq in w_row and w_row[eq] > 0:
                        de_risk = w_row[eq] * 0.50
                        w_row[eq] -= de_risk
                        w_row[cash_ticker] += de_risk
            final_weights.loc[d] = w_row

        return final_weights
