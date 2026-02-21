import os
import requests
import json

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

def test_gemini():
    # 가장 표준적인 경로 하나만 시도
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": "안녕? 너는 누구니?"}]}]}
    
    print(f"테스트 시작... 키 뒷자리: {GEMINI_API_KEY[-4:] if GEMINI_API_KEY else '없음'}")
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ 성공! Gemini 응답:", res.json()['candidates'][0]['content']['parts'][0]['text'])
        else:
            print(f"❌ 실패 (Code {res.status_code}): {res.text}")
    except Exception as e:
        print(f"❌ 연결 오류: {e}")

if __name__ == "__main__":
    test_gemini()
