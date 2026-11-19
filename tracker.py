import os
import re
import csv
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from playwright.sync_api import sync_playwright

TARGET_URL = "https://billing.dedirock.com/index.php/store/promo-vps-los-angeles"
CSV_FILE = "price_history.csv"
CHART_FILE = "price_trend.png"
TZ = ZoneInfo("America/Los_Angeles")  # 可按需改为 "Asia/Shanghai" 或 "UTC"

# 从 GitHub Actions 注入的环境变量中读取 SendKey
SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY")


def now_tz():
    """返回指定时区的当前时间"""
    return datetime.now(TZ)


def extract_price_from_html(html: str):
    """从渲染后的可见文本中提取价格"""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    visible_text = soup.get_text(" ", strip=True)

    # 优先匹配带货币单位或计费周期的价格
    candidates = re.findall(
        r'(?<!\w)\$(\d+\.\d{2})(?:\s*(?:USD|/yr|/mo|per\s+year|annually))?',
        visible_text,
        flags=re.IGNORECASE,
    )
    if not candidates:
        candidates = re.findall(r'(?<!\w)\$(\d+\.\d{2})', visible_text)

    prices = []
    for val in candidates:
        p = float(val)
        if p > 0:
            prices.append(p)

    return min(prices) if prices else None


def get_current_price(retries: int = 3):
    """使用 Playwright 真浏览器抓取页面价格"""
    for attempt in range(1, retries + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1366, "height": 768},
                    locale="en-US",
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = context.new_page()
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)

                # 等待 Cloudflare 质询页跳转完成（最多约 15 秒）
                for _ in range(15):
                    title = page.title()
                    html = page.content()
                    if "Just a moment" not in title and "cf-browser-verification" not in html:
                        break
                    time.sleep(1)

                # 等待动态内容渲染
                page.wait_for_timeout(3000)
                html = page.content()
                browser.close()

            price = extract_price_from_html(html)
            if price is not None:
                print(f"[{now_tz().strftime('%Y-%m-%d %H:%M:%S')}] 抓取到最新价格: ${price:.2f}")
                return price

            print(f"[第 {attempt}/{retries} 次尝试] 页面已加载，但未匹配到有效价格。")
            print("页面片段预览:", re.sub(r"\s+", " ", html)[:300])
        except Exception as e:
            print(f"[第 {attempt}/{retries} 次尝试] Playwright 抓取失败: {e}")

        if attempt < retries:
            time.sleep(4 * attempt)

    return None


def check_and_notify_new_low(current_price):
    """对比历史最低价，若破新低则推送微信通知"""
    if not SERVERCHAN_SENDKEY:
        print("未检测到 SERVERCHAN_SENDKEY，跳过微信通知。")
        return

    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        print("首次运行，尚无历史数据比对。")
        return

    df = pd.read_csv(CSV_FILE)
    if df.empty or 'price' not in df.columns or 'date' not in df.columns:
        return

    today_str = now_tz().strftime('%Y-%m-%d')
    history_df = df[df['date'].astype(str) != today_str]

    if history_df.empty:
        return

    historical_min = float(history_df['price'].min())

    if current_price < historical_min:
        drop_amount = historical_min - current_price
        drop_rate = (drop_amount / historical_min) * 100

        title = f"🔥 降价提醒：VPS 刷新历史最低价！现仅 ${current_price:.2f}"
        content = (
            f"### ⚡ DediRock LA VPS 出现新低价！\n\n"
            f"- **今日现价**：`${current_price:.2f}` USD\n"
            f"- **历史原低价**：`${historical_min:.2f}` USD\n"
            f"- **降价幅度**：`${drop_amount:.2f}` (降幅 `{drop_rate:.1f}%`)\n"
            f"- **检查时间**：`{now_tz().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
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
        "desp": desp,
    }
    try:
        resp = requests.post(api_url, data=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            print("微信推送发送成功！")
        else:
            print(f"微信推送失败: {result.get('message')}")
    except Exception as e:
        print(f"微信通知接口请求异常: {e}")


def record_price(price):
    """保存或更新价格至 CSV"""
    today = now_tz().strftime('%Y-%m-%d')
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        df = pd.read_csv(CSV_FILE)
        if 'date' in df.columns and today in df['date'].astype(str).values:
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

    plt.plot(
        df['date'],
        df['price'],
        marker='o',
        markersize=5,
        color='#1d4ed8',
        linewidth=2.2,
        label='Daily Price ($ USD)',
        zorder=3,
    )
    plt.axhline(
        y=min_price,
        color='#15803d',
        linestyle='--',
        linewidth=1.5,
        alpha=0.8,
        label=f'All-time Low: ${min_price:.2f}',
        zorder=2,
    )
    plt.scatter(
        min_records['date'],
        min_records['price'],
        color='#dc2626',
        s=110,
        zorder=5,
        edgecolors='black',
        linewidth=1.2,
        label='Lowest Point',
    )

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
            bbox=dict(boxstyle="round,pad=0.25", fc="#fee2e2", ec="#ef4444", lw=0.8),
        )

    plt.title(
        f"DediRock LA VPS Price Trend\nLatest: ${latest_row['price']:.2f} | All-time Lowest: ${min_price:.2f}",
        fontsize=12,
        fontweight='bold',
        pad=12,
    )
    plt.xlabel("Date", fontsize=10, labelpad=8)
    plt.ylabel("Price ($ USD)", fontsize=10, labelpad=8)
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
        check_and_notify_new_low(current_price)
        record_price(current_price)
        render_chart()
    else:
        print("本次未获取到有效价格，跳过数据更新与图表生成。")
