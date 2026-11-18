"""Wealth Notes: download SITCA official daily NAV and match seven TWD funds.
No ambiguous share classes are silently selected.
"""
import csv
import io
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

SOURCE = 'https://members.sitca.org.tw/OPF/K0000/files/F/03/nav.csv'
FUNDS = [
    ('統一奔騰', '統一', '奔騰'),
    ('統一黑馬', '統一', '黑馬'),
    ('統一龍馬', '統一', '龍馬'),
    ('安聯台灣科技', '安聯', '台灣科技'),
    ('安聯台灣大壩', '安聯', '台灣大壩'),
    ('安聯台灣智慧', '安聯', '台灣智慧'),
    ('野村優質', '野村', '優質'),
]
HEADERS = {
    'name': ('基金名稱',), 'company': ('公司名稱',),
    'date': ('日期', '資料日期', '淨值日期'),
    'nav': ('基金淨值', '淨值'), 'currency': ('幣別', '計價幣別'),
    'code': ('基金代號', '基金代碼'),
    'change': ('漲跌', '漲跌金額'), 'percent': ('漲跌幅',),
}

def clean(s):
    return re.sub(r'[\s\u3000\ufeff\-－_（）()]', '', str(s or '')).replace('臺', '台')

def field(row, kind):
    for key in HEADERS[kind]:
        if key in row:
            return (row[key] or '').strip()
    return ''

def decode(data):
    for encoding in ('utf-8-sig', 'cp950', 'big5'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError('Unsupported CSV encoding')

def parse_date(value):
    s = str(value).strip()
    for fmt in ('%Y/%m/%d', '%Y-%m-%d', '%Y%m%d'):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    if re.fullmatch(r'\d{3}/\d{1,2}/\d{1,2}', s):
        y, m, d = map(int, s.split('/'))
        return datetime(y + 1911, m, d).date().isoformat()
    return None

def number(value):
    s = str(value or '').strip().replace(',', '').replace('%', '').replace('＋', '+').replace('−', '-')
    try:
        n = float(s)
        return n if n == n and abs(n) != float('inf') else None
    except ValueError:
        return None

def main():
    req = urllib.request.Request(SOURCE, headers={'User-Agent': 'WealthNotesFundMonitor/1.0'})
    with urllib.request.urlopen(req, timeout=35) as response:
        raw = response.read(15_000_001)
    if len(raw) > 15_000_000:
        raise RuntimeError('CSV exceeds safety size limit')
    reader = csv.DictReader(io.StringIO(decode(raw)))
    if not reader.fieldnames or not {'基金名稱', '基金淨值', '日期'}.issubset(set(reader.fieldnames)):
        raise RuntimeError('Official CSV columns changed: ' + str(reader.fieldnames))
    rows = list(reader)
    if not rows:
        raise RuntimeError('Official CSV is empty')
    results = []
    for display, manager, keyword in FUNDS:
        candidates = []
        for row in rows:
            name = field(row, 'name')
            company = field(row, 'company')
            currency = clean(field(row, 'currency')).upper()
            if keyword not in clean(name) or (manager not in clean(name) and manager not in clean(company)):
                continue
            if currency not in ('TWD', 'NTD', '新台幣', '新臺幣', '台幣'):
                continue
            nav = number(field(row, 'nav'))
            date = parse_date(field(row, 'date'))
            if nav is None or nav <= 0 or not date:
                continue
            candidates.append({'official_name': name, 'fund_code': field(row, 'code'), 'date': date,
                               'nav': nav, 'currency': field(row, 'currency'),
                               'change': number(field(row, 'change')),
                               'change_percent_source': field(row, 'percent')})
        # Different share classes must not be collapsed. Latest record for the same exact class is OK.
        identities = {(x['official_name'], x['fund_code']) for x in candidates}
        if len(identities) == 1:
            selected = max(candidates, key=lambda x: x['date'])
            results.append({'name': display, 'status': 'ok', **selected})
        else:
            results.append({'name': display, 'status': 'not_found' if not candidates else 'ambiguous',
                            'candidate_count': len(identities),
                            'candidates': sorted([{'official_name': n, 'fund_code': c} for n, c in identities], key=lambda x: x['official_name'])[:15]})
    output = {'source': SOURCE, 'source_description': '金管會政府開放資料／投信投顧公會每日淨值',
              'checked_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
              'funds': results,
              'note': '資料日期為基金淨值日，非即時報價。ambiguous 表示多個級別待人工確認。'}
    path = Path('data/funds.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Updated', path, '; confirmed', sum(f['status'] == 'ok' for f in results), 'of', len(results))
    for f in results:
        print(f['name'], f['status'], f.get('date', ''), f.get('official_name', ''))

if __name__ == '__main__':
    main()
