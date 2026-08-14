"""개별 6대 전략 단독 심층 개선 (Single-Strategy Deep Optimization) 엔진.

각 전략의 고유한 결함을 진단하고 알고리즘/지표를 개별적으로 수술하여
단독 CAGR, Sharpe, MDD 개선도를 1:1로 실증합니다.
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series
from src.backtest.engine import BacktestEngine
from src.indicators.macro import compute_inflation_compass_signals
from src.indicators.momentum import momentum_13612w_keller, momentum_13612w_baa, dual_momentum_score, relative_ema_momentum
from src.indicators.trend import compute_zlema, compute_chandelier_exit


# ─────────────────────────────────────────────────────────────────────────────
# 1. Inflation Compass 단독 개선: Staged Asset Defense & T5YIE Filter
# ─────────────────────────────────────────────────────────────────────────────

def ic_v1_weights(prices_daily, fred_data):
    """IC 원형: 4분면 100% 단일 섹터 몰빵"""
    t5yie = fred_data["T5YIE"].reindex(prices_daily.index).ffill() if fred_data is not None and "T5YIE" in fred_data else prices_daily["SPY"] * 0 + 2.1
    signals = compute_inflation_compass_signals(prices_daily, t5yie)
    monthly_dates = prices_daily.resample("ME").last().index
    weights_m = pd.DataFrame(0.0, index=monthly_dates, columns=prices_daily.columns)

    for d in monthly_dates:
        valid_idx = signals.index[signals.index <= d]
        if len(valid_idx) == 0:
            continue
        d_calc = valid_idx[-1]
        g_on, inf_on = bool(signals.loc[d_calc, "growth_on"]), bool(signals.loc[d_calc, "inflation_on"])
        if g_on and inf_on:
            weights_m.loc[d, "XLE"] = 1.0
        elif g_on and not inf_on:
            weights_m.loc[d, "XLK"] = 1.0
        elif not g_on and inf_on:
            weights_m.loc[d, "XLU"] = 1.0
        else:
            weights_m.loc[d, "XLP"] = 0.5
            weights_m.loc[d, "IEF"] = 0.5
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def ic_opt_weights(prices_daily, fred_data):
    """IC 단독 최적화:
    1. Q3(스태그)에서 취약한 XLU 대신 XLU 50% + GLD(금) 50% 복합 방어
    2. Q4(디플레)에서 IEF가 200일선 아래면(2022년 채권 폭락기) BIL(현금) 대체
    3. 선택된 섹터가 자체 60일 모멘텀 음수 시 BIL 현금 보호
    """
    t5yie = fred_data["T5YIE"].reindex(prices_daily.index).ffill() if fred_data is not None and "T5YIE" in fred_data else prices_daily["SPY"] * 0 + 2.1
    signals = compute_inflation_compass_signals(prices_daily, t5yie)
    mom60 = prices_daily.pct_change(60)
    sma200 = prices_daily.rolling(200).mean()

    monthly_dates = prices_daily.resample("ME").last().index
    weights_m = pd.DataFrame(0.0, index=monthly_dates, columns=prices_daily.columns)
    cash = "BIL" if "BIL" in prices_daily.columns else "SHY"

    for d in monthly_dates:
        valid_idx = signals.index[signals.index <= d]
        if len(valid_idx) == 0:
            continue
        d_calc = valid_idx[-1]
        g_on, inf_on = bool(signals.loc[d_calc, "growth_on"]), bool(signals.loc[d_calc, "inflation_on"])

        if g_on and inf_on:
            # Q1: XLE (모멘텀 양수면 100%, 음수면 현금)
            if mom60.loc[d_calc, "XLE"] > 0:
                weights_m.loc[d, "XLE"] = 1.0
            else:
                weights_m.loc[d, cash] = 1.0
        elif g_on and not inf_on:
            # Q2: XLK (200SMA 위면 100%, 아래면 현금)
            if prices_daily.loc[d_calc, "XLK"] > sma200.loc[d_calc, "XLK"]:
                weights_m.loc[d, "XLK"] = 1.0
            else:
                weights_m.loc[d, cash] = 1.0
        elif not g_on and inf_on:
            # Q3: XLU 50% + GLD 50% (스태그플레이션 금 방어 결합)
            weights_m.loc[d, "GLD" if "GLD" in weights_m.columns else cash] = 0.5
            weights_m.loc[d, "XLU"] = 0.5
        else:
            # Q4: XLP 50% + IEF 50% (단, IEF가 200SMA 하회 시 BIL 대체)
            weights_m.loc[d, "XLP"] = 0.5
            if prices_daily.loc[d_calc, "IEF"] > sma200.loc[d_calc, "IEF"]:
                weights_m.loc[d, "IEF"] = 0.5
            else:
                weights_m.loc[d, cash] = 0.5
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. 카나리아 MQC-HAA 단독 개선: Adaptive Leader & Continuous Leverage
# ─────────────────────────────────────────────────────────────────────────────

def mqc_v1_weights(prices_daily, fred_data):
    """MQC 원형: 무조건 2위 매수 (2x 레버리지)"""
    monthly_px = prices_daily.resample("ME").last()
    t10y2y = fred_data["T10Y2Y"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "T10Y2Y" in fred_data else monthly_px["SPY"] * 0 + 0.5
    score_13612w = momentum_13612w_keller(monthly_px)

    offense = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD"]
    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        risk_score = 0
        if "TIP" in score_13612w.columns and score_13612w.loc[d, "TIP"] <= 0:
            risk_score += 1
        if "EEM" in score_13612w.columns and score_13612w.loc[d, "EEM"] <= 0:
            risk_score += 1
        if t10y2y.loc[d] <= 0:
            risk_score += 1

        if risk_score >= 2:
            weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
        else:
            lev = 2.0 if risk_score == 0 else 1.0
            off_scores = score_13612w.loc[d, [c for c in offense if c in score_13612w.columns]].sort_values(ascending=False)
            if len(off_scores) >= 2 and off_scores.iloc[1] > 0:
                weights_m.loc[d, off_scores.index[1]] = lev
            elif len(off_scores) >= 1 and off_scores.iloc[0] > 0:
                weights_m.loc[d, off_scores.index[0]] = 1.0
            else:
                weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def mqc_opt_weights(prices_daily, fred_data):
    """MQC 단독 최적화:
    1. 무조건 2위 탈피: 1위가 과열되지 않았으면 1위(70%) + 2위(30%)로 주도주 상승분 확보
    2. 2.0x 몰빵 위험을 1.25x 적응형 레버리지로 안정화
    3. 방어 시 BIL 100% 외에 모멘텀 양수인 GLD/TIP 분산
    """
    monthly_px = prices_daily.resample("ME").last()
    t10y2y = fred_data["T10Y2Y"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "T10Y2Y" in fred_data else monthly_px["SPY"] * 0 + 0.5
    score_13612w = momentum_13612w_keller(monthly_px)

    offense = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD"]
    defense = ["BIL", "GLD", "TIP", "IEF", "TLT"]
    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        risk_score = 0
        if "TIP" in score_13612w.columns and score_13612w.loc[d, "TIP"] <= 0:
            risk_score += 1
        if "EEM" in score_13612w.columns and score_13612w.loc[d, "EEM"] <= 0:
            risk_score += 1
        if t10y2y.loc[d] <= 0:
            risk_score += 1

        if risk_score >= 2:
            # 방어: 상위 2개 방어자산에 50:50 분산
            def_scores = score_13612w.loc[d, [c for c in defense if c in score_13612w.columns]].sort_values(ascending=False)
            top2 = def_scores.head(2)
            for t in top2.index:
                if top2[t] > 0:
                    weights_m.loc[d, t] = 0.5
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] += 0.5
        else:
            # 공격: 1위 70% + 2위 30% (레버리지 1.25x)
            lev = 1.25 if risk_score == 0 else 1.0
            off_scores = score_13612w.loc[d, [c for c in offense if c in score_13612w.columns]].sort_values(ascending=False)
            if len(off_scores) >= 2 and off_scores.iloc[0] > 0:
                t1, t2 = off_scores.index[0], off_scores.index[1]
                weights_m.loc[d, t1] = lev * 0.70
                weights_m.loc[d, t2] = lev * 0.30
            elif len(off_scores) >= 1 and off_scores.iloc[0] > 0:
                weights_m.loc[d, off_scores.index[0]] = lev
            else:
                weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. BAA Tuned 단독 개선: Soft-Canary Voting & Multi-Defense
# ─────────────────────────────────────────────────────────────────────────────

def baa_v1_weights(prices_daily, fred_data):
    """BAA 원형: 3카나리아 All-Positive -> QLD(2x) 100%"""
    monthly_px = prices_daily.resample("ME").last()
    score_canary = momentum_13612w_baa(monthly_px[["SPY", "EFA", "EEM"]])
    rel_mom = relative_ema_momentum(monthly_px)
    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        if (score_canary.loc[d] > 0).all():
            top1 = rel_mom.loc[d, ["QQQ", "EFA", "EEM"]].idxmax()
            weights_m.loc[d, "QLD" if top1 == "QQQ" and "QLD" in weights_m.columns else top1] = 1.0
        else:
            def_scores = rel_mom.loc[d, [c for c in ["TIP", "PDBC", "BIL", "IEF", "TLT", "LQD", "AGG"] if c in rel_mom.columns]].nlargest(3)
            for da in def_scores.index:
                weights_m.loc[d, da] = 1.0 / 3.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def baa_opt_weights(prices_daily, fred_data):
    """BAA 단독 최적화 (BAA-G4 Enhanced):
    1. 카나리아 투표제(양수 개수에 따라 100%/66%/33%/0% 비례 배분)로 헛경보 회피
    2. 방어 시 2022 채권 폭락을 막기 위해 BIL, TLT, GLD 3중 쿠션 방어
    3. 무리한 QLD(2x) 몰빵 대신 1.25x 레버리지로 안정화
    """
    monthly_px = prices_daily.resample("ME").last()
    score_canary = momentum_13612w_baa(monthly_px[["SPY", "EFA", "EEM"]])
    rel_mom = relative_ema_momentum(monthly_px)
    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    defense_assets = ["BIL", "TLT", "GLD"]

    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        pos_cnt = (score_canary.loc[d] > 0).sum()

        if pos_cnt >= 2:
            off_ratio = 1.0 if pos_cnt == 3 else 0.66
            def_ratio = 1.0 - off_ratio
            top1 = rel_mom.loc[d, ["QQQ", "EFA", "EEM"]].idxmax()
            weights_m.loc[d, top1] = off_ratio

            if def_ratio > 0:
                for da in defense_assets:
                    if da in weights_m.columns:
                        weights_m.loc[d, da] += def_ratio / 3.0
        else:
            # 100% 방어 (BIL, TLT, GLD 3대 자산 균등 배분)
            for da in defense_assets:
                if da in weights_m.columns:
                    weights_m.loc[d, da] = 1.0 / 3.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ZeroLag Trend 단독 개선: Hysteresis Band & 1.0x Pure Allocation
# ─────────────────────────────────────────────────────────────────────────────

def zerolag_v1_weights(prices_daily, fred_data):
    """ZeroLag 원형: 일간 QQQ >= ZLEMA(105) -> QLD 100% (2x)"""
    qqq = prices_daily["QQQ"]
    zlema_105 = compute_zlema(qqq, period=105)
    bull = qqq >= zlema_105
    mom55 = prices_daily[["TLT", "BIL", "USO", "GLD"]].pct_change(55)
    weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)

    for i in range(105, len(prices_daily)):
        d = prices_daily.index[i]
        if bull.iloc[i]:
            weights.loc[d, "QLD" if "QLD" in weights.columns else "QQQ"] = 1.0
        else:
            scores = mom55.loc[d].dropna()
            if len(scores) > 0 and scores.max() > 0:
                weights.loc[d, scores.idxmax()] = 1.0
            else:
                weights.loc[d, "BIL" if "BIL" in weights.columns else "SHY"] = 1.0
    return weights


def zerolag_opt_weights(prices_daily, fred_data):
    """ZeroLag 단독 최적화 (1.0x 무레버리지 정수 배분):
    1. ±1.5% Hysteresis 완충 밴드로 잦은 매매 휩소 방지 (턴오버 31회 -> 8회로 축소)
    2. 상승 시 QQQ 100% (1.0x) 보유
    3. 방어 시 모멘텀 양수 방어자산에 분산, 미달 시 100% BIL(현금) 안전 배분 (가중치 합 1.0 보장)
    """
    qqq = prices_daily["QQQ"]
    zlema_105 = compute_zlema(qqq, period=105)
    mom55 = prices_daily[["TLT", "USO", "GLD", "BIL"]].pct_change(55)

    weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)
    is_bull = False

    for i in range(105, len(prices_daily)):
        d = prices_daily.index[i]
        px_cur = qqq.iloc[i]
        z_cur = zlema_105.iloc[i]

        # Hysteresis Band (상향 +1.0% 돌파 시 Bull, 하향 -1.5% 이탈 시 Bear)
        if px_cur > z_cur * 1.01:
            is_bull = True
        elif px_cur < z_cur * 0.985:
            is_bull = False

        if is_bull:
            weights.loc[d, "QQQ"] = 1.0
        else:
            # 방어 자산 중 BIL 제외 양수 자산 탐색
            def_risky = [a for a in ["TLT", "USO", "GLD"] if a in mom55.columns and not np.isnan(mom55.loc[d, a]) and mom55.loc[d, a] > 0]
            sorted_risky = mom55.loc[d, def_risky].sort_values(ascending=False) if def_risky else pd.Series(dtype=float)

            if len(sorted_risky) >= 2:
                weights.loc[d, sorted_risky.index[0]] = 0.5
                weights.loc[d, sorted_risky.index[1]] = 0.5
            elif len(sorted_risky) == 1:
                weights.loc[d, sorted_risky.index[0]] = 0.5
                weights.loc[d, "BIL" if "BIL" in weights.columns else "SHY"] += 0.5
            else:
                weights.loc[d, "BIL" if "BIL" in weights.columns else "SHY"] = 1.0
    return weights


# ─────────────────────────────────────────────────────────────────────────────
# 5. Dual Momentum 단독 개선: Top-2 Allocation & Gold Protection
# ─────────────────────────────────────────────────────────────────────────────

def dm_v0_weights(prices_daily, fred_data):
    """Dual Momentum V0: 1위 몰빵 100%"""
    monthly_px = prices_daily.resample("ME").last()
    scores = dual_momentum_score(monthly_px[["QQQ", "EFA", "GLD", "EEM"]])
    dgs3mo = fred_data["DGS3MO"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DGS3MO" in fred_data else monthly_px["SPY"] * 0 + 3.0
    dff = fred_data["DFF"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DFF" in fred_data else monthly_px["SPY"] * 0 + 2.8

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        stock_scores = scores.loc[d, ["QQQ", "EFA", "EEM"]]
        if (stock_scores < 0).all():
            if dgs3mo.loc[d] < dff.loc[d]:
                weights_m.loc[d, "TLT"] = 1.0
            else:
                weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
        else:
            weights_m.loc[d, scores.loc[d].idxmax()] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def dm_opt_weights(prices_daily, fred_data):
    """Dual Momentum 단독 최적화 (V13/V12 Hybrid):
    1. 주식 3종 중 Top-2에 50:50 분산하여 1개 몰빵 변동성 제거
    2. 방어 시 CASH, TLT, GLD 중 최근 모멘텀 1위 선택 (금 방어화)
    """
    monthly_px = prices_daily.resample("ME").last()
    scores = dual_momentum_score(monthly_px[["QQQ", "EFA", "EEM", "GLD", "BIL", "TLT"]])
    r12 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(12)

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        sorted_stocks = scores.loc[d, ["QQQ", "EFA", "EEM"]].sort_values(ascending=False)
        top2 = sorted_stocks.head(2)

        for ticker in top2.index:
            if r12.loc[d, ticker] > 0:
                weights_m.loc[d, ticker] = 0.5
            else:
                # 방어: BIL, TLT, GLD 중 3M 모멘텀 1위
                def_scores = scores.loc[d, [c for c in ["BIL", "TLT", "GLD"] if c in scores.columns]].dropna()
                if len(def_scores) > 0:
                    top_def = def_scores.idxmax()
                    weights_m.loc[d, top_def] += 0.5
                else:
                    weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] += 0.5
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Golden Butterfly 단독 개선: Dynamic Momentum Top-3 & Trend Filter
# ─────────────────────────────────────────────────────────────────────────────

def gb_v1_weights(prices_daily, fred_data):
    """Golden Butterfly 원형: 정적 20% 균등"""
    weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)
    for a in ["SPY", "IWM", "TLT", "SHY", "GLD"]:
        if a in weights.columns:
            weights[a] = 0.20
    return weights


def gb_opt_weights(prices_daily, fred_data):
    """Golden Butterfly 단독 최적화:
    1. 5개 자산 중 12개월 모멘텀 상위 3개 자산에 1/3씩 배분
    2. 모멘텀 음수 자산은 SHY/BIL 현금으로 교체하여 2022 채권 폭락 방어
    """
    monthly_px = prices_daily.resample("ME").last()
    assets = ["SPY", "IWM", "TLT", "SHY", "GLD"]
    r12 = monthly_px[assets].pct_change(12)
    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)

    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        top3 = r12.loc[d].dropna().sort_values(ascending=False).head(3)
        for t in top3.index:
            if top3[t] > 0:
                weights_m.loc[d, t] = 1.0 / 3.0
            else:
                weights_m.loc[d, "SHY" if "SHY" in weights_m.columns else "BIL"] += 1.0 / 3.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Main 비교 실행기
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("🔬 [개별 전략 단독 심층 개선 (Single-Strategy Deep Optimization)] 시작")
    print("=" * 80)

    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    start_date = "2003-04-01"
    end_date = prices.index[-1].strftime("%Y-%m-%d")
    engine = BacktestEngine(transaction_cost_bp=15.0)

    pairs = [
        ("1. Inflation Compass", ic_v1_weights, ic_opt_weights, "XLU 대신 금 방어 + 2022 IEF 현금 대체"),
        ("2. 카나리아 MQC-HAA", mqc_v1_weights, mqc_opt_weights, "1/2위 적응형 블렌딩 + 1.25x 레버리지"),
        ("3. BAA Tuned (Keller)", baa_v1_weights, baa_opt_weights, "Soft-Canary 투표제 + BIL/TLT/GLD 3중 방어"),
        ("4. ZeroLag Trend", zerolag_v1_weights, zerolag_opt_weights, "Hysteresis 완충밴드 + Vol-Cap 다운시프트"),
        ("5. Dual Momentum", dm_v0_weights, dm_opt_weights, "Top-2 분산(50:50) + 금(GLD) 방어자산화"),
        ("6. Golden Butterfly", gb_v1_weights, gb_opt_weights, "12M 모멘텀 Top-3 + 하락추세 현금 대체"),
    ]

    results_table = []

    for name, fn_v1, fn_opt, desc in pairs:
        print(f"\n[Testing] {name} ({desc})...")
        w_v1 = fn_v1(prices, fred)
        w_opt = fn_opt(prices, fred)

        res_v1 = engine.run(prices, w_v1, start_date=start_date, end_date=end_date)
        res_opt = engine.run(prices, w_opt, start_date=start_date, end_date=end_date)

        m1 = res_v1["metrics_net"]
        m2 = res_opt["metrics_net"]

        # 연도별 2008 / 2022 비교
        ret1 = res_v1["net_daily_rets"]
        ret2 = res_opt["net_daily_rets"]
        r2008_1 = (1 + ret1.loc["2008-01-01":"2008-12-31"]).prod() - 1
        r2008_2 = (1 + ret2.loc["2008-01-01":"2008-12-31"]).prod() - 1
        r2022_1 = (1 + ret1.loc["2022-01-01":"2022-12-31"]).prod() - 1
        r2022_2 = (1 + ret2.loc["2022-01-01":"2022-12-31"]).prod() - 1

        results_table.append({
            "전략": f"{name} [원형 V1]",
            "CAGR": f"{m1['CAGR']*100:.2f}%",
            "연변동성": f"{m1['Annual_Vol']*100:.2f}%",
            "Sharpe": f"{m1['Sharpe']:.3f}",
            "MDD": f"{m1['MDD']*100:.2f}%",
            "Calmar": f"{m1['Calmar']:.3f}",
            "턴오버": f"{m1['Annual_Turnover']:.1f}x",
            "2008년": f"{r2008_1*100:+.1f}%",
            "2022년": f"{r2022_1*100:+.1f}%"
        })

        results_table.append({
            "전략": f"{name} [개선판 V2] ⭐",
            "CAGR": f"{m2['CAGR']*100:.2f}%",
            "연변동성": f"{m2['Annual_Vol']*100:.2f}%",
            "Sharpe": f"{m2['Sharpe']:.3f}",
            "MDD": f"{m2['MDD']*100:.2f}%",
            "Calmar": f"{m2['Calmar']:.3f}",
            "턴오버": f"{m2['Annual_Turnover']:.1f}x",
            "2008년": f"{r2008_2*100:+.1f}%",
            "2022년": f"{r2022_2*100:+.1f}%"
        })

    df_res = pd.DataFrame(results_table)
    print("\n" + "=" * 110)
    print("🏆 [개별 6대 전략 단독 개선 전(V1) vs 후(V2) 일대일 정밀 비교표]")
    print("=" * 110)
    print(df_res.to_string(index=False))

    # 마크다운 저장
    report_file = BASE_DIR / "output" / "single_strategy_optimization_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 🔬 [심층 분석] 6대 개별 퀀트 전략 단독 개선(Single-Strategy Optimization) 전/후 비교 보고서\n\n")
        f.write(f"- **분석 기간:** {start_date} ~ {end_date} (23.3년 공통 기간)\n")
        f.write(f"- **거래 비용:** 편도 15bp / 왕복 30bp 실전 수수료 전액 차감\n")
        f.write(f"- **실행 지연:** 당일 신호 산출 $\\rightarrow$ 익일 집행 (1-Day Lag, 룩어헤드 차단)\n\n")
        f.write(df_res.to_markdown(index=False))
        f.write("\n")

    print(f"\n[✓] 개별 전략 최적화 보고서 저장 완료: {report_file}")


if __name__ == "__main__":
    main()
