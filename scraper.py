import os
import requests
import telegram
import asyncio
import re
import time
import fitz  # PyMuPDF
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from io import BytesIO

# --- 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

BASE_URL = "https://consensus.hankyung.com"
SENT_REPORTS_FILE = "sent_reports.txt"

TARGET_CATEGORIES = [
    {"name": "산업", "icon": "🏗️", "type": "industry"},
    {"name": "시장", "icon": "📈", "type": "market"}
]

def get_sent_ids():
    if not os.path.exists(SENT_REPORTS_FILE): return set()
    try:
        with open(SENT_REPORTS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except: return set()

def save_sent_id(report_id):
    with open(SENT_REPORTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{report_id}\n")

# --- Gemini REST API (v1beta 버전으로 고정 및 데이터 구조 최적화) ---
def get_summary_rest(text):
    if not GEMINI_API_KEY: return "API 키 미설정"
    
    # 404 방지를 위한 정석적인 Endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    
    # 텍스트가 너무 길면 잘라서 전송 (안정성 확보)
    clean_text = text[:10000].replace('"', "'")
    prompt = f"당신은 금융 전문가입니다. 다음 리포트 내용을 바탕으로 투자자가 꼭 알아야 할 핵심 포인트 3가지를 전문적인 어조로 요약해주세요:\n\n{clean_text}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        # json.dumps를 사용하여 확실하게 직렬화
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        
        if response.status_code == 200:
            res_data = response.json()
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            # 로그에 상세 에러 출력 (404 원인 파악용)
            print(f"DEBUG: API Status {response.status_code}, Response: {response.text}")
            return f"요약 실패 (API Error {response.status_code})"
    except Exception as e:
        return f"통신 오류 발생: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(pdf_url, headers=headers, timeout=30)
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            # 텍스트가 너무 적으면 페이지를 더 읽음 (최대 5페이지)
            full_text = ""
            for page in doc[:5]:
                full_text += page.get_text()
            return full_text
    except: return ""

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    date_formats = [now_kst.strftime("%Y-%m-%d"), now_kst.strftime("%y-%m-%d"), now_kst.strftime("%Y.%m.%d")]
    
    sent_ids = get_sent_ids()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0'}

    new_count = 0
    
    for cat in TARGET_CATEGORIES:
        print(f"--- {cat['name']} 카테고리 스캔 시작 ---")
        for page in range(1, 3):
            url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['type']}&now_page={page}"
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4: continue
                
                row_text = row.get_text(strip=True)
                if any(d in row_text for d in date_formats):
                    a_tag = row.find('a', href=re.compile(r'report_idx='))
                    if not a_tag: continue
                    
                    report_id = re.search(r'report_idx=(\d+)', a_tag['href']).group(1)
                    if report_id not in sent_ids:
                        title = a_tag.get_text(strip=True)
                        
                        # --- [출처 탐색 강화] ---
                        provider = "출처 확인불가"
                        # 게시판마다 다른 위치를 탐색하되, 날짜나 숫자가 아닌 문자열을 우선 선택
                        for i in [4, 5, 3]:
                            if len(cols) > i:
                                val = cols[i].get_text(strip=True)
                                # 날짜 형식이 아니고(점 2개 미만), 텍스트가 존재할 때
                                if val and val.count('.') < 2 and not val.isdigit():
                                    provider = val
                                    break
                        
                        full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
                        
                        print(f"[{cat['name']}] 처리 중: {title}")
                        pdf_text = get_pdf_text(full_link)
                        
                        summary = get_summary_rest(pdf_text) if len(pdf_text) > 100 else "요약 실패 (PDF 본문 부족)"
                        
                        msg = (f"<b>{cat['icon']} {cat['name']} 리포트 도착!</b>\n\n"
                               f"출처: <b>{provider}</b>\n"
                               f"제목: {title}\n"
                               f"--------------------------\n"
                               f"{summary}\n"
                               f"--------------------------\n"
                               f"<a href='{full_link}'>👉 리포트 원문 보기</a>")
                        
                        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                        save_sent_id(report_id)
                        sent_ids.add(report_id)
                        new_count += 1
                        await asyncio.sleep(2)

    print(f"최종 전송 완료: {new_count}건")

if __name__ == "__main__":
    asyncio.run(main())
