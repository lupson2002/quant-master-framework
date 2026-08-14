"""통합 퀀트 마스터 인터랙티브 Streamlit 웹 대시보드 (Unified Quant Master Dashboard).

실행: streamlit run app/dashboard.py
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.data_loader.master_loader import load_yahoo_prices, load_fred_series
from src.backtest.engine import BacktestEngine
from src.production.signal_generator import get_latest_signals
from run_individual_deep_optimization import (
    ic_v1_weights, baa_opt_weights, zerolag_opt_weights, dm_v0_weights
)


st.set_page_config(
    page_title="Unified Quant Master Framework",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────────────────────
# 1. 사이드바 설정
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("🏛️ Quant Master Control")
st.sidebar.markdown("---")

strat_type = st.sidebar.radio(
    "운용 전략 선택",
    (
        "👑 마스터 전략: Master Pure Monthly (55/30/15)",
        "🚀 Option B: Dynamic Alpha (40/30/15/15)"
    )
)

capital = st.sidebar.number_input("운용 자산 규모 (USD)", min_value=1000.0, max_value=10000000.0, value=100000.0, step=10000.0)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ 전략 구성 가중치")
if "마스터" in strat_type:
    st.sidebar.success(
        "• **Inflation Compass (V1):** 55%\n"
        "• **Dual Momentum (V0):** 30%\n"
        "• **BAA-G4 (V2):** 15%\n\n"
        "*(100% 완전 월간 전용 | CAGR 18.1% | MDD -21.8%)*"
    )
else:
    st.sidebar.info(
        "• **Inflation Compass (V1):** 40%\n"
        "• **Dual Momentum (V0):** 30%\n"
        "• **ZeroLag Trend (1x):** 15% (일간 기동대)\n"
        "• **BAA-G4 (V2):** 15%\n\n"
        "*(월 85% + 일간 15% | CAGR 17.0% | MDD -19.7%)*"
    )

st.sidebar.markdown("---")
st.sidebar.markdown("### 📱 텔레그램 알림")
st.sidebar.caption("매일 아침 08:45 KST 자동 발송")
st.sidebar.code("python3 src/notification/telegram_bot.py --send", language="bash")


# ─────────────────────────────────────────────────────────────────────────────
# 2. 데이터 로드 및 백테스트 실행 (캐싱)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_all_backtest_data():
    prices = load_yahoo_prices(start="2002-01-01")
    fred = load_fred_series()
    engine = BacktestEngine(transaction_cost_bp=15.0)

    w_ic = ic_v1_weights(prices, fred)
    w_dm = dm_v0_weights(prices, fred)
    w_baa = baa_opt_weights(prices, fred)
    w_zl = zerolag_opt_weights(prices, fred)

    w_spy = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    w_spy["SPY"] = 1.0

    w_6040 = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    w_6040["SPY"] = 0.60
    w_6040["IEF"] = 0.40

    # 마스터 전략 (55/30/15) & Option B (40/30/15/15)
    w_master = w_ic * 0.55 + w_dm * 0.30 + w_baa * 0.15
    w_optb = w_ic * 0.40 + w_dm * 0.30 + w_zl * 0.15 + w_baa * 0.15

    start_date = "2003-04-01"
    end_date = prices.index[-1].strftime("%Y-%m-%d")

    res_spy = engine.run(prices, w_spy, start_date=start_date, end_date=end_date)
    res_6040 = engine.run(prices, w_6040, start_date=start_date, end_date=end_date)
    res_master = engine.run(prices, w_master, start_date=start_date, end_date=end_date)
    res_optb = engine.run(prices, w_optb, start_date=start_date, end_date=end_date)

    return {
        "prices": prices,
        "SPY": res_spy,
        "6040": res_6040,
        "Master": res_master,
        "OptionB": res_optb,
        "start_date": start_date,
        "end_date": end_date
    }


data = load_all_backtest_data()
current_res = data["Master"] if "마스터" in strat_type else data["OptionB"]
m = current_res["metrics_net"]
signals = get_latest_signals(capital_usd=capital)


# ─────────────────────────────────────────────────────────────────────────────
# 3. 메인 대시보드 헤더 & 핵심 지표 메트릭
# ─────────────────────────────────────────────────────────────────────────────
st.title("🏛️ Unified Quant Master Framework")
st.markdown(f"**20년 은퇴 연금 자산배분 연구 시스템** | 기간: `{data['start_date']} ~ {data['end_date']}` (23.3년) | 거래비용: 왕복 30bp 차감 | 집행: 1-Day Lag")

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("CAGR (연수익률)", f"{m['CAGR']*100:.2f}%", f"+{(m['CAGR']-data['SPY']['metrics_net']['CAGR'])*100:.2f}%p vs SPY")
col2.metric("Sharpe 지수", f"{m['Sharpe']:.3f}", f"Sortino: {m['Sortino']:.3f}")
col3.metric("MDD (최대낙폭)", f"{m['MDD']*100:.2f}%", f"SPY: {data['SPY']['metrics_net']['MDD']*100:.1f}%")
col4.metric("Calmar 지수", f"{m['Calmar']:.3f}", "수익/낙폭비율")
col5.metric("연간 변동성", f"{m['Annual_Vol']*100:.2f}%", f"SPY: {data['SPY']['metrics_net']['Annual_Vol']*100:.1f}%")
col6.metric("연간 턴오버", f"{m['Annual_Turnover']:.1f}x", "저비용 운용")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# 4. 5대 핵심 탭 인터페이스
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📡 오늘의 실전 매매 주문표",
    "🏆 32개 전략 그랜드 토너먼트 랭킹",
    "📈 성과 & 리스크 심층 분석",
    "🛡️ 4대 위기 스트레스 테스트",
    "📚 이론적 배경 & 감사 보고서"
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: 오늘의 실전 매매 주문표
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.subheader(f"📡 [오늘의 실전 매매 주문표] (기준 종가 일자: `{signals['latest_date']}`)")

    order_df = signals["master_table"] if "마스터" in strat_type else signals["optb_table"]

    c_left, c_right = st.columns([2, 1])
    with c_left:
        st.dataframe(
            order_df[["Ticker", "Weight_Pct", "Current_Price", "Target_Value_USD", "Shares_to_Hold"]].rename(
                columns={
                    "Ticker": "미국 티커",
                    "Weight_Pct": "목표 비중",
                    "Current_Price": "현재가 ($)",
                    "Target_Value_USD": "목표 금액 ($)",
                    "Shares_to_Hold": "매수 주수"
                }
            ),
            use_container_width=True,
            hide_index=True
        )

    with c_right:
        fig_pie = px.pie(
            order_df,
            values="Target_Weight",
            names="Ticker",
            title="자산 배분 비중",
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("### 🔍 주요 엔진 현재 상태")
    cs = signals["component_status"]
    ec1, ec2, ec3, ec4 = st.columns(4)
    ec1.success(f"**Inflation Compass (55%)**\n\n{cs['Inflation_Compass']}")
    ec2.info(f"**Dual Momentum (30%)**\n\n{cs['Dual_Momentum']}")
    ec3.info(f"**BAA-G4 (15%)**\n\n{cs['BAA_G4']}")
    ec4.warning(f"**ZeroLag Trend (보조)**\n\n{cs['ZeroLag_Trend']}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: 32개 전략 그랜드 토너먼트 랭킹
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("🏆 [20년 은퇴 연금 퀀트 자산배분 그랜드 토너먼트 종합 랭킹 (100% 무레버리지)]")
    st.caption("23.3년간의 실전 30bp 수수료 차감 후 CAGR, Sharpe, MDD, Calmar, 위기방어력을 종합 평가한 순위표입니다.")

    report_path = BASE_DIR / "output" / "grand_pension_tournament_report.md"
    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        table_lines = [l for l in lines if l.startswith("|")]
        if table_lines:
            st.markdown("".join(table_lines))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: 성과 & 리스크 심층 분석
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("📈 23.3년 누적 자산 성장 곡선 (Log Scale)")

    equity_strat = current_res["net_equity"]
    equity_spy = data["SPY"]["net_equity"]
    equity_6040 = data["6040"]["net_equity"]

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(x=equity_strat.index, y=equity_strat.values, name="My Strategy", line=dict(color="#1f77b4", width=2.8)))
    fig_cum.add_trace(go.Scatter(x=equity_spy.index, y=equity_spy.values, name="S&P 500 (SPY)", line=dict(color="#7f7f7f", width=1.2, dash="dot")))
    fig_cum.add_trace(go.Scatter(x=equity_6040.index, y=equity_6040.values, name="60/40 Portfolio", line=dict(color="#2ca02c", width=1.2, dash="dash")))

    fig_cum.update_layout(
        yaxis_type="log",
        yaxis_title="자산 가치 ($1 시작, Log)",
        xaxis_title="연도",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    # 수중도 (MDD) 차트
    st.subheader("🌊 낙폭 수중도 (Underwater Drawdown)")
    dd_strat = (equity_strat - equity_strat.cummax()) / equity_strat.cummax()
    dd_spy = (equity_spy - equity_spy.cummax()) / equity_spy.cummax()

    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=dd_strat.index, y=dd_strat.values * 100, name="My Strategy DD", fill="tozeroy", line=dict(color="#d62728", width=1.2)))
    fig_dd.add_trace(go.Scatter(x=dd_spy.index, y=dd_spy.values * 100, name="SPY DD", line=dict(color="#7f7f7f", width=1, dash="dot")))

    fig_dd.update_layout(
        yaxis_title="낙폭 (%)",
        xaxis_title="연도",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_dd, use_container_width=True)

    # 연도별/월별 수익률 히트맵
    st.subheader("🗓️ 연도별 / 월별 수익률 히트맵 (Monthly Heatmap)")
    daily_rets = current_res["net_daily_rets"]
    monthly_rets = daily_rets.resample("ME").apply(lambda r: (1 + r).prod() - 1) * 100
    
    df_m = pd.DataFrame({
        "Year": monthly_rets.index.year,
        "Month": monthly_rets.index.month,
        "Return": monthly_rets.values
    })
    heatmap_df = df_m.pivot(index="Year", columns="Month", values="Return").round(2)
    heatmap_df.columns = [f"{m}월" for m in heatmap_df.columns]

    fig_hm = px.imshow(
        heatmap_df,
        labels=dict(x="월", y="연도", color="수익률(%)"),
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0.0,
        text_auto=".1f",
        aspect="auto"
    )
    st.plotly_chart(fig_hm, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: 4대 위기 스트레스 테스트
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.subheader("🛡️ 역사적 4대 경제위기 스트레스 테스트 성과")

    ret_s = current_res["net_daily_rets"]
    ret_spy = data["SPY"]["net_daily_rets"]
    ret_6040 = data["6040"]["net_daily_rets"]

    crises = {
        "2008 글로벌 금융위기": ("2008-01-01", "2008-12-31"),
        "2011 미국 신용강등": ("2011-05-01", "2011-10-31"),
        "2020 코로나 팬데믹": ("2020-02-01", "2020-04-30"),
        "2022 금리/인플레 폭등기": ("2022-01-01", "2022-12-31"),
        "2026 최신 연도 (YTD)": ("2026-01-01", signals["latest_date"]),
    }

    c_rows = []
    for c_name, (s_d, e_d) in crises.items():
        r_strat = (1 + ret_s.loc[s_d:e_d]).prod() - 1
        r_sp = (1 + ret_spy.loc[s_d:e_d]).prod() - 1
        r_60 = (1 + ret_6040.loc[s_d:e_d]).prod() - 1
        c_rows.append({
            "위기 국면": c_name,
            "전략 성과": f"{r_strat*100:+.2f}%",
            "S&P 500 (SPY)": f"{r_sp*100:+.2f}%",
            "60/40 포트폴리오": f"{r_60*100:+.2f}%",
            "초과 방어력": f"{(r_strat - r_sp)*100:+.2f}%p"
        })

    st.table(pd.DataFrame(c_rows))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: 이론적 배경 & 감사 보고서
# ─────────────────────────────────────────────────────────────────────────────
with tab5:
    st.subheader("📚 [학술 명세서 및 퀀트 코드 감사 보고서]")
    doc_choice = st.radio("보고서 선택", ("🏛️ 전략 이론적 배경 및 논증서", "🛡️ 코드 및 백테스트 감사 보고서"))

    if "이론적" in doc_choice:
        doc_path = BASE_DIR / "docs" / "THEORETICAL_FOUNDATIONS.md"
    else:
        doc_path = BASE_DIR / "docs" / "QUANT_AUDIT_REPORT.md"

    if doc_path.exists():
        with open(doc_path, "r", encoding="utf-8") as f:
            st.markdown(f.read())
