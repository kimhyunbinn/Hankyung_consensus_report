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
    # 모델 인식률이 가장 높은 v1beta 표준 경로
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": f"너는 금융 전문가야. 다음 내용을 3가지 핵심 포인트로 요약해줘:\n\n{text[:8000]}"}]}]
    }
    
    try:
        # 키 뒷자리를 로그에 찍어 실제 적용된 키 확인 (보안상 뒤 4자리만)
        key_hint = GEMINI_API_KEY[-4:] if GEMINI_API_KEY else "None"
        res = requests.post(url, json=payload, timeout=20)
        
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"❌ 요약 실패 (Code {res.status_code})\n사용중인 키 뒷자리: {key_hint}\n에러내용: {res.text[:100]}"
    except Exception as e:
        return f"❌ 통신 오류: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        res = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    targets = [{"n":"산업", "i":"🏗️", "t":"industry"}, {"n":"시장", "i":"📈", "t":"market"}]
    
    print("🚀 수동 요약 테스트 시작...")
    
    for cat in targets:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('tr')[1:3] # 최신 2개씩
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            
            a = row.find('a', href=re.compile(r'report_idx='))
            title = a.get_text(strip=True)
            
            # 출처(증권사) 찾기 강화
            provider = "출처미상"
            for i in [4, 5, 3]:
                val = cols[i].get_text(strip=True)
                if val and not any(x.isdigit() for x in val.replace('.','')):
                    provider = val
                    break
            
            full_link = BASE_URL + a['href'] if a['href'].startswith('/') else a['href']
            summary = get_summary_rest(get_pdf_text(full_link))
            
            msg = (f"<b>{cat['i']} {cat['n']} 리포트</b>\n\n"
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
