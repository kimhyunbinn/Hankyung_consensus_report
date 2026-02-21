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
    
    # [최후의 보루] 가장 원초적인 모델 명칭과 경로 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": f"요약 전문가로서 다음 리포트의 핵심을 3줄로 요약해줘:\n\n{text[:6000]}"}]
        }]
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            # 404가 뜨면 '사용 가능한 모델 목록'을 확인하라는 메시지 출력
            return f"❌ 요약 실패 (Code {res.status_code})\n메시지: {res.text[:150]}"
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
    targets = [{"n":"산업", "i":"🏗️", "t":"industry"}, {"n":"시장", "i":"📈", "t":"market"}]
    
    print("🚀 수동 모드 실행 중...")
    
    for cat in targets:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 최신 1개씩만 테스트해서 성공 여부 확인
        row = soup.select('tr')[1]
        cols = row.find_all('td')
        if len(cols) < 5: continue
        
        a_tag = row.find('a', href=re.compile(r'report_idx='))
        title = a_tag.get_text(strip=True)
        
        # 출처 찾기 로직
        provider = "출처미상"
        for i in [4, 5, 3]:
            val = cols[i].get_text(strip=True)
            if val and not any(x.isdigit() for x in val.replace('.','')):
                provider = val
                break
        
        full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
        
        print(f"[{cat['n']}] {title} 요약 시도...")
        pdf_text = get_pdf_text(full_link)
        summary = get_summary_rest(pdf_text)
        
        msg = (f"<b>{cat['i']} {cat['n']} 리포트 (테스트)</b>\n\n"
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
