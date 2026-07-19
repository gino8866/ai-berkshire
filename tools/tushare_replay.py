#!/usr/bin/env python3
"""Tushare Replay API 数据工具 - 全市场 A 股日线 + 财报数据获取。

通过 Tushare Pro Replay 转发服务（ai-tool.indevs.in）获取 A 股全市场行情和财报数据。
零外部依赖（仅 Python stdlib），由 Claude Code Skills 自动调用。

用法：
    python tools/tushare_replay.py stock_basic                       # 全市场A股列表
    python tools/tushare_replay.py daily --trade-date 20260710        # 按交易日拉全市场日线
    python tools/tushare_replay.py daily --ts-code 600519.SH --start 20250101 --end 20260710  # 单股历史日线
    python tools/tushare_replay.py financials --ts-code 600519.SH     # 单股三大财报+财务指标
"""

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows 非 UTF-8 控制台兼容
_STDOUT_ENCODING = (getattr(sys.stdout, "encoding", "") or "").lower()
if _STDOUT_ENCODING and _STDOUT_ENCODING != "utf-8" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except ValueError:
        pass

# ---------------------------------------------------------------------------
# DNS fallback for ai-tool.indevs.in / tushare.indevs.in
# 来自官方文档示例：当本地 DNS 解析不到域名时，回退到 Cloudflare IP。
# 保持原始 HTTPS 主机名、Host 头和 SNI 不变。
# ---------------------------------------------------------------------------
_TUSHARE_DNS_FALLBACKS = {
    "ai-tool.indevs.in": ["172.67.197.91"],
    "tushare.indevs.in": ["172.67.197.91"],
}
_tushare_original_getaddrinfo = socket.getaddrinfo
_tushare_original_gethostbyname = socket.gethostbyname


def _tushare_normalize_host(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    return host.rstrip(".") if isinstance(host, str) else host


def _tushare_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _tushare_original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        fallback_ips = _TUSHARE_DNS_FALLBACKS.get(_tushare_normalize_host(host))
        if not fallback_ips:
            raise
        results = []
        for fallback_ip in fallback_ips:
            try:
                results.extend(_tushare_original_getaddrinfo(fallback_ip, port, family, type, proto, flags))
            except socket.gaierror:
                continue
        if not results:
            raise
        return results


def _tushare_gethostbyname(host):
    try:
        return _tushare_original_gethostbyname(host)
    except socket.gaierror:
        fallback_ips = _TUSHARE_DNS_FALLBACKS.get(_tushare_normalize_host(host))
        if not fallback_ips:
            raise
        return fallback_ips[0]


socket.getaddrinfo = _tushare_getaddrinfo
socket.gethostbyname = _tushare_gethostbyname

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
API_KEY = "huanghanchi"  # Tushare Replay 转发 API Key
BASE_URL = "https://ai-tool.indevs.in/tushare/pro"
DEFAULT_TIMEOUT = 30
RATE_LIMIT_SLEEP = 0.3  # 节流，避免触发限流
MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------

def _request(api_name, params=None):
    """调用 /tushare/pro/<api_name>，返回 JSON dict。"""
    url = f"{BASE_URL}/{api_name}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        url = f"{url}?{urllib.parse.urlencode(clean)}"

    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": API_KEY,
            "User-Agent": "ai-berkshire/1.0",
            "Accept": "application/json",
        },
    )

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 503, 504):
                wait = 2 ** attempt
                print(f"  ⚠️ HTTP {e.code}，{wait}s 后重试 ({attempt + 1}/{MAX_RETRIES})...", file=sys.stderr)
                time.sleep(wait)
                continue
            # 非 5xx 重试场景，直接抛出
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {e.code} 调用 {api_name} 失败：{body}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  ⚠️ 网络错误 {e}，{wait}s 后重试 ({attempt + 1}/{MAX_RETRIES})...", file=sys.stderr)
            time.sleep(wait)

    raise ConnectionError(f"请求 {api_name} 失败，重试 {MAX_RETRIES} 次：{last_err}")


def _rows_to_dicts(data):
    """tushare pro 返回二维数组 + fields 分离格式，转成 list[dict]。"""
    payload = data.get("data", {}) if isinstance(data, dict) else {}
    fields = payload.get("fields", [])
    items = payload.get("items", [])
    if not fields or not items:
        return items if isinstance(items, list) else []
    return [dict(zip(fields, row)) if isinstance(row, (list, tuple)) else row for row in items]


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------

def _fmt_yi(value):
    """金额格式化：千元 -> 亿/万。tushare amount 单位是千元。"""
    if value is None or value == "":
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    # tushare amount 单位千元，先转元
    yuan = v * 1000
    if abs(yuan) >= 1e8:
        return f"{yuan / 1e8:.2f}亿"
    if abs(yuan) >= 1e4:
        return f"{yuan / 1e4:.2f}万"
    return f"{yuan:.0f}"


def _fmt_pct(value):
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return str(value)


def _fmt_num(value, ndigits=2):
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):.{ndigits}f}"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

def cmd_stock_basic(args):
    """全市场 A 股列表。"""
    params = {"list_status": "L"}  # L=上市 D=退市 P=暂停
    if args.exchange:
        params["exchange"] = args.exchange

    data = _request("stock_basic", params)
    items = _rows_to_dicts(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"fields": data.get("data", {}).get("fields", []), "items": items}, f, ensure_ascii=False, indent=2)
        print(f"✅ 已写入 {args.output}，共 {len(items)} 只股票")
        return

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    print(f"全市场 A 股列表：共 {len(items)} 只")
    print("=" * 80)
    print(f"{'代码':<14}{'名称':<10}{'行业':<12}{'市场':<8}{'上市日期':<12}")
    print("-" * 80)
    for it in items[:50]:
        print(f"{it.get('ts_code', ''):<14}{it.get('name', '')[:8]:<10}"
              f"{(it.get('industry') or '-')[:10]:<12}{it.get('market', ''):<8}"
              f"{it.get('list_date', ''):<12}")
    if len(items) > 50:
        print(f"... 还有 {len(items) - 50} 只，使用 --json 或 --output 查看全部")


def cmd_daily(args):
    """日线行情：按交易日拉全市场 或 按股票拉历史。"""
    params = {}
    if args.trade_date:
        params["trade_date"] = args.trade_date
    if args.ts_code:
        params["ts_code"] = args.ts_code
    if args.start:
        params["start_date"] = args.start
    if args.end:
        params["end_date"] = args.end
    if args.adj:
        params["adj"] = args.adj

    data = _request("daily", params)
    items = _rows_to_dicts(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({"fields": data.get("data", {}).get("fields", []), "items": items}, f, ensure_ascii=False, indent=2)
        print(f"✅ 已写入 {args.output}，共 {len(items)} 条")
        return

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    label = f"交易日 {args.trade_date}" if args.trade_date else f"{args.ts_code} {args.start or ''}-{args.end or ''}"
    print(f"日线数据（{label}）：共 {len(items)} 条")
    print("=" * 90)
    if not items:
        return
    print(f"{'代码':<14}{'日期':<10}{'开':<10}{'高':<10}{'低':<10}{'收':<10}{'涨跌幅':<10}{'成交额':<14}")
    print("-" * 90)
    for it in items[:30]:
        print(f"{it.get('ts_code', ''):<14}{it.get('trade_date', ''):<10}"
              f"{_fmt_num(it.get('open')):<10}{_fmt_num(it.get('high')):<10}"
              f"{_fmt_num(it.get('low')):<10}{_fmt_num(it.get('close')):<10}"
              f"{_fmt_pct(it.get('pct_chg')):<10}{_fmt_yi(it.get('amount')):<14}")
    if len(items) > 30:
        print(f"... 还有 {len(items) - 30} 条，使用 --json 或 --output 查看全部")


def cmd_financials(args):
    """单股三大财报 + 财务指标。"""
    ts_code = args.ts_code
    limit = args.limit

    print(f"📊 {ts_code} 财务数据获取中...", file=sys.stderr)

    result = {"ts_code": ts_code, "income": [], "balancesheet": [], "cashflow": [], "fina_indicator": []}

    print(f"  拉取 income...", file=sys.stderr)
    data = _request("income", {"ts_code": ts_code, "limit": limit})
    result["income"] = _rows_to_dicts(data)
    time.sleep(RATE_LIMIT_SLEEP)

    print(f"  拉取 balancesheet...", file=sys.stderr)
    data = _request("balancesheet", {"ts_code": ts_code, "limit": limit})
    result["balancesheet"] = _rows_to_dicts(data)
    time.sleep(RATE_LIMIT_SLEEP)

    print(f"  拉取 cashflow...", file=sys.stderr)
    data = _request("cashflow", {"ts_code": ts_code, "limit": limit})
    result["cashflow"] = _rows_to_dicts(data)
    time.sleep(RATE_LIMIT_SLEEP)

    print(f"  拉取 fina_indicator...", file=sys.stderr)
    data = _request("fina_indicator", {"ts_code": ts_code, "limit": limit})
    result["fina_indicator"] = _rows_to_dicts(data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ 已写入 {args.output}")
        return

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 表格输出：核心财务指标
    print("\n" + "=" * 80)
    print(f"财务指标 (fina_indicator) - {ts_code}")
    print("=" * 80)
    fis = result.get("fina_indicator", [])
    if fis:
        print(f"{'报告期':<12}{'ROE(%)':<10}{'毛利率(%)':<10}{'净利率(%)':<10}{'资产负债率(%)':<14}")
        print("-" * 80)
        for fi in fis[:8]:
            print(f"{fi.get('end_date', ''):<12}{_fmt_num(fi.get('roe')):<10}"
                  f"{_fmt_num(fi.get('grossprofit_margin')):<10}"
                  f"{_fmt_num(fi.get('netprofit_margin')):<10}"
                  f"{_fmt_num(fi.get('debt_to_assets')):<14}")
    else:
        print("  无财务指标数据")

    print(f"\n数据明细：income {len(result['income'])} 条 / "
          f"balancesheet {len(result['balancesheet'])} 条 / "
          f"cashflow {len(result['cashflow'])} 条 / "
          f"fina_indicator {len(result['fina_indicator'])} 条")
    print("提示：使用 --json 或 --output 查看完整字段")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Tushare Replay API 数据工具 - 全市场 A 股日线 + 财报",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--output", "-o", help="输出到文件路径")
    sub = parser.add_subparsers(dest="command")

    p_basic = sub.add_parser("stock_basic", help="全市场 A 股列表")
    p_basic.add_argument("--exchange", choices=["SSE", "SZSE", "BSE"], help="限定交易所")
    p_basic.set_defaults(func=cmd_stock_basic)

    p_daily = sub.add_parser("daily", help="日线行情")
    p_daily.add_argument("--trade-date", help="交易日 YYYYMMDD（拉全市场）")
    p_daily.add_argument("--ts-code", help="股票代码，如 600519.SH")
    p_daily.add_argument("--start", help="开始日期 YYYYMMDD")
    p_daily.add_argument("--end", help="结束日期 YYYYMMDD")
    p_daily.add_argument("--adj", choices=["qfq", "hfq"], help="复权方式 qfq=前复权 hfq=后复权")
    p_daily.set_defaults(func=cmd_daily)

    p_fin = sub.add_parser("financials", help="单股三大财报 + 财务指标")
    p_fin.add_argument("--ts-code", required=True, help="股票代码，如 600519.SH")
    p_fin.add_argument("--limit", type=int, default=10, help="每项报告数（默认 10）")
    p_fin.set_defaults(func=cmd_financials)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
