#!/usr/bin/env python
# coding: utf-8

# In[2]:


pip install requests beautifulsoup4


# In[6]:


import requests
from bs4 import BeautifulSoup
import datetime
import os

# 텔레그램 설정 (실제 사용 시 환경변수로 관리하는 것이 보안상 좋습니다)
# 로컬에서 테스트할 때는 직접 입력하세요.
TELEGRAM_TOKEN = '8534796698:AAEwrXgBe3RbLRgalMGllE2jsUsgL0y2K_E'
CHAT_ID = '1594303792'

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    requests.post(url, json=payload)

def scrape_hankyung_consensus():
    # 한경 컨센서스 메인 페이지 (전체 리포트 목록)
    url = "https://markets.hankyung.com/consensus"
    
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 오늘 날짜 구하기 (YYYY-MM-DD 포맷)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 리포트 리스트 테이블의 행(row)들을 가져옵니다.
    # 사이트 구조에 따라 클래스명이 다를 수 있으나, 일반적으로 table body 안의 tr을 찾습니다.
    rows = soup.select("div.table_style01 table tbody tr")
    
    report_count = 0
    message_buffer = f"📊 <b>오늘({today})의 산업 리포트</b>\n\n"
    
    for row in rows:
        try:
            # 각 행의 데이터 추출
            # 구조: [작성일, 분류, 제목, 적정주가, 투자의견, 작성자, 제공출처] 순서라고 가정
            # 실제 HTML 구조에 맞춰 인덱싱이 필요합니다. 
            cols = row.find_all("td")
            
            # 데이터가 없는 빈 행 등은 건너뜀
            if len(cols) < 5:
                continue

            date = cols[0].text.strip()      # 작성일
            category = cols[1].text.strip()  # 분류 (산업, 기업, 시장 등)
            title_tag = cols[2].find("a")    # 제목 태그
            title = title_tag.text.strip()   # 제목 텍스트
            link = "https://markets.hankyung.com" + title_tag['href'] # 링크
            writer = cols[5].text.strip()    # 제공출처/작성자
            
            # 1. 날짜가 오늘인지 확인
            # (만약 주말이라 리포트가 없다면, 테스트를 위해 이 조건을 잠시 주석처리 하세요)
            if date != today:
                continue
                
            # 2. 분류가 '산업'인지 확인
            if category != "산업":
                continue
            
            # 메시지 구성
            message_buffer += f"🔹 <b>{title}</b>\n"
            message_buffer += f"   - 출처: {writer}\n"
            message_buffer += f"   - <a href='{link}'>원문 보러가기</a>\n\n"
            report_count += 1
            
        except Exception as e:
            print(f"Error parsing row: {e}")
            continue

    if report_count > 0:
        send_telegram_message(message_buffer)
        print(f"총 {report_count}개의 산업 리포트를 전송했습니다.")
    else:
        print("오늘 올라온 산업 리포트가 없습니다.")
        # 필요하다면 '리포트 없음' 알림을 보낼 수도 있습니다.

if __name__ == "__main__":
    scrape_hankyung_consensus()


# In[ ]:




