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
        # 브라우저처럼 보이기 위해 헤더 강화
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://consensus.hankyung.com/'
        }
        response = requests.get(pdf_url, headers=headers, timeout=30)
        response.raise_for_status() # HTTP 에러 발생 시 예외 처리
        
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            text = ""
            for page in doc[:3]:
                text += page.get_text()
        
        if not text.strip() or len(text) < 50:
            return "내용 요약 불가 (이미지 위주 리포트이거나 텍스트가 부족합니다.)"

        prompt = f"당신은 금융 전문가입니다. 다음 리포트 내용을 바탕으로 핵심 투자 포인트 3가지를 불렛포인트로 요약해주세요. \n\n내용:\n{text[:7000]}"
        
        # Gemini 호출 (재시도 로직 포함)
        for i in range(2):
            try:
                res = model.generate_content(prompt)
                return res.text.strip()
            except:
                time.sleep(2)
                continue
        return "Gemini API 응답 오류"
    except Exception as e:
        print(f"요약 중 에러 발생: {str(e)}") # 로그에서 에러 확인용
        return f"요약 실패 (원문 확인 요망)"

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    date_formats = [
        now_kst.strftime("%Y-%m-%d"),
        now_kst.strftime("%y-%m-%d"),
        now_kst.strftime("%Y.%m.%d")
    ]
    
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
            if any(date_str in row_text for date_str in date_formats):
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                link = a_tag['href']
                report_id = re.search(r'report_idx=(\d+)', link).group(1)
                
                if report_id not in sent_ids:
                    title = a_tag.get_text(strip=True)
                    provider = cols[4].get_text(strip=True)
                    full_link = BASE_URL + link if link.startswith('/') else link
                    
                    print(f"요약 시도 중: {title}")
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
                    await asyncio.sleep(2)

    print(f"최종 처리 완료: {new_count}건")

if __name__ == "__main__":
    asyncio.run(main())
