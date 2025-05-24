# -*- coding: utf-8 -*-
import os
import csv
import json
import logging
import sys
import time
from datetime import datetime
from typing import Dict, Optional, List

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
    global APP_ID, APP_SECRET, USER_OPENIDS, TEMPLATE_ID
    
    # 基础配置
    APP_ID = os.getenv("APP_ID")
    APP_SECRET = os.getenv("APP_SECRET")
    TEMPLATE_ID = os.getenv("TEMPLATE_ID")
    
    # 多用户配置（逗号分隔）
    openids = os.getenv("USER_OPENIDS", "")
    USER_OPENIDS = [oid.strip() for oid in openids.split(",") if oid.strip()]

    # 验证关键配置
    missing = []
    if not APP_ID: missing.append("APP_ID")
    if not APP_SECRET: missing.append("APP_SECRET")
    if not TEMPLATE_ID: missing.append("TEMPLATE_ID")
    if not USER_OPENIDS: missing.append("USER_OPENIDS")
    
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
        response.raise_for_status()
        
        data = response.json()
        if "access_token" not in data:
            logging.error(f"获取Token失败: {data.get('errmsg', '未知错误')}")
            return None
            
        return data["access_token"]
        
    except requests.exceptions.RequestException as e:
        logging.error(f"网络请求失败: {str(e)}")
    except json.JSONDecodeError:
        logging.error("微信API返回无效的JSON响应")
    except Exception as e:
        logging.error(f"获取Token异常: {str(e)}")
    return None

def normalize_date(date_str: str) -> Optional[str]:
    """标准化日期格式（支持多种输入格式）"""
    date_formats = [
        "%Y-%m-%d", "%Y-%-m-%-d", 
        "%Y/%m/%d", "%Y%m%d"
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    logging.warning(f"无法解析的日期格式: {date_str}")
    return None

def get_today_duty() -> Optional[Dict[str, str]]:
    """获取今日值班信息"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        logging.info(f"今日日期: {today}")

        if not os.path.exists(CSV_PATH):
            raise FileNotFoundError(f"CSV文件不存在: {CSV_PATH}")

        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if "date" not in reader.fieldnames:
                raise ValueError("CSV文件缺少date列")

            for row in reader:
                csv_date = normalize_date(row.get("date", ""))
                if csv_date == today:
                    return {
                        k: v.strip()
                        for k, v in row.items()
                        if k != "date" and v.strip()
                    }
        return None
        
    except Exception as e:
        logging.error(f"读取值班表失败: {str(e)}")
        raise

def format_positions(positions: Dict[str, str]) -> Dict[str, dict]:
    """
    生成6个标准化的模板字段
    - 按岗位名称排序确保稳定性
    - 不足6个用（无）填充
    - 超6个截断并记录警告
    """
    sorted_positions = sorted(positions.items())
    position_data = {}
    
    # 生成position1~position6
    for idx in range(1, 7):
        pos_name = f"position{idx}"
        if idx <= len(sorted_positions):
            pos, name = sorted_positions[idx-1]
            position_data[pos_name] = {
                "value": f"【{pos}】{name}",
                "color": "#173177"
            }
        else:
            position_data[pos_name] = {
                "value": "（无）",
                "color": "#666666"
            }
    
    if len(sorted_positions) > 6:
        logging.warning(f"检测到{len(sorted_positions)}个岗位，已截断前6个")
        
    return position_data

def send_reminder(access_token: str, positions: Dict[str, str]) -> Dict[str, dict]:
    """批量发送消息给多个用户"""
    results = {}
    
    try:
        if not access_token:
            raise ValueError("无效的access_token")
            
        position_data = format_positions(positions)
        base_data = {
            "date": {
                "value": datetime.now().strftime("%Y-%m-%d"),
                "color": "#173177"
            }
        }

        # 遍历所有用户发送
        for idx, openid in enumerate(USER_OPENIDS, 1):
            try:
                # 添加请求间隔（1秒/次）
                if idx > 1:
                    time.sleep(1)

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

                # 记录发送结果
                if result.get("errcode") == 0:
                    logging.info(f"✅ 发送成功至 {openid[:4]}...")
                else:
                    logging.error(f"❌ {openid[:4]}... 失败: {result.get('errmsg')}")

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                results[openid] = {"error": error_msg}
                logging.error(f"❌ {openid[:4]}... 异常: {error_msg}")

    except Exception as e:
        logging.error(f"发送流程异常: {str(e)}", exc_info=True)
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
                # 发送消息并获取结果
                send_results = send_reminder(token, duty_info)
                
                # 统计结果
                success = sum(1 for res in send_results.values() if res.get("errcode") == 0)
                failed = len(USER_OPENIDS) - success
                
                # 输出汇总
                logging.info(f"\n发送汇总：成功 {success} 人 / 失败 {failed} 人")
                if failed > 0:
                    logging.error("失败详情：")
                    for oid, res in send_results.items():
                        if res.get("errcode") != 0:
                            errmsg = res.get("errmsg") or res.get("error")
                            logging.error(f"• {oid[:6]}... : {errmsg}")
            else:
                logging.error("获取微信Token失败")
        else:
            logging.info("今日无值班安排")
            
    except Exception as e:
        logging.error(f"主程序异常: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        logging.info("任务执行结束\n" + "="*40)
