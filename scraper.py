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

# 감시할 대상 목록 (산업 + 시장)
TARGETS = [
    {
        "name": "산업",
        "icon": "🏗️",
        "url_pattern": "https://consensus.hankyung.com/analysis/list?skinType=industry&now_page={}"
    },
    {
        "name": "시장",
        "icon": "📈",
        "url_pattern": "https://consensus.hankyung.com/analysis/list?skinType=market&now_page={}"
    }
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

# --- Gemini REST API 요약 ---
def get_summary_rest(text):
    if not GEMINI_API_KEY:
        return "API 키가 설정되지 않았습니다."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = f"""
    당신은 금융 전문가입니다. 다음 리포트 내용을 바탕으로 투자자가 꼭 알아야 할 핵심 포인트 3가지를 요약해주세요.
    명확하고 전문적인 어조를 사용하세요.
    
    [리포트 내용]
    {text[:8000]}
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"API 호출 오류 (Code: {response.status_code})"
    except Exception as e:
        return f"연결 실패: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://consensus.hankyung.com/'
        }
        response = requests.get(pdf_url, headers=headers, timeout=30)
        
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            text = ""
            for page in doc[:3]: # 앞 3페이지만
                text += page.get_text()
        return text
    except:
        return ""

async def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    # 날짜 형식 유연하게 대응
    date_formats = [
        now_kst.strftime("%Y-%m-%d"),
        now_kst.strftime("%y-%m-%d"),
        now_kst.strftime("%Y.%m.%d")
    ]
    
    sent_ids = get_sent_ids()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0'}

    new_count = 0
    
    # 산업과 시장 리포트를 각각 순회
    for target in TARGETS:
        category_name = target['name']
        category_icon = target['icon']
        base_url = target['url_pattern']
        
        print(f"--- {category_name} 리포트 탐색 시작 ---")
        
        for page in range(1, 3): # 각 카테고리별 1~2페이지 탐색
            try:
                url = base_url.format(page)
                res = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                rows = soup.find_all('tr')
                
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 5: continue
                    
                    row_text = row.get_text(strip=True)
                    # 오늘 날짜와 일치하는지 확인
                    if any(date_str in row_text for date_str in date_formats):
                        a_tag = row.find('a', href=re.compile(r'report_idx='))
                        if not a_tag: continue
                        
                        link = a_tag['href']
                        report_id = re.search(r'report_idx=(\d+)', link).group(1)
                        
                        if report_id not in sent_ids:
                            title = a_tag.get_text(strip=True)
                            provider = cols[4].get_text(strip=True)
                            full_link = BASE_URL + link if link.startswith('/') else link
                            
                            print(f"[{category_name}] 새 리포트 발견: {title}")
                            
                            # PDF 텍스트 추출 및 요약
                            pdf_text = get_pdf_text(full_link)
                            
                            if len(pdf_text) > 50:
                                summary = get_summary_rest(pdf_text)
                            else:
                                summary = "요약 실패 (텍스트 추출 불가 - 이미지 리포트 가능성)"

                            # 메시지 전송 (카테고리별 아이콘 적용)
                            msg = (f"<b>{category_icon} 새로운 {category_name} 리포트!</b>\n\n"
                                   f"출처: <b>{provider}</b>\n"
                                   f"제목: {title}\n"
                                   f"--------------------------\n"
                                   f"{summary}\n"
                                   f"--------------------------\n"
                                   f"<a href='{full_link}'>👉 리포트 원문(PDF) 보기</a>")
                            
                            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                            save_sent_id(report_id)
                            sent_ids.add(report_id)
                            new_count += 1
                            
                            # API 제한 및 서버 부하 방지를 위한 대기
                            await asyncio.sleep(2)
            except Exception as e:
                print(f"{category_name} {page}페이지 오류: {e}")
            
            time.sleep(1) # 페이지 넘길 때 대기

    print(f"탐색 완료: 총 {new_count}건 전송")

if __name__ == "__main__":
    asyncio.run(main())
