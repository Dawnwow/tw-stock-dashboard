# 台股選股儀表板 demo：抓資料＋篩選邏輯，輸出 data.json
import json, re, subprocess, xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TPE = ZoneInfo('Asia/Taipei')
NOW = datetime.now(TPE)
OUT = {}

def fetch(url, timeout=20):
    r = subprocess.run(['/usr/bin/curl', '-s', '--max-time', str(timeout), '-A', 'Mozilla/5.0', url],
                       capture_output=True, check=True)
    return r.stdout

def roc_to_iso(s):
    if not s: return None
    s = str(s).strip()
    m = re.search(r'(\d{2,3})[./](\d{1,2})[./](\d{1,2})', s) or re.match(r'^(\d{3})(\d{2})(\d{2})$', s)
    if not m: return None
    return f"{int(m.group(1))+1911}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

# ---------- 1. Yahoo RSS 熱門族群新聞 ----------
rss = fetch('https://tw.stock.yahoo.com/rss?q=%E7%86%B1%E9%96%80%E6%97%8F%E7%BE%A4')
root = ET.fromstring(rss)
news = []
for item in root.iter('item'):
    t = item.findtext('title') or ''
    news.append({
        'title': t.strip(),
        'link': (item.findtext('link') or '').strip(),
        'pubDate': (item.findtext('pubDate') or '').strip(),
        'desc': re.sub(r'<[^>]+>', '', item.findtext('description') or '').strip()[:200],
    })
print('Yahoo RSS 新聞:', len(news))

# ---------- 2. EBC 參照資料 ----------
ebc = json.loads(fetch('https://pub-e13dde58e2134b369fa04c9c56ead9f5.r2.dev/data.json'))
ebc_today = ebc['records'].get(ebc['dates'][0], [])
ebc_text_all = ' '.join(r.get('text', '') for r in ebc_today)
ebc_codes = set()
ebc_code_names = {}
for r in ebc_today:
    for c in r.get('codes', []):
        ebc_codes.add(c)
        q = (r.get('quotes') or {}).get(c) or {}
        if q.get('name'): ebc_code_names[c] = q['name']
print('EBC 今日訊息:', len(ebc_today), '｜提到個股:', len(ebc_codes))

# ---------- 3. 每日行情（收盤價、成交量） ----------
quotes = {}  # code -> {name, close, vol_lots, market}
for row in json.loads(fetch('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL')):
    try:
        quotes[row['Code']] = {'name': row['Name'], 'close': float(row['ClosingPrice'] or 0),
                               'vol': round(int(row['TradeVolume'] or 0)/1000), 'market': '上市'}
    except (ValueError, KeyError): pass
for row in json.loads(fetch('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes')):
    try:
        quotes[row['SecuritiesCompanyCode']] = {'name': row['CompanyName'], 'close': float(row['Close'] or 0),
                                                'vol': round(int(row['TradingShares'] or 0)/1000), 'market': '上櫃'}
    except (ValueError, KeyError): pass
print('行情檔數:', len(quotes))
name_to_code = {}
for c, q in quotes.items():
    if len(c) == 4 and c.isdigit() and len(q['name']) >= 2:  # 只用四碼普通股做名稱比對，避免權證雜訊
        name_to_code.setdefault(q['name'], c)

# ---------- 4. 注意／處置名單 ----------
today_iso = NOW.strftime('%Y-%m-%d')
d7 = (NOW - timedelta(days=7)).strftime('%Y%m%d')
d0 = NOW.strftime('%Y%m%d')
twse_notice = json.loads(fetch(f'https://www.twse.com.tw/rwd/zh/announcement/notice?response=json&startDate={d7}&endDate={d0}'))
twse_punish = json.loads(fetch('https://www.twse.com.tw/rwd/zh/announcement/punish?response=json'))
tpex_notice = json.loads(fetch('https://www.tpex.org.tw/www/zh-tw/bulletin/attention?response=json'))
tpex_punish = json.loads(fetch('https://www.tpex.org.tw/www/zh-tw/bulletin/disposal?response=json'))

watch = {}  # code -> entry
def add_watch(code, name, market, kind, detail):
    e = watch.setdefault(code, {'code': code, 'name': re.sub(r'\s*\(.*\)\s*$', '', str(name)), 'market': market,
                                'kinds': [], 'details': []})
    if kind not in e['kinds']: e['kinds'].append(kind)
    e['details'].append(detail)

rows = twse_notice.get('data') or []
dates = sorted({roc_to_iso(r[5]) for r in rows if roc_to_iso(r[5])})
latest = dates[-1] if dates else None
for r in rows:
    if roc_to_iso(r[5]) == latest:
        add_watch(r[1], r[2], '上市', '注意', f"注意 累計{r[3]}次（{latest[5:]}）")
rows = ((tpex_notice.get('tables') or [{}])[0]).get('data') or []
dates = sorted({roc_to_iso(r[5]) for r in rows if roc_to_iso(r[5])})
latest = dates[-1] if dates else None
for r in rows:
    if roc_to_iso(r[5]) == latest:
        add_watch(r[1], r[2], '上櫃', '注意', f"注意 累計{r[3]}次（{latest[5:]}）")

def period(s):
    p = re.split(r'[～~]', str(s or ''))
    return roc_to_iso(p[0]), roc_to_iso(p[1] if len(p) > 1 else p[0])
for r in (twse_punish.get('data') or []):
    s, e = period(r[6])
    if s and e and s <= today_iso <= e:
        add_watch(r[2], r[3], '上市', '處置', f"{r[7]} {s[5:]}~{e[5:]}")
for r in (((tpex_punish.get('tables') or [{}])[0]).get('data') or []):
    s, e = period(r[5])
    if s and e and s <= today_iso <= e:
        add_watch(r[2], r[3], '上櫃', '處置', f"第{r[4]}次處置 {s[5:]}~{e[5:]}")
print('注意＋處置(原始):', len(watch))

# ---------- 5. 族群關鍵字與比對 ----------
SECTORS = ['軍工','無人機','矽光子','CPO','光通訊','記憶體','DRAM','HBM','AI伺服器','伺服器','散熱','液冷','重電','機器人',
           'PCB','載板','玻璃基板','銅箔基板','CCL','被動元件','半導體','封測','IC設計','晶圓代工','面板','網通','電源',
           '航運','貨櫃','散裝','航空','塑化','紡織','鋼鐵','水泥','生技','製藥','觀光','餐飲','營建','資產','金融','證券',
           '電動車','汽車零組件','太陽能','儲能','風電','電池','低軌衛星','蘋概','綠能','遊戲','銅纜','高速傳輸','車用',
           '矽智財','IP','先進封裝','CoWoS','ETF','東協','內需','醫材','隱形眼鏡','油價','原物料','航太','造船']

def find_sectors(text):
    return [s for s in SECTORS if s in text]

def find_stocks(text):
    hits = []
    for name, code in name_to_code.items():
        if name in text: hits.append(code)
    return hits

sector_count = {}
for n in news:
    text = n['title'] + ' ' + n['desc']
    n['sectors'] = find_sectors(text)
    n['stocks'] = find_stocks(text)
    for s in n['sectors']:
        sector_count[s] = sector_count.get(s, 0) + 1

ebc_sectors = set(find_sectors(ebc_text_all))
news_stock_codes = set(c for n in news for c in n['stocks'])

HOT_TH = 3   # 出現 >=3 則新聞 = 亮燈（很紅）
sectors_out = []
for s, cnt in sorted(sector_count.items(), key=lambda x: -x[1]):
    sectors_out.append({'name': s, 'count': cnt, 'hot': cnt >= HOT_TH, 'cross': s in ebc_sectors})

hot_sectors = {s['name'] for s in sectors_out if s['hot']}

# ---------- 6. 精選名單篩選 ----------
picked, dropped = [], []
for code, e in watch.items():
    q = quotes.get(code, {})
    e['close'] = q.get('close')
    e['vol'] = q.get('vol')
    in_news = code in news_stock_codes
    in_ebc = code in ebc_codes
    e['hit'] = ('新聞' if in_news else '') + ('＋' if in_news and in_ebc else '') + ('EBC' if in_ebc else '')
    e['news'] = [{'title': n['title'], 'link': n['link']} for n in news if code in n['stocks']][:3]
    e['sectors'] = sorted({s for n in news for s in n['sectors'] if code in n['stocks']})
    stock_hot = any(s in hot_sectors for s in e['sectors'])
    if not (in_news or in_ebc):
        e['drop_reason'] = '未上族群新聞'; dropped.append(e); continue
    low_vol = e['vol'] is not None and e['vol'] < 10000
    low_price = e['close'] is not None and e['close'] < 20
    if (low_vol or low_price) and not stock_hot:
        e['drop_reason'] = ('量<1萬張 ' if low_vol else '') + ('價<20' if low_price else ''); dropped.append(e); continue
    e['exempt'] = (low_vol or low_price) and stock_hot
    picked.append(e)
print('精選:', len(picked), '｜剔除:', len(dropped))

OUT = {
    'generated_at': NOW.strftime('%Y-%m-%d %H:%M'),
    'quote_date': '前一交易日' ,
    'sectors': sectors_out,
    'news': news,
    'ebc': [{'ts': r.get('ts'), 'label': r.get('label'), 'text': r.get('text'),
             'codes': [{'code': c, 'name': ebc_code_names.get(c, ''),
                        'pct': ((r.get('quotes') or {}).get(c) or {}).get('change_pct')} for c in r.get('codes', [])]}
            for r in ebc_today[:40]],
    'picked': picked,
    'dropped': dropped,
    'hot_threshold': HOT_TH,
}
import os
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, 'data.js'), 'w') as f:
    f.write('const DATA = ')
    json.dump(OUT, f, ensure_ascii=False, indent=1)
    f.write(';\n')
print('已輸出 data.js')
for s in sectors_out[:12]:
    print(('🔥' if s['hot'] else '  ') + ('🟡' if s['cross'] else '  '), s['name'], s['count'])
