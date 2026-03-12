import requests
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify
import urllib3
import re
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# 內建中文公司名稱與搜尋別名資料庫
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
        <link rel="apple-touch-icon" href="https://img.icons8.com/fluency/512/news.png">
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
            
            .widget-dropdown {{ display: none; position: absolute; top: 40px; left: 0; background: rgba(25, 30, 35, 0.98); backdrop-filter: blur(16px); border-radius: 12px; padding: 16px; width: max-content; min-width: 260px; box-shadow: 0 8px 32px rgba(0,0,0,0.8); border: 1px solid rgba(255, 255, 255, 0.15); text-align: left; }}
            .widget-dropdown.show {{ display: block; animation: fadeIn 0.2s ease-out; }}
            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(-5px); }} to {{ opacity: 1; transform: translateY(0); }} }}
            
            .calc-row {{ display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }}
            .calc-input {{ width: 110px; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.2); color: #ffffff; padding: 8px; border-radius: 8px; font-family: monospace; font-size: 1rem; outline: none; transition: 0.2s; text-align: right; }}
            .calc-input:focus {{ border-color: #74b9ff; background: rgba(0, 0, 0, 0.6); }}
            
            /* 單行計算機與固定匯率列表 CSS */
            .converter-row {{ display: flex; align-items: center; justify-content: space-between; background: rgba(0,0,0,0.3); padding: 12px 10px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.1); margin-bottom: 16px; }}
            .conv-input {{ width: 70px; background: transparent; border: none; border-bottom: 1px solid rgba(255,255,255,0.3); color: #fff; font-family: monospace; font-size: 1.05rem; text-align: center; outline: none; transition: 0.2s; padding-bottom: 2px; }}
            .conv-input:focus {{ border-bottom-color: #74b9ff; }}
            .conv-select {{ background: transparent; border: none; color: #a0aec0; font-size: 0.9rem; outline: none; cursor: pointer; padding: 0; }}
            .conv-select option {{ background: #1a202c; color: white; }}
            .conv-swap {{ background: transparent; border: none; color: #ff7675; cursor: pointer; font-size: 1.2rem; padding: 0 4px; transition: transform 0.3s; }}
            .conv-swap:hover {{ transform: rotate(180deg); color: #ff9ff3; }}

            @media (max-width: 900px) {{ 
                .widgets-row {{ position: static; justify-content: center; margin-bottom: 16px; flex-wrap: wrap; padding: 0 10px; }}
                .widget-dropdown {{ left: 50%; transform: translateX(-50%); width: 300px; }}
                .title-container {{ margin-top: 10px; }}
            }}
            
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

            function getWeatherEmoji(code) {{
                if(code===0) return '☀️'; if(code===1||code===2) return '⛅'; if(code===3) return '☁️';
                if(code>=45&&code<=48) return '🌫️'; if(code>=51&&code<=67) return '🌧️';
                if(code>=71&&code<=77) return '❄️'; if(code>=95&&code<=99) return '⛈️'; return '🌤️';
            }}
            function getDayName(d) {{ return ['週日','週一','週二','週三','週四','週五','週六'][new Date(d).getDay()]; }}
            
            function toggleWidget(id) {{
                document.querySelectorAll('.widget-dropdown').forEach(d => {{
                    if(d.id !== id) d.classList.remove('show');
                }});
                document.getElementById(id).classList.toggle('show');
            }}

            document.addEventListener('click', e => {{
                if (!e.target.closest('.widget-container')) {{
                    document.querySelectorAll('.widget-dropdown').forEach(d => d.classList.remove('show'));
                }}
            }});

            async function fetchWeather(lat, lon, locName) {{
                try {{
                    const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${{lat}}&longitude=${{lon}}&current_weather=true&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto`);
                    const data = await res.json();
                    document.getElementById('weather-temp').innerText = Math.round(data.current_weather.temperature) + '°C';
                    document.getElementById('weather-icon').innerText = getWeatherEmoji(data.current_weather.weathercode);
                    
                    let forecastHTML = `<div style="text-align:center; color:#a0aec0; margin-bottom:10px; font-size:0.8rem;">📍 ${{locName}}</div>`;
                    let labels = [], maxTemps = [], minTemps = [];

                    for (let i = 0; i < 7; i++) {{
                        let date = i === 0 ? '今日' : getDayName(data.daily.time[i]);
                        let icon = getWeatherEmoji(data.daily.weathercode[i]);
                        let maxT = Math.round(data.daily.temperature_2m_max[i]);
                        let minT = Math.round(data.daily.temperature_2m_min[i]);
                        labels.push(date); maxTemps.push(maxT); minTemps.push(minT);
                        forecastHTML += `<div class="forecast-item"><span class="forecast-day">${{date}}</span><span style="font-size: 1.1rem;">${{icon}}</span><span class="forecast-temps"><span class="temp-min">${{minT}}°</span> - <span class="temp-max">${{maxT}}°</span></span></div>`;
                    }}
                    document.getElementById('forecast-list').innerHTML = forecastHTML;

                    const ctx = document.getElementById('forecast-chart').getContext('2d');
                    if (weatherChartInstance) weatherChartInstance.destroy();
                    weatherChartInstance = new Chart(ctx, {{
                        type: 'line',
                        data: {{ labels: labels, datasets: [
                            {{ label: '高溫', data: maxTemps, borderColor: '#ff7675', backgroundColor: '#ff7675', borderWidth: 2, tension: 0.4, pointRadius: 2 }},
                            {{ label: '低溫', data: minTemps, borderColor: '#74b9ff', backgroundColor: '#74b9ff', borderWidth: 2, tension: 0.4, pointRadius: 2 }}
                        ]}},
                        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ color: '#a0aec0', font: {{ size: 10 }} }}, grid: {{ display: false }} }}, y: {{ ticks: {{ display: false }}, grid: {{ color: 'rgba(255,255,255,0.05)' }}, border: {{ display: false }} }} }}, interaction: {{ intersect: false, mode: 'index' }} }}
                    }});
                }} catch (e) {{
                    document.getElementById('weather-temp').innerText = '無資料';
                    document.getElementById('forecast-list').innerHTML = '無法取得氣象';
                }}
            }}

            async function fetchStock() {{
                let stockList = JSON.parse(localStorage.getItem('stockPrefs')) || ['^TWII', '^GSPC', '^IXIC'];
                let stockListHTML = `<div style="color:#a0aec0; margin-bottom:12px; font-size:0.8rem; text-align:center;">自選股與全球指數</div>`;
                
                try {{
                    let promises = stockList.map(t => fetch(`/api/market?ticker=${{encodeURIComponent(t)}}`).then(r => r.json()));
                    let results = await Promise.all(promises);
                    
                    results.forEach((data, index) => {{
                        if (data.taiex !== "N/A") {{
                            let color = data.change.includes('+') ? '#ff7675' : (data.change.includes('-') ? '#2ecc71' : '#e0e0e0');
                            
                            if (index === 0) {{
                                let btnName = data.name.length > 8 ? data.name.substring(0, 8) + '..' : data.name;
                                document.getElementById('stock-text').innerText = `${{btnName}} ${{data.taiex}}`;
                            }}
                            
                            stockListHTML += `
                                <div class="forecast-item" style="padding: 10px 0; align-items: center;">
                                    <div style="flex:1; display:flex; flex-direction:column; overflow: hidden; padding-right: 10px;">
                                        <span style="font-weight:bold; color:#ffffff; font-size:1.05rem; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${{data.name}}</span>
                                        <span style="font-size:0.75rem; color:#a0aec0;">${{data.ticker}}</span>
                                    </div>
                                    <div style="text-align:right; margin-right:12px; min-width: 90px;">
                                        <div style="font-family:monospace; font-size:1.1rem; color:${{color}}; font-weight:bold;">${{data.taiex}}</div>
                                        <div style="font-family:monospace; font-size:0.85rem; color:${{color}};">${{data.change}}</div>
                                    </div>
                                    <span onclick="removeStock('${{data.query.replace(/'/g, "\\'")}}')" class="delete-tag" style="font-size:1.3rem; padding:4px;" title="移除此標的">&times;</span>
                                </div>
                            `;
                        }} else {{
                            stockListHTML += `
                                <div class="forecast-item" style="padding: 10px 0; align-items: center; color:#ff7675;">
                                    <div style="flex:1; padding-right: 10px;">
                                        <div style="font-weight:bold; font-size:1rem; margin-bottom:4px;">找不到: ${{data.query}}</div>
                                        <div style="font-size:0.75rem; color:#a0aec0; line-height:1.4;">(部分台股中文名尚未支援，請改填 4 碼代號，例如: 3533)</div>
                                    </div>
                                    <span onclick="removeStock('${{data.query.replace(/'/g, "\\'")}}')" class="delete-tag" style="font-size:1.3rem; padding:4px;" title="移除此標的">&times;</span>
                                </div>
                            `;
                        }}
                    }});
                    
                    stockListHTML += `
                        <div class="calc-row" style="margin-top: 16px;">
                            <input type="text" id="new-stock-input" class="calc-input" style="flex:1; text-align:left;" placeholder="請輸入代號或名稱 (例: 3533, 蘋果)">
                            <button onclick="addStock()" style="background:#e74c3c; color:white; border:none; padding:8px 14px; border-radius:8px; cursor:pointer; font-weight:bold; transition:0.2s;">新增</button>
                        </div>
                        <div style="text-align: center; margin-top: 12px;">
                            <a href="https://tw.stock.yahoo.com/" target="_blank" class="ext-link-btn">前往 Yahoo 股市 ↗</a>
                        </div>
                    `;
                    
                    document.getElementById('stock-list').innerHTML = stockListHTML;
                    
                    document.getElementById('new-stock-input').addEventListener('keypress', function(e) {{
                        if (e.key === 'Enter') addStock();
                    }});
                    
                }} catch(e) {{
                    document.getElementById('stock-text').innerText = '股市連線異常';
                    document.getElementById('stock-list').innerHTML = '連線異常，請稍後再試。';
                }}
            }}

            window.addStock = function() {{
                let input = document.getElementById('new-stock-input').value.trim();
                if (!input) return;
                let stockList = JSON.parse(localStorage.getItem('stockPrefs')) || ['^TWII', '^GSPC', '^IXIC'];
                if (!stockList.includes(input)) {{
                    stockList.push(input);
                    localStorage.setItem('stockPrefs', JSON.stringify(stockList));
                    document.getElementById('stock-list').innerHTML = `<div style="text-align:center; padding:20px; color:#a0aec0;">⏳ 正在搜尋並更新股價...</div>`;
                    fetchStock(); 
                }} else {{
                    alert("此標的已經在您的清單中囉！");
                }}
            }};

            window.removeStock = function(query) {{
                let stockList = JSON.parse(localStorage.getItem('stockPrefs')) || ['^TWII', '^GSPC', '^IXIC'];
                if(stockList.length <= 1) {{
                    alert("請至少保留一檔股票喔！");
                    return;
                }}
                stockList = stockList.filter(t => t !== query);
                localStorage.setItem('stockPrefs', JSON.stringify(stockList));
                document.getElementById('stock-list').innerHTML = `<div style="text-align:center; padding:20px; color:#a0aec0;">⏳ 更新自選股中...</div>`;
                fetchStock();
            }};

            function handleAmountInput(el) {{
                let cursor = el.selectionStart;
                let oldLen = el.value.length;
                let val = el.value.replace(/,/g, '').replace(/[^\\d.]/g, '');
                let parts = val.split('.');
                if (parts.length > 2) parts = [parts[0], parts.slice(1).join('')];
                if (parts[0]) parts[0] = parts[0].replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ",");
                el.value = parts.join('.');
                let newLen = el.value.length;
                cursor += (newLen - oldLen);
                el.setSelectionRange(cursor, cursor);
                calcExchange();
            }}

            async function fetchCurrency() {{
                try {{
                    let res = await fetch('https://open.er-api.com/v6/latest/USD');
                    let data = await res.json();
                    globalExchangeRates = data.rates;
                    
                    let prefs = JSON.parse(localStorage.getItem('currencyPrefs')) || {{ from: 'USD', to: 'TWD' }};
                    
                    const shortCurrencies = {{
                        'TWD': '🇹🇼 TWD', 'USD': '🇺🇸 USD', 'JPY': '🇯🇵 JPY', 'EUR': '🇪🇺 EUR',
                        'MYR': '🇲🇾 MYR', 'GBP': '🇬🇧 GBP', 'AUD': '🇦🇺 AUD', 'KRW': '🇰🇷 KRW',
                        'HKD': '🇭🇰 HKD', 'SGD': '🇸🇬 SGD', 'CNY': '🇨🇳 CNY'
                    }};
                    
                    let optionsHTML = '';
                    for (let code in shortCurrencies) {{
                        optionsHTML += `<option value="${{code}}">${{shortCurrencies[code]}}</option>`;
                    }}
                    
                    let usd = (globalExchangeRates['TWD'] / globalExchangeRates['USD']).toFixed(2);
                    let jpy = (globalExchangeRates['TWD'] / globalExchangeRates['JPY']).toFixed(4);
                    let eur = (globalExchangeRates['TWD'] / globalExchangeRates['EUR']).toFixed(2);
                    let cny = (globalExchangeRates['TWD'] / globalExchangeRates['CNY']).toFixed(2);
                    let hkd = (globalExchangeRates['TWD'] / globalExchangeRates['HKD']).toFixed(2);
                    let krw = (globalExchangeRates['TWD'] / globalExchangeRates['KRW']).toFixed(4);
                    
                    let dropHTML = `
                        <div style="color:#a0aec0; margin-bottom:12px; font-size:0.8rem; text-align:center;">自訂匯率計算機</div>
                        
                        <div class="converter-row">
                            <input type="text" inputmode="decimal" id="calc-amount" class="conv-input" value="1" oninput="handleAmountInput(this)">
                            <select id="calc-from" class="conv-select" onchange="calcExchange()">${{optionsHTML}}</select>
                            
                            <button class="conv-swap" onclick="swapCurrency()">⇄</button>
                            
                            <input type="text" id="calc-result" readonly class="conv-input" style="border-bottom:none; color:#2ecc71; font-weight:bold; min-width:70px;">
                            <select id="calc-to" class="conv-select" onchange="calcExchange()">${{optionsHTML}}</select>
                        </div>
                        
                        <div style="border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 12px;">
                            <div style="color:#a0aec0; font-size:0.75rem; margin-bottom:8px; text-align:center;">常見外幣 (兌 台幣 TWD)</div>
                            <div class="forecast-item" style="padding: 6px 0;"><span>🇺🇸 美金 (USD)</span><span style="font-family:monospace; color:#e0e0e0; font-size:1.05rem;">${{usd}}</span></div>
                            <div class="forecast-item" style="padding: 6px 0;"><span>🇯🇵 日圓 (JPY)</span><span style="font-family:monospace; color:#e0e0e0; font-size:1.05rem;">${{jpy}}</span></div>
                            <div class="forecast-item" style="padding: 6px 0;"><span>🇪🇺 歐元 (EUR)</span><span style="font-family:monospace; color:#e0e0e0; font-size:1.05rem;">${{eur}}</span></div>
                            <div class="forecast-item" style="padding: 6px 0;"><span>🇨🇳 人民幣 (CNY)</span><span style="font-family:monospace; color:#e0e0e0; font-size:1.05rem;">${{cny}}</span></div>
                            <div class="forecast-item" style="padding: 6px 0;"><span>🇭🇰 港幣 (HKD)</span><span style="font-family:monospace; color:#e0e0e0; font-size:1.05rem;">${{hkd}}</span></div>
                            <div class="forecast-item" style="padding: 6px 0; border:none;"><span>🇰🇷 韓元 (KRW)</span><span style="font-family:monospace; color:#e0e0e0; font-size:1.05rem;">${{krw}}</span></div>
                        </div>
                    `;
                    document.getElementById('currency-list').innerHTML = dropHTML;
                    document.getElementById('calc-from').value = prefs.from;
                    document.getElementById('calc-to').value = prefs.to;
                    calcExchange(); 
                }} catch(e) {{
                    document.getElementById('curr-text').innerText = '匯率載入失敗';
                    document.getElementById('currency-list').innerHTML = '無法取得即時匯率';
                }}
            }}

            function calcExchange() {{
                if (!globalExchangeRates || !globalExchangeRates.USD) return;
                let rawAmt = document.getElementById('calc-amount').value.replace(/,/g, '');
                let amt = parseFloat(rawAmt);
                if (isNaN(amt)) amt = 0;
                
                let from = document.getElementById('calc-from').value;
                let to = document.getElementById('calc-to').value;

                let rateFromToUSD = 1 / globalExchangeRates[from];
                let rateUSDToTo = globalExchangeRates[to];
                let finalRate = rateFromToUSD * rateUSDToTo;
                let result = amt * finalRate;

                let resultDecimals = (result > 0 && result < 10) ? 4 : 2;
                document.getElementById('calc-result').value = result.toLocaleString('en-US', {{ minimumFractionDigits: resultDecimals, maximumFractionDigits: resultDecimals }});

                let headerDecimals = finalRate < 1 ? 4 : 2;
                let displayRate = finalRate.toLocaleString('en-US', {{ minimumFractionDigits: headerDecimals, maximumFractionDigits: headerDecimals }});
                document.getElementById('curr-text').innerText = `${{from}}/${{to}} ${{displayRate}}`;

                localStorage.setItem('currencyPrefs', JSON.stringify({{ from: from, to: to }}));
            }}

            function swapCurrency() {{
                let fromEl = document.getElementById('calc-from');
                let toEl = document.getElementById('calc-to');
                let temp = fromEl.value;
                fromEl.value = toEl.value;
                toEl.value = temp;
                calcExchange();
            }}

            document.addEventListener("DOMContentLoaded", () => {{
                let now = new Date();
                document.getElementById('last-updated').innerText = `最後更新時間：${{now.toLocaleTimeString('zh-TW', {{hour12: false, hour: '2-digit', minute:'2-digit'}})}}`;

                fetchStock();
                fetchCurrency();

                let isLocationFound = false;
                let locationTimeout = setTimeout(() => {{
                    if (!isLocationFound) fetchWeather(25.0330, 121.5654, "台北 (Taipei)");
                }}, 3000);

                if (navigator.geolocation) {{
                    navigator.geolocation.getCurrentPosition(
                        pos => {{
                            isLocationFound = true;
                            clearTimeout(locationTimeout);
                            fetchWeather(pos.coords.latitude, pos.coords.longitude, "您目前的位置");
                        }},
                        err => {{
                            isLocationFound = true;
                            clearTimeout(locationTimeout);
                            fetchWeather(25.0330, 121.5654, "台北 (Taipei)");
                        }},
                        {{ timeout: 3000, maximumAge: 60000 }} 
                    );
                }} else {{
                    clearTimeout(locationTimeout);
                    fetchWeather(25.0330, 121.5654, "台北 (Taipei)");
                }}

                let clickedNews = JSON.parse(localStorage.getItem('clickedNews') || '[]');
                
                document.querySelectorAll('.news-card').forEach(card => {{
                    if (clickedNews.includes(card.getAttribute('data-link'))) card.classList.add('read');
                }});
                
                let visibleCount = document.querySelectorAll('.news-card:not(.hidden):not(.read)').length;
                while (visibleCount < 20) {{
                    let nextSpare = document.querySelector('.news-card.hidden:not(.read)');
                    if (nextSpare) {{
                        nextSpare.classList.remove('hidden');
                        visibleCount++;
                    }} else {{
                        break; 
                    }}
                }}
                
                let customTags = JSON.parse(localStorage.getItem('customTags'));
                let migrated = localStorage.getItem('tagsMigrated');
                
                if (!customTags || !migrated) {{
                    customTags = ['國際', '科技', '財經', '體育', '娛樂', '日文', 'Netflix']; 
                    localStorage.setItem('customTags', JSON.stringify(customTags));
                    localStorage.setItem('tagsMigrated', 'true'); 
                }}
                
                const navTabs = document.getElementById('nav-tabs');
                const currentCategory = new URLSearchParams(window.location.search).get('category') || '綜合';
                
                customTags.forEach(tag => {{
                    let a = document.createElement('a');
                    a.href = `/?category=${{encodeURIComponent(tag)}}`;
                    a.innerHTML = `${{tag}} <span class="delete-tag" data-tag="${{tag}}" title="刪除">&times;</span>`;
                    if (currentCategory === tag) a.classList.add('active');
                    navTabs.appendChild(a);
                }});
                
                document.querySelectorAll('.delete-tag').forEach(btn => {{
                    btn.addEventListener('click', e => {{
                        e.preventDefault(); e.stopPropagation();
                        let t = e.target.getAttribute('data-tag');
                        if (confirm(`確定要刪除「${{t}}」嗎？`)) {{
                            customTags = customTags.filter(tag => tag !== t);
                            localStorage.setItem('customTags', JSON.stringify(customTags));
                            window.location.href = currentCategory === t ? '/?category=綜合' : window.location.href;
                        }}
                    }});
                }});
                
                let addBtn = document.createElement('a');
                addBtn.href = "#";
                addBtn.textContent = "+ 新增標籤";
                addBtn.className = "add-tag-btn";
                addBtn.onclick = e => {{
                    e.preventDefault();
                    let t = prompt("請輸入想要追蹤的關鍵字 (例如：台積電、大谷翔平)：");
                    if (t && t.trim() !== "") {{
                        t = t.trim();
                        if (t === '綜合') return alert("「綜合」為預設板塊，不需要重複新增喔！");
                        if (!customTags.includes(t)) {{
                            customTags.push(t); localStorage.setItem('customTags', JSON.stringify(customTags));
                            window.location.href = `/?category=${{encodeURIComponent(t)}}`;
                        }} else alert("這個標籤已經存在囉！");
                    }}
                }};
                navTabs.appendChild(addBtn);

                let activeTab = document.querySelector('.nav-tabs a.active');
                if (activeTab) activeTab.scrollIntoView({{ behavior: 'smooth', block: 'nearest', inline: 'center' }});
            }});

            async function fetchArticleSummary(card) {{
                if (card.hasAttribute('data-fetched')) return;
                card.setAttribute('data-fetched', 'true');
                let link = card.getAttribute('data-link');
                let title = card.getAttribute('data-title');
                let rss = card.getAttribute('data-rss');
                let contentDiv = card.querySelector('.hover-content');
                
                try {{
                    let res = await fetch('/api/summarize?url=' + encodeURIComponent(link) + '&title=' + encodeURIComponent(title));
                    let data = await res.json();
                    let text = data.summary === "FAIL" ? rss : data.summary;
                    text = text.split(title).join("").trim().replace(/^[\\s\\-：:|｜]+/, '').trim();
                    contentDiv.innerHTML = (text || "詳細內容請點擊標題閱讀。") + "<br><br><small style='color:#e74c3c;'>👉 點擊開啟新分頁</small>";
                }} catch (e) {{
                    contentDiv.innerHTML = rss + "<br><br><small style='color:#e74c3c;'>👉 點擊開啟新分頁</small>";
                }}
            }}

            function handleCardClick(e, card) {{
                if (window.getSelection().toString().length > 0) return;
                if (!e.target.closest('button') && !e.target.closest('.delete-tag')) {{
                    let link = card.getAttribute('data-link');
                    window.open(link, '_blank');
                    processAndHideCard(card);
                }}
            }}

            function dismissCard(e, btn) {{
                e.stopPropagation(); processAndHideCard(btn.closest('.news-card'));
            }}
            
            function processAndHideCard(card) {{
                let link = card.getAttribute('data-link');
                let clicked = JSON.parse(localStorage.getItem('clickedNews') || '[]');
                if (!clicked.includes(link)) {{ clicked.push(link); localStorage.setItem('clickedNews', JSON.stringify(clicked)); }}
                card.classList.add('read');
                let next = document.querySelector('.news-card.hidden:not(.read)');
                if (next) next.classList.remove('hidden');
            }}
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
