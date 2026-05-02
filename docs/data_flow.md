# 数据流程说明文档

## 1. 整体数据流概览

```
浏览器操作（选股 + 日期范围 + 点击"运行估值"）
    │
    │ POST /api/run {stocks, start_date, end_date}
    ▼
┌─────────────────────────────────────────────┐
│  AkShare 数据下载                            │
│  ak.stock_zh_a_hist() / ak.stock_hk_hist()  │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  SQLite: stock_prices 表                     │
│  UNIQUE(stock_code, trade_date)              │
│  INSERT OR REPLACE（幂等）                   │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  DCF 估值计算（src/dcf_model.py）             │
│  FCFF × N年 + Terminal Value + WACC 折现     │
│  valuation_date = end_date                   │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  SQLite: dcf_valuation_results 表            │
│  UNIQUE(stock_code, valuation_date)          │
│  不同 end_date → 追加新行                    │
│  相同 end_date → 幂等替换                    │
└──────────────────────┬──────────────────────┘
                       │ JSON 响应
                       ▼
┌─────────────────────────────────────────────┐
│  浏览器端 Plotly.js 渲染                      │
│  Plotly.react() 原地更新 5 个图表             │
└─────────────────────────────────────────────┘
```

---

## 2. 分阶段数据流详解

### Phase 0 — 配置加载

**触发**：`app.py` 启动时自动执行。

```
config/settings.py
    ├── A_SHARE_STOCKS = ["600519", "000001", "600000", "601318", "000858"]
    ├── H_SHARE_STOCKS = ["00700", "00941", "00005", "01299", "02318"]
    ├── STOCK_NAMES = {"600519": "贵州茅台", "00700": "腾讯控股", ...}
    ├── START_DATE = "2023-01-01"   # Web 应用默认值，用户可覆盖
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
    STOCK_NAMES → 注入 Jinja2 模板 → 渲染下拉选股框
```

---

### Phase 1 — 数据库初始化

**触发**：`app.py` 启动时调用 `init_tables()`，以及每次 `POST /api/run` 时调用（幂等，已存在则跳过）。

```
src/database.init_tables()
    ├── CREATE TABLE IF NOT EXISTS stock_prices
    │     UNIQUE (stock_code, trade_date)
    │
    ├── CREATE TABLE IF NOT EXISTS financial_assumptions（预留）
    │
    ├── CREATE TABLE IF NOT EXISTS dcf_valuation_results
    │     UNIQUE (stock_code, valuation_date)   ← 追加语义的关键约束
    │
    └── ALTER TABLE dcf_valuation_results ADD COLUMN start_date TEXT
          （迁移：列已存在时静默忽略）
                  │
                  ▼
          data/ah_dcf.db（文件不存在则创建，已存在则跳过）
```

---

### Phase 2 — 用户请求触发

**入口**：浏览器 → `runValuation()` → `POST /api/run`

```
Request payload:
{
  "stocks":     ["600519", "000001", "00700"],  // 用户勾选的股票
  "start_date": "2023-01-01",                   // 用户选择的起始日期
  "end_date":   "2024-12-31"                    // 用户选择的结束日期
}

app.py 验证：
  - stocks 不为空
  - start_date、end_date 均已填写
  - start_date ≤ end_date
  - 按 A_SHARE_STOCKS / H_SHARE_STOCKS 分类为 a_stocks / h_stocks
```

---

### Phase 3 — A 股数据下载与入库

**调用链**：`download_a_share_data(stock_list, start_date, end_date)` → `_download_single_a_share()` → `database.upsert_stock_prices()`

```
a_stocks + start_date + end_date
    │
    ▼
_to_akshare_date()  # "2023-01-01" → "20230101"
    │
    ▼
for each code in a_stocks:
    ak.stock_zh_a_hist(symbol=code, period="daily",
                       start_date="20230101", end_date="20241231", adjust="")
    │
    ▼
_parse_akshare_df()
    ├── rename 中文列名 → 英文字段名
    ├── stock_code, source="akshare_a"
    └── 过滤 close 为空或为 0 的行
    │
    ▼
database.upsert_stock_prices(records)
    INSERT OR REPLACE INTO stock_prices
    │
    ▼
data/ah_dcf.db → stock_prices 表
```

---

### Phase 4 — H 股数据下载与入库

**调用链**：`download_hk_stock_data(stock_list, start_date, end_date)` → `_download_single_hk_share()` → `database.upsert_stock_prices()`

```
h_stocks + start_date + end_date
    │
    ▼（与 A 股处理流程相同，仅接口和 source 不同）
ak.stock_hk_hist(symbol=code, ...)  # code 为 5 位纯数字
    │
    ▼
_parse_akshare_df() → source="akshare_hk"
    │
    ▼
INSERT OR REPLACE INTO stock_prices
```

**与 A 股的处理差异**：A 股收盘价单位为人民币元；H 股为港元。两者均纯数字代码，`stock_code` 字段原样存储。

---

### Phase 5 — DCF 估值计算与入库

**调用链**：`run_pipeline(stock_list, valuation_date=end_date, start_date=start_date)` → `_valuate_single()` → `DCFModel.run_valuation(valuation_date)` → `database.upsert_dcf_result()`

```
stock_list + valuation_date(=end_date) + start_date
    │
    ▼
for each stock_code:
    │
    ├─①  database.query_latest_close(stock_code)
    │         → latest_market_price（最新收盘价）
    │
    ├─②  fin = STOCK_FINANCIALS.get(stock_code, {})
    │         DCFAssumptions(wacc, revenue_growth_rate, ...)
    │
    ├─③  DCFModel(stock_code, market_price, assumptions,
    │             base_revenue=fin["revenue"], total_shares=fin["shares"])
    │         ├── forecast_free_cash_flow() → [FCFF_1..N]
    │         ├── calculate_terminal_value() → TV
    │         ├── discount_cash_flows()      → EV
    │         └── calculate_intrinsic_value()→ EV / total_shares
    │
    └─④  database.upsert_dcf_result(result)
              INSERT OR REPLACE INTO dcf_valuation_results
              (stock_code, valuation_date=end_date, start_date, ...)
              │
              │  追加语义：不同 end_date → 新行；相同 → 幂等替换
              ▼
          data/ah_dcf.db → dcf_valuation_results 表
```

---

### Phase 6 — JSON 响应与前端渲染

```
run_pipeline() 返回 List[dict] 估值结果
    │
    ├─ query_price_history(code, start_date, end_date) × N只
    │
    └─ 组装 JSON 响应：
        {
          "results":  [{stock_code, valuation_date, estimated_intrinsic_value, ...}],
          "history":  {"600519": [{"date": "2024-01-02", "close": 1823.0}, ...]},
          "a_stocks": ["600519", ...],
          "h_stocks": ["00700", ...],
          "errors":   []
        }
            │
            ▼ HTTP 200 JSON
浏览器端（templates/index.html）
    ├─ 更新统计卡片（总数/低估/高估/平均幅度）
    ├─ Plotly.react('chart-table',    ...)  DCF 明细表
    ├─ Plotly.react('chart-upside',   ...)  高低估条形图
    ├─ Plotly.react('chart-compare',  ...)  市场价 vs 内在价值
    ├─ Plotly.react('chart-history-a', ...) A 股走势图
    └─ Plotly.react('chart-history-h', ...) H 股走势图
```

---

## 3. 数据质量控制

| 环节 | 控制措施 |
|------|----------|
| AkShare 网络异常 | 单只股票 `try/except` 捕获，记录日志后继续，不中断整批 |
| 返回 DataFrame 为空 | `df.empty` 判断，记录 WARNING 后跳过 |
| 无效收盘价（空/零） | `_parse_akshare_df()` 过滤，不写入数据库 |
| 重复下载写入 | `INSERT OR REPLACE` 幂等处理，重复运行安全 |
| 无价格数据的估值 | `query_latest_close()` 返回 None 时跳过 |
| WACC ≤ 终端增长率 | `DCFModel.__init__` 抛出 `ValueError`，提前终止 |
| 下载失败 | `errors` 列表返回前端显示，不阻断其他股票估值 |

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
             │  market_price + STOCK_FINANCIALS 参数 │
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
