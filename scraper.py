import os
import requests
import telegram
import asyncio
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- 환경 변수 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

BASE_URL = "https://consensus.hankyung.com"
# 페이지 번호를 바꿀 수 있는 URL 구조
LIST_URL = "https://consensus.hankyung.com/analysis/list?page={}"
SENT_REPORTS_FILE = "sent_reports.txt"

def get_sent_ids():
    if not os.path.exists(SENT_REPORTS_FILE):
        return set()
    try:
        with open(SENT_REPORTS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except:
        return set()

def save_sent_id(report_id):
    try:
        with open(SENT_REPORTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{report_id}\n")
    except Exception as e:
        print(f"파일 저장 오류: {e}")

async def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        print(f"텔레그램 전송 오류: {e}")

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    # 스크린샷 확인 결과: 날짜 형식이 YYYY-MM-DD (하이픈)임
    today_str = now_kst.strftime("%Y-%m-%d")
    
    if now_kst.hour >= 17:
        print("오후 5시 종료.")
        return

    sent_ids = get_sent_ids()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    new_reports_count = 0

    # 1페이지부터 3페이지까지 탐색
    for page in range(1, 4):
        print(f"--- {page}페이지 탐색 중 ---")
        try:
            response = requests.get(LIST_URL.format(page), headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select('div.table_style01 table tbody tr')
            
            if not rows: break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                report_date = cols[0].get_text(strip=True)
                category = cols[1].get_text(strip=True)
                
                # 오늘 날짜이고 분류에 '산업'이 포함된 경우
                if report_date == today_str and "산업" in category:
                    title_tag = cols[2].find('a')
                    if not title_tag: continue
                    
                    title = title_tag.get_text(strip=True)
                    link = title_tag['href']
                    match = re.search(r'report_idx=(\d+)', link)
                    report_id = match.group(1) if match else title
                    
                    if report_id not in sent_ids:
                        full_link = BASE_URL + link if link.startswith('/') else link
                        securities = cols[5].get_text(strip=True)
                        
                        msg = (f"<b>🔔 새로운 산업 리포트!</b>\n\n"
                               f"기관: <b>{securities}</b>\n"
                               f"제목: {title}\n"
                               f"<a href='{full_link}'>👉 원문 보기</a>")
                        
                        await send_telegram_message(msg)
                        save_sent_id(report_id)
                        sent_ids.add(report_id)
                        new_reports_count += 1
            
            # 서버 부하 방지를 위해 페이지 간 짧은 휴식
            time.sleep(1)
            
        except Exception as e:
            print(f"{page}페이지 오류: {e}")

    print(f"[{now_kst.strftime('%H:%M')}] 총 {new_reports_count}건 전송 완료.")

if __name__ == "__main__":
    asyncio.run(main())
