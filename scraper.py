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

def get_summary_rest(text):
    if not GEMINI_API_KEY: return "❌ 키 미설정"
    # 표준 v1beta 경로 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": f"금융 리포트 전문가로서 핵심 3문장으로 요약해줘:\n\n{text[:7000]}"}]}]
    }
    
    try:
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        return f"❌ 요약 실패 (Code {res.status_code})\n{res.text[:100]}"
    except Exception as e:
        return f"❌ 통신 장애: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        res = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    targets = [{"n":"산업", "i":"🏗️", "t":"industry"}, {"n":"시장", "i":"📈", "t":"market"}]
    
    for cat in targets:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 게시판 최상단 리포트 1개씩 발송 테스트
        row = soup.select('tr')[1]
        cols = row.find_all('td')
        if len(cols) < 5: continue
        
        a_tag = row.find('a', href=re.compile(r'report_idx='))
        title = a_tag.get_text(strip=True)
        
        # 출처(증권사) 추출 로직
        provider = "출처미상"
        for i in [4, 5, 3]: # 증권사명이 위치할 수 있는 칸들
            val = cols[i].get_text(strip=True)
            if val and not any(x.isdigit() for x in val.replace('.','')):
                provider = val
                break
        
        full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
        summary = get_summary_rest(get_pdf_text(full_link))
        
        msg = (f"<b>{cat['i']} {cat['n']} 리포트 (한국계정 테스트)</b>\n\n"
               f"출처: <b>{provider}</b>\n"
               f"제목: {title}\n"
               f"--------------------------\n"
               f"{summary}\n"
               f"--------------------------\n"
               f"<a href='{full_link}'>👉 원문 보기</a>")
        
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)

if __name__ == "__main__":
    asyncio.run(main())
