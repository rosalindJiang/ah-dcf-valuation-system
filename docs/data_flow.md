# 数据流程说明文档

## 1. 整体数据流概览

```
┌─────────────────┐      ┌──────────────────────┐      ┌────────────────────┐
│  config/        │      │  外部数据源            │      │  SQLite 数据库      │
│  settings.py    │      │  （AkShare）           │      │  data/ah_dcf.db    │
│                 │      │                        │      │                    │
│  A_SHARE_STOCKS │─────▶│  ak.stock_zh_a_hist()  │─────▶│  stock_prices 表   │
│  H_SHARE_STOCKS │─────▶│  ak.stock_hk_hist()    │      │  source=akshare_a  │
│  START_DATE     │      │                        │      │  source=akshare_hk │
│  END_DATE       │      └──────────────────────┘      └─────────┬──────────┘
│  DCF 参数       │◀─────────────────────────────────────────────┤
└─────────────────┘                                              │
        │                                             ┌──────────▼──────────┐
        └────────────────────────────────────────────▶│  DCF 估值计算        │
                                                       │  src/dcf_model.py   │
                                                       └──────────┬──────────┘
                                                                  │
                                                       ┌──────────▼──────────┐
                                                       │  dcf_valuation_     │
                                                       │  results 表         │
                                                       └─────────────────────┘
```

---

## 2. 分阶段数据流详解

### Phase 0 — 配置加载

**触发**：`main.py` 或任意 `scripts/` 脚本启动时自动执行。

**数据流**：

```
config/settings.py
    ├── A_SHARE_STOCKS = ["600519", "000001", "600000", "601318", "000858"]
    │                    # AkShare 格式：6位纯数字，无交易所前缀
    ├── H_SHARE_STOCKS = ["00700", "00941", "00005", "01299", "02318"]
    │                    # AkShare 格式：5位纯数字，无 .HK 后缀
    ├── START_DATE = "2023-01-01"
    ├── END_DATE   = "2024-12-31"
    ├── DB_PATH    = "<project_root>/data/ah_dcf.db"
    ├── DCF 全局参数（DEFAULT_WACC=0.10, TERMINAL_GROWTH_RATE=0.03, ...）
    └── STOCK_FINANCIALS = {
            "600519": {"revenue": 150_300_000_000, "shares": 1_256_197_800,
                       "wacc": 0.08, "revenue_growth_rate": 0.12},
            ...（10 只股票各自的真实年报营收、总股本、WACC 和增长率）
        }
            │
            ▼
    各模块 import settings → 直接使用常量
```

---

### Phase 1 — 数据库初始化

**入口**：`main.py` Step 1 / `scripts/init_db.py`

**数据流**：

```
src/database.init_tables()
    ├── CREATE TABLE IF NOT EXISTS stock_prices
    │     (id, stock_code, trade_date, open, high, low, close,
    │      volume, amount, source, created_at)
    │     UNIQUE (stock_code, trade_date)
    │
    ├── CREATE TABLE IF NOT EXISTS financial_assumptions
    │     （预留表，用于未来存储按股票/日期的自定义假设）
    │
    └── CREATE TABLE IF NOT EXISTS dcf_valuation_results
          (id, stock_code, valuation_date, forecast_years, wacc,
           terminal_growth_rate, estimated_intrinsic_value,
           latest_market_price, upside_downside_pct,
           assumptions_json, created_at)
          UNIQUE (stock_code, valuation_date)
                  │
                  ▼
          data/ah_dcf.db（文件不存在则创建，已存在则跳过）
```

**特性**：`CREATE TABLE IF NOT EXISTS` 保证幂等，重复执行不破坏已有数据。

---

### Phase 2 — A 股数据下载与入库

**入口**：`main.py` Step 2 / `scripts/run_download.py`  
**调用链**：`download_a_share_data()` → `_download_single_a_share()` → `database.upsert_stock_prices()`

**数据流**：

```
settings.A_SHARE_STOCKS + settings.START_DATE + settings.END_DATE
    │
    ▼
_to_akshare_date()  # "2023-01-01" → "20230101"（AkShare 要求的格式）
    │
    ▼
for each stock_code in A_SHARE_STOCKS:
    ak.stock_zh_a_hist(
        symbol=stock_code,      # 如 "600519"
        period="daily",
        start_date="20230101",
        end_date="20241231",
        adjust="",              # 不复权；可改 "qfq"（前复权）
    )
    │
    ├── 返回 DataFrame，中文列名：日期, 开盘, 最高, 最低, 收盘, 成交量, 成交额, ...
    │
    ▼
_parse_akshare_df()
    ├── rename 中文列名 → 英文字段名（日期→trade_date, 收盘→close, ...）
    ├── 补充 stock_code 和 source="akshare_a"
    └── 过滤 close 为空或为 0 的行
    │
    ▼
database.upsert_stock_prices(records)
    │
    INSERT OR REPLACE INTO stock_prices
        (stock_code, trade_date, open, high, low, close, volume, amount, source)
    │
    ▼
data/ah_dcf.db → stock_prices 表（每只约 484 条/两年）
```

**数据量估算（全市场）**：
- A 股 5000 只 × 500 交易日 = 250 万条记录
- 每条约 200 字节 → 约 500MB SQLite 文件
- 可通过批量下载 + 断点重跑（`INSERT OR REPLACE` 幂等）应对中断

---

### Phase 3 — H 股数据下载与入库

**入口**：`main.py` Step 2 / `scripts/run_download.py`  
**调用链**：`download_hk_stock_data()` → `_download_single_hk_share()` → `database.upsert_stock_prices()`

**数据流**：

```
settings.H_SHARE_STOCKS + settings.START_DATE + settings.END_DATE
    │
    ▼
_to_akshare_date()  # "2023-01-01" → "20230101"
    │
    ▼
for each stock_code in H_SHARE_STOCKS:
    ak.stock_hk_hist(
        symbol=stock_code,      # 如 "00700"
        period="daily",
        start_date="20230101",
        end_date="20241231",
        adjust="",
    )
    │
    ├── 返回 DataFrame，列名结构与 A 股相同（日期, 开盘, 收盘, ...）
    │
    ▼
_parse_akshare_df()
    ├── rename 列名（与 A 股共用同一解析函数）
    ├── source="akshare_hk"
    └── 过滤无效行
    │
    ▼
database.upsert_stock_prices(records)
    │
    INSERT OR REPLACE INTO stock_prices
    │
    ▼
data/ah_dcf.db → stock_prices 表（每只约 489 条/两年，含港股非交易日过滤）
```

**与 A 股的处理差异**：
- A 股收盘价单位：人民币元；H 股收盘价单位：港元
- A 股代码 6 位，H 股代码 5 位；两者均为纯数字，`stock_code` 字段原样存储
- 港股交易日历与 A 股略有差异（含港股通非交易日），由 AkShare 自动处理

---

### Phase 4 — DCF 估值计算与入库

**入口**：`main.py` Step 3 / `scripts/run_valuation.py`  
**调用链**：`run_pipeline()` → `_valuate_single()` → `DCFModel.run_valuation()` → `database.upsert_dcf_result()`

**数据流**：

```
settings.A_SHARE_STOCKS + settings.H_SHARE_STOCKS（合并为 10 只）
    │
    ▼
for each stock_code:
    │
    ├─①  database.query_latest_close(stock_code)
    │         SELECT stock_code, trade_date, close
    │         FROM stock_prices
    │         WHERE stock_code = ?
    │         ORDER BY trade_date DESC LIMIT 1
    │                   │
    │                   ▼
    │         latest_market_price（最新收盘价，元或港元）
    │
    ├─②  fin = STOCK_FINANCIALS.get(stock_code, {})
    │         DCFAssumptions(
    │             wacc               = fin.get("wacc", DEFAULT_WACC),
    │             revenue_growth_rate= fin.get("revenue_growth_rate", REVENUE_GROWTH_RATE),
    │         )         # 其余参数继续使用全局 settings 默认值
    │
    ├─③  DCFModel(stock_code, market_price, assumptions,
    │             base_revenue=fin["revenue"], total_shares=fin["shares"])
    │         │
    │         ├── forecast_free_cash_flow()
    │         │       base_revenue = fin["revenue"]（年报近似营收，非虚拟代理）
    │         │       for t in 1..N:
    │         │           revenue  *= (1 + revenue_growth_rate)
    │         │           nopat     = revenue × OPERATING_MARGIN × (1 - TAX_RATE)
    │         │           da        = revenue × DEPRECIATION_RATIO
    │         │           capex     = revenue × CAPEX_RATIO
    │         │           delta_wc  = revenue × WORKING_CAPITAL_RATIO
    │         │           FCFF_t    = nopat + da - capex - delta_wc
    │         │       return [FCFF_1, ..., FCFF_N]
    │         │
    │         ├── calculate_terminal_value(FCFF_N)
    │         │       TV = FCFF_N × (1 + g) / (WACC - g)
    │         │
    │         ├── discount_cash_flows(fcff_list, TV)
    │         │       EV = Σ[FCFF_t / (1+WACC)^t] + TV / (1+WACC)^N
    │         │
    │         └── calculate_intrinsic_value(EV)
    │                 total_shares    = fin["shares"]（年报近似总股本）
    │                 intrinsic_value = EV / total_shares
    │                 upside_pct      = (intrinsic - market_price) / market_price × 100%
    │
    └─④  database.upsert_dcf_result(result)
              INSERT OR REPLACE INTO dcf_valuation_results
                  (stock_code, valuation_date, forecast_years, wacc,
                   terminal_growth_rate, estimated_intrinsic_value,
                   latest_market_price, upside_downside_pct, assumptions_json)
              │
              ▼
          data/ah_dcf.db → dcf_valuation_results 表
```

---

### Phase 5 — 可视化报告生成

**入口**：`main.py` Step 4 / `scripts/run_report.py`  
**调用链**：`generate_report()` → 四个图表函数 → `_build_html()` → 写入 HTML 文件

**数据流**：

```
database.query_all_dcf_results()
    │  每只股票取 MAX(valuation_date) 最新一条，按 upside_downside_pct DESC 排序
    │
    ▼
results（估值结果列表）
    │
    ├─① 预加载全量价格数据
    │       database.query_price_history(code) × 10只
    │       price_history = {code: [{date, close}, ...]}
    │
    └─② _build_html(results, price_history)
            ├── 嵌入 JSON 数据到 <script> 块：
            │     ALL_DCF = [...估值结果...]
            │     ALL_HISTORY = {code: [{date, close}]}
            │     A_STOCKS / H_STOCKS = [...]
            ├── 嵌入 Plotly CDN（plotly-2.26.0.min.js）
            ├── 嵌入 _css()：渐变标题、筛选面板、卡片样式
            ├── 嵌入 _js()：renderAll() / renderTable() / renderUpsideBar()
            │              renderPriceComparison() / renderPriceHistory()
            │              selectAll() / selectNone() / selectAOnly() / selectHOnly()
            └── 交互筛选面板 HTML：股票复选框 + 日期选择器

    浏览器端交互流程：
        用户改变复选框 / 日期
            → renderAll()
            → 过滤 ALL_DCF / ALL_HISTORY
            → Plotly.react(divId, traces, layout) × 5 个图表
            → 统计卡片数字同步更新
    │
    ▼
data/dcf_report.html（约 230KB，独立文件，无需服务器）
* 图表渲染需要加载 Plotly CDN；如需完全离线，可将 plotly.min.js 本地化
```

---

### Phase 6 — 结果查询与投资参考

**方式 A：HTML 可视化报告（run_report.py / main.py 自动生成）**

```
open data/dcf_report.html   # 浏览器打开，查看交互式图表
```

**方式 B：命令行输出（run_valuation.py / main.py 自动打印）**

```
================================================================================
                             DCF 估值结果汇总
================================================================================
股票代码           市场价       内在价值    高低估(%)     估值日期       判断
--------------------------------------------------------------------------------
02318           49.27      112.06    +127.5%    2026-05-02  ▲低估
601318          64.02      112.06     +75.0%    2026-05-02  ▲低估
00941           95.64      105.89     +10.7%    2026-05-02  ▲低估
01299           36.27       35.59      -1.9%    2026-05-02  →合理
00005           56.67       51.15      -9.7%    2026-05-02  →合理
000001          21.05       13.63     -35.2%    2026-05-02  ▼高估
600000          20.23        9.58     -52.6%    2026-05-02  ▼高估
000858         169.37       73.84     -56.4%    2026-05-02  ▼高估
600519        1699.48      434.92     -74.4%    2026-05-02  ▼高估
00700          458.57      115.98     -74.7%    2026-05-02  ▼高估
================================================================================
  完成 10 只，跳过 0 只
  注意：当前为 demo 简化 DCF，估值仅供参考，不构成投资建议。
================================================================================
```

**方式 C：直接查询 SQLite**

```sql
-- 查看所有估值结果（按高低估排序）
SELECT stock_code, valuation_date, latest_market_price,
       estimated_intrinsic_value, upside_downside_pct
FROM dcf_valuation_results
ORDER BY upside_downside_pct DESC;

-- 查看 A 股和 H 股数据量对比
SELECT source, COUNT(*) as records
FROM stock_prices GROUP BY source;
-- 预期：akshare_a: 2420, akshare_hk: 2445

-- 查看贵州茅台最近 10 条收盘价
SELECT trade_date, close FROM stock_prices
WHERE stock_code = '600519'
ORDER BY trade_date DESC LIMIT 10;

-- 查看估值参数快照（可复现历史估值）
SELECT stock_code, valuation_date, assumptions_json
FROM dcf_valuation_results
WHERE stock_code = '600519';
```

---

## 3. 数据质量与文件输出

| 产出文件 | 路径 | 说明 |
|----------|------|------|
| 数据库 | `data/ah_dcf.db` | 行情数据 + 估值结果，不提交到版本库 |
| 可视化报告 | `data/dcf_report.html` | Plotly 交互式 HTML，不提交到版本库 |

## 4. 数据质量控制

| 环节 | 控制措施 |
|------|----------|
| AkShare 网络异常 | 单只股票 `try/except` 捕获，记录日志后继续，不中断整批 |
| 返回 DataFrame 为空 | `df.empty` 判断，记录 WARNING 后跳过 |
| 无效收盘价（空/零） | `_parse_akshare_df()` 过滤，不写入数据库 |
| 重复下载写入 | `INSERT OR REPLACE` 幂等处理，重复运行安全 |
| 无价格数据的估值 | `query_latest_close()` 返回 None 时跳过，列入"跳过"汇总 |
| WACC ≤ 终端增长率 | `DCFModel.__init__` 抛出 `ValueError`，提前终止 |
| 日期格式错误 | `validate_date_range()` 在下载前校验格式和先后顺序 |

---

## 4. 数据血缘（Data Lineage）

```
AkShare（东方财富数据源）
    ├─[A股日线行情]──▶ stock_prices.source = 'akshare_a'
    └─[H股日线行情]──▶ stock_prices.source = 'akshare_hk'
                                │
                    最新收盘价 (close)
                                │
             ┌──────────────────▼──────────────────┐
             │            DCF 计算                  │
             │  market_price + settings.py 参数      │
             │  → FCFF × N年 + Terminal Value        │
             │  → Enterprise Value → 内在价值        │
             └──────────────────┬──────────────────┘
                                │
                         [估值结果]
                                │
                                ▼
                    dcf_valuation_results
                    .estimated_intrinsic_value   （估算内在价值）
                    .upside_downside_pct         （高低估比例）
                    .assumptions_json            （参数快照，用于复现）
```

`assumptions_json` 字段在每次估值时将完整参数序列化保存，即使未来 `settings.py` 参数发生变化，历史估值结果仍可完整追溯。
