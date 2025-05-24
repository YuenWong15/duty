# -*- coding: utf-8 -*-
import os
import re
import csv
import json
import logging
import sys
import time
from datetime import datetime
from typing import Dict, Optional, List

import requests

# -------------------------- 初始化配置 --------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# -------------------------- 环境变量配置 --------------------------
def load_env_vars() -> None:
    """加载并验证环境变量"""
    global APP_ID, APP_SECRET, USER_OPENIDS, TEMPLATE_ID
    
    APP_ID = os.getenv("APP_ID")
    APP_SECRET = os.getenv("APP_SECRET")
    TEMPLATE_ID = os.getenv("TEMPLATE_ID")
    
    openids = os.getenv("USER_OPENIDS", "")
    USER_OPENIDS = [oid.strip() for oid in openids.split(",") if oid.strip()]

    missing = []
    if not APP_ID: missing.append("APP_ID")
    if not APP_SECRET: missing.append("APP_SECRET")
    if not TEMPLATE_ID: missing.append("TEMPLATE_ID")
    if not USER_OPENIDS: missing.append("USER_OPENIDS")
    
    if missing:
        raise EnvironmentError(f"缺少环境变量: {', '.join(missing)}")

# -------------------------- 路径配置 --------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, "data/duty_schedule.csv")

# -------------------------- 核心功能 --------------------------
def get_access_token() -> Optional[str]:
    """获取微信access_token（带重试机制）"""
    for _ in range(3):
        try:
            url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={APP_ID}&secret={APP_SECRET}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if "access_token" in data:
                return data["access_token"]
            logging.error(f"获取Token失败: {data.get('errmsg', '未知错误')}")
        except Exception as e:
            logging.warning(f"Token请求失败: {str(e)}")
            time.sleep(2)
    return None

def normalize_date(date_str: str) -> Optional[str]:
    """标准化日期格式"""
    try:
        cleaned = re.sub(r"[^0-9]", "", date_str)
        if len(cleaned) == 8:
            return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:8]}"
        return datetime.strptime(cleaned, "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return None

def get_today_duty() -> Optional[Dict[str, str]]:
    """获取今日值班信息（带数据校验）"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        if not os.path.exists(CSV_PATH):
            raise FileNotFoundError(f"CSV文件不存在: {CSV_PATH}")

        required_columns = {'date', '数据质控', '大数据云平台保障', 
                          '信息安全保障', '运行监控与视频会商', 
                          '大夜班1', '大夜班2'}
        
        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not required_columns.issubset(reader.fieldnames):
                missing = required_columns - set(reader.fieldnames)
                raise ValueError(f"CSV文件缺少必要列: {', '.join(missing)}")

            for row in reader:
                if normalize_date(row.get('date', '')) == today:
                    return {k: v.strip() for k, v in row.items() if k != 'date'}
        return None
    except Exception as e:
        logging.error(f"读取值班表失败: {str(e)}")
        raise

def format_positions(positions: Dict[str, str]) -> Dict[str, dict]:
    """格式化岗位信息（修正后的版本）"""
    fixed_order = [
        ('数据质控', 8),
        ('大数据云平台保障', 10),
        ('信息安全保障', 8),
        ('运行监控与视频会商', 12),
        ('大夜班1', 8),
        ('大夜班2', 8)
    ]
    
    position_data = {}
    for idx in range(1, 7):
        key, width = fixed_order[idx-1]
        name = positions.get(key, "（暂无）")
        
        # 计算需要填充的空格
        current_width = len(key.encode('gbk'))
        padding = '　' * ((width - current_width) // 2)
        
        # 生成对齐后的文本
        aligned_text = f"{key}{padding}｜{name}"
        
        position_data[f"position{idx}"] = {
            "value": aligned_text,
            "color": "#173177" if name != "（暂无）" else "#FF0000"
        }
    return position_data

def send_reminder(access_token: str, positions: Dict[str, str]) -> Dict[str, dict]:
    """发送提醒消息（修正后的版本）"""
    # 添加调试输出
    position_data = format_positions(positions)
    logging.info("调试数据 - 格式化后的岗位信息:")
    for k, v in position_data.items():
        logging.info(f"{k}: {v['value']}")

    results = {}
    try:
        base_data = {
            "date": {
                "value": datetime.now().strftime("%Y-%m-%d"),
                "color": "#173177"
            }
        }

        for idx, openid in enumerate(USER_OPENIDS, 1):
            try:
                if idx > 1:
                    time.sleep(1)  # 防止频率限制

                payload = {
                    "touser": openid,
                    "template_id": TEMPLATE_ID,
                    "data": {**base_data, **position_data}
                }

                url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
                response = requests.post(url, json=payload, timeout=15)
                response.raise_for_status()
                
                result = response.json()
                results[openid] = result

                if result.get("errcode") == 0:
                    logging.info(f"✅ 发送成功至 {openid[:4]}...")
                else:
                    logging.error(f"❌ {openid[:4]}... 失败: {result.get('errmsg')}")
            except Exception as e:
                logging.error(f"❌ {openid[:4]}... 异常: {str(e)}")
                results[openid] = {"error": str(e)}

    except Exception as e:
        logging.error(f"发送流程异常: {str(e)}")
        return {"_global": {"error": str(e)}}
    
    return results

# -------------------------- 主程序 --------------------------
if __name__ == "__main__":
    try:
        load_env_vars()
        logging.info("="*40)
        logging.info(f"开始执行值班提醒 | 接收用户数: {len(USER_OPENIDS)}")
        
        if duty_info := get_today_duty():
            logging.info(f"今日值班信息: {duty_info}")
            if token := get_access_token():
                send_results = send_reminder(token, duty_info)
                
                success = sum(1 for res in send_results.values() if res.get("errcode") == 0)
                failed = len(USER_OPENIDS) - success
                
                logging.info(f"\n发送汇总：成功 {success} 人 / 失败 {failed} 人")
                if failed > 0:
                    logging.error("失败详情：")
                    for oid, res in send_results.items():
                        if res.get("errcode") != 0:
                            logging.error(f"• {oid[:6]}... : {res.get('errmsg')}")
            else:
                logging.error("获取微信Token失败")
        else:
            logging.info("今日无值班安排")
            
    except Exception as e:
        logging.error(f"主程序异常: {str(e)}")
        sys.exit(1)
    finally:
        logging.info("任务执行结束\n" + "="*40)
