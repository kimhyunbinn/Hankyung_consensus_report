import os
import requests
import telegram
import asyncio
import re
import fitz
import json
from bs4 import BeautifulSoup
from io import BytesIO

# --- 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"

# --- [핵심] 404 오류를 뚫기 위한 다중 경로 호출 함수 ---
def get_summary_rest(text):
    if not GEMINI_API_KEY: return "❌ API 키 미설정"
    
    # 시도할 모델 경로 후보들
    endpoints = [
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
        f"https://generativelanguage.googleapis.com/v1beta/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    ]
    
    clean_text = text[:7000].replace('"', "'")
    payload = {"contents": [{"parts": [{"text": f"금융 리포트 요약해줘: {clean_text}"}]}]}
    
    last_error = ""
    for url in endpoints:
        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            last_error = f"Code {res.status_code}: {res.text[:100]}"
        except Exception as e:
            last_error = str(e)
            continue
            
    return f"❌ 모든 경로 호출 실패\n최종에러: {last_error}"

# --- PDF 및 크롤링 로직 (수동 모드: 중복체크X) ---
def get_pdf_text(pdf_url):
    try:
        res = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    for cat in [{"n":"산업","t":"industry"},{"n":"시장","t":"market"}]:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('tr')[1:3] # 최신 2개씩만
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            a = row.find('a', href=re.compile(r'report_idx='))
            title = a.get_text(strip=True)
            # 출처 찾기 (숫자 없는 칸 탐색)
            provider = next((c.get_text(strip=True) for i in [4,5,3] if (c:=cols[i]) and not any(x.isdigit() for x in c.get_text(strip=True).replace('.',''))), "출처미상")
            
            full_link = BASE_URL + a['href'] if a['href'].startswith('/') else a['href']
            summary = get_summary_rest(get_pdf_text(full_link))
            
            msg = f"<b>[{cat['n']}] {provider}</b>\n{title}\n\n{summary}\n\n<a href='{full_link}'>원문보기</a>"
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
