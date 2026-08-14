"""매일 아침 08:45 KST 텔레그램 자동 발송 스케줄러 (Daily Scheduler).

사용법:
  1. 백그라운드 데몬 실행: python3 run_daily_scheduler.py &
  2. 또는 Linux Cron 등록:
     45 8 * * * /usr/bin/python3 /home/mikey/quant-master-framework/src/notification/telegram_bot.py --send >> /home/mikey/quant-master-framework/logs/cron.log 2>&1
"""

from __future__ import annotations
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import zoneinfo

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.notification.telegram_bot import build_telegram_message, send_telegram_alert


def run_scheduler_daemon():
    print("=" * 80)
    print("⏰ [Quant Master] 매일 아침 08:45 KST 텔레그램 스케줄러 데몬 시작")
    print("=" * 80)

    kst = zoneinfo.ZoneInfo("Asia/Seoul")

    while True:
        now_kst = datetime.now(kst)
        target_time = now_kst.replace(hour=8, minute=45, second=0, microsecond=0)

        if now_kst >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now_kst).total_seconds()
        print(f"[*] 다음 발송 예정 시각: {target_time.strftime('%Y-%m-%d %H:%M:%S')} KST (대기: {wait_seconds/3600:.2f}시간)")

        # 30초 단위로 슬립
        time.sleep(min(wait_seconds, 60))

        now_kst = datetime.now(kst)
        if now_kst.hour == 8 and now_kst.minute == 45:
            print(f"[!] 08:45 KST 도달. 오늘의 퀀트 포트폴리오 텔레그램 알림 발송 중...")
            try:
                msg = build_telegram_message()
                send_telegram_alert(msg)
            except Exception as e:
                print(f"[✗] 발송 중 에러 발생: {e}")
            # 중복 발송 방지를 위해 70초 슬립
            time.sleep(70)


if __name__ == "__main__":
    run_scheduler_daemon()
