import os
import requests
import telegram
import asyncio
import re
import fitz
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime

# --- 설정 (GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"

def get_summary(text):
    if not GEMINI_API_KEY: return "❌ 키 미설정"
    
    # 성공했던 최신 모델 리스트 (성공한 모델을 가장 앞에 두세요)
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        
        # 5가지 포인트를 요구하는 프롬프트 수정
        payload = {
            "contents": [{"parts": [{"text": f"너는 금융 전문가야. 다음 리포트 내용을 분석해서 투자자가 꼭 알아야 할 핵심 내용을 반드시 5개의 불렛포인트(*)로 요약해줘. 한국어로 작성해:\n\n{text[:8000]}"}]}]
        }
        
        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            continue 
        except:
            continue
            
    return "❌ 요약 실패 (모델 확인 필요)"

def get_pdf_text(pdf_url):
    try:
        res = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    targets = [{"n":"시장", "i":"📈", "t":"market"}, {"n":"산업", "i":"🏗️", "t":"industry"}]
    
    # 오늘 날짜 (YYYY.MM.DD)
    today_str = datetime.now().strftime("%Y.%m.%d")
    
    for cat in targets:
        url = f"{BASE_URL}/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        row = soup.select('tr')[1]
        cols = row.find_all('td')
        if len(cols) < 5: continue
        
        a_tag = row.find('a', href=re.compile(r'report_idx='))
        title = a_tag.get_text(strip=True)
        
        # 증권사(출처) 추출
        provider = "출처미상"
        for i in [4, 5, 3]:
            val = cols[i].get_text(strip=True)
            if val and not any(x.isdigit() for x in val):
                provider = val
                break
        
        full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
        
        # 요약 수행
        summary_content = get_summary(get_pdf_text(full_link))
        
        # 메시지 양식 조립
        msg = (f"{cat['i']} <b>{cat['n']} 리포트</b>\n\n"
               f"출처: <b>{provider}</b>\n"
               f"제목: {title}\n"
               f"({today_str})\n"
               f"--------------------------\n"
               f"✅ <b>핵심 내용 요약</b>\n"
               f"{summary_content}\n"
               f"--------------------------\n"
               f"<a href='{full_link}'>👉 원문 보기</a>")
        
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
