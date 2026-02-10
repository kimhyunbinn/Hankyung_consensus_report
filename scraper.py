import os
import requests
import telegram
import asyncio
import re
import time
import fitz  # PyMuPDF
import google.generativeai as genai
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from io import BytesIO

# --- 환경 변수 가져오기 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Gemini 설정
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
    try:
        with open(SENT_REPORTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{report_id}\n")
    except: pass

# --- 요약 함수 ---
async def get_summary(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers, timeout=20)
        # PDF 앞 3페이지만 읽기 (속도/비용 최적화)
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            text = "".join([page.get_text() for page in doc[:3]])
        
        if not text.strip(): return "내용 요약 불가 (이미지 위주 리포트)"
        
        prompt = f"금융 분석가로서 다음 리포트를 핵심만 3줄 요약해줘:\n{text[:7000]}"
        # 동기 함수인 generate_content를 비동기처럼 실행
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        return res.text
    except:
        return "요약 생성 중 오류가 발생했습니다. 원문을 참고하세요."

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    today_str = now_kst.strftime("%Y-%m-%d")
    
    sent_ids = get_sent_ids()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for page in range(1, 3):
        url = TARGET_URL.format(page)
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            
            if today_str in row.get_text():
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                link = a_tag['href']
                report_id = re.search(r'report_idx=(\d+)', link).group(1)
                
                if report_id not in sent_ids:
                    title = a_tag.get_text(strip=True)
                    provider = cols[4].get_text(strip=True)
                    full_link = BASE_URL + link if link.startswith('/') else link
                    
                    # 1. 즉시 알림 전송 (지연 최소화)
                    base_msg = (f"<b>🏗️ 새로운 산업 리포트!</b>\n\n"
                                f"출처: <b>{provider}</b>\n"
                                f"제목: {title}\n"
                                f"⏳ <i>요약 분석 중... 잠시만 기다려주세요.</i>\n\n"
                                f"<a href='{full_link}'>👉 원문 보기</a>")
                    
                    sent_msg = await bot.send_message(chat_id=CHAT_ID, text=base_msg, parse_mode='HTML', disable_web_page_preview=True)
                    save_sent_id(report_id)
                    sent_ids.add(report_id)

                    # 2. 백그라운드에서 요약 후 기존 메시지 수정
                    summary = await get_summary(full_link)
                    updated_msg = (f"<b>🏗️ 산업 리포트 요약</b>\n\n"
                                   f"출처: <b>{provider}</b>\n"
                                   f"제목: {title}\n"
                                   f"--------------------------\n"
                                   f"{summary}\n"
                                   f"--------------------------\n"
                                   f"<a href='{full_link}'>👉 원문 보기</a>")
                    
                    try:
                        await bot.edit_message_text(chat_id=CHAT_ID, message_id=sent_msg.message_id, text=updated_msg, parse_mode='HTML', disable_web_page_preview=True)
                    except:
                        pass 
                    
                    await asyncio.sleep(1) # API 부하 방지

if __name__ == "__main__":
    asyncio.run(main())
