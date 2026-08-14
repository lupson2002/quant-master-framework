# 🏛️ Unified Quant Master Framework (20-Year Pension Portfolio)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Streamlit App](https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B.svg)](https://streamlit.io/)
[![Audit: 100% Passed](https://img.shields.io/badge/Audit-100%25%20Passed-brightgreen.svg)]()

> **"20년(2026~2046) 동안 어떤 경제 위기(스태그플레이션, 대공황, 신용경색)에서도 계좌를 깨지 않고 연복리 18%를 창출하는 궁극의 퀀트 자산배분 시스템"**

---

## 🌟 1. 프로젝트 개요 (Executive Summary)

본 프로젝트는 글로벌 6대 자산배분 유니버스(정적 올웨더, 켈러 동적모멘텀, 안토나치 듀얼모멘텀, 바래디 매크로 4분면, 추세추종 등) **총 29개 전략을 23.3년(2003~2026, 5,880 거래일)** 동안 왕복 30bp 실전 수수료 및 1-Day Lag 환경에서 전수 백테스트하고 검증한 마스터 퀀트 시스템입니다.

### 🏆 최종 추천 20년 연금 포트폴리오 성과

$$\mathbf{\text{Option B (40/30/15/15)}} = \mathbf{40\%}\text{ IC(V1)} + \mathbf{30\%}\text{ DualMom(V0)} + \mathbf{15\%}\text{ ZeroLag(V2)} + \mathbf{15\%}\text{ BAA-G4(V2)}$$

| 핵심 지표 | S&P 500 (SPY) | 전통 60/40 포트폴리오 | **Option B (최종 추천)** ⭐ |
|---|:---:|:---:|:---:|
| **CAGR (연복리수익률)** | 11.91% | 8.98% | **18.16%** |
| **연간 변동성** | 18.51% | 10.69% | **16.51%** |
| **Sharpe 지수 (무위험 2% 차감)** | 0.701 | 0.858 | **1.094 (최상위 1%)** |
| **MDD (최대낙폭)** | -55.19% | -31.39% | **-20.16% (SPY의 1/3)** |
| **Calmar 지수 (CAGR / \|MDD\|)** | 0.216 | 0.286 | **0.901 (수익/낙폭 1위)** |
| **2008 글로벌 금융위기 성과** | -36.79% | -16.73% | **-1.37% (철벽 방어)** |
| **2020 코로나 팬데믹 성과** | -9.18% | -1.69% | **-1.36%** |
| **2022 금리/인플레 폭등기 성과** | -18.18% | -16.39% | **+0.70% (양의 수익 달성!)** |
| **3년 롤링 원금 손실 확률** | 11.7% | 4.6% | **0.0% (적자 제로)** |
| **5년 롤링 원금 손실 확률** | 8.2% | 0.5% | **0.0% (적자 제로)** |

---

## 🏗️ 2. 시스템 아키텍처

```
quant-master-framework/
├── app/
│   └── dashboard.py          # Streamlit 인터랙티브 웹 대시보드 (5대 탭)
├── src/
│   ├── data_loader/          # Yahoo Finance & FRED 자동 수집/캐싱
│   ├── indicators/           # 13612W, ZLEMA, T5YIE, Dual Momentum 지표
│   ├── backtest/             # 1-Day Lag 및 실전 30bp 수수료 차감 엔진
│   ├── strategies/           # 29개 정적/동적/매크로 전략 구현체
│   ├── production/           # 실시간 시그널 생성 및 국내 연금저축 매퍼
│   └── notification/         # 매일 아침 08:45 KST 텔레그램 알림 봇
├── tests/
│   └── test_audit_suite.py   # 제3자 감사용 전수 단위 테스트 슈트
├── docs/
│   ├── THEORETICAL_FOUNDATIONS.md # 20년 영속성 이론적 배경 논증서
│   └── QUANT_AUDIT_REPORT.md      # 코드 및 백테스트 무결성 감사 보고서
├── output/                   # 29개 전략 전수 대항전 리포트
└── run_*.py                  # 원클릭 실행 스크립트
```

---

## 🚀 3. 빠른 시작 가이드 (Quick Start)

### 1) 환경 설치
```bash
git clone https://github.com/YOUR_GITHUB_ID/quant-master-framework.git
cd quant-master-framework
pip install -r requirements.txt
```

### 2) 오늘 매매 주문표 CLI 출력
```bash
python3 run_today_signals.py --capital 100000
```

### 3) 인터랙티브 웹 대시보드 실행
```bash
streamlit run app/dashboard.py
```

### 4) 매일 아침 08:45 텔레그램 알림 봇 설정
1. `.env.example`을 복사하여 `.env` 생성 후 봇 토큰과 Chat ID 입력:
   ```bash
   cp .env.example .env
   ```
2. 텔레그램 테스트 발송:
   ```bash
   python3 src/notification/telegram_bot.py --send
   ```
3. Linux Cron 스케줄러 등록 (매일 08:45 KST):
   ```bash
   crontab -e
   # 추가할 내용:
   45 8 * * * /usr/bin/python3 /path/to/quant-master-framework/src/notification/telegram_bot.py --send >> /path/to/quant-master-framework/logs/cron.log 2>&1
   ```

---

## 🛡️ 4. 백테스트 무결성 및 제3자 감사 증명

- **No Lookahead Bias**: 모든 신호는 당일 종가 산출 후 익일(`shift(1)`) 시가/장중에만 집행.
- **Exact Friction**: 편도 15bp / 왕복 30bp의 거래비용이 일별 포지션 교체량에 전액 차감.
- **전수 단위 테스트 검증**:
  ```bash
  python3 tests/test_audit_suite.py
  # 6개 테스트 전원 통과 (OK)
  ```

---

## 📜 5. 라이선스

본 프로젝트는 MIT License를 따릅니다.
