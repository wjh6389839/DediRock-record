import os
import re
import csv
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TARGET_URL = "https://billing.dedirock.com/index.php/store/promo-vps-los-angeles"
CSV_FILE = "price_history.csv"
CHART_FILE = "price_trend.png"

def get_current_price():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        resp = requests.get(TARGET_URL, headers=headers, timeout=20)
        resp.raise_for_status()
        match = re.search(r'\$(\d+\.\d{2})\s*(?:USD)?', resp.text)
        return float(match.group(1)) if match else None
    except Exception as e:
        print(f"抓取失败: {e}")
        return None

def record_price(price):
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
        if today in df['date'].values:
            df.loc[df['date'] == today, 'price'] = price
            df.to_csv(CSV_FILE, index=False)
            return
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
            writer.writerow(['date', 'price'])
        writer.writerow([today, price])

def render_chart():
    if not os.path.exists(CSV_FILE):
        return
    df = pd.read_csv(CSV_FILE)
    if df.empty:
        return
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    min_price = df['price'].min()
    current_price = df['price'].iloc[-1]
    min_records = df[df['price'] == min_price]

    plt.figure(figsize=(9, 4.8), dpi=150)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    plt.plot(df['date'], df['price'], marker='o', color='#2563eb', linewidth=2, label='Daily Price ($)', zorder=3)
    plt.axhline(y=min_price, color='#16a34a', linestyle='--', linewidth=1.2, label=f'All-time Low: ${min_price:.2f}')
    plt.scatter(min_records['date'], min_records['price'], color='#dc2626', s=100, zorder=5, edgecolors='black', label='Lowest')
    
    for _, row in min_records.iterrows():
        plt.annotate(f"Lowest: ${row['price']:.2f}", (row['date'], row['price']),
                     textcoords="offset points", xytext=(0, 10), ha='center',
                     fontweight='bold', color='#dc2626')

    plt.title(f'DediRock LA VPS Price Tracker (Current: ${current_price:.2f} | Low: ${min_price:.2f})', fontsize=12, fontweight='bold')
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    plt.gcf().autofmt_xdate()
    plt.legend(loc='best')
    plt.tight_layout()
    plt.savefig(CHART_FILE)
    plt.close()

if __name__ == "__main__":
    price = get_current_price()
    if price is not None:
        record_price(price)
        render_chart()
