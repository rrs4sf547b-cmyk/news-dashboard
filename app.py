import os
import json
import requests
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify
import urllib3
import re
import redis
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# 讀取 REDIS_URL 環境變數
REDIS_URL = os.environ.get('REDIS_URL')
try:
    redis_client = redis.from_url(REDIS_URL) if REDIS_URL else None
except Exception:
    redis_client = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

STOCK_NAMES = {
    "^TWII": "台灣加權大盤", "^GSPC": "標普 500", "^IXIC": "納斯達克", "^DJI": "道瓊工業",
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2382.TW": "廣達",
    "2308.TW": "台達電", "2881.TW": "富邦金", "2882.TW": "國泰金", "2412.TW": "中華電",
    "2891.TW": "中信金", "2603.TW": "長榮", "3231.TW": "緯創", "2303.TW": "聯電",
    "2886.TW": "兆豐金", "3711.TW": "日月光", "2207.TW": "和泰車", "2884.TW": "玉山金",
    "0050.TW": "元大台灣50", "0056.TW": "元大高股息", "00878.TW": "國泰永續高息",
    "3533.TW": "嘉澤", "3017.TW": "奇鋐", "2376.TW": "技嘉", "3008.TW": "大立光", "2395.TW": "研華",
    "AAPL": "蘋果 (Apple)", "TSLA": "特斯拉 (Tesla)", "NVDA": "輝達 (NVIDIA)", 
    "MSFT": "微軟 (Microsoft)", "GOOG": "Google", "AMZN": "亞馬遜", "META": "Meta",
    "AMD": "超微 (AMD)", "INTC": "英特爾", "TSM": "台積電 (ADR)"
}

ALIAS_MAP = {
    "大盤": "^TWII", "台股": "^TWII", "美股": "^GSPC", "標普": "^GSPC", "納指": "^IXIC", "道瓊": "^DJI",
    "蘋果": "AAPL", "輝達": "NVDA", "微軟": "MSFT", "特斯拉": "TSLA", "亞馬遜": "AMZN",
    "台積電": "2330.TW", "鴻海": "2317.TW", "聯發科": "2454.TW", "廣達": "2382.TW",
    "緯創": "3231.TW", "長榮": "2603.TW", "聯電": "2303.TW", "台達電": "2308.TW",
    "富邦金": "2881.TW", "國泰金": "2882.TW", "中華電": "2412.TW", "中信金": "2891.TW",
    "嘉澤": "3533.TW", "奇鋐": "3017.TW", "技嘉": "2376.TW", "大立光": "3008.TW", "研華": "2395.TW"
}

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

@app.route('/api/sync', methods=['POST', 'GET'])
def sync_prefs():
    if not redis_client:
        return jsonify({"status": "no_db"})

    if request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        prefs = data.get('prefs')
        if user_id and prefs:
            try:
                redis_client.set(f"news_prefs_{user_id}", json.dumps(prefs))
                return jsonify({"status": "ok"})
            except Exception as e:
                return jsonify({"status": "error", "msg": str(e)})
        return jsonify({"status": "error"})

    elif request.method == 'GET':
        user_id = request.args.get('user_id')
        if user_id:
            try:
                prefs = redis_client.get(f"news_prefs_{user_id}")
                if prefs:
                    return jsonify({"status": "ok", "prefs": json.loads(prefs)})
            except Exception as e:
                return jsonify({"status": "error", "msg": str(e)})
        return jsonify({"status": "empty"})

def get_latest_news(topic_url):
    try:
        response = requests.get(topic_url, headers=HEADERS, verify=False, timeout=10)
        root = ET.fromstring(response.content)
        news_list = []
        valid_count = 0 
        
        for item in root.findall('./channel/item'):
            if valid_count >= 60: break
                
            pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ''
            if pub_date_str:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_str)
                    now = datetime.now(pub_dt.tzinfo or timezone.utc)
                    if now - pub_dt > timedelta(days=7): continue
                except Exception:
                    pass
                    
            title = item.find('title').text
            link = item.find('link').text
            pub_date = pub_date_str.replace(' GMT', '')
            source_tag = item.find('source')
            source_name = source_tag.text if source_tag is not None else "新聞"
            logo_url = f"https://www.google.com/s2/favicons?domain={source_tag.attrib.get('url', '') if source_tag is not None else ''}&sz=64"
            
            desc_element = item.find('description')
            rss_desc = re.sub(r'<[^>]+>', '', desc_element.text) if desc_element is not None else ""
            display_class = "" if valid_count < 20 else "hidden"
            
            news_list.append(f"""
                <div class="news-card {display_class}" data-link="{link}" data-title="{title}" data-rss="{rss_desc[:120]}" onmouseenter="fetchArticleSummary(this)" onclick="handleCardClick(event, this)">
                    <button class="dismiss-btn" onclick="dismissCard(event, this)" aria-label="隱藏此新聞">&times;</button>
                    <div class="content-wrapper">
                        <span class="source-badge">
                            <img src="{logo_url}" class="source-icon" loading="lazy" alt="logo">
                            {source_name}
                        </span>
                        <div class="article-title">{title}</div>
                        <div class="date">{pub_date}</div>
                    </div>
                    <div class="hover-overlay">
                        <div class="hover-content">正在探索深度內容...</div>
                    </div>
                </div>
            """)
            valid_count += 1
            
        return "".join(news_list) if valid_count > 0 else "<div class='news-card'>過去一週內沒有找到相關的新聞。</div>"
    except:
        return "無法載入新聞"

@app.route('/api/summarize')
def summarize_article():
    article_url = request.args.get('url')
    title = request.args.get('title', '')
    try:
        res = requests.get(article_url, headers=HEADERS, verify=False, timeout=6)
        soup = BeautifulSoup(res.content, 'html.parser')
        
        meta_refresh = soup.find('meta', attrs={'http-equiv': lambda x: x and x.lower() == 'refresh'})
        if meta_refresh:
            content = meta_refresh.get('content', '')
            parts = re.split(r'url=', content, flags=re.IGNORECASE)
            if len(parts) > 1:
                res = requests.get(parts[1].strip('\'"'), headers=HEADERS, verify=False, timeout=6)
                soup = BeautifulSoup(res.content, 'html.parser')

        for junk in soup(["script", "style", "nav", "footer", "header", "aside"]): junk.extract()
            
        text_blocks = []
        for p in soup.find_all(['p', 'div']):
            t = p.get_text().strip()
            if title in t: t = t.split(title)[-1].strip()
            if len(t) > 40 and similar(title, t[:len(title)]) < 0.3:
                if t not in text_blocks: text_blocks.append(t)
        
        final_text = " ".join(text_blocks[:3])
        return jsonify({"summary": final_text[:250] if final_text else "FAIL"})
    except:
        return jsonify({"summary": "FAIL"})

@app.route('/api/market')
def market_data():
    original_query = request.args.get('ticker', '^TWII').strip()
    query = original_query.upper()
    ticker = query
    resolved_name = None
    
    if query in ALIAS_MAP:
        ticker = ALIAS_MAP[query]
    elif re.match(r'^\d{4,5}$', query):
        ticker = query + ".TW"
    else:
        try:
            search_url = "https://query2.finance.yahoo.com/v1/finance/search"
            params = {
                "q": original_query, 
                "quotesCount": 1, 
                "newsCount": 0,
                "lang": "zh-Hant-TW",
                "region": "TW"
            }
            search_res = requests.get(search_url, headers=HEADERS, params=params, verify=False, timeout=5)
            search_data = search_res.json()
            if search_data.get('quotes') and len(search_data['quotes']) > 0:
                quote = search_data['quotes'][0]
                ticker = quote['symbol']
                resolved_name = quote.get('shortname') or quote.get('longname')
        except Exception:
            pass 
        
    try:
        res = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}', headers=HEADERS, verify=False, timeout=5)
        data = res.json()
        meta = data['chart']['result'][0]['meta']
        
        price = meta['regularMarketPrice']
        prev_close = meta['chartPreviousClose']
        change = price - prev_close
        change_pct = (change / prev_close) * 100
        sign = "+" if change > 0 else ""
        change_str = f"{sign}{change:,.2f} ({sign}{change_pct:.2f}%)"
        
        fetched_name = meta.get('shortName', ticker)
        display_name = STOCK_NAMES.get(ticker) or resolved_name or fetched_name
        
        if ".TW" in ticker and display_name == fetched_name:
            display_name = display_name.replace(" INC", "").replace(" CO., LTD.", "").replace(" CORP.", "").strip()[:12]
            
        def fmt(val): return f"{val:,.2f}" if isinstance(val, (int, float)) else "N/A"
            
        return jsonify({
            "query": original_query, 
            "ticker": ticker,
            "name": display_name, 
            "taiex": fmt(price), 
            "change": change_str,
            "open": fmt(meta.get('regularMarketOpen')),
            "high": fmt(meta.get('regularMarketDayHigh')),
            "low": fmt(meta.get('regularMarketDayLow'))
        })
    except Exception as e:
        return jsonify({"query": original_query, "ticker": ticker, "taiex": "N/A", "change": "", "name": original_query})

@app.route('/')
def home():
    category = request.args.get('category', '綜合')
    urls = {'綜合': 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'}
    selected_url = urls.get(category, f'https://news.google.com/rss/search?q={category}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant')
    news_html = get_latest_news(selected_url)
    
    return f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>每日重點新聞</title>
        
        <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📰</text></svg>">
        <link rel="apple-touch-icon" href="https://ui-avatars.com/api/?name=新&background=e74c3c&color=fff&size=512&font-size=0.6">
        <meta name="apple-mobile-web-app-title" content="情報中心">
        <meta name="theme-color" content="#121212">
        
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: -apple-system, sans-serif; background-color: #121212; background-image: url('https://www.transparenttextures.com/patterns/dark-matter.png'); color: #e0e0e0; margin: 0; }}
            .sticky-header {{ position: sticky; top: 0; z-index: 1000; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
            header {{ position: relative; background-image: linear-gradient(135deg, rgba(52, 152, 219, 0.85), rgba(155, 89, 182, 0.85)), url('https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000&auto=format&fit=crop'); background-size: cover; background-position: center; color: #ffffff; padding: 24px 20px 20px 20px; text-align: center; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }}
            
            .widgets-row {{ position: absolute; top: 16px; left: 16px; display: flex; gap: 10px; z-index: 1001; }}
            .widget-container {{ position: relative; }}
            .widget-btn {{ display: flex; align-items: center; gap: 6px; background: rgba(0, 0, 0, 0.4); padding: 6px 14px; border-radius: 20px; backdrop-filter: blur(8px); cursor: pointer; border: 1px solid rgba(255, 255, 255, 0.2); transition: 0.2s; font-size: 0.9rem; font-weight: 600; text-shadow: 0 1px 2px rgba(0,0,0,0.5); animation: pulse 2s infinite; }}
            .widget-btn:hover {{ background: rgba(0, 0, 0, 0.6); animation: none; }}
            @keyframes pulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(255,255,255,0.2); }} 70% {{ box-shadow: 0 0 0 6px rgba(255,255,255,0); }} 100% {{ box-shadow: 0 0 0 0 rgba(255,255,255,0); }} }}
            .widget-arrow {{ font-size: 0.6rem; opacity: 0.7; margin-left: 2px; }}
            
            .widget-dropdown {{ display: none; position: absolute; top: 40px; left: 0; background: rgba(25, 30, 35, 0.98); backdrop-filter: blur(16px); border-radius: 12px; padding: 16px; width: max-content; min-width: 260px; box-shadow: 0 8px 32px rgba(0,0,0,0.8); border: 1px solid rgba(255, 255, 255, 0.15); text-align: left; z-index: 1005; }}
            .widget-dropdown.show {{ display: block; animation: fadeIn 0.2s ease-out; }}
            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(-5px); }} to {{ opacity: 1; transform: translateY(0); }} }}
            
            @media (max-width: 1400px) {{ 
                .widgets-row {{ position: static; justify-content: center; margin-bottom: 16px; flex-wrap: wrap; padding: 0 10px; z-index: 1010; }}
                .widget-dropdown {{ left: 50%; transform: translateX(-50%); width: 320px; z-index: 1020; }}
                .title-container {{ margin-top: 10px; }}
            }}
            
            .calc-row {{ display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }}
            .calc-input {{ width: 110px; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.2); color: #ffffff; padding: 8px; border-radius: 8px; font-family: monospace; font-size: 1rem; outline: none; transition: 0.2s; text-align: right; }}
            .calc-input:focus {{ border-color: #74b9ff; background: rgba(0, 0, 0, 0.6); }}
            
            .converter-row {{ display: flex; align-items: center; justify-content: space-between; background: rgba(0,0,0,0.3); padding: 12px 10px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1); margin-bottom: 16px; }}
            .conv-input {{ width: 70px; background: transparent; border: none; border-bottom: 1px solid rgba(255,255,255,0.3); color: #fff; font-family: monospace; font-size: 1.05rem; text-align: center; outline: none; transition: 0.2s; padding-bottom: 2px; }}
            .conv-input:focus {{ border-bottom-color: #74b9ff; }}
            .conv-select {{ background: transparent; border: none; color: #a0aec0; font-size: 0.9rem; outline: none; cursor: pointer; padding: 0; }}
            .conv-select option {{ background: #1a202c; color: white; }}
            .conv-swap {{ background: transparent; border: none; color: #ff7675; cursor: pointer; font-size: 1.2rem; padding: 0 4px; transition: transform 0.3s; }}
            .conv-swap:hover {{ transform: rotate(180deg); color: #ff9ff3; }}
            
            .title-container {{ display: flex; align-items: center; justify-content: center; gap: 12px; }}
            .header-icon {{ width: 32px; height: 32px; stroke: #ffffff; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.4)); }}
            .main-title {{ font-weight: 800; font-size: 1.8rem; letter-spacing: 2px; margin: 0; text-shadow: 0 2px 6px rgba(0,0,0,0.6); }}
            .last-updated {{ font-size: 0.85rem; color: rgba(255, 255, 255, 0.85); margin-top: 10px; font-weight: 500; letter-spacing: 1px; text-shadow: 0 1px 3px rgba(0,0,0,0.5); }}
            
            .forecast-item {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 8px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05); color: #e0e0e0; font-size: 0.85rem; }}
            .forecast-item:last-child {{ border-bottom: none; }}
            .forecast-day {{ width: 45px; font-weight: bold; color: #a0aec0; }}
            .forecast-temps {{ display: flex; gap: 10px; font-family: monospace; font-size: 0.9rem; }}
            .temp-max {{ color: #ff7675; }} .temp-min {{ color: #74b9ff; }}
            .chart-container {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1); width: 280px; }}
            
            .ext-link-btn {{ display: inline-block; color: #ffffff; background: rgba(255,255,255,0.15); text-decoration: none; font-size: 0.85rem; padding: 6px 16px; border-radius: 20px; transition: background 0.2s; border: 1px solid rgba(255,255,255,0.1); text-align: center; margin-top: 12px; }}
            .ext-link-btn:hover {{ background: rgba(255,255,255,0.3); }}

            .nav-tabs {{ display: flex; overflow-x: auto; background: rgba(255, 255, 255, 0.15); backdrop-filter: blur(15px); padding: 14px 16px; gap: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.25); }}
            .nav-tabs::-webkit-scrollbar {{ display: none; }}
            .nav-tabs a {{ flex: 0 0 auto; text-decoration: none; color: #ffffff; background: rgba(0, 0, 0, 0.3); padding: 8px 18px; border-radius: 20px; font-size: 0.92rem; font-weight: 600; border: 1px solid rgba(255, 255, 255, 0.1); transition: 0.2s; display: flex; align-items: center; gap: 6px; }}
            .nav-tabs a.active {{ background-color: #e74c3c; color: #ffffff; border-color: #e74c3c; box-shadow: 0 4px 12px rgba(231, 76, 60, 0.4); }}
            .nav-tabs a:hover {{ background-color: rgba(0, 0, 0, 0.5); }}
            
            .container {{ padding: 24px 16px; max-width: 1400px; width: 100%; box-sizing: border-box; margin: 0 auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; align-items: start; }}
            .news-card {{ position: relative; overflow: hidden; background: #ffffff; padding: 20px; border-radius: 12px; border-left: 5px solid #e74c3c; box-shadow: 0 4px 12px rgba(0,0,0,0.3); transition: transform 0.2s; cursor: pointer; }}
            .news-card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 25px rgba(0,0,0,0.5); }}
            .content-wrapper {{ position: relative; z-index: 1; }}
            .source-badge {{ display: inline-flex; align-items: center; background-color: rgba(231, 76, 60, 0.1); color: #e74c3c; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; margin-bottom: 12px; border: 1px solid rgba(231, 76, 60, 0.2); }}
            .source-icon {{ width: 14px; height: 14px; margin-right: 6px; border-radius: 2px; }}
            .article-title {{ color: #1a202c; font-size: 1.1rem; font-weight: 700; margin-bottom: 10px; line-height: 1.4; padding-right: 28px; transition: color 0.2s; }}
            .news-card:hover .article-title {{ color: #e74c3c; }}
            .date {{ font-size: 0.8rem; color: #a0aec0; }}
            
            .hover-overlay {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(8px); opacity: 0; visibility: hidden; transition: opacity 0.3s; padding: 20px; display: flex; align-items: center; z-index: 5; }}
            .hover-content {{ color: #2c3e50; font-size: 0.9rem; line-height: 1.5; text-align: justify; overflow-y: auto; max-height: 100%; }}
            .news-card:hover .hover-overlay {{ opacity: 1; visibility: visible; }}
            
            .dismiss-btn {{ position: absolute; top: 12px; right: 12px; width: 28px; height: 28px; background: #f2f2f7; border: none; border-radius: 50%; z-index: 10; cursor: pointer; color: #8e8e93; display: flex; align-items: center; justify-content: center; transition: 0.2s; }}
            .dismiss-btn:hover {{ background-color: #e74c3c; color: #ffffff; }}
            .read, .hidden {{ display: none !important; }}
            .add-tag-btn {{ background-color: rgba(46, 204, 113, 0.15) !important; color: #2ecc71 !important; border: 1px dashed #2ecc71 !important; cursor: pointer; }}
            .add-tag-btn:hover {{ background-color: rgba(46, 204, 113, 0.3) !important; }}
            .delete-tag {{ color: #ff7675; cursor: pointer; font-size: 1.1em; padding-left: 4px; transition: 0.2s; }}
            .delete-tag:hover {{ color: #d63031; transform: scale(1.2); }}
        </style>
    </head>
    <body>
        <div class="sticky-header">
            <header>
                <div class="widgets-row">
                    <div class="widget-container">
                        <div class="widget-btn" onclick="promptSync()" title="跨裝置同步設定">
                            <span>🔄</span>
                            <span id="sync-text">未同步</span>
                        </div>
                    </div>
                    
                    <div class="widget-container">
                        <div class="widget-btn" onclick="toggleWidget('weather-dropdown')" title="七天氣象">
                            <span id="weather-icon">🌍</span>
                            <span id="weather-temp">載入中...</span>
                            <span class="widget-arrow">▼</span>
                        </div>
                        <div class="widget-dropdown" id="weather-dropdown">
                            <div id="forecast-list">定位中...</div>
                            <div class="chart-container"><canvas id="forecast-chart" height="130"></canvas></div>
                        </div>
                    </div>
                    
                    <div class="widget-container">
                        <div class="widget-btn" onclick="toggleWidget('stock-dropdown')" title="自選股清單">
                            <span>📈</span>
                            <span id="stock-text">股市載入中...</span>
                            <span class="widget-arrow">▼</span>
                        </div>
                        <div class="widget-dropdown" id="stock-dropdown">
                            <div id="stock-list">載入中...</div>
                        </div>
                    </div>

                    <div class="widget-container">
                        <div class="widget-btn" onclick="toggleWidget('currency-dropdown')" title="匯率計算機">
                            <span>💵</span>
                            <span id="curr-text">匯率載入中...</span>
                            <span class="widget-arrow">▼</span>
                        </div>
                        <div class="widget-dropdown" id="currency-dropdown">
                            <div id="currency-list">載入中...</div>
                        </div>
                    </div>
                </div>

                <div class="title-container">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="header-icon">
                        <circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line>
                        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                    </svg>
                    <h1 class="main-title">每日重點新聞</h1>
                </div>
                <div class="last-updated" id="last-updated">最後更新時間：載入中...</div>
            </header>
            <div class="nav-tabs" id="nav-tabs">
                <a href="/?category=綜合" class="{'active' if category == '綜合' else ''}">綜合</a>
            </div>
        </div>
        
        <div class="container">{news_html}</div>
        
        <script>
            setTimeout(() => {{ window.location.reload(); }}, 600000);
            let weatherChartInstance = null;
            let globalExchangeRates = {{}};
            
            let syncCode = localStorage.getItem('syncCode') || '';
            
            document.addEventListener("DOMContentLoaded", () => {{
                updateSyncUI();
            }});

            function updateSyncUI() {{
                document.getElementById('sync-text').innerText = syncCode ? syncCode : '未同步';
                document.getElementById('sync-text').style.color = syncCode ? '#2ecc71' : '';
            }}

            async function promptSync() {{
                let code = prompt("請輸入您的「專屬同步代碼」(例如：slee13)：\\n\\n💡 只要在其他裝置輸入相同代碼，就能自動同步所有設定！\\n(清空輸入框可解除同步)", syncCode);
                if (code !== null) {{
                    syncCode = code.trim();
                    localStorage.setItem('syncCode', syncCode);
                    updateSyncUI();
                    
                    if (syncCode) {{
                        document.getElementById('sync-text').innerText = '同步中...';
                        await pullFromCloud();
                    }}
                }}
            }}

            async function pullFromCloud() {{
                if (!syncCode) return;
                try {{
                    let res = await fetch('/api/sync?user_id=' + encodeURIComponent(syncCode));
                    let data = await res.json();
                    if (data.status === 'ok' && data.prefs) {{
                        localStorage.setItem('stockPrefs', JSON.stringify(data.prefs.stocks || ['^TWII', '^GSPC', '^IXIC']));
                        localStorage.setItem('customTags', JSON.stringify(data.prefs.tags || ['國際', '科技', '財經', '體育', '娛樂', '日文', 'Netflix']));
                        localStorage.setItem('currencyPrefs', JSON.stringify(data.prefs.currency || {{ from: 'USD', to: 'TWD' }}));
                        localStorage.setItem('clickedNews', JSON.stringify(data.prefs.clicked || []));
                        alert("✅ 成功從雲端同步設定！畫面將自動重新整理。");
                        window.location.reload();
                    }} else if (data.status === 'empty') {{
                        await pushToCloud();
                        updateSyncUI();
                    }} else {{
                        alert("連線資料庫失敗，請確認已加入 REDIS_URL 變數。");
                        updateSyncUI();
                    }}
                }} catch(e) {{
                    updateSyncUI();
                }}
            }}

            async function pushToCloud() {{
                if (!syncCode) return;
                let prefs = {{
                    stocks: JSON.parse(localStorage.getItem('stockPrefs')) || ['^TWII', '^GSPC', '^IXIC'],
                    tags: JSON.parse(localStorage.getItem('customTags')) || ['國際', '科技', '財
