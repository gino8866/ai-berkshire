# stockai888.top Tushare 代理服务 API 参考文档

**服务地址**：`https://fastapic.stockai888.top`
**协议**：Tushare Pro 兼容协议（`api_name` + `token` + `params`）
**请求方式**：POST，`Content-Type: application/json`

## 调用模板

```python
import urllib.request, json

payload = json.dumps({
    "api_name": "fund_daily",
    "token": "<TOKEN>",
    "params": {
        "ts_code": "510300.SH",
        "start_date": "20260701",
        "end_date": "20260721"
    }
}).encode("utf-8")

req = urllib.request.Request(
    "https://fastapic.stockai888.top",
    data=payload,
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://stockai888.top",
        "Referer": "https://stockai888.top/"
    },
    method="POST"
)

with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode("utf-8"))

# 返回结构
# {
#   "code": 0,
#   "msg": "",
#   "request_id": "xxx",
#   "data": {
#     "fields": ["ts_code", "trade_date", ...],
#     "items": [["510300.SH", "20260721", ...], ...],
#     "has_more": false,
#     "count": 12
#   }
# }
```

## 重要注意事项

1. **必须带浏览器请求头**：否则返回 HTTP 403 + Cloudflare 错误码 1010。
2. **限流**：并发请求超过阈值会返回 429，需配合 sleep(0.3-0.5s) 节流。
3. **`fund_share` 默认只返回深市**：要拉沪市基金份额必须加 `market=SH` 参数。
4. **`fund_nav` 的 `net_asset` 字段为空**：代理服务不返回基金净资产规模数据。
5. **`fund_portfolio` 数据严重滞后**：部分基金持仓数据只更新到 2021 Q2。
6. **场外基金份额季度披露**：`fund_share` 对场外基金（`.OF` 后缀）仅在季度末（3/31、6/30、9/30、12/31）返回数据。

---

## 基金类接口

### 1. fund_basic - 基金基础信息

**作用**：获取基金基础信息，包括名称、类型、成立日、管理费、托管费、基准等。

**请求参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码（可选，不传则返回全市场） |
| `market` | string | 市场筛选：`E`=场内、`O`=场外 |

**返回字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码（.SH/.SZ/.OF 后缀） |
| `name` | string | 基金名称 |
| `management` | string | 基金管理人 |
| `custodian` | string | 基金托管人 |
| `fund_type` | string | 基金大类：股票型/混合型/债券型/货币市场型/商品型/REITs/QDII/另类投资型 |
| `invest_type` | string | 投资类型：被动指数型/混合型等 |
| `found_date` | string | 成立日 YYYYMMDD |
| `list_date` | string | 上市日 YYYYMMDD |
| `issue_date` | string | 发行日 YYYYMMDD |
| `delist_date` | string | 退市日 |
| `issue_amount` | float | 发行份额（亿份） |
| `m_fee` | float | 管理费率（%） |
| `c_fee` | float | 托管费率（%） |
| `p_value` | float | 面值 |
| `min_amount` | float | 起购金额 |
| `benchmark` | string | 业绩比较基准 |
| `status` | string | 状态：`L`=在交易、`D`=退市、`I`=发行中 |
| `purc_startdate` | string | 申购开始日 |
| `redm_startdate` | string | 赎回开始日 |
| `market` | string | 市场：`E`=场内、`O`=场外 |
| `type` | string | 基金类型（契约型开放式等） |

**调用示例**：
```python
call("fund_basic", {"market": "E"})  # 全市场场内基金
call("fund_basic", {"ts_code": "510300.SH"})  # 单只基金
```

---

### 2. fund_daily - 场内基金日线行情

**作用**：获取 ETF/LOF 等场内基金的日线行情数据。

**请求参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码（与 `trade_date` 二选一） |
| `trade_date` | string | 交易日 YYYYMMDD（拉全市场） |
| `start_date` | string | 起始日期 YYYYMMDD |
| `end_date` | string | 结束日期 YYYYMMDD |

**返回字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `trade_date` | string | 交易日 YYYYMMDD |
| `open` | float | 开盘价 |
| `high` | float | 最高价 |
| `low` | float | 最低价 |
| `close` | float | 收盘价 |
| `pre_close` | float | 昨收价 |
| `change` | float | 涨跌额 |
| `pct_chg` | float | 涨跌幅（%） |
| `vol` | float | 成交量（手） |
| `amount` | float | 成交额（千元） |

**调用示例**：
```python
call("fund_daily", {"ts_code": "510300.SH", "start_date": "20260701", "end_date": "20260721"})
call("fund_daily", {"trade_date": "20260721"})  # 全市场当日（约 2000+ 只）
```

---

### 3. fund_nav - 基金净值

**作用**：获取基金单位净值、累计净值等数据。场内场外基金均有，T+1 披露。

**请求参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `start_date` | string | 起始日期 YYYYMMDD |
| `end_date` | string | 结束日期 YYYYMMDD |
| `trade_date` | string | 指定日期（⚠️ 代理服务 500 错误，不可用） |

**返回字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `ann_date` | string | 公告日期 |
| `nav_date` | string | 净值日期 |
| `unit_nav` | float | 单位净值（元） |
| `accum_nav` | float | 累计净值（元） |
| `accum_div` | float | 累计分红 |
| `net_asset` | float | 基金净资产（⚠️ 代理服务为空） |
| `total_netasset` | float | 合计净资产（⚠️ 代理服务为空） |
| `adj_nav` | float | 复权净值 |
| `update_flag` | string | 更新标志 |

**调用示例**：
```python
call("fund_nav", {"ts_code": "005827.OF", "start_date": "20260701", "end_date": "20260721"})
```

---

### 4. fund_share - 基金份额

**作用**：获取基金总份额。**场内 ETF/LOF 日频披露，场外基金季度披露**。

**请求参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `trade_date` | string | 交易日 YYYYMMDD（拉全市场） |
| `start_date` | string | 起始日期 |
| `end_date` | string | 结束日期 |
| `market` | string | **必须传**：`SH`=沪市、`SZ`=深市（不传默认只返回深市） |

**返回字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `trade_date` | string | 日期 |
| `fd_share` | float | 基金份额（万份） |
| `fund_type` | string | 基金类型（场外基金此字段为 None） |
| `market` | string | 市场：SH/SZ/O |

**单位换算**：
- `fd_share` 单位为**万份**
- 换算为亿份：`fd_share / 10000`
- 估算规模（亿元）：`fd_share(万份) × close(元) / 10000`

**调用示例**：
```python
# 单只 ETF 日频
call("fund_share", {"ts_code": "510300.SH", "start_date": "20260101", "end_date": "20260721"})

# 全市场沪市
call("fund_share", {"trade_date": "20260721", "market": "SH"})

# 全市场深市
call("fund_share", {"trade_date": "20260721", "market": "SZ"})

# 场外基金（季度披露）
call("fund_share", {"ts_code": "110011.OF", "start_date": "20260101", "end_date": "20260630"})
```

---

### 5. fund_portfolio - 基金持仓股票

**作用**：获取基金持仓股票明细。

**请求参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `period` | string | 报告期 YYYYMMDD（如 20260331） |

**返回字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `ann_date` | string | 公告日 |
| `end_date` | string | 报告期截止日 |
| `symbol` | string | 股票代码 |
| `mkv` | float | 市值（万元） |
| `amount` | float | 持股数（万股） |
| `stk_mkv_ratio` | float | 占股票市值比 |
| `stk_float_ratio` | float | 占流通股比 |

**数据完整性提示**：
- 季报（Q1/Q3）：仅前十大重仓股，约 15 条
- 半年报/年报：完整持仓，约 300-400 条
- **⚠️ 部分基金数据严重滞后**：如 110011.OF 只更新到 2021 Q2
- 510300.SH 最新数据为 2026 Q1（15 条）

**调用示例**：
```python
call("fund_portfolio", {"ts_code": "510300.SH", "period": "20251231"})  # 2025 年报完整持仓
call("fund_portfolio", {"ts_code": "510300.SH"})  # 所有历史期间
```

---

### 6. fund_manager - 基金经理信息

**作用**：获取基金经理历史任职记录和简历。

**请求参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |

**返回字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `ann_date` | string | 公告日 |
| `name` | string | 基金经理姓名 |
| `gender` | string | 性别 |
| `birth_year` | string | 出生年份 |
| `edu` | string | 学历 |
| `nationality` | string | 国籍 |
| `begin_dates` | string | 任职开始日 |
| `end_date` | string | 任职结束日（None 表示在任） |
| `resume` | string | 简历 |

**调用示例**：
```python
call("fund_manager", {"ts_code": "110011.OF"})
```

---

### 7. fund_div - 基金分红

**作用**：获取基金历史分红记录。

**请求参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |

**返回字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts_code` | string | 基金代码 |
| `ann_date` | string | 公告日 |
| `imp_anndate` | string | 实施公告日 |
| `base_date` | string | 权益登记日 |
| `div_proc` | string | 流程状态（实施/预案） |
| `record_date` | string | 除息日 |
| `ex_date` | string | 除权日 |
| `pay_date` | string | 派现日 |
| `earpay_date` | string | 红利发放日 |
| `net_ex_date` | string | 净除息日 |
| `div_cash` | float | 每份派现（元） |
| `base_unit` | float | 基准单位 |
| `ear_distr` | float | 收益分配 |
| `ear_amount` | float | 收益金额 |
| `account_date` | string | 派发日 |
| `base_year` | string | 基准年 |

**调用示例**：
```python
call("fund_div", {"ts_code": "110011.OF"})
```

---

## 数据完整性总结

| 数据维度 | 场内 ETF/LOF | 场外基金 |
|---|---|---|
| 基础信息 | ✅ 完整 | ✅ 完整 |
| 日线行情 | ✅ 日频 | ❌ 无（场外无交易价） |
| 单位净值 | ✅ T+1 | ✅ T+1 |
| 基金份额 | ✅ 日频 | ⚠️ 仅季度披露 |
| 基金经理 | ✅ 完整 | ✅ 完整 |
| 分红记录 | ✅ 完整 | ✅ 完整 |
| 持仓股票 | ⚠️ 部分滞后 | ⚠️ 部分滞后 |
| 净资产规模 | ❌ 字段为空 | ❌ 字段为空 |

## 常见应用场景

### 1. 估算 ETF 规模
```python
# 1. 拉最新份额（注意 market 参数）
share = call("fund_share", {"trade_date": "20260721", "market": "SH"})

# 2. 拉最新收盘价
daily = call("fund_daily", {"trade_date": "20260721"})

# 3. 计算：规模(亿元) = fd_share(万份) × close(元) / 10000
```

### 2. 计算 ETF 净申购额
```python
# 1. 拉份额时间序列
share = call("fund_share", {"ts_code": "510300.SH", "start_date": "20260121", "end_date": "20260721"})

# 2. 拉收盘价时间序列
daily = call("fund_daily", {"ts_code": "510300.SH", "start_date": "20260121", "end_date": "20260721"})

# 3. 逐日计算：净申购额(亿元) = (当日份额 - 前日份额)(万份) × 当日收盘(元) / 10000
```

### 3. 估算场外基金规模
```python
# 1. 拉季度末份额（仅季末有数据）
share = call("fund_share", {"ts_code": "110011.OF", "start_date": "20260101", "end_date": "20260630"})

# 2. 拉同期净值
nav = call("fund_nav", {"ts_code": "110011.OF", "start_date": "20260629", "end_date": "20260701"})

# 3. 估算：规模(亿元) = fd_share(亿份) × unit_nav(元)
```

### 4. 筛选大规模基金
```python
# 1. 拉全市场基金基础信息
basic = call("fund_basic", {"market": "E"})

# 2. 按名称筛选（如纯沪深300 ETF）
pure_etfs = [d for d in basic if d["name"].startswith("沪深300ETF") and d["status"] == "L"]

# 3. 并行拉份额（沪深分两次）+ 收盘价，估算规模，筛选 > 100 亿
```

## 完整 Python 封装示例

```python
import urllib.request, json
import time
from concurrent.futures import ThreadPoolExecutor

class StockAI888Client:
    BASE_URL = "https://fastapic.stockai888.top"
    HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://stockai888.top",
        "Referer": "https://stockai888.top/"
    }

    def __init__(self, token):
        self.token = token

    def call(self, api_name, params=None, retries=3):
        for i in range(retries):
            payload = json.dumps({
                "api_name": api_name,
                "token": self.token,
                "params": params or {}
            }).encode("utf-8")
            req = urllib.request.Request(
                self.BASE_URL, data=payload,
                headers=self.HEADERS, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500):
                    time.sleep(1.5 * (i + 1))
                    continue
                raise
        raise RuntimeError(f"调用 {api_name} 失败，重试 {retries} 次")

    def call_parallel(self, tasks, max_workers=8):
        """并行调用多个接口
        tasks: [(api_name, params), ...]
        """
        def fetch(task):
            api_name, params = task
            time.sleep(0.3)  # 节流
            return self.call(api_name, params)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(fetch, tasks))


# 使用示例
client = StockAI888Client(token="<TOKEN>")

# 拉 510300 近 10 天日线
daily = client.call("fund_daily", {
    "ts_code": "510300.SH",
    "start_date": "20260710",
    "end_date": "20260721"
})

# 并行拉多只 ETF 份额
tasks = [("fund_share", {"ts_code": ts, "start_date": "20260121", "end_date": "20260721"})
         for ts in ["510300.SH", "510310.SH", "159919.SZ"]]
results = client.call_parallel(tasks)
```

## 已知数据质量问题

1. **货币 ETF 规模虚高约 50 倍**：511880 银华日利显示 9.29 万亿元，实际约 1,500-2,000 亿元。可能 `fd_share` 对货币 ETF 单位处理有误。

2. **510300 份额系统性偏低约 25%**：估算 1,166 亿元，实际约 1,500 亿元。代理服务数据可能未包含全部份额口径。

3. **场外基金规模估算偏低约 50%**：如 110022 易方达消费行业估算 97 亿元，实际约 200 亿元。可能 `fd_share` 只覆盖个人投资者场外申赎份额。

4. **`fund_portfolio` 部分基金严重滞后**：如 110011.OF 持仓数据只到 2021 Q2，5 年未更新。

5. **1 月单月净赎回数据异常**：510300 显示 1 月单月净赎回约 1,100 亿元，规模偏大，建议用上交所官方数据交叉验证。

## 参考资源

- **Tushare Pro 官方文档**：https://tushare.pro/document/2
- **上交所 ETF 每日份额**：https://www.sse.com.cn/disclosure/fund/etfinfo/
- **深交所 ETF 数据**：http://www.szse.cn/disclosure/fund/
- **基金定期报告**：各基金公司官网或证监会基金电子披露网站
