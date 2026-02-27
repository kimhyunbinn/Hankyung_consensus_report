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

# --- 설정 로드 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"

def get_summary_from_gemini(image_data=None, text_content=None):
    """Gemini 2.0 Flash를 사용하여 이미지 또는 텍스트 요약"""
    if not GEMINI_API_KEY: return "❌ API 키 미설정"
    
    # 가장 범용적인 모델명 사용
    model_name = "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = "너는 금융 전문가야. 리포트 내용을 분석해서 투자자가 알아야 할 핵심 내용만 5가지로 요약해줘.\n조건: 서론 없이 ✅ 기호 사용, '~함' 형태의 음슴체로 간결하게 작성."
    
    if image_data:
        encoded_image = base64.b64encode(image_data).decode('utf-8')
        parts = [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": encoded_image}}
        ]
    else:
        parts = [{"text": f"{prompt}\n\n내용:\n{text_content[:8000]}"}]

    payload = {"contents": [{"parts": parts}]}
    
    try:
        res = requests.post(url, json=payload, timeout=60)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"❌ 요약 실패 (HTTP {res.status_code}: {res.text[:100]})"
    except Exception as e:
        return f"❌ 요약 에러: {str(e)[:30]}"

def process_pdf(pdf_url, session):
    """PDF를 처리하여 이미지 또는 텍스트 추출"""
    try:
        res = session.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            # 1순위: 이미지 변환
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")
            
            # 2순위: 텍스트 추출
            text_data = "".join([p.get_text() for p in doc[:3]])
            return img_data, text_data
    except:
        return None, None

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    
    session = requests.Session()
    session.mount("https://", DESAdapter())
    
    targets = [
        {"n": "시장", "i": "📈", "t": "market"},
        {"n": "산업", "i": "🏗️", "t": "industry"}
    ]
    
    for cat in targets:
        url = f"{BASE_URL}/analysis/list?skinType={cat['t']}"
        try:
            res = session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            # 상단 3개만 테스트로 가져옴
            rows = soup.select('tr')[1:4]
            
            for row in rows:
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                title = a_tag.get_text(strip=True)
                full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
                
                print(f"진행 중: {title}") # 로그 확인용
                
                # PDF 처리 및 요약
                img_data, text_data = process_pdf(full_link, session)
                summary = get_summary_from_gemini(image_data=img_data, text_content=text_data)
                
                msg = (f"{cat['i']} <b>{cat['n']} 테스트</b>\n\n"
                       f"제목: {title}\n"
                       f"--------------------------\n"
                       f"📝 <b>핵심 요약</b>\n{summary}\n"
                       f"--------------------------\n"
                       f"<a href='{full_link}'>👉 원문 보기</a>")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                await asyncio.sleep(1) # 전송 속도 조절
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
