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

def normalize_date(date_str):
    """处理不同格式的日期字符串"""
    try:
        # 尝试解析带前导零的日期
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        try:
            # 尝试解析无前导零的日期
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except:
            return None
            
def get_today_duty():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n==== 今日日期 ====\n{today}")
    
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        print(f"\n==== CSV文件完整内容 ====\n{f.read()}")
        f.seek(0)
        
        reader = csv.DictReader(f)
        print(f"\n==== CSV列名 ====\n{reader.fieldnames}")
        
        for row in reader:
            print(f"\n当前检查行: {row}")
            if row.get('date', '').strip() == today:
                print("!!! 找到匹配记录 !!!")
                return {k:v.strip() for k,v in row.items() if k != 'date' and v.strip()}
        return None

def send_reminder(access_token, positions):
    url = f'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}'
    url = f'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}'
    
    # 生成岗位信息字符串（关键修改点）
    positions_str = "\n".join([
        f"【{position}】{names}" 
        for position, names in positions.items()
    ])
    
    data = {
        "touser": USER_OPENID,
        "template_id": TEMPLATE_ID,
        "data": {
            "positions": {  # 必须与模板中的{{positions.DATA}}完全匹配
                "value": positions_str,
                "color": "#173177"
            },
            "date": {  # 必须与模板中的{{date.DATA}}完全匹配
                "value": datetime.now().strftime('%Y-%m-%d'),
                "color": "#173177"
            }
        }
    }
    
    # 打印调试信息
    print("\n==== 发送的模板数据 ====")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    response = requests.post(url, json=data)
    return response.json()

if __name__ == "__main__":
    if duty_info := get_today_duty():
        token = get_access_token()
        print("发送结果:", send_reminder(token, duty_info))
    else:
        print("今日无值班安排")
