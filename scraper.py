import os
import requests
import telegram
import asyncio
import re
import fitz
import json
from bs4 import BeautifulSoup
from io import BytesIO

# --- 설정 (GitHub Secrets 환경 변수) ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"

def get_summary_rest(text):
    if not GEMINI_API_KEY: return "❌ 키 미설정"
    # 가장 표준적인 v1beta 경로 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": f"당신은 금융 분석 전문가입니다. 다음 리포트의 핵심 투자 포인트 3가지를 전문적인 어조로 요약해줘:\n\n{text[:7000]}"}]}]
    }
    
    try:
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        return f"❌ 요약 실패 (Code {res.status_code})\n{res.text[:150]}"
    except Exception as e:
        return f"❌ 통신 장애: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        res = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            # 텍스트가 풍부한 앞 3페이지를 추출
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    # 산업(industry)과 시장(market) 리포트를 모두 순회합니다.
    targets = [{"n":"산업", "i":"🏗️", "t":"industry"}, {"n":"시장", "i":"📈", "t":"market"}]
    
    print("🚀 [한국 계정 테스트] 리포트 수집 및 요약 시작...")
    
    for cat in targets:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 게시판 최상단 리포트 1개씩만 테스트 발송
        row = soup.select('tr')[1]
        cols = row.find_all('td')
        if len(cols) < 5: continue
        
        a_tag = row.find('a', href=re.compile(r'report_idx='))
        title = a_tag.get_text(strip=True)
        
        # 출처(증권사) 추출: 숫자가 없는 문자열 칸을 우선 선택
        provider = "출처미상"
        for i in [4, 5, 3]:
            val = cols[i].get_text(strip=True)
            if val and not any(x.isdigit() for x in val.replace('.','')):
                provider = val
                break
        
        full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
        
        print(f"[{cat['n']}] {title} 처리 중...")
        pdf_text = get_pdf_text(full_link)
        summary = get_summary_rest(pdf_text)
        
        msg = (f"<b>{cat['i']} {cat['n']} 리포트 도착</b>\n\n"
               f"출처: <b>{provider}</b>\n"
               f"제목: {title}\n"
               f"--------------------------\n"
               f"{summary}\n"
               f"--------------------------\n"
               f"<a href='{full_link}'>👉 리포트 원문 보기</a>")
        
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
