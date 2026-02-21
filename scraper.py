import os
import requests
import telegram
import asyncio
import re
import fitz  # PyMuPDF
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from io import BytesIO

# --- 설정 (GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

BASE_URL = "https://consensus.hankyung.com"

# 테스트를 위해 산업과 시장 각각 최신 3개씩만 확인
TARGET_CATEGORIES = [
    {"name": "산업", "icon": "🏗️", "type": "industry"},
    {"name": "시장", "icon": "📈", "type": "market"}
]

# --- Gemini REST API (가장 안정적인 호출 방식) ---
def get_summary_rest(text):
    if not GEMINI_API_KEY: return "❌ API 키가 설정되지 않았습니다."
    
    # 404 오류 방지를 위한 정석적인 Endpoint (v1 버전 사용)
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    
    # 프롬프트 구성
    clean_text = text[:8000].replace('"', "'")
    prompt = f"당신은 전문 금융 분석가입니다. 다음 리포트 내용을 바탕으로 투자자가 핵심적으로 파악해야 할 내용 3가지를 전문적인 어조로 요약하세요:\n\n{clean_text}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        
        if response.status_code == 200:
            res_data = response.json()
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            # 에러 발생 시 상세 응답 내용을 함께 반환하여 원인 파악
            return f"❌ API 오류 (Code: {response.status_code})\n상세내용: {response.text[:100]}"
    except Exception as e:
        return f"❌ 통신 오류: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers, timeout=30)
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            full_text = ""
            # 분석을 위해 앞 3페이지만 추출
            for page in doc[:3]:
                full_text += page.get_text()
            return full_text
    except Exception as e:
        print(f"PDF 추출 에러: {e}")
        return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    print("🚀 수동 요약 테스트 시작 (중복 체크 무시)")
    
    for cat in TARGET_CATEGORIES:
        print(f"🔍 {cat['name']} 카테고리 최신 리포트 조회 중...")
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['type']}"
        
        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.find_all('tr')[1:4] # 상단 공지 제외 최신 3개만 테스트
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                title = a_tag.get_text(strip=True)
                
                # 출처(증권사) 추출 - 여러 칸 중 텍스트가 있는 곳 탐색
                provider = "출처미상"
                for i in [4, 5, 3]:
                    val = cols[i].get_text(strip=True)
                    if val and val.count('.') < 2 and not val.isdigit():
                        provider = val
                        break
                
                full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
                
                print(f"📝 [{provider}] {title} 요약 시도 중...")
                
                # 텍스트 추출 및 요약
                pdf_text = get_pdf_text(full_link)
                summary = get_summary_rest(pdf_text) if len(pdf_text) > 100 else "❌ PDF 텍스트 추출 실패"
                
                # 메시지 구성
                msg = (f"<b>{cat['icon']} {cat['name']} 리포트 (수동 테스트)</b>\n\n"
                       f"출처: <b>{provider}</b>\n"
                       f"제목: {title}\n"
                       f"--------------------------\n"
                       f"{summary}\n"
                       f"--------------------------\n"
                       f"<a href='{full_link}'>👉 리포트 원문 보기</a>")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                print(f"✅ 전송 완료: {title}")
                await asyncio.sleep(1) # 전송 속도 제한

        except Exception as e:
            print(f"❌ {cat['name']} 처리 중 에러: {e}")

    print("🏁 모든 리포트 처리 완료")

if __name__ == "__main__":
    asyncio.run(main())
