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
    
    # [핵심 변경] 모델명 뒤에 -latest를 붙여 최신 모델로 강제 지정
    # 404 방지를 위해 가장 범용적인 v1beta 엔드포인트 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": f"너는 금융 전문가야. 다음 리포트의 핵심 투자 포인트 3가지를 전문적인 한국어로 요약해줘:\n\n{text[:7000]}"}]
        }]
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        
        # 만약 404가 뜨면 주소 체계를 v1으로 변경하여 재시도
        if res.status_code == 404:
            url_v1 = url.replace("v1beta", "v1")
            res = requests.post(url_v1, headers=headers, json=payload, timeout=20)
            
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"❌ 요약 실패 (Code {res.status_code})\n에러: {res.text[:100]}"
    except Exception as e:
        return f"❌ 통신 오류: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(pdf_url, headers=headers, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            return "".join([p.get_text() for p in doc[:3]])
    except: return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    # 산업(industry)과 시장(market) 카테고리 설정
    targets = [
        {"n":"산업", "i":"🏗️", "t":"industry"}, 
        {"n":"시장", "i":"📈", "t":"market"}
    ]
    
    print("🚀 수동 모드: 산업/시장 최신 리포트 발송 시작")
    
    for cat in targets:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 최신 리포트 2개씩 선정
        rows = soup.select('tr')[1:3] 
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            
            a_tag = row.find('a', href=re.compile(r'report_idx='))
            if not a_tag: continue
            
            title = a_tag.get_text(strip=True)
            
            # 출처(증권사) 찾기: 숫자가 없는 문자열을 우선적으로 추출
            provider = "출처미상"
            for i in [4, 5, 3]:
                val = cols[i].get_text(strip=True)
                if val and not any(x.isdigit() for x in val.replace('.','')):
                    provider = val
                    break
            
            full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
            
            # PDF 텍스트 추출 및 요약
            pdf_text = get_pdf_text(full_link)
            summary = get_summary_rest(pdf_text) if len(pdf_text) > 100 else "❌ PDF 내용 추출 실패"
            
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
