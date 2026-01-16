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
# 산업 섹션 직접 타겟팅
TARGET_URL = "https://consensus.hankyung.com/analysis/list?skinType=industry&now_page={}"
SENT_REPORTS_FILE = "sent_reports.txt"

def get_sent_ids():
    if not os.path.exists(SENT_REPORTS_FILE): return set()
    try:
        with open(SENT_REPORTS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except: return set()

def save_sent_id(report_id):
    try:
        with open(SENT_REPORTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{report_id}\n")
    except: pass

async def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        print(f"전송 오류: {e}")

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    today_str = now_kst.strftime("%Y-%m-%d")
    
    if now_kst.hour >= 18: 
        print("업무 시간 종료")
        return

    sent_ids = get_sent_ids()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    new_count = 0
    # 1~3페이지 탐색
    for page in range(1, 4):
        try:
            url = TARGET_URL.format(page)
            res = requests.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 모든 행을 가져옴
            rows = soup.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                # 데이터 추출
                row_text = row.get_text("|", strip=True)
                # 조건: 오늘 날짜가 포함되어 있는가? (산업 섹션이므로 날짜만 확인해도 됨)
                if today_str in row_text:
                    a_tag = row.find('a', href=re.compile(r'report_idx='))
                    if not a_tag: continue
                    
                    title = a_tag.get_text(strip=True)
                    link = a_tag['href']
                    
                    # 고유 ID (중복 방지용)
                    report_id = re.search(r'report_idx=(\d+)', link).group(1)
                    
                    if report_id not in sent_ids:
                        full_link = BASE_URL + link if link.startswith('/') else link
                        # 제공처는 보통 5번째 td
                        provider = cols[4].get_text(strip=True)
                        
                        msg = (f"<b>🏗️ 새로운 산업 리포트!</b>\n\n"
                               f"출처: <b>{provider}</b>\n"
                               f"제목: {title}\n"
                               f"<a href='{full_link}'>👉 리포트 보기(PDF)</a>")
                        
                        await send_telegram_message(msg)
                        save_sent_id(report_id)
                        sent_ids.add(report_id)
                        new_count += 1
                        print(f"전송 성공: {title}")
            
            time.sleep(1)
        except Exception as e:
            print(f"{page}페이지 오류: {e}")

    print(f"탐색 완료: 오늘 자 {new_count}건 처리")

if __name__ == "__main__":
    asyncio.run(main())
