import os
import csv
import requests
from datetime import datetime

# 路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, 'data/duty_schedule.csv')

# 从环境变量读取配置
APP_ID = os.getenv('APP_ID')
APP_SECRET = os.getenv('APP_SECRET')
USER_OPENID = os.getenv('USER_OPENID')
print(f"APP_ID exists: {bool(APP_ID)}")  # 用于调试验证

def get_access_token():
    url = f'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APP_ID}&secret={APP_SECRET}'
    return requests.get(url).json().get('access_token')

def get_today_duty():
    today = datetime.now().strftime('%Y-%m-%d')
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['date'] == today:
                return {k:v for k,v in row.items() if k != 'date' and v.strip()}
        return None

def send_reminder(access_token, positions):
    url = f'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}'
    content = '\n'.join([f"{pos}：{name}" for pos, name in positions.items()])
    
    data = {
        "touser": USER_OPENID,
        "template_id": "GvAf-JiuA2St6W4lLqwzNzX7BUx3X9Dml0lTLEF03c4",
        "data": {
            "content": {"value": content},
            "date": {"value": datetime.now().strftime('%Y-%m-%d')}
        }
    }
    return requests.post(url, json=data).json()

if __name__ == "__main__":
    if duty_info := get_today_duty():
        token = get_access_token()
        print("发送结果:", send_reminder(token, duty_info))
    else:
        print("今日无值班安排")
