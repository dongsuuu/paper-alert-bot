import os
import re
import json
import requests
from datetime import datetime

BOT_TOKEN = os.environ["BUDGET_BOT_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

def extract_transactions(text):
    """카드 내역에서 거래 추출"""
    transactions = []
    
    # 패턴: 날짜 + 가맹점 + 금액
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 날짜 패턴 (MM/DD 또는 MM-DD)
        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})', line)
        
        # 금액 패턴 (숫자 + ,)
        amount_match = re.search(r'(\d{1,3}(?:,\d{3})+)', line.replace(',', ''))
        amount_match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', line)
        
        if date_match and amount_match:
            # 가맹점 추출 (날짜와 금액 사이)
            date_str = date_match.group(0)
            amount_str = amount_match.group(1).replace(',', '')
            
            # 가맹점 이름 추출
            merchant = line.replace(date_str, '').replace(amount_str, '').strip()
            merchant = re.sub(r'[^\w\s]', '', merchant).strip()
            
            if merchant and len(merchant) > 1:
                transactions.append({
                    'date': f"2025-{date_match.group(1).zfill(2)}-{date_match.group(2).zfill(2)}",
                    'merchant': merchant,
                    'amount': int(amount_str),
                    'category': categorize(merchant)
                })
    
    return transactions

def categorize(merchant):
    """가맹점별 카테고리 분류"""
    categories = {
        '식비': ['맥도날드', '버거킹', '스타벅스', '카페', '식당', '배달', '마트', '편의점', 'CU', 'GS25'],
        '교통': ['택시', '버스', '지하철', '카카오T', '우버', '주유', '주차'],
        '쇼핑': ['쿠팡', '11번가', 'G마켓', '아마존', '쇼핑', '백화점', '무신사'],
        '구독': ['넷플릭스', '유튜브', '멜론', '스포티파이', '구독'],
        '의료': ['병원', '약국', '의원', '치과', '피부과'],
        '기타': []
    }
    
    merchant_lower = merchant.lower()
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in merchant_lower:
                return cat
    return '기타'

def save_to_notion(transaction):
    """Notion에 저장"""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "이름": {"title": [{"text": {"content": transaction['merchant']}}]},
            "날짜": {"date": {"start": transaction['date']}},
            "금액": {"number": transaction['amount']},
            "카테고리": {"select": {"name": transaction['category']}},
            "결제수단": {"select": {"name": "카드"}}
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    return response.status_code == 200

def process_budget(text):
    """메인 처리"""
    transactions = extract_transactions(text)
    results = []
    
    for t in transactions:
        success = save_to_notion(t)
        results.append({
            'merchant': t['merchant'],
            'amount': t['amount'],
            'saved': success
        })
    
    return results

if __name__ == "__main__":
    # 테스트
    sample = """
    03/15 스타벅스 4,500
    03/15 카카오T 12,300
    03/16 CU편의점 2,100
    """
    results = process_budget(sample)
    print(f"처리 완료: {len(results)}건")
