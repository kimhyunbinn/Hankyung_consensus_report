  import os
import requests
import telegram
import asyncio
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- 환경 변수 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

URL = "https://consensus.hankyung.com/analysis/list"
BASE_URL = "https://consensus.hankyung.com"
SENT_REPORTS_FILE = "sent_reports.txt"

def get_sent_ids():
    """이미 보낸 리포트 ID 목록을 파일에서 읽어옵니다."""
    if not os.path.exists(SENT_REPORTS_FILE):
        return set()
    try:
        with open(SENT_REPORTS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except Exception:
        return set()

def save_sent_id(report_id):
    """새로 보낸 리포트 ID를 파일에 저장합니다."""
    try:
        with open(SENT_REPORTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{report_id}\n")
    except Exception as e:
        print(f"파일 저장 중 에러: {e}")

async def send_telegram_message(message):
    """텔레그램 메시지를 전송합니다."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: 텔레그램 설정이 누락되었습니다.")
        return
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")

async def main():
    # 1. 한국 시간 설정 (UTC+9)
    now_kst = datetime.utcnow() + timedelta(hours=9)
    today_str = now_kst.strftime("%Y.%m.%d")
    
    # 오후 5시(17시) 이후 실행 방지
    if now_kst.hour >= 17:
        print(f"[{now_kst.strftime('%H:%M')}] 현재 시간이 오후 5시 이후이므로 작업을 수행하지 않습니다.")
        return

    sent_ids = get_sent_ids()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }

    try:
        # 2. 웹 데이터 가져오기
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 테이블 행 선택
        rows = soup.select('div.table_style01 table tbody tr')
        
        if not rows:
            print("리포트 목록(rows)을 찾을 수 없습니다.")
            return

        new_reports_count = 0

        # 3. 리포트 분석 및 전송
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5:
                continue
            
            report_date = cols[0].text.strip()
            category = cols[1].text.strip()
            
            # 오늘 날짜이고 '산업' 카테고리인 경우만
            if report_date == today_str and category == "산업":
                title_tag = cols[2].find('a')
                if not title_tag:
                    continue
                
                title = title_tag.text.strip()
                link = title_tag['href']
                
                # 중복 전송 방지를 위한 고유 ID 추출
                match = re.search(r'report_idx=(\d+)', link)
                report_id = match.group(1) if match else title
                
                if report_id not in sent_ids:
                    full_link = BASE_URL + link if link.startswith('/') else link
                    securities = cols[5].text.strip()
                    
                    msg = (f"<b>🔔 새로운 산업 리포트!</b>\n\n"
                           f"기관: <b>{securities}</b>\n"
                           f"제목: {title}\n"
                           f"<a href='{full_link}'>👉 원문 보기</a>")
                    
                    await send_telegram_message(msg)
                    save_sent_id(report_id)
                    sent_ids.add(report_id)
                    new_reports_count += 1
                    print(f"전송 완료: {title}")

        print(f"[{now_kst.strftime('%H:%M')}] 탐색 결과: 새 리포트 {new_reports_count}건 발견.")

    except Exception as e:
        print(f"실행 중 오류 발생: {e}")

# --- 프로그램 시작점 ---
if __name__ == "__main__":
    asyncio.run(main())
