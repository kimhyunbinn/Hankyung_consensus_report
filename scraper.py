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
    
    # [최종 수정] 404 방지를 위해 v1 정식 버전 엔드포인트 사용
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": f"다음 금융 리포트를 3가지 핵심 요점으로 요약해줘:\n\n{text[:7000]}"}]
        }]
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        
        # 만약 v1에서 404가 나면 v1beta로 한 번 더 시도 (자동 전환)
        if res.status_code == 404:
            url_beta = url.replace("/v1/", "/v1beta/")
            res = requests.post(url_beta, headers=headers, json=payload, timeout=20)
            
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"❌ 요약 실패 (Code {res.status_code})\n에러: {res.text[:100]}"
    except Exception as e:
        return f"❌ 통신 오류: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        # 리포트 원문 접속을 위한 헤더
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(pdf_url, headers=headers, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    # 산업(industry)과 시장(market) 모두 추적
    targets = [{"n":"산업", "i":"🏗️", "t":"industry"}, {"n":"시장", "i":"📈", "t":"market"}]
    
    print("🚀 리포트 수집 및 요약 시작 (수동 실행)")
    
    for cat in targets:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 최신 2개씩만 테스트
        rows = soup.select('tr')[1:3] 
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            
            a_tag = row.find('a', href=re.compile(r'report_idx='))
            if not a_tag: continue
            
            title = a_tag.get_text(strip=True)
            
            # 출처(증권사) 찾기: 숫자/날짜가 아닌 칸을 우선 선택
            provider = "출처미상"
            for i in [4, 5, 3]:
                val = cols[i].get_text(strip=True)
                if val and not any(x.isdigit() for x in val.replace('.','')):
                    provider = val
                    break
            
            full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
            
            # 요약 진행
            pdf_text = get_pdf_text(full_link)
            summary = get_summary_rest(pdf_text) if len(pdf_text) > 100 else "❌ PDF 텍스트 추출 불가"
            
            msg = (f"<b>{cat['i']} {cat['n']} 리포트</b>\n\n"
                   f"출처: <b>{provider}</b>\n"
                   f"제목: {title}\n"
                   f"--------------------------\n"
                   f"{summary}\n"
                   f"--------------------------\n"
                   f"<a href='{full_link}'>👉 리포트 원문 보기</a>")
            
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
