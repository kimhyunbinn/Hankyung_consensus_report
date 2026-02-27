import os
import requests
import telegram
import asyncio
import re
import fitz
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime

# --- 환경 변수 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"
DB_FILE = "sent_reports.txt"

# 중복 방지용 파일 생성 (없을 경우)
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f: f.write("")

def get_sent_list():
    """이미 발송된 리포트 ID 목록 불러오기"""
    with open(DB_FILE, "r") as f:
        return f.read().splitlines()

def add_to_sent_list(report_id):
    """발송 완료된 리포트 ID 저장하기"""
    with open(DB_FILE, "a") as f:
        f.write(report_id + "\n")

def get_summary(text):
    """Gemini API를 이용한 음슴체 5줄 요약"""
    if not GEMINI_API_KEY: return "❌ API 키 미설정"
    
    # 최신 모델 리스트 순차적 시도 (2026년 기준)
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]
    
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        
        prompt = (
            "너는 금융 전문가야. 다음 리포트 내용을 분석해서 투자자가 알아야 할 핵심 내용만 5가지로 요약해줘.\n"
            "조건:\n"
            "1. 서론이나 설명(예: '요약하겠습니다' 등) 없이 바로 요약 내용만 출력할 것.\n"
            "2. 각 항목 앞에는 반드시 '✅ ' 기호를 붙일 것.\n"
            "3. '~함', '~임', '~함' 같은 음슴체로 간결하게 작성할 것.\n\n"
            f"내용:\n{text[:8000]}"
        )
        
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except:
            continue
            
    return "❌ 모델 호출 실패 (404 또는 권한 문제)"

def get_pdf_text(pdf_url):
    """PDF 원문 텍스트 추출"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(pdf_url, headers=headers, timeout=20)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            # 앞 3페이지 텍스트 추출
            return "".join([p.get_text() for p in doc[:3]])
    except Exception:
        return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    sent_list = get_sent_list()
    
    # 감시 대상: 시장(market), 산업(industry)
    targets = [
        {"n": "시장", "i": "📈", "t": "market"},
        {"n": "산업", "i": "🏗️", "t": "industry"}
    ]
    
    today_str = datetime.now().strftime("%Y.%m.%d")
    
    for cat in targets:
        url = f"{BASE_URL}/analysis/list?skinType={cat['t']}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 최근 올라온 리포트 5개씩 확인
        rows = soup.select('tr')[1:6]
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            
            a_tag = row.find('a', href=re.compile(r'report_idx='))
            if not a_tag: continue
            
            title = a_tag.get_text(strip=True)
            report_idx = re.search(r'report_idx=(\d+)', a_tag['href']).group(1)
            
            # [중복 체크] 이미 보낸 리포트라면 건너뛰기
            if report_idx in sent_list:
                continue
                
            # 증권사(출처) 추출
            provider = "출처미상"
            for i in [4, 5, 3]:
                val = cols[i].get_text(strip=True)
                if val and not any(x.isdigit() for x in val):
                    provider = val
                    break
            
            full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
            
            # 요약 생성
            pdf_text = get_pdf_text(full_link)
            if len(pdf_text) < 100:
                summary = "❌ PDF 텍스트 추출 불가 (이미지 위주 리포트일 수 있음)"
            else:
                summary = get_summary(pdf_text)
            
            # 텔레그램 메시지 양식
            msg = (f"{cat['i']} <b>{cat['n']} 리포트</b>\n\n"
                   f"출처: <b>{provider}</b>\n"
                   f"제목: {title}\n"
                   f"({today_str})\n"
                   f"--------------------------\n"
                   f"📝 <b>핵심 내용 요약</b>\n"
                   f"{summary}\n"
                   f"--------------------------\n"
                   f"<a href='{full_link}'>👉 원문 보기</a>")
            
            # 메시지 발송
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
            
            # 발송 리스트 업데이트
            add_to_sent_list(report_idx)
            sent_list.append(report_idx) # 현재 루프 내 중복 방지
            
            await asyncio.sleep(2) # 도배 방지

if __name__ == "__main__":
    asyncio.run(main())
