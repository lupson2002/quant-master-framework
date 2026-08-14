# 🏛️ Unified Quant Master Framework — 시스템 아키텍처 및 기술 명세서

본 문서는 `quant-master-framework`의 전체 구조, 데이터 파이프라인, 백테스트 엔진 메커니즘, 지표 수학적 수식, 그리고 제3자 검증 절차를 완벽하게 문서화한 공식 기술 명세서입니다.

---

## 1. 디렉토리 구조 및 모듈 역할

```
quant-master-framework/
├── src/
│   ├── data_loader/          # 데이터 수집, 정제, 캐싱 파이프라인
│   │   └── master_loader.py  # Yahoo Finance ETF 및 FRED 거시경제 시계열 로더
│   ├── indicators/           # 계량 퀀트 지표 모듈
│   │   ├── macro.py          # Inflation Compass 4분면, T5YIE 추세, 확인 지표 기울기
│   │   ├── momentum.py       # Keller 13612W, BAA 13612W, Dual Momentum, 12-1 지표
│   │   └── trend.py          # ZLEMA(105), Chandelier Exit(ATR), Percentile Channels
│   ├── backtest/             # 고성능 벡터화 백테스트 엔진
│   │   ├── engine.py         # 1-Day Lag 집행, 턴오버 계산, 실전 수수료 차감 엔진
│   │   └── metrics.py        # CAGR, Sharpe, Sortino, MDD, Calmar, Turnover 연율화 계산기
│   ├── strategies/           # 개별 전략 표준 인터페이스 (BaseStrategy 상속)
│   │   ├── s1_inflation_compass.py  # Varadi 인플레이션 나침반 (V1 / V2)
│   │   ├── s2_canary_mqc.py         # 카나리아 MQC-HAA (V1 / V2)
│   │   ├── s3_golden_butterfly.py   # Golden Butterfly (V1 / V2)
│   │   ├── s4_dual_momentum.py      # Dual Momentum (V0, V12, V20T1)
│   │   ├── s5_baa_tuned.py          # BAA Tuned (V1 2x / BAA-G4 V2)
│   │   ├── s6_zerolag_trend.py      # ZeroLag Trend (V1 / V2)
│   │   ├── s7_vaa_g1.py             # Keller VAA-G1
│   │   └── s8_pct_channels.py       # Percentile Channels TAA
│   └── hybrid/               # 차세대 앙상블 및 메타 하이브리드 엔진
│       ├── h1_macro_trend_meta.py       # 4단계 계층형 메타 엔진
│       └── h2_allweather_dynamic_alpha.py # 최적 리스크버짓팅 앙상블
├── tests/
│   └── test_audit_suite.py   # 제3자 감사용 전수 단위 테스트 슈트
├── docs/
│   ├── SYSTEM_ARCHITECTURE.md # 본 시스템 기술 명세서
│   └── QUANT_AUDIT_REPORT.md  # 퀀트 논리 및 코드 무결성 감사 보고서
├── output/                   # 모든 백테스트 검증 리포트 산출물
│   ├── step1_verification_report.md
│   ├── step2_hybrid_report.md
│   ├── single_strategy_optimization_report.md
│   ├── dualmom_extended_optimization_report.md
│   ├── global_ensemble_optimization_report.md
│   └── MASTER_FINAL_REPORT.md # 최종 마스터 종합 보고서
└── run_*.py                  # 재현 실행용 엔트리포인트 스크립트들
```

---

## 2. 데이터 파이프라인 및 무결성 관리

1. **데이터 소스**:
   - **자산 가격**: Yahoo Finance API (수정주가 Adjusted Close 기준, 배당 및 액면분할 100% 반영).
   - **거시 지표**: FRED (Federal Reserve Bank of St. Louis) API.
     - `T5YIE`: 5-Year Breakeven Inflation Rate (인플레이션 기대치).
     - `T10Y2Y`: 10-Year minus 2-Year Treasury Yield Spread (장단기 금리차).
     - `SAHMREALTIME`: Sahm Rule Recession Indicator (실시간 실업률 기반 침체 지표).
     - `DGS3MO` / `DFF`: 3개월 국채금리 / 연방기금 실효금리.
2. **캐싱 및 오프라인 결정론**:
   - 수집된 모든 일별 시계열은 `data/cache/*.parquet` 파일로 로컬 저장되어, 네트워크 상태와 무관하게 동일한 백테스트 결과를 100% 결정론적으로 재현합니다.

---

## 3. 백테스트 엔진 메커니즘 (No Lookahead & Exact Cost)

### ① 룩어헤드 편향 원천 차단 (`shift(1)` 집행)
- $t$일 장 마감 후 종가와 거시 지표로 계산된 포트폴리오 목표 비중 $w_t$는 **익일($t+1$일) 아침 시가/장중에 반영**됩니다.
- 엔진 내부 공식:
  $$\text{Effective Weight}_{t} = w_{t-1}$$
  $$\text{Gross Return}_t = \sum_{i} \left( w_{t-1, i} \cdot \frac{P_{t, i} - P_{t-1, i}}{P_{t-1, i}} \right)$$

### ② 정밀한 일별 턴오버 및 실전 거래 수수료 차감
- 포지션 변경 시 발생하는 편도 15bp (왕복 30bp, 0.0030) 슬리피지/수수료를 매일 차감:
  $$\text{Turnover}_t = \sum_{i} |w_{t, i} - w_{t-1, i}|$$
  $$\text{Cost}_t = \text{Turnover}_t \times \text{One-way Fee (0.0015)}$$
  $$\text{Net Return}_t = \text{Gross Return}_t - \text{Cost}_t$$

---

## 4. 핵심 지표 수학적 명세서

### ① Keller 13612W 가중 모멘텀
$$Score_{13612W} = 12 \cdot r_{1M} + 4 \cdot r_{3M} + 2 \cdot r_{6M} + 1 \cdot r_{12M}$$
- 단기 1개월에 12배, 3개월에 4배의 가중치를 부여하여 급격한 시장 추세 전환 및 위기 초동을 신속히 감지.

### ② Zero-Lag Exponential Moving Average (ZLEMA)
$$Lag = \frac{Period - 1}{2}$$
$$ZData_t = 2 \cdot Price_t - Price_{t - Lag}$$
$$ZLEMA_t = EMA(ZData_t, Period)$$
- 일반 EMA 대비 위상 지연(Phase Lag)을 제거하여 급락 초기에 손절선을 빠르게 상향 조정.

### ③ Inflation Compass (Varadi 4-Quadrant Mapping)
- **성장 축 (Growth Axis)**: $SPY_t > SMA_{200}(SPY_t) \rightarrow \text{Growth UP, else DOWN}$
- **인플레이션 축 (Inflation Axis)**:
  - 주 조건: $T5YIE_t > 2.0\%$ AND $T5YIE_t > T5YIE_{t-60}$
  - 보조 확인(Confirming Indicator): 원자재(DBC), 에너지(XLE), 유틸리티(XLU), 팁스(TIP)의 60일 선형회귀 기울기 합산 $> 0$
  - 둘 중 하나라도 만족 시 $\rightarrow \text{Inflation UP, else DOWN}$
- **4분면 자산 배분**:
  - Q1 (Growth UP, Inf UP): **XLE (에너지 100%)**
  - Q2 (Growth UP, Inf DOWN): **XLK/QQQ (기술주 100%)**
  - Q3 (Growth DOWN, Inf UP): **XLU/GLD (유틸리티/금 100%)**
  - Q4 (Growth DOWN, Inf DOWN): **XLP(소비재 50%) + IEF(국채 50%)**

---

## 5. 최종 완성형 포트폴리오 공식: `Option B (40/30/15/15)`

$$\mathbf{Portfolio_t} = 0.40 \cdot \mathbf{W}_{IC}(t) + 0.30 \cdot \mathbf{W}_{DualMom}(t) + 0.15 \cdot \mathbf{W}_{ZeroLag}(t) + 0.15 \cdot \mathbf{W}_{BAA}(t)$$

- **CAGR:** **18.16%**
- **MDD:** **-20.16%**
- **Sharpe:** **1.094**
- **Calmar:** **0.901**
- **2008년 성과:** **-1.37%**
- **2022년 성과:** **+0.70% (양의 수익)**
- **3년/5년 롤링 원금 손실 확률:** **0.0%**
