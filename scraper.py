import os
import requests
import telegram
import asyncio
import re
import fitz  # PyMuPDF
import ssl
import base64
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# --- 구형 SSL 보안 설정 허용 ---
class DESAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1')
        kwargs['ssl_context'] = context
        return super(DESAdapter, self).init_poolmanager(*args, **kwargs)

# --- 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"
DB_FILE = "sent_reports.txt"

if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f: f.write("")

def get_sent_list():
    with open(DB_FILE, "r") as f: return f.read().splitlines()

def add_to_sent_list(report_id):
    with open(DB_FILE, "a") as f: f.write(report_id + "\n")

def get_summary_from_image(image_data):
    """이미지(PDF 첫페이지)를 Gemini에게 직접 전달하여 요약"""
    if not GEMINI_API_KEY: return "❌ API 키 미설정"
    
    # 2.0-flash 모델은 이미지 이해력이 매우 뛰어남
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    encoded_image = base64.b64encode(image_data).decode('utf-8')
    
    payload = {
        "contents": [{
            "parts": [
                {"text": "너는 금융 전문가야. 첨부된 리포트 이미지를 분석해서 투자자가 알아야 할 핵심 내용만 5가지로 요약해줘.\n조건: 서론 없이 ✅ 기호 사용, 음슴체로 간결하게 작성."},
                {"inline_data": {"mime_type": "image/png", "data": encoded_image}}
            ]
        }]
    }
    
    try:
        res = requests.post(url, json=payload, timeout=40)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f"Gemini Vision Error: {e}")
    return "❌ 멀티모달 요약 실패"

def get_pdf_first_page_image(pdf_url, session):
    """PDF를 다운로드하여 첫 페이지를 이미지 데이터로 변환"""
    try:
        res = session.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=25)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            page = doc[0]  # 첫 페이지만 분석 (핵심 내용이 보통 첫 장에 있음)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 화질 2배 강화
            return pix.tobytes("png")
    except Exception as e:
        print(f"PDF to Image Error: {e}")
        return None

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    sent_list = get_sent_list()
    
    session = requests.Session()
    session.mount("https://", DESAdapter())
    
    targets = [
        {"n": "시장", "i": "📈", "t": "market"},
        {"n": "산업", "i": "🏗️", "t": "industry"}
    ]
    
    today_str = datetime.now().strftime("%Y.%m.%d")
    
    for cat in targets:
        url = f"{BASE_URL}/analysis/list?skinType={cat['t']}"
        try:
            res = session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('tr')[1:6]
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                report_idx = re.search(r'report_idx=(\d+)', a_tag['href']).group(1)
                if report_idx in sent_list: continue
                
                title = a_tag.get_text(strip=True)
                provider = "출처미상"
                for i in [4, 5, 3]:
                    val = cols[i].get_text(strip=True)
                    if val and not any(x.isdigit() for x in val):
                        provider = val; break
                
                full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
                
                # 텍스트 추출 대신 이미지 변환 후 요약 시도
                img_data = get_pdf_first_page_image(full_link, session)
                if img_data:
                    summary = get_summary_from_image(img_data)
                else:
                    summary = "❌ PDF 이미지를 불러올 수 없음"
                
                msg = (f"{cat['i']} <b>{cat['n']} 리포트</b>\n\n"
                       f"출처: <b>{provider}</b>\n제목: {title}\n({today_str})\n"
                       f"--------------------------\n"
                       f"📝 <b>핵심 요약 (AI 분석)</b>\n{summary}\n"
                       f"--------------------------\n"
                       f"<a href='{full_link}'>👉 원문 보기</a>")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                add_to_sent_list(report_idx)
                sent_list.append(report_idx)
                await asyncio.sleep(2)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
