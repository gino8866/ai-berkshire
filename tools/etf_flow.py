#!/usr/bin/env python3
"""ETF每日净申购量通用工具(沪深两市,零依赖)

数据源:
  沪市ETF: 上交所官方 query.sse.com.cn (资产净值SCALE,亿元)
  深市ETF: 深交所官方 szse.cn/api/report/ShowReport (份额,份,xlsx)
  净值:   东方财富 lsjz (单位净值DWJZ)

口径:
  份额(亿份) = 沪市 SCALE/净值 ; 深市 份额/1e8
  资产净值(亿) = 沪市 SCALE ; 深市 份额×净值/1e8
  净申购(亿份) = 当日份额 - 前日份额
  资金净流入(亿) ≈ 净申购 × 当日净值

用法:
  python tools/etf_flow.py 510300                    # 最近交易日净申购
  python tools/etf_flow.py 510300 159919 588000      # 多只(沪深混合)
  python tools/etf_flow.py 510300 --days 30          # 指定回看天数
  python tools/etf_flow.py 510300 -o out.csv         # 输出CSV
"""

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import urllib.parse
import zipfile
from datetime import datetime, timedelta

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _curl(url, ref=None, t=30):
    """curl 直连,绕过系统代理。"""
    cmd = ['curl', '-s', '--noproxy', '*', '-H', f'User-Agent: {_UA}']
    if ref:
        cmd += ['-H', f'Referer: {ref}']
    cmd += ['-m', str(t), url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=t + 5)
        return r.stdout
    except Exception:
        return b''


def is_sh(code):
    """ETF代码:5/6开头=沪市,1开头=深市。"""
    return code.startswith('5') or code.startswith('6')


# ---- 沪市: 上交所资产净值历史(亿元) ----
_SSE_SQLID = 'COMMON_JJZWZ_JJLB_JJXQ_JJGM_CKLSGM_L'


def fetch_sse(code, days=30):
    """返回 [(日期, 资产净值亿元), ...] 按日期升序。"""
    p = {
        'isPagination': 'true', 'jsonCallBack': 'jsonpCallback',
        'pageNo': '1', 'pageSize': str(days),
        'sqlId': _SSE_SQLID, 'FUND_CODE': code,
    }
    raw = _curl(
        f'http://query.sse.com.cn/commonQuery.do?{urllib.parse.urlencode(p)}',
        'http://etf.sse.com.cn/',
    ).decode('utf-8', 'replace')
    m = re.search(r'\{.*\}', raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0)).get('pageHelp', {}).get('data') or []
    except Exception:
        return []
    out = []
    for r in data:
        try:
            out.append((r['TRADE_DATE'], float(r['SCALE'])))
        except (KeyError, ValueError):
            pass
    return sorted(out)


# ---- 深市: 深交所份额历史(xlsx,份) ----
def fetch_szse_batch(codes, days=30):
    """一次拉区间xlsx,返回 {code: [(日期, 份额份), ...]}。区间≤6个月。"""
    if not codes:
        return {}
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=days + 15)).strftime('%Y-%m-%d')
    url = (
        'https://www.szse.cn/api/report/ShowReport'
        f'?SHOWTYPE=xlsx&CATALOGID=scsj_fund_jjgm&TABKEY=tab1'
        f'&txtStart={start}&txtEnd={end}&jjlb=ETF'
    )
    raw = _curl(url, 'http://www.szse.cn/')
    if raw[:2] != b'PK':
        return {}
    out = {c: [] for c in codes}
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    except Exception:
        return out
    for row in re.findall(r'<row[^>]*>(.*?)</row>', sheet, re.S)[1:]:
        vals = re.findall(r'<is><t>([^<]*)</t></is>', row)
        if len(vals) >= 4 and vals[1] in out:
            try:
                out[vals[1]].append((vals[0], float(vals[3])))
            except ValueError:
                pass
    for c in out:
        out[c].sort()
    return out


# ---- 净值: 东财 ----
def fetch_nav(code, days=60):
    """返回 {日期: 单位净值}。"""
    raw = _curl(
        f'http://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize={days}',
        'https://fundf10.eastmoney.com/',
    ).decode('utf-8', 'replace')
    try:
        lst = json.loads(raw).get('Data', {}).get('LSJZList') or []
        return {r['FSRQ']: float(r['DWJZ']) for r in lst}
    except Exception:
        return {}


def compute(code, days, sz_cache=None):
    """合并规模+净值,算净申购时序。返回 list[dict]。"""
    sh = is_sh(code)
    if sh:
        scale = fetch_sse(code, days)
    elif sz_cache is not None:
        scale = sz_cache.get(code, [])
    else:
        scale = fetch_szse_batch([code], days).get(code, [])
    nav = fetch_nav(code, days + 20)
    if not scale or not nav:
        return []
    rows = []
    for date, raw_val in scale:
        n = nav.get(date)
        if not n:
            continue
        if sh:
            asset, share = raw_val, raw_val / n      # 沪市: SCALE=资产净值(亿)
        else:
            share, asset = raw_val / 1e8, raw_val * n / 1e8  # 深市: 份额(份)->亿份
        rows.append({'date': date, 'nav': n, 'share': share, 'asset': asset})
    rows.sort(key=lambda x: x['date'])
    for i, r in enumerate(rows):
        if i == 0:
            r['share_chg'] = None
            r['flow'] = None
        else:
            r['share_chg'] = r['share'] - rows[i - 1]['share']
            r['flow'] = r['share_chg'] * r['nav']
    return rows


def fmt_flow(rows, code):
    print(f'\n=== {code} ===')
    print(f'{"日期":<12}{"份额(亿份)":>11}{"净值":>9}{"资产净值(亿)":>13}{"净申购(亿份)":>13}{"资金净流入(亿)":>15}')
    for r in rows:
        sc = f'{r["share_chg"]:+.2f}' if r["share_chg"] is not None else '-'
        fl = f'{r["flow"]:+.2f}' if r["flow"] is not None else '-'
        print(f'{r["date"]:<12}{r["share"]:>11.2f}{r["nav"]:>9.4f}{r["asset"]:>13.1f}{sc:>13}{fl:>15}')


def main():
    ap = argparse.ArgumentParser(description='ETF每日净申购量(沪深两市)')
    ap.add_argument('codes', nargs='+', help='ETF代码(可多个,沪深混合)')
    ap.add_argument('--days', type=int, default=15, help='回看天数(默认15)')
    ap.add_argument('-o', '--output', help='输出CSV路径')
    args = ap.parse_args()

    sz_codes = [c for c in args.codes if not is_sh(c)]
    sz_cache = fetch_szse_batch(sz_codes, args.days) if sz_codes else {}

    all_rows = []
    for code in args.codes:
        rows = compute(code, args.days, sz_cache)
        if not rows:
            print(f'{code}: 无数据(检查代码/网络,或该日净值未披露)', file=sys.stderr)
            continue
        fmt_flow(rows, code)
        for r in rows:
            all_rows.append({'code': code, **r})

    if args.output:
        with open(args.output, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=['code', 'date', 'share', 'nav', 'asset', 'share_chg', 'flow'])
            w.writeheader()
            w.writerows(all_rows)
        print(f'\n已写入 {args.output}')


if __name__ == '__main__':
    main()
