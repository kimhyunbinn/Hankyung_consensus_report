import os
import requests
import telegram
import asyncio
import re
import time
import fitz
import google.generativeai as genai
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from io import BytesIO

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

BASE_URL = "https://consensus.hankyung.com"
TARGET_URL = "https://consensus.hankyung.com/analysis/list?skinType=industry&now_page={}"
SENT_REPORTS_FILE = "sent_reports.txt"

def get_sent_ids():
    if not os.path.exists(SENT_REPORTS_FILE): return set()
    try:
        with open(SENT_REPORTS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except: return set()

def save_sent_id(report_id):
    with open(SENT_REPORTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{report_id}\n")

def get_summary(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers, timeout=25)
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            text = "".join([page.get_text() for page in doc[:3]])
        if not text.strip(): return "내용 요약 불가 (이미지 위주)"
        prompt = f"금융 전문가로서 다음 리포트를 핵심만 3줄 요약해줘:\n{text[:7000]}"
        res = model.generate_content(prompt)
        return res.text.strip()
    except:
        return "요약 생성 실패 (원문 확인)"

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    # 한경컨센서스에서 사용하는 다양한 날짜 형식을 리스트로 만듭니다.
    date_formats = [
        now_kst.strftime("%Y-%m-%d"), # 2026-02-11
        now_kst.strftime("%y-%m-%d"), # 26-02-11
        now_kst.strftime("%Y.%m.%d")  # 2026.02.11
    ]
    print(f"체크할 날짜 형식들: {date_formats}")
    
    sent_ids = get_sent_ids()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    new_count = 0
    for page in range(1, 3):
        url = TARGET_URL.format(page)
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            
            row_text = row.get_text(strip=True)
            # 설정한 날짜 형식 중 하나라도 행 안에 포함되어 있는지 확인
            if any(date_str in row_text for date_str in date_formats):
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                link = a_tag['href']
                report_id = re.search(r'report_idx=(\d+)', link).group(1)
                
                if report_id not in sent_ids:
                    title = a_tag.get_text(strip=True)
                    provider = cols[4].get_text(strip=True)
                    full_link = BASE_URL + link if link.startswith('/') else link
                    
                    print(f"새 리포트 발견: {title} (ID: {report_id})")
                    summary = get_summary(full_link)
                    
                    msg = (f"<b>🏗️ 새로운 산업 리포트!</b>\n\n"
                           f"출처: <b>{provider}</b>\n"
                           f"제목: {title}\n"
                           f"--------------------------\n"
                           f"{summary}\n"
                           f"--------------------------\n"
                           f"<a href='{full_link}'>👉 리포트 원문(PDF) 보기</a>")
                    
                    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                    save_sent_id(report_id)
                    sent_ids.add(report_id)
                    new_count += 1
                    await asyncio.sleep(1)

    print(f"최종 처리 완료: {new_count}건 전송")

if __name__ == "__main__":
    asyncio.run(main())
