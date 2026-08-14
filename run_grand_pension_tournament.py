"""20년 은퇴 연금 퀀트 자산배분 그랜드 토너먼트 (Grand Pension Tournament).

총 25개 이상의 정적/동적/매크로/모멘텀/추세추종 및 하이브리드 전략을
동일한 2003~2026(23.3년) 실전 환경(왕복 30bp 수수료, 1-Day Lag)에서
전수 백테스트하고, 20년 연금 관점의 다차원 순위를 도출합니다.
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
from src.indicators.momentum import (
    momentum_13612w_keller, momentum_13612w_baa, dual_momentum_score, momentum_121
)
from src.indicators.trend import compute_zlema
from src.indicators.macro import compute_inflation_compass_signals

# 기존 모듈 임포트
from run_individual_deep_optimization import (
    ic_v1_weights, ic_opt_weights, mqc_v1_weights, mqc_opt_weights,
    baa_v1_weights, baa_opt_weights, zerolag_v1_weights, zerolag_opt_weights,
    dm_v0_weights, gb_v1_weights, gb_opt_weights
)
from run_dualmom_extended_optimization import (
    v8_original_weights, v20t1_enhanced_weights, v12_t8_enhanced_weights,
    vaa_g1_original_weights, vaa_g1_enhanced_weights
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. 정적 올웨더 및 리스크 패리티 계열 (Static All-Weather / Risk Parity)
# ─────────────────────────────────────────────────────────────────────────────

def dalio_allweather_weights(prices_daily, fred_data):
    """Ray Dalio All-Weather: SPY 30%, TLT 40%, IEF 15%, GLD 7.5%, DBC 7.5%"""
    w = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)
    w["SPY"] = 0.30
    w["TLT"] = 0.40
    w["IEF"] = 0.15
    w["GLD"] = 0.075
    w["DBC" if "DBC" in w.columns else "PDBC"] = 0.075
    return w.fillna(0.0)


def permanent_portfolio_weights(prices_daily, fred_data):
    """Harry Browne Permanent Portfolio: SPY 25%, TLT 25%, GLD 25%, BIL 25%"""
    w = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)
    w["SPY"] = 0.25
    w["TLT"] = 0.25
    w["GLD"] = 0.25
    w["BIL" if "BIL" in w.columns else "SHY"] = 0.25
    return w.fillna(0.0)


def risk_parity_equal_vol_weights(prices_daily, fred_data):
    """Equal Risk Contribution (변동성 역가중): SPY, TLT, GLD, DBC의 60일 변동성 역수 배분"""
    assets = ["SPY", "TLT", "GLD", "DBC" if "DBC" in prices_daily.columns else "PDBC"]
    vol60 = prices_daily[assets].pct_change().rolling(60).std()
    inv_vol = 1.0 / vol60.replace(0, np.nan)
    w_raw = inv_vol.div(inv_vol.sum(axis=1), axis=0)

    # 월말 리밸런싱
    w_m = w_raw.resample("ME").last()
    weights = pd.DataFrame(0.0, index=prices_daily.index, columns=prices_daily.columns)
    for a in assets:
        weights[a] = w_m[a].reindex(prices_daily.index).ffill().fillna(0.25)
    return weights


# ─────────────────────────────────────────────────────────────────────────────
# 2. 켈러(Keller) 동적 자산배분 계열 (PAA, VAA-G12, DAA)
# ─────────────────────────────────────────────────────────────────────────────

def keller_paa_weights(prices_daily, fred_data):
    """Keller PAA (Protective Asset Allocation - G6): 6개 자산 중 모멘텀 음수 개수에 따라 보호자산 비례 배분"""
    monthly_px = prices_daily.resample("ME").last()
    assets = ["SPY", "QQQ", "IWM", "EFA", "EEM", "GLD"]
    score_13612w = momentum_13612w_keller(monthly_px[assets])
    safe_asset = "IEF" if "IEF" in monthly_px.columns else "SHY"

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        scores = score_13612w.loc[d].dropna()
        pos_assets = scores[scores > 0]
        n_pos = len(pos_assets)

        risky_weight = n_pos / len(assets)
        safe_weight = 1.0 - risky_weight

        if n_pos > 0:
            top_risky = pos_assets.sort_values(ascending=False).head(3)
            for t in top_risky.index:
                weights_m.loc[d, t] += risky_weight / len(top_risky)

        if safe_weight > 0:
            weights_m.loc[d, safe_asset] += safe_weight

    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def keller_vaa_g12_weights(prices_daily, fred_data):
    """Keller VAA-G12 (공격형): 4개 카나리아(SPY, EFA, EEM, AGG) 모두 양수면 12-1 1위 100%, 1개라도 음수면 LQD/IEF/SHY 1위"""
    monthly_px = prices_daily.resample("ME").last()
    score_13612w = momentum_13612w_keller(monthly_px)
    score_121 = momentum_121(monthly_px)

    canaries = ["SPY", "EFA", "EEM", "AGG"]
    offense = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD", "TLT", "LQD", "HYG"]
    defense = ["LQD", "IEF", "SHY"]

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        canary_scores = score_13612w.loc[d, [c for c in canaries if c in score_13612w.columns]].dropna()

        if len(canary_scores) == len(canaries) and (canary_scores > 0).all():
            off_scores = score_121.loc[d, [c for c in offense if c in score_121.columns]].dropna()
            top1 = off_scores.idxmax() if len(off_scores) > 0 else "SPY"
            weights_m.loc[d, top1] = 1.0
        else:
            def_scores = score_13612w.loc[d, [c for c in defense if c in score_13612w.columns]].dropna()
            top_def = def_scores.idxmax() if len(def_scores) > 0 else "SHY"
            weights_m.loc[d, top_def] = 1.0

    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def keller_daa_weights(prices_daily, fred_data):
    """Keller DAA (Dynamic Asset Allocation): 카나리아 2종(EEM, AGG)으로 위험 감지 후 Top-2 공격"""
    monthly_px = prices_daily.resample("ME").last()
    score_13612w = momentum_13612w_keller(monthly_px)
    canaries = ["EEM", "AGG"]
    offense = ["SPY", "IWM", "QQQ", "EFA", "VNQ", "GLD"]
    defense = ["SHY", "IEF", "LQD"]

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        c_scores = score_13612w.loc[d, [c for c in canaries if c in score_13612w.columns]].dropna()
        n_pos = (c_scores > 0).sum()

        off_scores = score_13612w.loc[d, [c for c in offense if c in score_13612w.columns]].dropna().sort_values(ascending=False)
        def_scores = score_13612w.loc[d, [c for c in defense if c in score_13612w.columns]].dropna().sort_values(ascending=False)

        top_def = def_scores.index[0] if len(def_scores) > 0 else "SHY"

        if n_pos == 2:
            # 100% 공격 (Top-2 자산에 50:50)
            top2 = off_scores.head(2)
            for t in top2.index:
                weights_m.loc[d, t] = 0.50
        elif n_pos == 1:
            # 50% 공격(Top-1) + 50% 방어
            top1 = off_scores.index[0] if len(off_scores) > 0 else "SPY"
            weights_m.loc[d, top1] = 0.50
            weights_m.loc[d, top_def] += 0.50
        else:
            # 100% 방어
            weights_m.loc[d, top_def] = 1.0

    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. 안토나치(Antonacci) & 파버(Faber) & ReSolve 듀얼모멘텀 계열
# ─────────────────────────────────────────────────────────────────────────────

def antonacci_gem_weights(prices_daily, fred_data):
    """Antonacci GEM (Global Equity Momentum): SPY vs EFA 12M 상대모멘텀, 12M > BIL 아니면 AGG 100%"""
    monthly_px = prices_daily.resample("ME").last()
    r12 = monthly_px[["SPY", "EFA", "BIL", "AGG"]].pct_change(12)

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        spy_r = r12.loc[d, "SPY"]
        efa_r = r12.loc[d, "EFA"]
        bil_r = r12.loc[d, "BIL"] if "BIL" in r12.columns else 0.02

        top_equity = "SPY" if spy_r >= efa_r else "EFA"
        top_return = max(spy_r, efa_r)

        if top_return > bil_r:
            weights_m.loc[d, top_equity] = 1.0
        else:
            weights_m.loc[d, "AGG" if "AGG" in weights_m.columns else "IEF"] = 1.0

    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def faber_gtaa5_weights(prices_daily, fred_data):
    """Meb Faber GTAA-5: 5대 자산(SPY, EFA, IEF, DBC, VNQ) 중 200일선 위에 있는 자산만 각 20% 보유, 아니면 BIL"""
    assets = ["SPY", "EFA", "IEF", "DBC" if "DBC" in prices_daily.columns else "PDBC", "VNQ"]
    valid_assets = [a for a in assets if a in prices_daily.columns]
    sma200 = prices_daily[valid_assets].rolling(200).mean()
    monthly_dates = prices_daily.resample("ME").last().index
    weights_m = pd.DataFrame(0.0, index=monthly_dates, columns=prices_daily.columns)
    cash_ticker = "BIL" if "BIL" in prices_daily.columns else "SHY"

    for d in monthly_dates:
        valid_idx = prices_daily.index[prices_daily.index <= d]
        if len(valid_idx) == 0:
            continue
        d_calc = valid_idx[-1]

        for a in valid_assets:
            if not np.isnan(sma200.loc[d_calc, a]) and prices_daily.loc[d_calc, a] > sma200.loc[d_calc, a]:
                weights_m.loc[d, a] = 1.0 / len(valid_assets)
            else:
                weights_m.loc[d, cash_ticker] += 1.0 / len(valid_assets)

    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


def resolve_aaa_weights(prices_daily, fred_data):
    """ReSolve Adaptive Asset Allocation (AAA): 10개 자산 중 13612W 상위 5개 자산 선택 후 60일 변동성 역가중 배분"""
    monthly_px = prices_daily.resample("ME").last()
    assets = ["SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "DBC", "GLD", "TLT", "IEF"]
    valid_assets = [c for c in assets if c in monthly_px.columns]
    score_13612w = momentum_13612w_keller(monthly_px[valid_assets])
    vol60 = prices_daily[valid_assets].pct_change().rolling(60).std()

    weights_m = pd.DataFrame(0.0, index=monthly_px.index, columns=prices_daily.columns)
    for i in range(12, len(monthly_px)):
        d = monthly_px.index[i]
        scores = score_13612w.loc[d].dropna().sort_values(ascending=False)
        top5 = scores.head(5).index.tolist()

        valid_vols = vol60.index[vol60.index <= d]
        if len(valid_vols) == 0:
            continue
        d_vol = valid_vols[-1]

        vols = vol60.loc[d_vol, top5].dropna()
        if len(vols) == 5 and (vols > 0).all():
            inv_vols = 1.0 / vols
            w_norm = inv_vols / inv_vols.sum()
            for t in top5:
                weights_m.loc[d, t] = w_norm[t]
        else:
            for t in top5:
                weights_m.loc[d, t] = 1.0 / len(top5)

    return weights_m.reindex(prices_daily.index).ffill().fillna(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. 그랜드 토너먼트 마스터 실행 및 다차원 랭킹 분석
# ─────────────────────────────────────────────────────────────────────────────

def rolling_stats(daily_rets: pd.Series, window_years: int = 3) -> dict[str, float]:
    w_days = int(window_years * 252)
    if len(daily_rets) < w_days:
        return {}
    rolling_cum = (1.0 + daily_rets).rolling(w_days).apply(np.prod, raw=True)
    rolling_cagr = (rolling_cum ** (1.0 / window_years)) - 1.0
    rolling_cagr = rolling_cagr.dropna()

    return {
        "Rolling_Avg": rolling_cagr.mean(),
        "Rolling_Min": rolling_cagr.min(),
        "Rolling_Max": rolling_cagr.max(),
        "Negative_Ratio": (rolling_cagr < 0).mean()
    }


def main():
    print("=" * 110)
    print("🏛️  [20년 은퇴 연금 퀀트 자산배분 그랜드 토너먼트 (Grand Pension Tournament)]")
    print("=" * 110)

    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()

    start_date = "2003-04-01"
    end_date = prices.index[-1].strftime("%Y-%m-%d")
    engine = BacktestEngine(transaction_cost_bp=15.0)  # 편도 15bp / 왕복 30bp

    # 전체 25개 검증 대상 전략 풀 구성
    all_strategies = {
        # [벤치마크]
        "Benchmark_SPY": lambda p, f: pd.DataFrame({"SPY": 1.0}, index=p.index).reindex(columns=p.columns).fillna(0.0),
        "Benchmark_60_40": lambda p, f: pd.DataFrame({"SPY": 0.6, "IEF": 0.4}, index=p.index).reindex(columns=p.columns).fillna(0.0),

        # [1. 정적 올웨더 & 영구 포트폴리오]
        "1. Ray Dalio All-Weather": dalio_allweather_weights,
        "2. Tyler Golden Butterfly (V1 정적)": gb_v1_weights,
        "3. Golden Butterfly (V2 동적 Top-3)": gb_opt_weights,
        "4. Harry Browne Permanent Port": permanent_portfolio_weights,
        "5. Risk Parity (Equal Vol)": risk_parity_equal_vol_weights,

        # [2. 켈러(Keller) 동적 모멘텀 패밀리 (1.0x)]
        "6. Keller PAA (Protective G6)": keller_paa_weights,
        "9. Keller DAA (Dynamic Allocation)": keller_daa_weights,
        "10. Keller BAA Tuned (V1 2x)": baa_v1_weights,
        "11. Keller BAA-G4 (V2 3중방어)": baa_opt_weights,

        # [3. 안토나치 & 파버 & ReSolve 듀얼모멘텀]
        "12. Antonacci GEM (Global Momentum)": antonacci_gem_weights,
        "13. Dual Momentum (V0 원형 100%)": dm_v0_weights,
        "14. Dual Momentum (V8 3-Asset)": v8_original_weights,
        "15. Dual Momentum (V20T1 SAHM침체)": v20t1_enhanced_weights,
        "16. Dual Momentum (T8/V12 Top-2)": v12_t8_enhanced_weights,
        "17. Meb Faber GTAA-5": faber_gtaa5_weights,
        "18. ReSolve AAA (Adaptive Asset)": resolve_aaa_weights,

        # [4. 매크로 4분면 & 카나리아 MQC & 추세추종]
        "19. Inflation Compass (V1 원형)": ic_v1_weights,
        "20. Inflation Compass (V2 추세필터)": ic_opt_weights,
        "21. 카나리아 MQC-HAA (V1 2x)": mqc_v1_weights,
        "22. 카나리아 MQC-HAA (V2 1.5x)": mqc_opt_weights,
        "23. ZeroLag Trend (V1 QLD 2x)": zerolag_v1_weights,
        "24. ZeroLag Trend (V2 완충밴드)": zerolag_opt_weights,

        # [5. 융합 하이브리드 포트폴리오]
        "25. Hybrid 2: All-Weather Dynamic": lambda p, f: ic_v1_weights(p, f)*0.35 + baa_opt_weights(p, f)*0.30 + dm_v0_weights(p, f)*0.20 + gb_v1_weights(p, f)*0.15,
        "26. 🚀 Option A (40/30/20/10)": lambda p, f: ic_v1_weights(p, f)*0.40 + dm_v0_weights(p, f)*0.30 + zerolag_opt_weights(p, f)*0.20 + baa_opt_weights(p, f)*0.10,
        "27. ☕ Option B (40/30/15/15)": lambda p, f: ic_v1_weights(p, f)*0.40 + dm_v0_weights(p, f)*0.30 + zerolag_opt_weights(p, f)*0.15 + baa_opt_weights(p, f)*0.15,
    }

    print(f"[*] 총 {len(all_strategies)}개 전략 백테스트 실행 중 (기간: {start_date} ~ {end_date}, 총 5,880 거래일)...")

    results = {}
    table_rows = []

    for name, fn in all_strategies.items():
        try:
            w = fn(prices, fred)
            res = engine.run(prices, w, start_date=start_date, end_date=end_date)
            results[name] = res
            m = res["metrics_net"]
            daily_rets = res["net_daily_rets"]

            r2008 = (1 + daily_rets.loc["2008-01-01":"2008-12-31"]).prod() - 1
            r2020 = (1 + daily_rets.loc["2020-02-01":"2020-04-30"]).prod() - 1
            r2022 = (1 + daily_rets.loc["2022-01-01":"2022-12-31"]).prod() - 1

            r3 = rolling_stats(daily_rets, window_years=3)
            r5 = rolling_stats(daily_rets, window_years=5)

            table_rows.append({
                "전략명": name,
                "CAGR": m["CAGR"],
                "연변동성": m["Annual_Vol"],
                "Sharpe": m["Sharpe"],
                "Sortino": m["Sortino"],
                "MDD": m["MDD"],
                "Calmar": m["Calmar"],
                "턴오버": m["Annual_Turnover"],
                "2008년": r2008,
                "2020년": r2020,
                "2022년": r2022,
                "3년최악": r3.get("Rolling_Min", 0.0),
                "3년적자확률": r3.get("Negative_Ratio", 0.0),
                "5년최악": r5.get("Rolling_Min", 0.0),
                "5년적자확률": r5.get("Negative_Ratio", 0.0),
            })
            print(f"  [✓] {name:<36} | CAGR: {m['CAGR']*100:6.2f}% | Sharpe: {m['Sharpe']:5.3f} | MDD: {m['MDD']*100:6.2f}% | Calmar: {m['Calmar']:5.3f}")
        except Exception as e:
            print(f"  [✗] {name} 실패: {e}")

    df_res = pd.DataFrame(table_rows)

    # ─────────────────────────────────────────────────────────────────────────
    # 20년 연금 종합 점수 (Pension Composite Score) 산출
    # Score = 0.35 * Sharpe + 0.35 * Calmar + 0.15 * (1 - 3년적자확률) + 0.15 * (2022년 방어점수)
    # ─────────────────────────────────────────────────────────────────────────
    df_res["Score"] = (
        df_res["Sharpe"] * 0.35 +
        df_res["Calmar"] * 0.35 +
        (1.0 - df_res["3년적자확률"]) * 0.15 +
        np.clip((df_res["2022년"] + 0.20) / 0.40, 0, 1) * 0.15
    )

    df_sorted = df_res.sort_values(by="Score", ascending=False).reset_index(drop=True)

    # 포맷팅 출력용 DataFrame
    df_display = pd.DataFrame()
    df_display["순위"] = [f"{i+1}위" for i in range(len(df_sorted))]
    df_display["전략명"] = df_sorted["전략명"]
    df_display["CAGR"] = df_sorted["CAGR"].apply(lambda x: f"{x*100:.2f}%")
    df_display["변동성"] = df_sorted["연변동성"].apply(lambda x: f"{x*100:.2f}%")
    df_display["Sharpe"] = df_sorted["Sharpe"].apply(lambda x: f"{x:.3f}")
    df_display["MDD"] = df_sorted["MDD"].apply(lambda x: f"{x*100:.2f}%")
    df_display["Calmar"] = df_sorted["Calmar"].apply(lambda x: f"{x:.3f}")
    df_display["2008년"] = df_sorted["2008년"].apply(lambda x: f"{x*100:+.1f}%")
    df_display["2022년"] = df_sorted["2022년"].apply(lambda x: f"{x*100:+.1f}%")
    df_display["3년최악"] = df_sorted["3년최악"].apply(lambda x: f"{x*100:+.1f}%")
    df_display["3년적자확률"] = df_sorted["3년적자확률"].apply(lambda x: f"{x*100:.1f}%")
    df_display["연금종합점수"] = df_sorted["Score"].apply(lambda x: f"{x:.3f}")

    print("\n" + "=" * 130)
    print("🏆 [20년 은퇴 연금 퀀트 자산배분 그랜드 토너먼트 종합 랭킹]")
    print("=" * 130)
    print(df_display.to_string(index=False))

    # 마크다운 저장
    report_file = BASE_DIR / "output" / "grand_pension_tournament_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 🏛️ [Grand Tournament Report] 20년 은퇴 연금 퀀트 자산배분 종합 대항전 보고서\n\n")
        f.write(f"- **분석 기간:** {start_date} ~ {end_date} (23.3년 풀윈도우, 총 5,880 거래일)\n")
        f.write(f"- **실전 거래비용:** 편도 15bp / 왕복 30bp 전액 차감\n")
        f.write(f"- **실행 지연:** 당일 신호 산출 후 익일 집행(1-Day Shift, 룩어헤드 차단)\n")
        f.write(f"- **검증 전략:** 글로벌 6대 유니버스 총 {len(all_strategies)}개 전략\n\n")
        f.write("## 1. 20년 연금 종합 랭킹 전수 비교표\n\n")
        f.write(df_display.to_markdown(index=False))
        f.write("\n")

    print(f"\n[✓] 그랜드 토너먼트 최종 보고서 저장 완료: {report_file}")


if __name__ == "__main__":
    main()
