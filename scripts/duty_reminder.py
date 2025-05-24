# -*- coding: utf-8 -*-
import os
import csv
import json
import logging
import sys
from datetime import datetime
from typing import Dict, Optional

import requests

# -------------------------- 初始化配置 --------------------------
# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# -------------------------- 环境变量配置 --------------------------
def load_env_vars() -> None:
    """验证并加载环境变量"""
    global APP_ID, APP_SECRET, USER_OPENID, TEMPLATE_ID
    APP_ID = os.getenv("APP_ID")
    APP_SECRET = os.getenv("APP_SECRET")
    USER_OPENID = os.getenv("USER_OPENID")
    TEMPLATE_ID = os.getenv("TEMPLATE_ID")

    # 验证关键配置是否存在
    missing = []
    if not APP_ID: missing.append("APP_ID")
    if not APP_SECRET: missing.append("APP_SECRET")
    if not USER_OPENID: missing.append("USER_OPENID")
    if not TEMPLATE_ID: missing.append("TEMPLATE_ID")
    
    if missing:
        raise EnvironmentError(f"缺少必需环境变量: {', '.join(missing)}")

# -------------------------- 路径配置 --------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data/duty_schedule.csv")

# -------------------------- 核心功能 --------------------------
def get_access_token() -> Optional[str]:
    """获取微信access_token（带完整错误处理）"""
    try:
        url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APP_ID}&secret={APP_SECRET}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # 触发HTTP错误状态
        
        data = response.json()
        if "access_token" not in data:
            logging.error(f"获取Token失败: {data.get('errmsg', '未知错误')}")
            return None
            
        return data["access_token"]
        
    except requests.exceptions.RequestException as e:
        logging.error(f"网络请求失败: {str(e)}")
    except json.JSONDecodeError:
        logging.error("微信API返回无效的JSON响应")
    except KeyError:
        logging.error("微信API响应缺少access_token字段")
    return None

def normalize_date(date_str: str) -> Optional[str]:
    """标准化日期格式（支持多种输入格式）"""
    date_formats = [
        "%Y-%m-%d",   # 标准格式
        "%Y-%-m-%-d",  # 无前导零（Linux）
        "%Y/%m/%d",    # 斜杠格式
        "%Y%m%d"       # 紧凑格式
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")  # 统一输出标准格式
        except ValueError:
            continue
    logging.warning(f"无法解析的日期格式: {date_str}")
    return None

def get_today_duty() -> Optional[Dict[str, str]]:
    """获取今日值班信息（增强健壮性版本）"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        logging.info(f"今日日期: {today}")

        if not os.path.exists(CSV_PATH):
            raise FileNotFoundError(f"CSV文件不存在: {CSV_PATH}")

        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            # 单次读取并缓存内容
            content = f.read()
            logging.debug(f"CSV原始内容:\n{content}")
            f.seek(0)
            
            reader = csv.DictReader(f)
            if "date" not in reader.fieldnames:
                raise ValueError("CSV文件缺少date列")

            for row in reader:
                csv_date = normalize_date(row.get("date", ""))
                if not csv_date:
                    continue
                
                logging.debug(f"比对日期: CSV={csv_date} vs TODAY={today}")
                if csv_date == today:
                    # 过滤空值和date列
                    return {
                        k: v.strip()
                        for k, v in row.items()
                        if k != "date" and v.strip()
                    }
        return None
        
    except Exception as e:
        logging.error(f"读取值班表失败: {str(e)}")
        raise

def send_reminder(access_token: str, positions: Dict[str, str]) -> Dict:
    """发送微信模板消息（生产级错误处理）"""
    try:
        # ================== 参数校验 ==================
        if not access_token:
            raise ValueError("无效的access_token")
        if not positions or not isinstance(positions, dict):
            raise ValueError("positions必须是非空字典")

        # ================== 数据准备 ==================
        positions_str = "\n".join(
            [f"【{pos}】{name}" for pos, name in positions.items() if name]
        )
        if not positions_str:
            logging.warning("所有岗位信息均为空")
            return {"errcode": -1, "errmsg": "无有效值班信息"}

        payload = {
            "touser": USER_OPENID,
            "template_id": TEMPLATE_ID,
            "data": {
                "positions": {
                    "value": positions_str,
                    "color": "#173177"
                },
                "date": {
                    "value": datetime.now().strftime("%Y-%m-%d"),
                    "color": "#173177"
                }
            }
        }

        # ================== 请求发送 ==================
        url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
        logging.debug(f"请求URL: {url}")
        logging.debug(f"请求体:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()

        # ================== 响应处理 ==================
        result = response.json()
        logging.debug(f"微信响应: {json.dumps(result, indent=2)}")

        if result.get("errcode", -1) != 0:
            errmsg = result.get("errmsg", "未知错误")
            raise RuntimeError(f"微信API错误: [{result['errcode']}] {errmsg}")

        return result

    except requests.exceptions.RequestException as e:
        logging.error(f"网络请求异常: {str(e)}")
        return {"errcode": -2, "errmsg": str(e)}
    except json.JSONDecodeError:
        logging.error("响应内容不是有效JSON")
        return {"errcode": -3, "errmsg": "Invalid JSON response"}
    except Exception as e:
        logging.error(f"未处理的异常: {str(e)}", exc_info=True)
        return {"errcode": -4, "errmsg": str(e)}

# -------------------------- 主程序 --------------------------
if __name__ == "__main__":
    try:
        load_env_vars()  # 必须在最前面调用
        logging.info("="*40)
        logging.info("开始执行值班提醒任务")
        
        if duty_info := get_today_duty():
            logging.info(f"今日值班信息: {duty_info}")
            if token := get_access_token():
                result = send_reminder(token, duty_info)
                if result.get("errcode") == 0:
                    logging.info("✅ 消息发送成功")
                else:
                    logging.error(f"❌ 发送失败: {result.get('errmsg')}")
            else:
                logging.error("获取微信Token失败")
        else:
            logging.info("今日无值班安排")
            
    except Exception as e:
        logging.error(f"主程序异常: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        logging.info("任务执行结束\n" + "="*40)
