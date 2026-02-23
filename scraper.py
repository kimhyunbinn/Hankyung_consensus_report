import os
import requests
import telegram
import asyncio
import re
import fitz
from bs4 import BeautifulSoup
from io import BytesIO

# --- 설정 (GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"

def get_summary(text):
    if not GEMINI_API_KEY: return "❌ 키 미설정"
    
    # [변경] 2026년 현재 사용 가능한 최신 모델들
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": f"너는 최고의 금융 분석가야. 다음 리포트의 핵심을 3줄로 요약해줘:\n\n{text[:8000]}"}]}]
        }
        
        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            # 404가 나면 다음 모델로 넘어감
            continue 
        except:
            continue
            
    return "❌ 모든 최신 모델 호출 실패 (404/계정 권한 확인 필요)"

def get_pdf_text(pdf_url):
    try:
        res = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    targets = [{"n":"시장", "i":"📈", "t":"market"}, {"n":"산업", "i":"🏗️", "t":"industry"}]
    
    for cat in targets:
        url = f"{BASE_URL}/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        row = soup.select('tr')[1]
        cols = row.find_all('td')
        if len(cols) < 5: continue
        
        a_tag = row.find('a', href=re.compile(r'report_idx='))
        title = a_tag.get_text(strip=True)
        provider = "출처미상"
        for i in [4, 5, 3]:
            val = cols[i].get_text(strip=True)
            if val and not any(x.isdigit() for x in val):
                provider = val; break
        
        full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
        summary = get_summary(get_pdf_text(full_link))
        
        msg = (f"<b>{cat['i']} {cat['n']} 리포트 (2026 최신모델)</b>\n\n"
               f"출처: <b>{provider}</b>\n"
               f"제목: {title}\n"
               f"--------------------------\n"
               f"{summary}\n"
               f"--------------------------\n"
               f"<a href='{full_link}'>👉 원문 보기</a>")
        
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
