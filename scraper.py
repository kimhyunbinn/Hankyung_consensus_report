import os
import requests
import telegram
import asyncio
import re
import fitz  # PyMuPDF
import json
from bs4 import BeautifulSoup
from io import BytesIO

# --- 설정 (GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

BASE_URL = "https://consensus.hankyung.com"

TARGET_CATEGORIES = [
    {"name": "산업", "icon": "🏗️", "type": "industry"},
    {"name": "시장", "icon": "📈", "type": "market"}
]

# --- Gemini API (404 오류 해결을 위한 경로 수정) ---
def get_summary_rest(text):
    if not GEMINI_API_KEY: return "❌ API 키가 설정되지 않았습니다."
    
    # [수정] 404 에러 방지를 위한 가장 확실한 v1beta 엔드포인트
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    
    # 텍스트 전처리
    clean_text = text[:8000].replace('"', "'").replace('\n', ' ')
    prompt = f"금융 전문가로서 다음 리포트의 투자 핵심 3가지를 전문적인 한국어로 요약해줘:\n\n{clean_text}"
    
    # [수정] 구글이 요구하는 표준 JSON 구조
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            res_data = response.json()
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            # 404가 또 뜰 경우를 대비한 상세 로그 출력
            return f"❌ API 오류 (Code: {response.status_code})\n메시지: {response.text[:200]}"
    except Exception as e:
        return f"❌ 통신 오류: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers, timeout=30)
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            full_text = ""
            for page in doc[:3]: # 상위 3페이지만
                full_text += page.get_text()
            return full_text
    except:
        return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    print("🚀 [수동 모드] 최신 리포트 요약 테스트 시작...")
    
    for cat in TARGET_CATEGORIES:
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['type']}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            # 상단 공지사항을 제외한 실제 최신 리포트 3개 추출
            rows = soup.select('tr')[1:4] 
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                title = a_tag.get_text(strip=True)
                
                # [출처 찾기] 숫자가 아닌 텍스트가 있는 칸을 탐색
                provider = "출처미상"
                for i in [4, 5, 3]:
                    val = cols[i].get_text(strip=True)
                    if val and not any(c.isdigit() for c in val.replace('.','')):
                        provider = val
                        break
                
                full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
                
                print(f"🔍 요약 시도: {title}")
                pdf_text = get_pdf_text(full_link)
                summary = get_summary_rest(pdf_text) if len(pdf_text) > 100 else "❌ PDF 텍스트 추출 실패"
                
                msg = (f"<b>{cat['icon']} {cat['name']} 리포트 (수동 확인)</b>\n\n"
                       f"출처: <b>{provider}</b>\n"
                       f"제목: {title}\n"
                       f"--------------------------\n"
                       f"{summary}\n"
                       f"--------------------------\n"
                       f"<a href='{full_link}'>👉 리포트 원문 보기</a>")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                await asyncio.sleep(2) # 전송 간격

        except Exception as e:
            print(f"❌ {cat['name']} 처리 중 오류: {e}")

    print("🏁 테스트 완료")

if __name__ == "__main__":
    asyncio.run(main())
