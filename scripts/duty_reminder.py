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
    """发送微信模板消息（带完整错误处理）"""
    try:
        # ================== 1.参数校验 ==================
        if not access_token:
            raise ValueError("access_token不能为空")
            
        if not positions or not isinstance(positions, dict):
            raise ValueError("positions参数必须是非空字典")

        # ================== 2.构造请求数据 ==================
        url = f'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}'
        
        # 处理岗位信息（含空值过滤）
        positions_str = "\n".join([
            f"【{position}】{names}" 
            for position, names in positions.items()
            if names.strip()  # 过滤空值
        ])
        
        # 当没有有效岗位时触发警告
        if not positions_str:
            logging.warning("所有岗位值班信息均为空")
            return {"errcode": -1, "errmsg": "无有效值班信息"}

        data = {
            "touser": USER_OPENID,
            "template_id": TEMPLATE_ID,
            "data": {
                "positions": {
                    "value": positions_str,
                    "color": "#173177"
                },
                "date": {
                    "value": datetime.now().strftime('%Y-%m-%d'),
                    "color": "#173177"
                }
            }
        }

        # ================== 3.请求前日志 ==================
        logging.info("\n==== 请求数据详情 ====")
        logging.info(f"API地址: {url}")
        logging.info(f"请求体:\n{json.dumps(data, indent=2, ensure_ascii=False)}")

        # ================== 4.发送请求 ==================
        response = requests.post(
            url, 
            json=data,
            timeout=10  # 添加超时控制
        )
        
        # ================== 5.响应处理 ==================
        # 强制检查HTTP状态码
        if response.status_code != 200:
            raise requests.HTTPError(
                f"HTTP错误 {response.status_code}: {response.reason}"
            )

        result = response.json()
        
        logging.info("\n==== 微信API响应 ====")
        logging.info(f"状态码: {response.status_code}")
        logging.info(f"响应内容:\n{json.dumps(result, indent=2, ensure_ascii=False)}")

        # 业务逻辑错误检查
        if result.get('errcode') != 0:
            raise RuntimeError(
                f"微信API错误: [{result.get('errcode')}] {result.get('errmsg')}"
            )
            
        return result

    except requests.exceptions.RequestException as e:
        logging.error(f"网络请求失败: {str(e)}")
        return {"errcode": -2, "errmsg": str(e)}
        
    except json.JSONDecodeError:
        logging.error("响应内容不是有效的JSON格式")
        return {"errcode": -3, "errmsg": "Invalid JSON response"}
        
    except Exception as e:
        logging.error(f"未捕获异常: {str(e)}", exc_info=True)
        return {"errcode": -4, "errmsg": str(e)}

if __name__ == "__main__":
    if duty_info := get_today_duty():
        token = get_access_token()
        print("发送结果:", send_reminder(token, duty_info))
    else:
        print("今日无值班安排")
