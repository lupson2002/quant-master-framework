"""매일 아침 08:45 텔레그램 포지션 알림 봇 (Daily Telegram Alert Bot).

미국 장 마감 후 오늘의 거시 시장 상태와
Master Pure Monthly (IC 55% + DM 30% + BAA 15%) 포트폴리오 목표 비중 및 매매 지침을 발송합니다.
"""

from __future__ import annotations
import sys
import os
import argparse
from pathlib import Path
import json
import urllib.request
import urllib.parse
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.production.signal_generator import get_latest_signals


def load_env():
    """ .env 파일에서 토큰 및 설정 로드 """
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()


def build_telegram_message(capital_usd: float = 100000.0) -> str:
    """오늘의 텔레그램 마크다운 브리핑 메시지 생성."""
    sig = get_latest_signals(capital_usd=capital_usd)
    dt = sig["latest_date"]
    cs = sig["component_status"]

    lines = []
    lines.append(f"🏛️ *[Quant Master] 20년 은퇴 연금 데일리 브리핑*")
    lines.append(f"📅 기준일자: `{dt}` | 💵 운용자산: `${capital_usd:,.0f} USD`")
    lines.append("━" * 28)

    # 1. 거시 시장 레짐 상태
    lines.append("\n📊 *[거시 시장 레짐 판정]*")
    ic_status = cs.get("Inflation_Compass", {})
    if "XLK" in ic_status:
        lines.append("• *경기/물가 레짐:* 디스인플레 성장 (XLK 기술주 주도 🟢)")
    elif "XLE" in ic_status:
        lines.append("• *경기/물가 레짐:* 리플레이션 (XLE 에너지 주도 🔴)")
    elif "XLU" in ic_status:
        lines.append("• *경기/물가 레짐:* 스태그플레이션 (XLU 유틸리티/금 방어 🟡)")
    else:
        lines.append("• *경기/물가 레짐:* 디플레이션 침체 (XLP/채권 안전 방어 🔵)")

    # 2. 마스터 전략 브리핑 (Master Pure Monthly 55/30/15)
    lines.append("\n👑 *[마스터 전략] Master Pure Monthly (55/30/15)*")
    lines.append("_(IC 55% + DM 30% + BAA 15% | CAGR 18.1% | MDD -21.8%)_")
    lines.append("• *운용:* 100% 매월 마지막 거래일 장 마감 후 월 1회 리밸런싱\n")

    df_master = sig["master_table"]
    for _, row in df_master.iterrows():
        t = row["Ticker"]
        w = row["Weight_Pct"]
        val = row["Target_Value_USD"]
        px = row["Current_Price"]
        shares = row["Shares_to_Hold"]
        lines.append(f"• *{t}* ({w}): `${val:,.0f}` (현재가 `${px:.2f}` ➔ *{shares}주*)")

    lines.append("\n" + "━" * 28)
    lines.append("💡 *실전 운용 권장:*")
    lines.append("• 매월 말일 종가 기준으로 해당 종목의 목표 비중대로 매수/리밸런싱하십시오.")
    lines.append("• 웹 대시보드: `http://localhost:8501`")

    return "\n".join(lines)


def send_telegram_alert(message: str) -> bool:
    """텔레그램 봇 API를 통해 메시지 전송."""
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id or token == "YOUR_BOT_TOKEN_HERE":
        print("[!] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 .env에 설정되지 않았습니다.")
        print("[*] 생성된 메시지 미리보기:\n")
        print(message)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            if res_json.get("ok"):
                print("[✓] 텔레그램 알림 메시지 발송 성공!")
                return True
            else:
                print(f"[✗] 텔레그램 발송 실패: {res_json.get('description', 'Unknown error')}")
                return False
    except Exception as e:
        err_msg = str(e).replace(token, "***") if token else str(e)
        print(f"[✗] 텔레그램 API 요청 에러: {err_msg}")
        return False


def main():
    parser = argparse.ArgumentParser(description="오늘의 퀀트 알림 텔레그램 봇")
    parser.add_argument("--send", action="store_true", help="실제 텔레그램으로 메시지 발송")
    parser.add_argument("--capital", type=float, default=100000.0, help="운용 자산 (USD)")
    args = parser.parse_args()

    msg = build_telegram_message(capital_usd=args.capital)

    if args.send:
        send_telegram_alert(msg)
    else:
        print("=" * 80)
        print("📡 [텔레그램 발송 메시지 미리보기] (--send 플래그 지정 시 실제 전송)")
        print("=" * 80)
        print(msg)
        print("=" * 80)


if __name__ == "__main__":
    main()
