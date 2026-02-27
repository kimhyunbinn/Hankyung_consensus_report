import os
import requests
import telegram
import asyncio
import re
import fitz  # PyMuPDF
import ssl
import base64
import time
from bs4 import BeautifulSoup
from io import BytesIO
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

def get_summary_from_gemini(image_data):
    """이미지 분석 요약 테스트"""
    if not GEMINI_API_KEY: return "❌ API 키 미설정"
    
    # 429 에러 방지를 위해 가장 가벼운 1.5-flash 또는 최신 2.0-flash 사용
    model_name = "gemini-2.0-flash" 
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
    
    encoded_image = base64.b64encode(image_data).decode('utf-8')
    
    payload = {
        "contents": [{
            "parts": [
                {"text": "금융 전문가로서 이 리포트 이미지를 읽고 핵심 내용 5가지만 ✅ 기호와 함께 음슴체로 요약해줘."},
                {"inline_data": {"mime_type": "image/png", "data": encoded_image}}
            ]
        }]
    }
    
    try:
        res = requests.post(url, json=payload, timeout=60)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return f"❌ 요약 실패 (HTTP {res.status_code}: {res.text[:100]})"
    except Exception as e:
        return f"❌ 에러: {str(e)[:30]}"

def process_pdf_to_image(pdf_url, session):
    """PDF 첫 장을 이미지로 변환"""
    try:
        res = session.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        with fitz.open(stream=BytesIO(res.content), filetype="pdf") as doc:
            page = doc[0]
            # 할당량 절약을 위해 해상도를 적절히 조절 (1.5배)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            return pix.tobytes("png")
    except Exception as e:
        print(f"PDF 변환 에러: {e}")
        return None

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    session = requests.Session()
    session.mount("https://", DESAdapter())
    
    # 테스트를 위해 '시장' 카테고리 하나만 접속
    test_url = f"{BASE_URL}/analysis/list?skinType=market"
    
    try:
        print("리포트 목록 가져오는 중...")
        res = session.get(test_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 딱 첫 번째 리포트 하나만 선택
        row = soup.select('tr')[1] 
        a_tag = row.find('a', href=re.compile(r'report_idx='))
        
        if a_tag:
            title = a_tag.get_text(strip=True)
            full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
            
            print(f"대상 선정: {title}")
            print("이미지 변환 및 AI 요약 중... (약 10~20초 소요)")
            
            # 이미지 변환
            img_data = process_pdf_to_image(full_link, session)
            
            if img_data:
                # 딱 한 번의 API 호출
                summary = get_summary_from_gemini(img_data)
            else:
                summary = "❌ PDF 이미지를 생성하지 못했습니다."
            
            msg = (f"🧪 <b>1개 리포트 집중 테스트</b>\n\n"
                   f"제목: {title}\n"
                   f"--------------------------\n"
                   f"📝 <b>AI 요약 결과</b>\n{summary}\n"
                   f"--------------------------\n"
                   f"<a href='{full_link}'>👉 원문 보기</a>")
            
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML')
            print("테스트 완료! 텔레그램을 확인하세요.")
            
    except Exception as e:
        print(f"테스트 실패: {e}")

if __name__ == "__main__":
    asyncio.run(main())
