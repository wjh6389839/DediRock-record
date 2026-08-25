import os
import re
import csv
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 无图形界面环境必须设置
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TARGET_URL = "https://billing.dedirock.com/index.php/store/promo-vps-los-angeles"
CSV_FILE = "price_history.csv"
CHART_FILE = "price_trend.png"

def get_current_price():
    """抓取页面价格"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=20)
        response.raise_for_status()
        
        # 正则匹配形如 $10.88 的价格文本
        match = re.search(r'\$(\d+\.\d{2})\s*(?:USD)?', response.text)
        if match:
            price = float(match.group(1))
            print(f"[{datetime.now()}] 成功获取价格: ${price:.2f} USD")
            return price
        else:
            print("警告：未能在网页中匹配到价格正则。")
            return None
    except Exception as e:
        print(f"请求失败: {e}")
        return None

def record_price(price):
    """保存或更新当日价格至 CSV"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        df = pd.read_csv(CSV_FILE)
        # 如果当天已记录过，覆盖更新
        if today in df['date'].astype(str).values:
            df.loc[df['date'].astype(str) == today, 'price'] = price
            df.to_csv(CSV_FILE, index=False)
            print(f"[{today}] 记录已更新为: ${price:.2f}")
            return
    
    # 写入新的一天
    file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['date', 'price'])
        writer.writerow([today, price])
    print(f"[{today}] 新增价格记录: ${price:.2f}")

def render_chart():
    """生成走势折线图并高亮历史最低价"""
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        print("未找到数据文件，跳过画图。")
        return
    
    df = pd.read_csv(CSV_FILE)
    if df.empty:
        return
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    min_price = df['price'].min()
    latest_row = df.iloc[-1]
    latest_price = latest_row['price']
    latest_date_str = latest_row['date'].strftime('%Y-%m-%d')
    min_records = df[df['price'] == min_price]
    
    # 画布与风格设置
    plt.figure(figsize=(10, 5), dpi=180)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # 1. 价格走势主折线
    plt.plot(df['date'], df['price'], marker='o', markersize=5, color='#1d4ed8', 
             linewidth=2.2, label='Daily Price ($ USD)', zorder=3)
    
    # 2. 最低价水平基准参考线
    plt.axhline(y=min_price, color='#15803d', linestyle='--', linewidth=1.5, 
                alpha=0.8, label=f'All-time Low: ${min_price:.2f}', zorder=2)
    
    # 3. 高亮所有最低价格的数据点
    plt.scatter(min_records['date'], min_records['price'], color='#dc2626', 
                s=110, zorder=5, edgecolors='black', linewidth=1.2, label='Lowest Price Point')
    
    # 4. 最低点悬浮标签
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
    
    # 坐标轴与标题
    plt.title(
        f"DediRock LA VPS Price Trend Tracker\nLatest ({latest_date_str}): ${latest_price:.2f}  |  All-time Lowest: ${min_price:.2f}",
        fontsize=12, fontweight='bold', pad=12
    )
    plt.xlabel("Date", fontsize=10, labelpad=8)
    plt.ylabel("Annual Price ($ USD)", fontsize=10, labelpad=8)
    
    # 日期轴格式优化
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    if len(df) > 1:
        plt.gcf().autofmt_xdate(rotation=30)
    
    plt.legend(loc='best', frameon=True, fontsize=9)
    plt.tight_layout()
    plt.savefig(CHART_FILE)
    plt.close()
    print("折线图已成功生成并保存。")

if __name__ == "__main__":
    price = get_current_price()
    if price is not None:
        record_price(price)
        render_chart()
