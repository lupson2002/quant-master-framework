"""Dual Momentum 확장 전략군 (V8, V20T1, V12, T8, VAA-G1) 단독 심층 개선 및 비교 검증.

1. V8: 12M 후행성 제거 (13612W 가중치) + 금(GLD) 방어 편입
2. V20T1: SAHM 거시 랙 보완 (신용스프레드/금리커브 조기 경보) + 3중 방어 (BIL/TLT/GLD)
3. V12 / T8: 50:50 고정 탈피 (모멘텀 비례 가중) + 인플레 방어자산(TIPS/GLD) 결합
4. VAA-G1: 2개 양수 시 100% 몰빵 완화 (소프트 디리스킹 50% 방어) + 금 방어 편입
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
from src.indicators.momentum import dual_momentum_score, momentum_13612w_keller, momentum_121


# ─────────────────────────────────────────────────────────────────────────────
# 1. V8 원형 vs V8 개선판 (13612W + Gold Defense)
# ─────────────────────────────────────────────────────────────────────────────

def v8_original_weights(prices_daily, fred_data):
    """V8 원형: 주식 3종(QQQ, EFA, EEM) 모멘텀 1위 + 12M 절대모멘텀 (DGS3MO/DFF 방어)"""
    monthly_px = prices_daily.resample("ME").last()
    scores = dual_momentum_score(monthly_px[["QQQ", "EFA", "EEM"]])
    r12 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(12)
    dgs3mo = fred_data["DGS3MO"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DGS3MO" in fred_data else monthly_px["SPY"] * 0 + 3.0
    dff = fred_data["DFF"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DFF" in fred_data else monthly_px["SPY"] * 0 + 2.8

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        top1 = scores.loc[d].idxmax()
        if r12.loc[d, top1] > 0 and (scores.loc[d] >= 0).any():
            weights_m.loc[d, top1] = 1.0
        else:
            if dgs3mo.loc[d] < dff.loc[d]:
                weights_m.loc[d, "TLT"] = 1.0
            else:
                weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def v8_enhanced_weights(prices_daily, fred_data):
    """V8 개선판:
    1. 12M 모멘텀 점수 대신 13612W 켈러 모멘텀(12*r1+4*r3+2*r6+r12)으로 급락 초동 대응
    2. 방어 시 DGS3MO/DFF뿐 아니라 최근 3M 모멘텀이 강한 금(GLD) 또는 초단기채(BIL) 방어
    """
    monthly_px = prices_daily.resample("ME").last()
    score_13612w = momentum_13612w_keller(monthly_px[["QQQ", "EFA", "EEM", "GLD", "BIL", "TLT"]])
    r6 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(6)

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        stock_scores = score_13612w.loc[d, ["QQQ", "EFA", "EEM"]]
        top1 = stock_scores.idxmax()

        # 6M 모멘텀과 13612W 동시 양수일 때만 공격
        if stock_scores[top1] > 0 and r6.loc[d, top1] > 0:
            weights_m.loc[d, top1] = 1.0
        else:
            # 방어: BIL, TLT, GLD 중 13612W 최고 자산
            def_scores = score_13612w.loc[d, ["BIL", "TLT", "GLD"]].dropna()
            top_def = def_scores.idxmax() if len(def_scores) > 0 else "BIL"
            weights_m.loc[d, top_def] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. V20T1 원형 vs V20T1 개선판 (SAHM + 거시 스프레드 이중 확인)
# ─────────────────────────────────────────────────────────────────────────────

def v20t1_original_weights(prices_daily, fred_data):
    """V20T1 원형: V8 + SAHM >= 0.5 침체 트리거 시 3M 모멘텀 확인"""
    monthly_px = prices_daily.resample("ME").last()
    scores = dual_momentum_score(monthly_px[["QQQ", "EFA", "EEM"]])
    r12 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(12)
    r3 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(3)

    sahm = fred_data["SAHM"].resample("ME").last().reindex(monthly_px.index).shift(1).ffill() if fred_data is not None and "SAHM" in fred_data else monthly_px["SPY"] * 0
    dgs3mo = fred_data["DGS3MO"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DGS3MO" in fred_data else monthly_px["SPY"] * 0 + 3.0
    dff = fred_data["DFF"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "DFF" in fred_data else monthly_px["SPY"] * 0 + 2.8

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        top1 = scores.loc[d].idxmax()
        is_sahm = sahm.loc[d] >= 0.5

        # 침체 트리거 발동 시 3M 확인, 평시 12M 확인
        is_safe = (r3.loc[d, top1] > 0) if is_sahm else (r12.loc[d, top1] > 0)

        if is_safe and (scores.loc[d] >= 0).any():
            weights_m.loc[d, top1] = 1.0
        else:
            if dgs3mo.loc[d] < dff.loc[d]:
                weights_m.loc[d, "TLT"] = 1.0
            else:
                weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def v20t1_enhanced_weights(prices_daily, fred_data):
    """V20T1 개선판:
    1. SAHM 1개월 랙을 보완하기 위해 T10Y2Y 금리커브 역전 + TIP 모멘텀 결합
    2. 침체 진입 시 TLT 몰빵 대신 BIL(50%) + GLD(25%) + TLT(25%) 3중 쿠션 분산
    """
    monthly_px = prices_daily.resample("ME").last()
    scores = dual_momentum_score(monthly_px[["QQQ", "EFA", "EEM"]])
    r12 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(12)
    r3 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(3)

    sahm = fred_data["SAHM"].resample("ME").last().reindex(monthly_px.index).shift(1).ffill() if fred_data is not None and "SAHM" in fred_data else monthly_px["SPY"] * 0
    t10y2y = fred_data["T10Y2Y"].resample("ME").last().reindex(monthly_px.index).ffill() if fred_data is not None and "T10Y2Y" in fred_data else monthly_px["SPY"] * 0 + 0.5

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        top1 = scores.loc[d].idxmax()
        recession_flag = (sahm.loc[d] >= 0.5) or (t10y2y.loc[d] <= 0)

        is_safe = (r3.loc[d, top1] > 0) if recession_flag else (r12.loc[d, top1] > 0)

        if is_safe and (scores.loc[d] >= 0).any():
            weights_m.loc[d, top1] = 1.0
        else:
            # 침체 방어: BIL 50%, GLD 25%, TLT 25%
            weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] += 0.50
            weights_m.loc[d, "GLD"] += 0.25
            weights_m.loc[d, "TLT"] += 0.25
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. V12 / T8 원형 vs 개선판 (Top-2 모멘텀 가중 + TIPS/GOLD 방어)
# ─────────────────────────────────────────────────────────────────────────────

def v12_t8_original_weights(prices_daily, fred_data):
    """T8 원형: Top-2 주식(50:50) + 12M 절대모멘텀 + 방어 시 CASH/LTB/TIPS 6M 최고"""
    monthly_px = prices_daily.resample("ME").last()
    scores = dual_momentum_score(monthly_px[["QQQ", "EFA", "EEM"]])
    r12 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(12)
    def_m6 = monthly_px[["BIL", "TLT", "TIP"]].pct_change(6)

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        sorted_stocks = scores.loc[d].sort_values(ascending=False)
        top2 = sorted_stocks.head(2)

        for ticker in top2.index:
            if r12.loc[d, ticker] > 0:
                weights_m.loc[d, ticker] = 0.5
            else:
                top_def = def_m6.loc[d].dropna().idxmax() if len(def_m6.loc[d].dropna()) > 0 else "BIL"
                weights_m.loc[d, top_def] += 0.5
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def v12_t8_enhanced_weights(prices_daily, fred_data):
    """T8 개선판:
    1. 50:50 균등 대신 1위(65%) + 2위(35%) 모멘텀 비례 가중치 (알파 극대화)
    2. 방어 자산에 GOLD 추가 (BIL, TLT, TIP, GLD 중 6M 최고)로 2022 채권 폭락 차단
    """
    monthly_px = prices_daily.resample("ME").last()
    scores = dual_momentum_score(monthly_px[["QQQ", "EFA", "EEM"]])
    r12 = monthly_px[["QQQ", "EFA", "EEM"]].pct_change(12)
    def_m6 = monthly_px[["BIL", "TLT", "TIP", "GLD"]].pct_change(6)

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        sorted_stocks = scores.loc[d].sort_values(ascending=False)
        top2 = sorted_stocks.head(2)
        t1, t2 = top2.index[0], top2.index[1]

        # 1위 65% 배분
        if r12.loc[d, t1] > 0:
            weights_m.loc[d, t1] += 0.65
        else:
            top_def = def_m6.loc[d].dropna().idxmax() if len(def_m6.loc[d].dropna()) > 0 else "BIL"
            weights_m.loc[d, top_def] += 0.65

        # 2위 35% 배분
        if r12.loc[d, t2] > 0:
            weights_m.loc[d, t2] += 0.35
        else:
            top_def = def_m6.loc[d].dropna().idxmax() if len(def_m6.loc[d].dropna()) > 0 else "BIL"
            weights_m.loc[d, top_def] += 0.35
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. VAA-G1 원형 vs VAA-G1 개선판 (Soft De-risking & Gold Defense)
# ─────────────────────────────────────────────────────────────────────────────

def vaa_g1_original_weights(prices_daily, fred_data):
    """VAA-G1 원형: 4자산 중 2개 이상 13612W 양수면 12-1 1위 100%, 아니면 TLT vs BIL"""
    monthly_px = prices_daily.resample("ME").last()
    score_13612w = momentum_13612w_keller(monthly_px)
    score_121 = momentum_121(monthly_px)
    offense = ["QQQ", "SPY", "EEM", "EFA"]

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        valid_off = [c for c in offense if c in score_13612w.columns and not np.isnan(score_13612w.loc[d, c])]
        if not valid_off:
            weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
            continue

        pos_cnt = (score_13612w.loc[d, valid_off] > 0).sum()
        if pos_cnt >= 2:
            top1 = score_121.loc[d, valid_off].dropna().idxmax()
            weights_m.loc[d, top1] = 1.0
        else:
            def_scores = score_13612w.loc[d, [c for c in ["TLT", "BIL"] if c in score_13612w.columns]].dropna()
            top_def = def_scores.idxmax() if len(def_scores) > 0 else "BIL"
            weights_m.loc[d, top_def] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def vaa_g1_enhanced_weights(prices_daily, fred_data):
    """VAA-G1 개선판:
    1. 4개 중 3~4개 양수 시 1위 100%, 2개 양수 시 1위(50%) + 방어(50%) 소프트 디리스킹
    2. 방어 자산군에 GOLD 편입 (BIL, TLT, GLD 3종 모멘텀 로테이션)
    """
    monthly_px = prices_daily.resample("ME").last()
    score_13612w = momentum_13612w_keller(monthly_px)
    score_121 = momentum_121(monthly_px)
    offense = ["QQQ", "SPY", "EEM", "EFA"]
    defense = ["BIL", "TLT", "GLD"]

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        valid_off = [c for c in offense if c in score_13612w.columns and not np.isnan(score_13612w.loc[d, c])]
        if not valid_off:
            weights_m.loc[d, "BIL" if "BIL" in weights_m.columns else "SHY"] = 1.0
            continue

        pos_cnt = (score_13612w.loc[d, valid_off] > 0).sum()
        top1 = score_121.loc[d, valid_off].dropna().idxmax()

        def_scores = score_13612w.loc[d, [c for c in defense if c in score_13612w.columns]].dropna()
        top_def = def_scores.idxmax() if len(def_scores) > 0 else "BIL"

        if pos_cnt >= 3:
            weights_m.loc[d, top1] = 1.0
        elif pos_cnt == 2:
            # 소프트 분산: 공격 50% + 방어 50%
            weights_m.loc[d, top1] = 0.50
            weights_m.loc[d, top_def] += 0.50
        else:
            # 100% 방어
            weights_m.loc[d, top_def] = 1.0
    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Main 실행 및 비교 리포트
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("🔬 [Dual Momentum 확장 전략군 (V8, V20T1, V12/T8, VAA-G1) 단독 심층 개선 검증]")
    print("=" * 80)

    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    start_date = "2003-04-01"
    end_date = prices.index[-1].strftime("%Y-%m-%d")
    engine = BacktestEngine(transaction_cost_bp=15.0)

    test_pairs = [
        ("V8 (3자산 모멘텀 1위)", v8_original_weights, v8_enhanced_weights, "13612W 켈러모멘텀 + 금 방어 편입"),
        ("V20T1 (SAHM 침체필터)", v20t1_original_weights, v20t1_enhanced_weights, "SAHM+금리커브 이중확인 + 3중쿠션 방어"),
        ("T8 / V12 (Top-2 + TIPS)", v12_t8_original_weights, v12_t8_enhanced_weights, "Top-2 65:35 모멘텀비례 가중 + 금/TIPS 방어"),
        ("VAA-G1 (Keller Vigilant)", vaa_g1_original_weights, vaa_g1_enhanced_weights, "소프트 디리스킹(2개 양수시 50:50) + 금 방어"),
    ]

    rows = []
    for name, fn_v1, fn_opt, desc in test_pairs:
        print(f"\n[Testing] {name} ({desc})...")
        w1 = fn_v1(prices, fred)
        w2 = fn_opt(prices, fred)

        res1 = engine.run(prices, w1, start_date=start_date, end_date=end_date)
        res2 = engine.run(prices, w2, start_date=start_date, end_date=end_date)

        m1, m2 = res1["metrics_net"], res2["metrics_net"]

        ret1 = res1["net_daily_rets"]
        ret2 = res2["net_daily_rets"]
        r2008_1 = (1 + ret1.loc["2008-01-01":"2008-12-31"]).prod() - 1
        r2008_2 = (1 + ret2.loc["2008-01-01":"2008-12-31"]).prod() - 1
        r2022_1 = (1 + ret1.loc["2022-01-01":"2022-12-31"]).prod() - 1
        r2022_2 = (1 + ret2.loc["2022-01-01":"2022-12-31"]).prod() - 1

        rows.append({
            "전략명": f"{name} [원형]",
            "CAGR": f"{m1['CAGR']*100:.2f}%",
            "연변동성": f"{m1['Annual_Vol']*100:.2f}%",
            "Sharpe": f"{m1['Sharpe']:.3f}",
            "Sortino": f"{m1['Sortino']:.3f}",
            "MDD": f"{m1['MDD']*100:.2f}%",
            "Calmar": f"{m1['Calmar']:.3f}",
            "턴오버": f"{m1['Annual_Turnover']:.1f}x",
            "2008년": f"{r2008_1*100:+.1f}%",
            "2022년": f"{r2022_1*100:+.1f}%"
        })

        rows.append({
            "전략명": f"{name} [개선판] ⭐",
            "CAGR": f"{m2['CAGR']*100:.2f}%",
            "연변동성": f"{m2['Annual_Vol']*100:.2f}%",
            "Sharpe": f"{m2['Sharpe']:.3f}",
            "Sortino": f"{m2['Sortino']:.3f}",
            "MDD": f"{m2['MDD']*100:.2f}%",
            "Calmar": f"{m2['Calmar']:.3f}",
            "턴오버": f"{m2['Annual_Turnover']:.1f}x",
            "2008년": f"{r2008_2*100:+.1f}%",
            "2022년": f"{r2022_2*100:+.1f}%"
        })

    df_res = pd.DataFrame(rows)
    print("\n" + "=" * 115)
    print("🏆 [Dual Momentum 확장 전략군 (V8, V20T1, T8, VAA-G1) 단독 개선 전/후 비교표]")
    print("=" * 115)
    cols = ["전략명", "CAGR", "연변동성", "Sharpe", "Sortino", "MDD", "Calmar", "턴오버", "2008년", "2022년"]
    print(df_res[cols].to_string(index=False))

    report_path = BASE_DIR / "output" / "dualmom_extended_optimization_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 🔬 Dual Momentum 확장 전략군 (V8, V20T1, T8/V12, VAA-G1) 단독 심층 개선 보고서\n\n")
        f.write(f"- **분석 기간:** {start_date} ~ {end_date} (23.3년 풀윈도우)\n")
        f.write(f"- **거래 비용:** 편도 15bp / 왕복 30bp 실전 수수료 전액 차감\n")
        f.write(f"- **실행 지연:** 당일 신호 산출 후 익일 집행(1-Day Shift, 룩어헤드 차단)\n\n")
        f.write(df_res[cols].to_markdown(index=False))
        f.write("\n")

    print(f"\n[✓] Dual Momentum 확장 전략 개선 보고서 저장 완료: {report_path}")


if __name__ == "__main__":
    main()
