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

# 감시 카테고리 (산업 + 시장)
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

# --- 핵심 수정: 404 오류 방지를 위한 URL 구조 변경 ---
def get_summary_rest(text):
    if not GEMINI_API_KEY: return "API 키 미설정"
    
    # 모델 경로를 v1 버전의 정석적인 주소로 변경
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"당신은 금융 전문가입니다. 다음 리포트 내용을 바탕으로 핵심 투자 포인트 3가지를 요약해주세요:\n\n{text[:8000]}"
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        # verify=True(기본값)로 보안 연결 유지
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            res_json = response.json()
            return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            # 상세 에러 메시지 출력 (디버깅용)
            print(f"API 에러 상세: {response.text}")
            return f"API 오류 (Code: {response.status_code})"
    except Exception as e:
        return f"요약 실패 (통신 오류)"

def get_pdf_text(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(pdf_url, headers=headers, timeout=30)
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            return "".join([page.get_text() for page in doc[:3]])
    except: return ""

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    date_formats = [now_kst.strftime("%Y-%m-%d"), now_kst.strftime("%y-%m-%d"), now_kst.strftime("%Y.%m.%d")]
    
    sent_ids = get_sent_ids()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0'}

    new_count = 0
    
    for cat in TARGET_CATEGORIES:
        for page in range(1, 3):
            url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['type']}&now_page={page}"
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                row_text = row.get_text(strip=True)
                if any(d in row_text for d in date_formats):
                    a_tag = row.find('a', href=re.compile(r'report_idx='))
                    if not a_tag: continue
                    
                    report_id = re.search(r'report_idx=(\d+)', a_tag['href']).group(1)
                    if report_id not in sent_ids:
                        title = a_tag.get_text(strip=True)
                        provider = cols[4].get_text(strip=True)
                        full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
                        
                        pdf_text = get_pdf_text(full_link)
                        summary = get_summary_rest(pdf_text) if len(pdf_text) > 50 else "요약 불가 리포트"
                        
                        msg = (f"<b>{cat['icon']} 새로운 {cat['name']} 리포트!</b>\n\n"
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

    print(f"완료: {new_count}건")

if __name__ == "__main__":
    asyncio.run(main())
