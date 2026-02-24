import os
import requests
import telegram
import asyncio
import re
import fitz
import ssl  # 추가
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from requests.adapters import HTTPAdapter  # 추가
from urllib3.util.ssl_ import create_urllib3_context  # 추가

# --- 보안 설정 완화 클래스 (추가) ---
class DESAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1')
        kwargs['ssl_context'] = context
        return super(DESAdapter, self).init_poolmanager(*args, **kwargs)

# --- 환경 변수 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BASE_URL = "https://consensus.hankyung.com"
DB_FILE = "sent_reports.txt"

# (중략: get_sent_list, add_to_sent_list, get_summary, get_pdf_text 함수는 그대로 두세요)

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    sent_list = get_sent_list()
    
    # 보안 완화 세션 생성 (수정)
    session = requests.Session()
    session.mount("https://", DESAdapter())
    
    targets = [
        {"n": "시장", "i": "📈", "t": "market"},
        {"n": "산업", "i": "🏗️", "t": "industry"}
    ]
    
    today_str = datetime.now().strftime("%Y.%m.%d")
    
    for cat in targets:
        url = f"{BASE_URL}/analysis/list?skinType={cat['t']}"
        
        # session.get 사용으로 변경 (수정)
        res = session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        rows = soup.select('tr')[1:6]
        
        for row in rows:
            # ... (이후 로직은 동일하게 유지하되, 리포트 목록 가져올 때 session을 사용하게 됩니다)
