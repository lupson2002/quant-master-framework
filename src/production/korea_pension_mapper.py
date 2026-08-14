"""국내 연금저축 / IRP 전용 ETF 1:1 매핑 모듈 (Korea Pension ETF Mapper).

미국 직투 티커(US ETF)를 국내 상장 해외 ETF(절세 계좌용)로 자동 매핑합니다.
"""

from __future__ import annotations

# 미국 ETF -> 국내 상장 절세/연금계좌 ETF 매핑 사전
KOREA_PENSION_ETF_MAP = {
    # 1. 미국 빅테크 / 기술주
    "XLK": {
        "kr_code": "381180",
        "kr_name": "TIGER 미국테크TOP10 INDXX",
        "alt_code": "381170",
        "alt_name": "KODEX 미국FANG플러스(H)",
        "asset_type": "미국 빅테크/기술주"
    },
    "QQQ": {
        "kr_code": "133690",
        "kr_name": "TIGER 미국나스닥100",
        "alt_code": "379810",
        "alt_name": "ACE 미국나스닥100",
        "asset_type": "미국 나스닥100"
    },
    # 2. 미국 대표 대형주
    "SPY": {
        "kr_code": "360750",
        "kr_name": "TIGER 미국S&P500",
        "alt_code": "379800",
        "alt_name": "ACE 미국S&P500",
        "asset_type": "미국 S&P500"
    },
    "IWM": {
        "kr_code": "280920",
        "kr_name": "TIGER 미국러셀2000",
        "alt_code": "-",
        "alt_name": "-",
        "asset_type": "미국 중소형주"
    },
    # 3. 글로벌 / 선진국 / 신흥국 주식
    "EFA": {
        "kr_code": "195930",
        "kr_name": "TIGER 유로스탁스50(합성 H)",
        "alt_code": "245340",
        "alt_name": "TIGER 일본니케이225",
        "asset_type": "선진국 주식"
    },
    "EEM": {
        "kr_code": "195980",
        "kr_name": "TIGER 인도니프티50",
        "alt_code": "373530",
        "alt_name": "TIGER 차이나전기차SOLACTIVE",
        "asset_type": "신흥국 주식"
    },
    # 4. 대체자산 (금 / 원자재 / 에너지)
    "GLD": {
        "kr_code": "411060",
        "kr_name": "ACE KRX금현물",
        "alt_code": "132030",
        "alt_name": "KODEX 골드선물(H)",
        "asset_type": "금(Gold) 현물"
    },
    "XLE": {
        "kr_code": "219480",
        "kr_name": "TIGER 미국S&P500에너지(합성)",
        "alt_code": "275980",
        "alt_name": "KODEX 미국원유에너지",
        "asset_type": "미국 에너지 섹터"
    },
    "DBC": {
        "kr_code": "130680",
        "kr_name": "TIGER 원유선물Enhanced(H)",
        "alt_code": "219480",
        "alt_name": "TIGER 미국에너지",
        "asset_type": "원자재/에너지"
    },
    "PDBC": {
        "kr_code": "130680",
        "kr_name": "TIGER 원유선물Enhanced(H)",
        "alt_code": "219480",
        "alt_name": "TIGER 미국에너지",
        "asset_type": "원자재/에너지"
    },
    # 5. 미국 국채 및 초단기채 (현금성)
    "TLT": {
        "kr_code": "453850",
        "kr_name": "ACE 미국30년국채액티브(H)",
        "alt_code": "476550",
        "alt_name": "TIGER 미국30년국채프리미엄액티브",
        "asset_type": "미국 30년 초장기국채"
    },
    "IEF": {
        "kr_code": "305080",
        "kr_name": "TIGER 미국채10년선물",
        "alt_code": "329750",
        "alt_name": "KODEX 미국채10년액티브",
        "asset_type": "미국 10년 중기국채"
    },
    "SHY": {
        "kr_code": "438320",
        "kr_name": "TIGER 미국달러SOFR금리액티브(합성)",
        "alt_code": "130730",
        "alt_name": "KODEX 단기채권",
        "asset_type": "미국 단기국채"
    },
    "BIL": {
        "kr_code": "438320",
        "kr_name": "TIGER 미국달러SOFR금리액티브(합성)",
        "alt_code": "130730",
        "alt_name": "KODEX 단기채권(원화)",
        "asset_type": "초단기 파킹/현금성"
    },
    "TIP": {
        "kr_code": "438320",
        "kr_name": "TIGER 미국달러SOFR금리액티브",
        "alt_code": "305080",
        "alt_name": "TIGER 미국채10년",
        "asset_type": "물가연동채/단기채"
    },
    # 6. 섹터
    "XLU": {
        "kr_code": "139260",
        "kr_name": "TIGER 200 중공업/유틸리티",
        "alt_code": "130730",
        "alt_name": "KODEX 단기채권",
        "asset_type": "유틸리티/방어주"
    },
    "XLP": {
        "kr_code": "227560",
        "kr_name": "TIGER 코스닥150 필수소비재",
        "alt_code": "360750",
        "alt_name": "TIGER 미국S&P500",
        "asset_type": "필수소비재"
    }
}


def map_us_to_kr_etf(us_ticker: str) -> dict:
    """미국 티커에 해당하는 국내 연금저축/IRP 매핑 정보 반환."""
    return KOREA_PENSION_ETF_MAP.get(us_ticker, {
        "kr_code": "-",
        "kr_name": f"국내 매핑 미정 ({us_ticker})",
        "alt_code": "-",
        "alt_name": "-",
        "asset_type": "기타"
    })
