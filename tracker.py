import os
import re
import csv
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TARGET_URL = "https://billing.dedirock.com/index.php/store/promo-vps-los-angeles"
CSV_FILE = "price_history.csv"
CHART_FILE = "price_trend.png"

# 从 GitHub Actions 注入的环境变量中读取 SendKey
SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY")

def get_current_price():
    """抓取页面价格"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=20)
        response.raise_for_status()
        match = re.search(r'\$(\d+\.\d{2})\s*(?:USD)?', response.text)
        if match:
            price = float(match.group(1))
            print(f"[{datetime.now()}] 抓取到最新价格: ${price:.2f}")
            return price
        else:
            print("未能匹配到价格字段。")
            return None
    except Exception as e:
        print(f"网页抓取失败: {e}")
        return None

def check_and_notify_new_low(current_price):
    """对比历史最低价，若破新低则推送微信通知"""
    if not SERVERCHAN_SENDKEY:
        print("未检测到 SERVERCHAN_SENDKEY，跳过微信通知。")
        return

    # 检查是否有历史数据进行比对
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        print("首次运行，尚无历史数据比对。")
        return

    df = pd.read_csv(CSV_FILE)
    if df.empty or 'price' not in df.columns:
        return

    # 获取排除当天（如果已存在）之前的历史最低价
    today_str = datetime.now().strftime('%Y-%m-%d')
    history_df = df[df['date'].astype(str) != today_str]
    
    if history_df.empty:
        return

    historical_min = history_df['price'].min()

    # 核心判断：今日价格比历史最低还要低
    if current_price < historical_min:
        drop_amount = historical_min - current_price
        drop_rate = (drop_amount / historical_min) * 100
        
        title = f"🔥 降价提醒：VPS 刷新历史最低价！现仅 ${current_price:.2f}"
        content = (
            f"### ⚡ DediRock LA VPS 出现新低价！\n\n"
            f"- **今日现价**：`${current_price:.2f}` USD/年\n"
            f"- **历史原低价**：`${historical_min:.2f}` USD/年\n"
            f"- **降价幅度**：`${drop_amount:.2f}` (降幅 `{drop_rate:.1f}%`)\n"
            f"- **检查时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            f"[👉 点击直达购买页面]({TARGET_URL})"
        )
        
        send_wechat_push(title, content)
    else:
        print(f"今日价格 ${current_price:.2f} 未低于历史最低价 ${historical_min:.2f}，不触发微信通知。")

def send_wechat_push(title, desp):
    """调用 Server酱 API 发送微信模板消息"""
    api_url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
    payload = {
        "title": title,
        "desp": desp
    }
    try:
        resp = requests.post(api_url, data=payload, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            print("微信推送发送成功！")
        else:
            print(f"微信推送失败: {result.get('message')}")
    except Exception as e:
        print(f"微信通知接口请求异常: {e}")

def record_price(price):
    """保存或更新价格至 CSV"""
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        df = pd.read_csv(CSV_FILE)
        if today in df['date'].astype(str).values:
            df.loc[df['date'].astype(str) == today, 'price'] = price
            df.to_csv(CSV_FILE, index=False)
            return
    
    file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['date', 'price'])
        writer.writerow([today, price])

def render_chart():
    """生成带最低价高亮的走势图"""
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        return
    df = pd.read_csv(CSV_FILE)
    if df.empty:
        return

    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    min_price = df['price'].min()
    latest_row = df.iloc[-1]
    min_records = df[df['price'] == min_price]
    
    plt.figure(figsize=(10, 5), dpi=180)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    plt.plot(df['date'], df['price'], marker='o', markersize=5, color='#1d4ed8', linewidth=2.2, label='Daily Price ($ USD)', zorder=3)
    plt.axhline(y=min_price, color='#15803d', linestyle='--', linewidth=1.5, alpha=0.8, label=f'All-time Low: ${min_price:.2f}', zorder=2)
    plt.scatter(min_records['date'], min_records['price'], color='#dc2626', s=110, zorder=5, edgecolors='black', linewidth=1.2, label='Lowest Point')
    
    for _, row in min_records.iterrows():
        plt.annotate(
            f"Lowest: ${row['price']:.2f}",
            (row['date'], row['price']),
            textcoords="offset points",
            xytext=(0, 12),
            ha='center',
            fontsize=9.5,
            fontweight='bold',
            color='#b91c1c',
            bbox=dict(boxstyle="round,pad=0.25", fc="#fee2e2", ec="#ef4444", lw=0.8)
        )
    
    plt.title(f"DediRock LA VPS Price Trend\nLatest: ${latest_row['price']:.2f} | All-time Lowest: ${min_price:.2f}", fontsize=12, fontweight='bold', pad=12)
    plt.xlabel("Date", fontsize=10, labelpad=8)
    plt.ylabel("Annual Price ($ USD)", fontsize=10, labelpad=8)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    if len(df) > 1:
        plt.gcf().autofmt_xdate(rotation=30)
    plt.legend(loc='best', frameon=True, fontsize=9)
    plt.tight_layout()
    plt.savefig(CHART_FILE)
    plt.close()

if __name__ == "__main__":
    current_price = get_current_price()
    if current_price is not None:
        # 先比对历史低价并发送通知，再写入今日数据
        check_and_notify_new_low(current_price)
        record_price(current_price)
        render_chart()
