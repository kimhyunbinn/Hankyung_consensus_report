import os
import requests
import telegram
import asyncio

# 환경 변수 로드
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

async def final_check():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    
    # API 활성화 여부 최종 확인용 주소
    test_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": "안녕? 너는 이제 준비가 됐니? 대답해줘."}]}]
    }
    
    try:
        res = requests.post(test_url, json=payload, timeout=10)
        if res.status_code == 200:
            answer = res.json()['candidates'][0]['content']['parts'][0]['text']
            msg = f"✅ 성공! Gemini가 대답했습니다:\n\n{answer}"
        else:
            msg = f"❌ 여전히 오류 (Code {res.status_code})\n메시지: {res.text[:200]}"
            
        await bot.send_message(chat_id=CHAT_ID, text=msg)
    except Exception as e:
        await bot.send_message(chat_id=CHAT_ID, text=f"❌ 연결 오류: {str(e)}")

if __name__ == "__main__":
    asyncio.run(final_check())
