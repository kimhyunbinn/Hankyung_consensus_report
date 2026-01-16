import os
import requests
import telegram
import asyncio
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- 환경 변수 설정 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

URL = "https://consensus.hankyung.com/analysis/list"
BASE_URL = "https://consensus.hankyung.com"
SENT_REPORTS_FILE = "sent_reports.txt"

def get_sent_ids():
    """이미 보낸 리포트 ID 목록을 파일에서 읽어옵니다."""
    if not os.path.exists(SENT_REPORTS_FILE):
        return set()
    try:
        with open(SENT_REPORTS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines() if line.strip())
    except Exception:
        return set()

def save_sent_id(report_id):
    """새로 보낸 리포트 ID를 파일에 저장합니다."""
    try:
        with open(SENT_REPORTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{report_id}\n")
    except Exception as e:
        print(f"파일 저장 중 에러: {e}")

async def send_telegram_message(message):
    """텔레그램 메시지를 전송합니다."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("에러: 텔레그램 설정(Token/ID)이 누락되었습니다.")
        return
    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")

async def main():
    # 1. 시간 및 날짜 설정
    now_kst = datetime.utcnow() + timedelta(hours=9)
    today_str = now_kst.strftime("%Y.%m.%d")
    
    # 오후 5시 이후에는 중단
    if now_kst.hour >= 17:
        print(f"[{now_kst.strftime('%H:%M')}] 오후 5시 이후이므로 작업을 종료합니다.")
        return

    sent_ids = get_sent_ids()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }

    try:
        # 2. 웹사이트 크롤링
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 테이블 행(row) 추출
        rows = soup.select('div.table_style01 table tbody tr')
        
        if not rows:
            print("리포트 목록을 찾을 수 없습니다.")
            return

        new_reports_found = 0

        # 3. 리포트 분석 및 전송
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5:
                continue
            
            report_date = cols[0].text.strip()
            category = cols[1].text.strip()
            
            # 오늘 날짜 + '산업' 카테고리 필터링
            if report_date == today_str and category == "산업":
                title_tag = cols[2].find('a')
                if not title_tag:
                    continue
                
                title = title_tag.text.strip()
                link = title_tag['href']
                
                # 고유 ID 추출 (중복 전송 방지용)
                match = re.search(r'report_idx=(\d+)', link)
                report_id = match.group(1) if match else title
                
                if report_id not in sent_ids:
                    full_link = BASE_URL + link if link.startswith('/') else link
                    securities = cols[5].text.strip()
                    
                    msg = (f"<b>🔔 새로운 산업 리포트!</b>\n\n"
                           f"기관: <b>{securities}</b>\n"
                           f"제목: {title}\n"
                           f"<a href='{full_link}'>👉 원문 보기</a>")
                    
                    await send_telegram_message(msg)
                    save_sent_id(report_id)
                    sent_ids.add(report_id)
                    new_reports_found += 1
                    print(f"전송 완료: {title}")

        print(f"[{now_kst.strftime('%H:%M')}] 탐색 완료. 새 리포트 {new_reports_found}건 발견.")

    except Exception as e:
        print(f"실행 중 오류 발생: {e}")

if __name__ == "__main__":
    # 비동기 실행
    asyncio.run(main())    if now_kst.hour >= 17:
        print("오후 5시 이후이므로 종료합니다.")
        return

    sent_ids = get_sent_ids()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        response = requests.get(URL, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('div.table_style01 table tbody tr')
        
        new_reports_found = 0

        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            
            report_date = cols[0].text.strip()
            category = cols[1].text.strip()
            
            # 오늘 날짜 + '산업' 카테고리
            if report_date == today_str and category == "산업":
                title_tag = cols[2].find('a')
                if not title_tag: continue
                
                title = title_tag.text.strip()
                link = title_tag['href']
                
                # 고유 ID 추출 (예: report_idx=645432)
                import re
                match = re.search(r'report_idx=(\d+)', link)
                report_id = match.group(1) if match else title
                
                # 3. 중복 확인: 이미 보낸 ID가 아니면 전송
                if report_id not in sent_ids:
                    full_link = BASE_URL + link if link.startswith('/') else link
                    securities = cols[5].text.strip()
                    
                    msg = (f"<b>🔔 새로운 산업 리포트 발견!</b>\n\n"
                           f"기관: <b>{securities}</b>\n"
                           f"제목: {title}\n"
                           f"<a href='{full_link}'>👉 원문 보기</a>")
                    
                    await send_telegram_message(msg)
                    save_sent_id(report_id) # 보낸 목록에 추가
                    sent_ids.add(report_id)
                    new_reports_found += 1
                    print(f"새 리포트 전송: {title}")

        if new_reports_found == 0:
            print(f"[{now_kst.strftime('%H:%M')}] 새로운 리포트가 없습니다.")
        else:
            print(f"총 {new_reports_found}개의 새 리포트를 보냈습니다.")

    except Exception as e:
        print(f"에러 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())    
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




