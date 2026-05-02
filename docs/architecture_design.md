# 系统架构设计文档

## 1. 设计目标

构建一个可扩展、可维护的全市场 AH 股 DCF 估值系统，满足以下核心目标：

- **全市场覆盖能力**：架构支持 A 股全市场（5000+ 只）及港股全市场（2000+ 只），demo 阶段以 5+5 只标的验证系统可行性。
- **统一数据源**：A 股和 H 股均通过 AkShare 接口采集，无需注册账号，接口风格一致。
- **模块化分层**：数据采集、存储、计算、调度各自独立，可单独替换或升级。
- **参数化配置**：所有可调参数集中于 `config/settings.py`，零硬编码。
- **双模式入口**：Web 应用（`app.py`）提供交互式选股 + 实时计算；命令行（`main.py`）提供一键批量运行。

---

## 2. 系统分层架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    Layer 7 – 入口 / 调度层                        │
│                                                                    │
│   app.py（Web 应用，推荐）          main.py（命令行一键运行）      │
│   └─ GET  /  → templates/index.html  └─ Step1: init_tables()      │
│   └─ POST /api/run → JSON 响应        Step2: download_*()          │
│                                       Step3: run_pipeline()        │
│   scripts/init_db.py  run_download.py  run_valuation.py           │
│   scripts/run_report.py  │  src/valuation_pipeline.py             │
└──────────┬─────────────────────────────────────┬──────────────────┘
           │ (Web 路由返回 JSON)                  │ (命令行调用)
┌──────────▼──────────────────┐      ┌────────────▼─────────────────┐
│  Layer 6a – Web 展示层       │      │  Layer 6b – 静态报告层        │
│  templates/index.html        │      │  src/visualizer.py           │
│  Plotly.js 客户端渲染         │      │  Plotly → data/dcf_report.html│
│  无需刷新页面，实时更新图表   │      │  单文件，浏览器直接打开       │
└──────────┬──────────────────┘      └──────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│                       Layer 5 – Pipeline 调度层                   │
│                       src/valuation_pipeline.py                   │
│   run_pipeline(stock_list, valuation_date, start_date)            │
│   → 批量估值 → 结果入库 → 返回 List[dict] 供上层消费              │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                       Layer 4 – 估值计算层                         │
│                       src/dcf_model.py                            │
│   DCFAssumptions（参数封装）→ DCFModel（FCFF / TV / 折现）         │
│   run_valuation(valuation_date) → 内在价值 + 高低估%              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                       Layer 3 – 数据存储层                         │
│                       src/database.py                             │
│   SQLite（data/ah_dcf.db）                                        │
│   stock_prices 表  │  dcf_valuation_results 表（含 start_date）    │
│   UNIQUE(stock_code, valuation_date) → 按日期范围追加语义          │
│   financial_assumptions 表（预留）                                │
└──────────┬──────────────────────────────┬────────────────────────┘
           │                              │
┌──────────▼──────────┐       ┌───────────▼──────────────────────┐
│  Layer 2a – A 股    │       │  Layer 2b – H 股采集层            │
│  数据采集层          │       │  数据采集层                       │
│                     │       │                                   │
│  AkShare            │       │  AkShare                          │
│  ak.stock_zh_a_hist │       │  ak.stock_hk_hist                 │
│  (symbol, period,   │       │  (symbol, period,                 │
│   start, end)       │       │   start, end)                     │
│  source='akshare_a' │       │  source='akshare_hk'              │
└──────────┬──────────┘       └──────────────────────┬───────────┘
           │                                          │
┌──────────▼──────────────────────────────────────────▼───────────┐
│                       Layer 1 – 配置层                            │
│                       config/settings.py                          │
│   A_SHARE_STOCKS（6位）  H_SHARE_STOCKS（5位）  STOCK_FINANCIALS  │
│   STOCK_NAMES（中文名称映射）                                      │
│   START_DATE / END_DATE  │  DB_PATH  │  DCF 参数  │  LOG_LEVEL   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 各层详细说明

### 3.1 配置层（config/settings.py）

**职责**：集中管理所有可变参数，是系统的唯一真相源（Single Source of Truth）。

| 配置项 | 格式 | 说明 |
|--------|------|------|
| `A_SHARE_STOCKS` | `["600519", "000001", ...]` | A 股股票池，AkShare 格式（6位纯数字） |
| `H_SHARE_STOCKS` | `["00700", "00941", ...]` | H 股股票池，AkShare 格式（5位纯数字） |
| `STOCK_NAMES` | `dict[str, str]` | 股票代码→中文名称映射，Web UI 展示用 |
| `START_DATE` / `END_DATE` | `"YYYY-MM-DD"` | 历史数据下载日期范围（Web 应用可由用户覆盖） |
| `DB_PATH` | 绝对路径 | SQLite 数据库文件路径（由 BASE_DIR 动态拼接） |
| DCF 全局参数 | `float` / `int` | WACC、终端增长率、预测年数、利润率等默认值 |
| `STOCK_FINANCIALS` | `dict[str, dict]` | 各股票年报近似营收、总股本、WACC 和增长率覆盖值 |

**扩展方式**：生产环境可将常量替换为从 YAML 文件、数据库或环境变量读取，实现动态配置：

```python
# 支持环境变量覆盖（适合 CI/CD）
DEFAULT_WACC = float(os.getenv("DCF_WACC", "0.10"))
```

---

### 3.2 数据采集层（src/data_downloader.py）

**职责**：通过 AkShare 拉取 A 股和 H 股真实日线行情，清洗后写入数据库。

**A 股采集**：
- 接口：`ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date, adjust="")`
- 代码格式：6 位纯数字（如 `"600519"`）
- 日期格式：AkShare 使用 `YYYYMMDD`，由 `_to_akshare_date()` 自动转换
- 数据库标记：`source = 'akshare_a'`

**H 股采集**：
- 接口：`ak.stock_hk_hist(symbol, period="daily", start_date, end_date, adjust="")`
- 代码格式：5 位纯数字（如 `"00700"`）
- 数据库标记：`source = 'akshare_hk'`

**列名统一**：`_parse_akshare_df()` 将 AkShare 中文列名（日期、开盘、收盘等）映射为内部英文字段名，两种市场共用同一解析逻辑。

**容错机制**：
- 单只股票下载失败时 `except` 捕获异常、记录日志后继续，不影响整批
- `df.empty` 判断处理停牌或代码错误的情况
- 过滤收盘价为空或为零的行

**扩展到全市场**：
```python
# 获取 A 股全量代码
import akshare as ak
df = ak.stock_info_a_code_name()          # 返回全量 A 股代码+名称
all_a_codes = df["code"].tolist()         # 写入 settings.A_SHARE_STOCKS

# 获取 H 股全量代码
df_hk = ak.stock_hk_spot_em()
all_hk_codes = df_hk["代码"].tolist()     # 写入 settings.H_SHARE_STOCKS
```

---

### 3.3 数据存储层（src/database.py）

**职责**：管理 SQLite 数据库的连接、建表、读写操作。

**设计原则**：
- 所有 SQL 语句集中在此模块，业务层通过函数调用交互，不直接写 SQL
- `INSERT OR REPLACE` 实现幂等写入，重复运行不产生重复记录
- `PRAGMA journal_mode=WAL` 开启写前日志，支持并发读写
- `conn.row_factory = sqlite3.Row` 使查询结果支持列名访问，返回字典列表

**主要函数**：

| 函数 | 说明 |
|------|------|
| `get_connection()` | 创建数据库连接，自动创建目录 |
| `init_tables()` | 幂等建表（CREATE TABLE IF NOT EXISTS） |
| `upsert_stock_prices()` | 批量写入日线价格，支持断点重跑 |
| `upsert_dcf_result()` | 写入单只股票 DCF 估值结果 |
| `query_latest_close()` | 查询最新一条收盘价 |
| `query_price_history()` | 查询历史价格序列（支持日期范围过滤） |
| `query_all_dcf_results()` | 查询所有估值结果，按高低估排序 |

**生产扩展**：当数据量超出 SQLite 适用范围时，仅需将 `get_connection()` 替换为 PostgreSQL / TimescaleDB 连接，其他所有模块无需改动。

---

### 3.4 估值计算层（src/dcf_model.py）

**职责**：实现 DCF 估值算法，封装为 `DCFModel` 类，输出每股内在价值和高低估比例。

**核心类**：

`DCFAssumptions`（dataclass）：封装单次估值所需的全部假设参数，默认值来自 settings.py，可针对单只股票覆盖，并可序列化为 JSON 存入数据库。

`DCFModel`：接收 `stock_code`、`market_price`、`DCFAssumptions`，执行四步估值：

```
STOCK_FINANCIALS[stock_code]（营收、总股本、WACC、增长率）
    │
    ├─ valuation_pipeline._valuate_single()
    │     读取个股财务数据 → 构建 DCFAssumptions → 实例化 DCFModel
    │
    └─ DCFModel（stock_code, market_price, assumptions, base_revenue, total_shares）
          │
          ├─ Step 1: forecast_free_cash_flow()
          │     逐年营收增长 → NOPAT + D&A - CapEx - △WC
          │     返回 [FCFF_1, FCFF_2, ..., FCFF_N]
          │
          ├─ Step 2: calculate_terminal_value(FCFF_N)
          │     TV = FCFF_N × (1 + g) / (WACC - g)
          │
          ├─ Step 3: discount_cash_flows(fcff_list, TV)
          │     EV = Σ[FCFF_t / (1+WACC)^t] + TV / (1+WACC)^N
          │
          └─ Step 4: calculate_intrinsic_value(EV)
                intrinsic_value = EV / total_shares（优先使用真实股本）
                upside_pct = (intrinsic - market_price) / market_price × 100%
```

**Demo 限制与生产升级路径**：

| 项目 | Demo 简化 | 生产改进 |
|------|-----------|----------|
| 基准营收 | 年报近似值（STOCK_FINANCIALS） | AkShare 财务报表接口实时获取 |
| WACC | 按行业手工设定（STOCK_FINANCIALS） | CAPM：Rf + β×(Rm-Rf) + 资本结构加权 |
| 增长率 | 按股票手工估计 | 分析师一致预期 / 行业基准 |
| 股本 | 年报近似总股本 | 与当日实际流通股本同步 |
| 净负债 | 忽略（EV≈股权价值） | 接入资产负债表（EV - 净负债） |
| 情景分析 | 单一基准 | 悲观 / 基准 / 乐观三情景 |

---

### 3.5 可视化层

系统提供两种可视化方式，共用同一套数据查询接口：

#### 3.5a Web 应用层（app.py + templates/index.html）

**职责**：提供浏览器交互界面，用户实时选股 + 选日期 + 一键触发完整估值流程，结果通过 JSON API 返回并在浏览器端渲染。

**运行方式**：`python app.py`，浏览器访问 `http://localhost:5000`

**路由设计**：

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 渲染主页，传入股票列表和默认日期 |
| `/api/run` | POST | 接收 `{stocks, start_date, end_date}`，执行下载+估值，返回 JSON |

**`/api/run` 执行流程**：
```
接收 JSON payload
    → init_tables()（幂等建表）
    → download_a_share_data(stock_list, start_date, end_date)
    → download_hk_stock_data(stock_list, start_date, end_date)
    → run_pipeline(stock_list, valuation_date=end_date, start_date=start_date)
    → query_price_history(code, start_date, end_date) × N只
    → 返回 {results, history, a_stocks, h_stocks, errors}
```

**前端架构**（templates/index.html）：
- Jinja2 模板，服务端注入股票列表
- 自定义下拉多选框（▾），按 A/H 市场分组，支持搜索
- `runValuation()` 异步 fetch POST /api/run
- Plotly.js `Plotly.react()` 原地更新 5 个图表，无需刷新页面
- 统计卡片（总数/低估/高估/平均幅度）随结果动态更新

#### 3.5b 静态报告层（src/visualizer.py）

**职责**：从数据库读取估值结果和历史价格，生成独立的 HTML 报告文件，双击用浏览器打开，无需服务器。

**输出文件**：`data/dcf_report.html`，约 230KB，单文件无外部依赖（CDN 除外）。

**主要函数**：

| 函数 | 说明 |
|------|------|
| `generate_report()` | 主入口，查数据库 → 嵌入数据 → 写 HTML 文件 |
| `_css()` | 返回样式字符串（独立函数避免 f-string 大括号冲突） |
| `_js()` | 返回 JavaScript 渲染与筛选逻辑（`renderAll`、`renderTable` 等） |
| `_build_html()` | 组装完整 HTML，嵌入 JSON 数据 + Plotly CDN + CSS + JS |

**JS 初始化修复**：脚本位于 `<body>` 末尾，DOM 解析完成后脚本才执行，`DOMContentLoaded` 可能已触发。通过检查 `document.readyState` 解决：
```javascript
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderAll);
} else {
    renderAll();
}
```

---

### 3.6 入口 / 调度层

**`app.py`（Web 应用，推荐）**：启动 Flask 服务器，用户通过浏览器交互式选股、选日期、触发估值，实时查看图表。

**`main.py`（命令行一键运行）**：串联四个步骤（init → download → valuate → report），适合批量运行和自动化调度。

**`scripts/` 分步脚本**：适合调试单个阶段或在 CI/CD 中按需调用：

| 脚本 | 职责 |
|------|------|
| `scripts/init_db.py` | 建库建表（幂等） |
| `scripts/run_download.py` | 下载 A 股 + H 股数据 |
| `scripts/run_valuation.py` | 运行估值 Pipeline |
| `scripts/run_report.py` | 生成静态 HTML 报告 |

**`src/valuation_pipeline.py`（Pipeline 协调器）**：接收 `stock_list`、`valuation_date`、`start_date` 参数 → 批量查价 → 调用 DCFModel → 写库 → **返回结果列表**（供 Web API 使用）。生产环境可接入 Airflow / Prefect，实现每日定时触发。

---

## 4. 未来扩展架构（全市场版本）

```
┌──────────────────────────────────────────────────────────┐
│                   任务调度层（Airflow / Prefect）           │
│    每日盘后自动触发：数据下载 DAG → 估值计算 DAG          │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               数据采集层（AkShare 为主，按需扩展）          │
│   A 股全市场 ak.stock_zh_a_hist  │  H 股全市场 ak.stock_hk_hist  │
│   财务报表 ak.stock_financial_*  │  宏观数据 ak.macro_*          │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│         数据存储层（PostgreSQL + TimescaleDB）             │
│   stock_prices（时序数据）│ financial_data（财务报表）     │
│   dcf_results（估值结果） │ macro_data（宏观指标）         │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│              估值计算层（并行计算）                         │
│   多进程 DCF │ 行业 WACC 矩阵 │ 蒙特卡洛情景分析           │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│               展示层（可选）                               │
│   REST API（FastAPI）│ 报表导出（Excel/PDF）│ 看板（Dash）│
└──────────────────────────────────────────────────────────┘
```

---

## 5. 关键设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 数据库 | SQLite | 零配置、文件式、适合 demo 和小规模生产；接口封装后可平滑替换 |
| 数据源 | AkShare | 免费、无需注册、A 股和 H 股统一接口、数据覆盖全面 |
| 股票代码格式 | 纯数字（6位/5位） | AkShare 原生格式，避免前缀转换，A/H 两市统一处理 |
| 配置管理 | Python 文件（settings.py） | 类型安全、IDE 自动补全、直接 import、无额外解析依赖 |
| DCF 模型 | 简化 FCFF + Gordon Growth | 在缺乏完整财务数据时保持模型结构完整，便于未来替换输入项 |
| Web 框架 | Flask | 轻量、无依赖、适合单页应用；不需要 ORM 或复杂路由 |
| 前端渲染 | Plotly.js（客户端） | 数据由 API 返回，`Plotly.react()` 原地更新，无刷新页面 |
| 可视化（静态） | Plotly → 独立 HTML | 无需服务器，单文件分发，图表交互功能完整 |
| 追加语义 | valuation_date = end_date | 不同日期范围产生不同行，UNIQUE 约束保证同范围幂等 |
| 语言 | Python 3.8+ | 生态成熟，AkShare / pandas / numpy / plotly / flask 工具链完备 |
