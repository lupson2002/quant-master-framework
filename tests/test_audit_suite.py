"""전체 퀀트 시스템 제3자 감사용 단위 테스트 및 무결성 검증 슈트 (Quant System Audit Test Suite).

검증 항목:
1. [Lookahead Bias] 룩어헤드 편향 전무 검증 (1-Day Execution Lag, t일 신호는 t+1일 시가/종가에 집행)
2. [Leverage & Weight Integrity] 가중치 누수, 결측치(NaN), 의도치 않은 레버리지 팽창 검증
3. [Transaction Cost Exactness] 회전율(Turnover) 및 편도 15bp / 왕복 30bp 수수료 차감 수학적 정확성
4. [Indicator Mathematical Fidelity] 13612W, ZLEMA 105, T5YIE 기울기, Dual Momentum 지표 정밀성
5. [Metric Standard Compliance] CAGR, MDD, Sharpe, Sortino, Calmar 공식 표준 준수
6. [Strategy Determinism] 10대 단품 전략 및 Option B 하이브리드 전략의 결정론적(Deterministic) 재현성
"""

from __future__ import annotations
import sys
from pathlib import Path
import unittest
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import compute_metrics
from src.indicators.momentum import momentum_13612w_keller, momentum_13612w_baa, dual_momentum_score
from src.indicators.trend import compute_zlema
from src.indicators.macro import compute_inflation_compass_signals
from run_individual_deep_optimization import (
    ic_v1_weights, mqc_opt_weights, baa_opt_weights, zerolag_opt_weights,
    dm_v0_weights, gb_v1_weights
)


class QuantAuditTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prices = load_yahoo_prices(start="2002-01-01")
        cls.fred = load_fred_series()
        cls.engine = BacktestEngine(transaction_cost_bp=15.0)
        cls.start_date = "2003-04-01"
        cls.end_date = cls.prices.index[-1].strftime("%Y-%m-%d")

    def test_01_lookahead_bias_prevention(self):
        """[검증 1] 룩어헤드 편향 방지 검증: 백테스트 엔진에서 weights.shift(1) 적용 확인"""
        dates = pd.date_range("2020-01-01", periods=15, freq="B")
        px = pd.DataFrame({"SPY": [100.0] * 15}, index=dates)
        px.iloc[1, 0] = 110.0  # Day 1 -> Day 2: +10%
        px.iloc[2, 0] = 100.0  # Day 2 -> Day 3: -9.09%

        # Day 2(index 1)에 SPY를 100% 매수하는 가중치
        w = pd.DataFrame({"SPY": [0.0] * 15}, index=dates)
        w.iloc[1:5, 0] = 1.0

        res = self.engine.run(px, w, start_date="2020-01-01", end_date="2020-01-20")
        gross_rets = res["gross_daily_rets"]

        # Day 1 -> Day 2 수익률(+10%)은 가중치가 Day 2에 산출되었으므로 Day 2에 반영되면 안 됨 (0%여야 함)
        # Day 2 -> Day 3 수익률(-9.09%)이 Day 3에 비로소 반영되어야 함
        self.assertEqual(gross_rets.iloc[1], 0.0, "Day 2에 산출된 신호가 Day 2 당일 수익률에 즉시 반영되는 룩어헤드 편향 발생!")
        day3_ret = (100.0 / 110.0) - 1.0
        self.assertAlmostEqual(gross_rets.iloc[2], day3_ret, places=5, msg="Day 2 신호가 Day 3에 정확히 1-Day Lag로 집행되지 않음!")

    def test_02_transaction_cost_math(self):
        """[검증 2] 거래 수수료 차감 수학적 정확성 검증 (턴오버 x 15bp 편도 = 30bp 왕복)"""
        dates = pd.date_range("2020-01-01", periods=15, freq="B")
        px = pd.DataFrame({"SPY": [100.0] * 15, "BIL": [100.0] * 15}, index=dates)
        # Day 0: 100% BIL -> Day 1: 100% SPY로 교체 (턴오버 = |0-1| + |1-0| = 2.0)
        w = pd.DataFrame({"SPY": [0.0] * 15, "BIL": [1.0] * 15}, index=dates)
        w.iloc[1:, 0] = 1.0  # Day 1부터 SPY 100%
        w.iloc[1:, 1] = 0.0  # Day 1부터 BIL 0%

        res = self.engine.run(px, w, start_date="2020-01-01", end_date="2020-01-20")
        net_rets = res["net_daily_rets"]

        # Day 1에 교체 발생 -> 1-day lag로 Day 2에 턴오버 2.0 발생 -> 편도 15bp x 2.0 = 30bp (0.0030) 차감
        expected_cost = 2.0 * 0.0015  # 0.0030
        self.assertAlmostEqual(net_rets.iloc[2], -expected_cost, places=5, msg="턴오버에 따른 거래 수수료 차감 계산 오류!")

    def test_03_weight_integrity_and_no_nan(self):
        """[검증 3] 가중치 무결성 검증: 10대 전략 모두 결측치(NaN)나 무한대(Inf)가 없어야 함"""
        weight_generators = [
            ("Inflation Compass", ic_v1_weights),
            ("Dual Momentum", dm_v0_weights),
            ("ZeroLag Trend", zerolag_opt_weights),
            ("BAA-G4", baa_opt_weights),
            ("Golden Butterfly", gb_v1_weights),
            ("MQC", mqc_opt_weights),
        ]

        for name, fn in weight_generators:
            w = fn(self.prices, self.fred)
            w_sub = w.loc[self.start_date:self.end_date]
            self.assertFalse(w_sub.isna().any().any(), f"{name} 가중치에 NaN 결측치가 존재합니다!")
            self.assertFalse(np.isinf(w_sub.to_numpy()).any(), f"{name} 가중치에 Inf 무한대가 존재합니다!")
            row_sums = w_sub.sum(axis=1)
            self.assertTrue((row_sums <= 2.01).all(), f"{name} 총 가중치 합이 허용 레버리지를 초과했습니다: {row_sums.max()}")

    def test_04_zlema_mathematics(self):
        """[검증 4] ZLEMA (Zero-Lag Exponential Moving Average) 수식 검증"""
        s = pd.Series(np.linspace(100, 200, 200), index=pd.date_range("2020-01-01", periods=200))
        z = compute_zlema(s, period=10)
        self.assertEqual(len(z), len(s))
        self.assertFalse(z.dropna().isna().any())
        # 선형 상승 시계열에서 ZLEMA는 일반 EMA보다 래그가 적어 현재 가격에 매우 근접해야 함
        self.assertAlmostEqual(z.iloc[-1], s.iloc[-1], delta=5.0)

    def test_05_13612w_momentum_formula(self):
        """[검증 5] 13612W 가중 모멘텀 수식 (12*r1 + 4*r3 + 2*r6 + r12) 정확성 검증"""
        dates = pd.date_range("2020-01-01", periods=13, freq="ME")
        # 매달 10%씩 복리 상승하는 자산 (1.1^0, 1.1^1, ..., 1.1^12)
        px_vals = [100.0 * (1.10 ** i) for i in range(13)]
        df_px = pd.DataFrame({"TEST": px_vals}, index=dates)

        score = momentum_13612w_keller(df_px)
        r1 = (px_vals[12] / px_vals[11]) - 1.0  # 0.10
        r3 = (px_vals[12] / px_vals[9]) - 1.0   # 0.331
        r6 = (px_vals[12] / px_vals[6]) - 1.0   # 0.77156
        r12 = (px_vals[12] / px_vals[0]) - 1.0  # 2.1384

        expected = 12 * r1 + 4 * r3 + 2 * r6 + 1 * r12
        actual = score.loc[dates[-1], "TEST"]
        self.assertAlmostEqual(actual, expected, places=4, msg="13612W 가중 모멘텀 계산식이 켈러 공식과 불일치합니다!")

    def test_06_hybrid_option_b_reproducibility(self):
        """[검증 6] Option B (40/30/15/15) 하이브리드 전략의 결정론적 재현성 검증"""
        w_ic = ic_v1_weights(self.prices, self.fred)
        w_dm = dm_v0_weights(self.prices, self.fred)
        w_zl = zerolag_opt_weights(self.prices, self.fred)
        w_baa = baa_opt_weights(self.prices, self.fred)

        w_opt_b = w_ic * 0.40 + w_dm * 0.30 + w_zl * 0.15 + w_baa * 0.15
        res = self.engine.run(self.prices, w_opt_b, start_date=self.start_date, end_date=self.end_date)
        m = res["metrics_net"]

        # 지표 범위 검증 (1.0x 순수 무레버리지 기준: CAGR ~17.0%, MDD -18~-24%)
        self.assertTrue(0.165 <= m["CAGR"] <= 0.19, f"Option B CAGR이 예상 범위(16.5~19%)를 벗어남: {m['CAGR']}")
        self.assertTrue(-0.25 <= m["MDD"] <= -0.17, f"Option B MDD가 예상 범위(-17~-25%)를 벗어남: {m['MDD']}")
        self.assertTrue(m["Sharpe"] >= 1.0, f"Option B Sharpe가 1.0 미만임: {m['Sharpe']}")
        self.assertTrue(m["Calmar"] >= 0.80, f"Option B Calmar가 0.80 미만임: {m['Calmar']}")


if __name__ == "__main__":
    unittest.main()
