# 系统架构设计文档

## 1. 设计目标

构建一个可扩展、可维护的全市场 AH 股 DCF 估值系统，满足以下核心目标：

- **全市场覆盖能力**：架构支持 A 股全市场（5000+ 只）及港股全市场（2000+ 只），demo 阶段以 5+5 只标的验证系统可行性。
- **统一数据源**：A 股和 H 股均通过 AkShare 接口采集，无需注册账号，接口风格一致。
- **模块化分层**：数据采集、存储、计算、调度各自独立，可单独替换或升级。
- **参数化配置**：所有可调参数集中于 `config/settings.py`，零硬编码。
- **Web 优先**：`app.py` 提供交互式选股 + 日期范围 + 一键估值 + 实时图表。

---

## 2. 系统分层架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    Layer 5 – Web 入口层                           │
│   app.py（Flask）                                                 │
│   GET  /         → templates/index.html                          │
│   POST /api/run  → 下载 + 估值 + 返回 JSON                       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                    Layer 4b – Web 展示层                           │
│   templates/index.html                                            │
│   Jinja2 模板 + Plotly.js 客户端渲染                              │
│   Plotly.react() 原地更新 5 个图表，无需刷新页面                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ (JSON)
┌────────────────────────────▼─────────────────────────────────────┐
│                    Layer 4a – Pipeline 调度层                      │
│                    src/valuation_pipeline.py                       │
│   run_pipeline(stock_list, valuation_date, start_date)            │
│   → 批量估值 → 结果入库 → 返回 List[dict]                         │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                    Layer 3 – 估值计算层                            │
│                    src/dcf_model.py                                │
│   DCFAssumptions（参数封装）→ DCFModel（FCFF / TV / 折现）         │
│   run_valuation(valuation_date) → 内在价值 + 高低估%              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                    Layer 2 – 数据存储层                            │
│                    src/database.py                                 │
│   SQLite（data/ah_dcf.db）                                        │
│   stock_prices 表  │  dcf_valuation_results 表（含 start_date）    │
│   UNIQUE(stock_code, valuation_date) → 按日期范围追加语义          │
└──────────┬──────────────────────────────┬────────────────────────┘
           │                              │
┌──────────▼──────────┐       ┌───────────▼──────────────────────┐
│  Layer 1a – A 股    │       │  Layer 1b – H 股采集层            │
│  数据采集层          │       │  数据采集层                       │
│  AkShare            │       │  AkShare                          │
│  ak.stock_zh_a_hist │       │  ak.stock_hk_hist                 │
│  source='akshare_a' │       │  source='akshare_hk'              │
└──────────┬──────────┘       └──────────────────────┬───────────┘
           │                                          │
┌──────────▼──────────────────────────────────────────▼───────────┐
│                    Layer 0 – 配置层                               │
│                    config/settings.py                              │
│   A_SHARE_STOCKS（6位）  H_SHARE_STOCKS（5位）  STOCK_FINANCIALS  │
│   STOCK_NAMES（中文名称映射）                                      │
│   START_DATE / END_DATE  │  DB_PATH  │  DCF 参数  │  LOG_LEVEL   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 各层详细说明

### 3.0 配置层（config/settings.py）

**职责**：集中管理所有可变参数，是系统的唯一真相源（Single Source of Truth）。

| 配置项 | 格式 | 说明 |
|--------|------|------|
| `A_SHARE_STOCKS` | `["600519", ...]` | A 股股票池，AkShare 格式（6位纯数字） |
| `H_SHARE_STOCKS` | `["00700", ...]` | H 股股票池，AkShare 格式（5位纯数字） |
| `STOCK_NAMES` | `dict[str, str]` | 股票代码→中文名称映射，Web UI 展示用 |
| `START_DATE` / `END_DATE` | `"YYYY-MM-DD"` | 默认历史数据日期范围（Web 应用可由用户覆盖） |
| `DB_PATH` | 绝对路径 | SQLite 数据库文件路径（由 BASE_DIR 动态拼接） |
| DCF 全局参数 | `float` / `int` | WACC、终端增长率、预测年数、利润率等默认值 |
| `STOCK_FINANCIALS` | `dict[str, dict]` | 各股票年报近似营收、总股本、WACC 和增长率覆盖值 |

---

### 3.1 数据采集层（src/data_downloader.py）

**职责**：通过 AkShare 拉取 A 股和 H 股真实日线行情，清洗后写入数据库。

**A 股采集**：
- 接口：`ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date, adjust="")`
- 代码格式：6 位纯数字（如 `"600519"`）
- 数据库标记：`source = 'akshare_a'`

**H 股采集**：
- 接口：`ak.stock_hk_hist(symbol, period="daily", start_date, end_date, adjust="")`
- 代码格式：5 位纯数字（如 `"00700"`）
- 数据库标记：`source = 'akshare_hk'`

**列名统一**：`_parse_akshare_df()` 将 AkShare 中文列名映射为内部英文字段名，A/H 两市共用同一解析逻辑。

**容错机制**：单只股票下载失败时捕获异常、记录日志后继续，不影响整批；`df.empty` 判断处理停牌情况；过滤收盘价为空或为零的行。

**扩展到全市场**：
```python
# 获取 A 股全量代码
df = ak.stock_info_a_code_name()
all_a_codes = df["code"].tolist()

# 获取 H 股全量代码
df_hk = ak.stock_hk_spot_em()
all_hk_codes = df_hk["代码"].tolist()
```

---

### 3.2 数据存储层（src/database.py）

**职责**：管理 SQLite 数据库的连接、建表、读写操作。所有 SQL 语句集中于此，业务层通过函数调用交互。

**主要函数**：

| 函数 | 说明 |
|------|------|
| `get_connection()` | 创建数据库连接，WAL 模式，自动创建目录 |
| `init_tables()` | 幂等建表 + `start_date` 列迁移 |
| `upsert_stock_prices()` | 批量写入日线价格，`INSERT OR REPLACE` 幂等 |
| `upsert_dcf_result()` | 写入单只股票 DCF 估值结果（含 start_date） |
| `query_latest_close()` | 查询最新一条收盘价 |
| `query_price_history()` | 查询历史价格序列（支持日期范围过滤） |
| `query_all_dcf_results()` | 每只股票取 MAX(valuation_date) 最新一条，按高低估排序 |

**追加语义**：`UNIQUE(stock_code, valuation_date)`，`valuation_date = end_date`（用户选择的结束日期）。不同 end_date → 新行；相同 end_date → 幂等替换。

---

### 3.3 估值计算层（src/dcf_model.py）

**职责**：实现 DCF 估值算法，封装为 `DCFModel` 类，输出每股内在价值和高低估比例。

**四步计算**：

```
STOCK_FINANCIALS[stock_code]（营收、总股本、WACC、增长率）
    │
    └─ DCFModel(stock_code, market_price, assumptions, base_revenue, total_shares)
          ├─ forecast_free_cash_flow()  → [FCFF_1, ..., FCFF_N]
          ├─ calculate_terminal_value() → TV = FCFF_N × (1+g) / (WACC-g)
          ├─ discount_cash_flows()      → EV = Σ[FCFF_t/(1+WACC)^t] + TV/(1+WACC)^N
          └─ calculate_intrinsic_value()→ EV / total_shares
```

---

### 3.4 Pipeline 调度层（src/valuation_pipeline.py）

**职责**：接收股票列表和日期参数，批量调用 DCFModel，写入数据库，返回结果列表供 Web API 使用。

**签名**：`run_pipeline(stock_list=None, db_path=None, valuation_date=None, start_date=None) -> List[dict]`

---

### 3.5 Web 应用层（app.py + templates/index.html）

**路由**：

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 渲染主页，注入股票列表和默认日期 |
| `/api/run` | POST | 接收 `{stocks, start_date, end_date}`，执行完整流程，返回 JSON |

**`/api/run` 执行流程**：

```
接收 JSON payload（stocks, start_date, end_date）
    → init_tables()（幂等建表）
    → download_a_share_data(a_stocks, start_date, end_date)
    → download_hk_stock_data(h_stocks, start_date, end_date)
    → run_pipeline(stocks, valuation_date=end_date, start_date=start_date)
    → query_price_history(code, start_date, end_date) × N只
    → 返回 {results, history, a_stocks, h_stocks, errors}
```

**前端架构**（templates/index.html）：
- Jinja2 模板，服务端注入股票列表（STOCK_NAMES）
- 自定义下拉多选框（▾），按 A/H 市场分组
- `runValuation()` 异步 fetch POST `/api/run`
- Plotly.js `Plotly.react()` 原地更新 5 个图表，无需刷新页面
- 统计卡片（总数/低估/高估/平均幅度）随结果动态更新

---

## 4. 未来扩展架构（全市场版本）

```
┌──────────────────────────────────────────────────────────┐
│                 任务调度层（Airflow / Prefect）              │
│    每日盘后自动触发：数据下载 DAG → 估值计算 DAG           │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│          数据采集层（AkShare 为主，按需扩展）               │
│  A 股全市场 ak.stock_zh_a_hist  │  H 股全市场 ak.stock_hk_hist  │
│  财务报表 ak.stock_financial_*  │  宏观数据 ak.macro_*          │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│       数据存储层（PostgreSQL + TimescaleDB）               │
│  stock_prices（时序数据）│ financial_data（财务报表）      │
│  dcf_results（估值结果） │ macro_data（宏观指标）          │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│           估值计算层（并行计算）                            │
│  多进程 DCF │ 行业 WACC 矩阵 │ 蒙特卡洛情景分析            │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│              展示层（Web 应用 / REST API）                  │
│  Flask/FastAPI │ Plotly.js 图表 │ 报表导出（Excel/PDF）    │
└──────────────────────────────────────────────────────────┘
```

---

## 5. 关键设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 数据库 | SQLite | 零配置、文件式、适合 demo；接口封装后可平滑替换 |
| 数据源 | AkShare | 免费、无需注册、A/H 股统一接口、数据覆盖全面 |
| 股票代码格式 | 纯数字（6位/5位） | AkShare 原生格式，A/H 两市统一处理 |
| 配置管理 | Python 文件（settings.py） | 类型安全、IDE 自动补全、直接 import |
| DCF 模型 | 简化 FCFF + Gordon Growth | 保持模型结构完整，便于未来替换输入项 |
| Web 框架 | Flask | 轻量，适合单页应用，无需 ORM |
| 前端渲染 | Plotly.js（客户端） | `Plotly.react()` 原地更新，无刷新页面 |
| 追加语义 | valuation_date = end_date | 不同日期范围产生不同行，UNIQUE 约束保证同范围幂等 |
| 语言 | Python 3.8+ | AkShare / pandas / numpy / plotly / flask 工具链完备 |
