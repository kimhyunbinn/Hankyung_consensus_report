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
    
    # [중요 수정] v1beta1 엔드포인트로 변경하여 모델 인식률을 높임
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    
    # 텍스트 전처리 (불필요한 공백 및 특수문자 제거)
    clean_text = text[:8000].replace('"', "'").replace('\n', ' ')
    prompt = f"금융 전문가로서 다음 리포트의 핵심 투자 포인트 3가지를 요약해줘. 한국어로 작성하고 전문적인 어조를 사용해:\n\n{clean_text}"
    
    # [수정] 구글 API 표준 페이로드 구조
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "topK": 40
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            res_data = response.json()
            return res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            # 여전히 에러가 난다면 상세 내용을 출력
            return f"❌ API 오류 (Code: {response.status_code})\n메시지: {response.text[:200]}"
    except Exception as e:
        return f"❌ 통신 오류: {str(e)}"

def get_pdf_text(pdf_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers, timeout=30)
        with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
            full_text = ""
            # 본문 파악을 위해 1~3페이지 추출
            for page in doc[:3]:
                full_text += page.get_text()
            return full_text
    except:
        return ""

async def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    print("🚀 [수동 모드] 최신 리포트 발송 테스트 시작...")
    
    for cat in TARGET_CATEGORIES:
        # 각 카테고리 게시판 접속
        url = f"https://consensus.hankyung.com/analysis/list?skinType={cat['type']}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            # 상단 공지사항을 제외한 실제 최신 리포트 3개만 선택
            rows = soup.select('tr')[1:4] 
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                a_tag = row.find('a', href=re.compile(r'report_idx='))
                if not a_tag: continue
                
                title = a_tag.get_text(strip=True)
                
                # [출처 찾기] 숫자가 포함되지 않은 텍스트 칸을 증권사로 판단
                provider = "출처미상"
                for i in [4, 5, 3]:
                    val = cols[i].get_text(strip=True)
                    if val and not any(c.isdigit() for c in val.replace('.','')):
                        provider = val
                        break
                
                full_link = BASE_URL + a_tag['href'] if a_tag['href'].startswith('/') else a_tag['href']
                
                print(f"🔍 [{provider}] {title} 요약 시도 중...")
                
                # PDF 텍스트 추출 및 요약 수행
                pdf_text = get_pdf_text(full_link)
                summary = get_summary_rest(pdf_text) if len(pdf_text) > 100 else "❌ PDF 텍스트 추출 실패"
                
                msg = (f"<b>{cat['icon']} {cat['name']} 리포트 (수동 테스트)</b>\n\n"
                       f"출처: <b>{provider}</b>\n"
                       f"제목: {title}\n"
                       f"--------------------------\n"
                       f"{summary}\n"
                       f"--------------------------\n"
                       f"<a href='{full_link}'>👉 리포트 원문 보기</a>")
                
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode='HTML', disable_web_page_preview=True)
                await asyncio.sleep(2) # 전송 간격 유지

        except Exception as e:
            print(f"❌ {cat['name']} 처리 오류: {e}")

    print("🏁 모든 리포트 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())
