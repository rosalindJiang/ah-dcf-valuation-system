# AH 股 DCF 估值计算系统

> 一个可扩展的全市场 A 股 + H 股 DCF（折现现金流）自动化估值系统，内置交互式 Web 可视化报告。  
> Demo 阶段以 5 只 A 股 + 5 只 H 股验证完整流程，架构设计支持扩展至全市场 5000+ 只 A 股和 2000+ 只港股。

---

## 项目背景

DCF（Discounted Cash Flow，折现现金流）是价值投资的核心估值方法之一，通过预测企业未来自由现金流并以适当折现率折现，得出股票内在价值，从而判断其相对市场价格是否被高估或低估。

本系统旨在自动化这一流程：通过 AkShare 免费接口同时采集 A 股和 H 股真实历史行情数据，基于统一的参数配置进行批量 DCF 估值，将结果持久化至本地 SQLite 数据库，并通过 **Web 界面**或**静态 HTML 报告**呈现交互式图表。

---

## 业务目标

- 通过统一数据接口（AkShare）自动化采集 A 股和 H 股真实历史行情
- 基于 DCF 模型批量计算股票内在价值
- 将估值结果存储于本地 SQLite 数据库，支持按日期范围**追加**（不覆盖历史记录）
- 提供 **Web 应用**（选股 + 日期 + 一键估值）和**静态 HTML 报告**两种可视化方式
- 系统架构支持从 demo（5+5 只股票）平滑扩展至全市场（7000+ 只）

---

## 系统架构

```
配置层（config/settings.py）
        │
        ▼
数据采集层（src/data_downloader.py）
   A 股：ak.stock_zh_a_hist()    H 股：ak.stock_hk_hist()
        │                               │
        └───────────────┬───────────────┘
                        ▼
        数据存储层（src/database.py + data/ah_dcf.db）
          stock_prices 表  │  dcf_valuation_results 表
                        │
                        ▼
        估值计算层（src/dcf_model.py）
          FCFF 预测 → Terminal Value → WACC 折现 → 内在价值
                        │
                        ▼
        Pipeline 调度层（src/valuation_pipeline.py）
          读取股票池 → 批量估值 → 结果入库 → 返回结果列表
                        │
               ┌────────┴────────┐
               ▼                 ▼
     Web 应用层                 可视化层
     app.py + templates/        src/visualizer.py
     Flask Web 界面              静态 HTML 报告
     http://localhost:5000       data/dcf_report.html
```

详细架构说明见 [docs/architecture_design.md](docs/architecture_design.md)

---

## 数据流程

```
用户在 Web 界面选择股票 + 日期范围，点击"运行估值"
    ↓
POST /api/run → 触发 AkShare 下载选定时间段的行情数据
    ↓
stock_prices 表（SQLite，source = akshare_a / akshare_hk）
    ↓
读取各股最新收盘价 + 从 STOCK_FINANCIALS 读取营收 / 股本 / WACC
    ↓
DCF 模型计算（FCFF + Terminal Value + WACC 折现 → EV / 总股本）
    ↓
dcf_valuation_results 表（按 stock_code + end_date 追加，不覆盖）
    ↓
返回 JSON → 浏览器端 Plotly.js 渲染图表
```

详细数据流说明见 [docs/data_flow.md](docs/data_flow.md)

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

`requirements.txt` 包含：
- `akshare` — A 股和 H 股数据接口
- `pandas` — 数据处理
- `numpy` — 数值计算
- `plotly` — 交互式可视化图表
- `flask` — Web 应用框架

### 2. 启动 Web 应用（推荐）

```bash
python app.py
```

浏览器访问 **http://localhost:5000**，即可看到以下操作界面：

1. **选择股票**：点击下拉箭头，从 10 只 Demo 股票中勾选（可多选，支持 A 股 / 全选 / 全不选快捷按钮）
2. **选择日期范围**：设置数据起始日期和结束日期
3. **点击"运行估值"**：后端自动下载数据 → 计算 DCF → 将结果追加入库 → 返回可视化图表

每次运行会以 `(stock_code, end_date)` 为唯一键追加一条记录，相同 end_date 重跑则幂等替换。

### 3. 一键命令行运行（可选）

```bash
python main.py
```

自动按顺序执行：初始化数据库 → 下载数据 → DCF 估值 → 生成静态 HTML 报告（`data/dcf_report.html`）。

### 4. 分步运行（调试用）

```bash
python scripts/init_db.py       # 初始化数据库
python scripts/run_download.py  # 下载行情数据
python scripts/run_valuation.py # 运行 DCF 估值
python scripts/run_report.py    # 生成静态 HTML 报告
```

---

## Web 应用功能

### 选股面板

| 控件 | 功能 |
|------|------|
| 下拉多选框 | 点击展开，从 10 只 Demo 股票中勾选任意组合 |
| 全选 / 全不选 | 一键操作 |
| 仅 A 股 / 仅 H 股 | 按市场快速筛选 |
| 日期起止 | 设置行情下载和估值的时间窗口 |
| 运行估值 | 触发数据下载 + DCF 计算 + 图表渲染 |

### 图表列表

| 模块 | 内容 |
|------|------|
| 顶部统计卡片 | 估值总数、低估数量、高估数量、平均高低估幅度 |
| DCF 结果明细表 | 股票名称、市场价、内在价值、高低估%、WACC、评级，颜色区分 |
| 高低估百分比图 | 水平条形图，绿=低估，红=高估 |
| 价值对比图 | 市场价 vs DCF 内在价值分组条形图 |
| A 股历史走势图 | 选定日期范围内的收盘价折线图 |
| H 股历史走势图 | 选定日期范围内的收盘价折线图 |

---

## DCF 模型说明

本系统采用 **简化企业自由现金流（FCFF）折现模型**，计算步骤如下：

**Step 1：预测未来 N 年 FCFF**
```
FCFF = EBIT × (1 - 税率) + D&A - CapEx - 营运资本增量
     = NOPAT + D&A - CapEx - △WC
```
各项均以当年营收为基数按比例估算（营收年增长率来自 `REVENUE_GROWTH_RATE`）。

**Step 2：Gordon Growth 终值**
```
Terminal Value = FCFF_N × (1 + g) / (WACC - g)
```
其中 g = `TERMINAL_GROWTH_RATE`。

**Step 3：WACC 折现**
```
Enterprise Value = Σ[FCFF_t / (1+WACC)^t]  +  TV / (1+WACC)^N
```

**Step 4：每股内在价值**
```
Intrinsic Value = Enterprise Value / 总股本
```

股票池内各股票的真实营收、总股本和 WACC 配置在 `config/settings.py` 的 `STOCK_FINANCIALS` 字典中；未配置的股票回退到虚拟代理值。

**⚠️ Demo 限制说明**

| 限制项 | 当前处理 | 生产环境应改为 |
|--------|----------|---------------|
| 基准营收 | 年报近似值（STOCK_FINANCIALS） | 接入 AkShare 财务报表接口实时获取 |
| WACC | 按行业特征手工设定 | 基于 Beta 和资本结构 CAPM 计算 |
| 股本数 | 年报近似总股本 | 与当日实际流通股本同步 |
| 净负债 | 忽略（EV≈股权价值） | 资产负债表数据（EV - 净负债） |
| 增长率 | 按股票手工估计 | 分析师一致预期 / 行业基准 |

**估值结果仅供学习和参考，不构成任何投资建议。**

---

## 数据库设计

SQLite 数据库文件：`data/ah_dcf.db`（运行后自动生成，不提交到版本库）

### stock_prices 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| stock_code | TEXT | 股票代码（A 股 6 位数字 / H 股 5 位数字） |
| trade_date | TEXT | 交易日期（YYYY-MM-DD） |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| volume | REAL | 成交量 |
| amount | REAL | 成交额 |
| source | TEXT | 数据来源（`akshare_a` / `akshare_hk`） |
| created_at | TEXT | 写入时间 |

### dcf_valuation_results 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| stock_code | TEXT | 股票代码 |
| valuation_date | TEXT | 估值日期（= 用户选择的结束日期） |
| start_date | TEXT | 数据起始日期（= 用户选择的起始日期） |
| forecast_years | INTEGER | 预测年数 |
| wacc | REAL | 加权平均资本成本 |
| terminal_growth_rate | REAL | 终端增长率 |
| estimated_intrinsic_value | REAL | 估算内在价值（元 / 港元） |
| latest_market_price | REAL | 估值时最新市场价 |
| upside_downside_pct | REAL | 高低估百分比（正=低估，负=高估） |
| assumptions_json | TEXT | 估值参数快照（JSON，用于复现） |
| created_at | TEXT | 写入时间 |

**追加语义**：`UNIQUE(stock_code, valuation_date)`——相同股票选择不同 `end_date` 时每次产生新行，历史估值记录完整保留；重跑相同 `end_date` 则幂等替换。

### financial_assumptions 表

预留表，用于未来按股票/日期存储自定义估值假设，支持多版本参数回测。

---

## 扩展到全市场

### 从 10 只 Demo 扩展到全部 A 股（5000+）

**第一步：获取全量 A 股代码**

```python
import akshare as ak

df = ak.stock_info_a_code_name()   # 返回全量 A 股代码 + 名称
# 典型列：code（6位纯数字）, name
all_a_codes = df["code"].tolist()
```

**第二步：更新 `config/settings.py`**

```python
# 将 A_SHARE_STOCKS 替换为全量代码列表
A_SHARE_STOCKS = all_a_codes   # 约 5000+ 只

# 对应补充 STOCK_NAMES（如需显示中文名称）
STOCK_NAMES = dict(zip(df["code"], df["name"]))
```

**第三步（可选）：补充 STOCK_FINANCIALS**

Demo 中 10 只股票的营收/股本数据已手工填入 `STOCK_FINANCIALS`；扩展到全市场时，建议改为从 AkShare 财务报表接口动态获取：

```python
# 示例：获取年度财务摘要
fin_df = ak.stock_financial_abstract_ths(symbol="600519", indicator="按年度")
```

---

### 从 10 只 Demo 扩展到全部 H 股（2000+）

**第一步：获取全量港股代码**

```python
import akshare as ak

df_hk = ak.stock_hk_spot_em()     # 东方财富港股全量行情快照
# 典型列：代码（5位纯数字）, 名称
all_hk_codes = df_hk["代码"].tolist()
```

**第二步：更新 `config/settings.py`**

```python
H_SHARE_STOCKS = all_hk_codes   # 约 2000+ 只

# 补充 STOCK_NAMES
for _, row in df_hk.iterrows():
    STOCK_NAMES[row["代码"]] = row["名称"]
```

---

### 全市场运行注意事项

| 事项 | 说明 |
|------|------|
| **下载耗时** | 5000 只 A 股 × 2 年日线 ≈ 250 万条，预计耗时 2–4 小时（AkShare 限速） |
| **断点续传** | `INSERT OR REPLACE` 幂等写入，中断后重跑自动跳过已下载股票 |
| **数据库大小** | 约 500MB SQLite 文件，建议全市场版本迁移至 PostgreSQL |
| **并发下载** | 可将 `data_downloader.py` 改为多线程/多进程，注意 AkShare 接口限流 |
| **批量估值** | `run_pipeline()` 支持任意股票列表，无需修改；全市场运行约需 10–30 分钟 |
| **Web UI 股票列表** | 将 `settings.A_SHARE_STOCKS` / `H_SHARE_STOCKS` 替换后，Web 下拉自动更新，无需改前端代码 |

---

## 直接查询数据库

```bash
sqlite3 data/ah_dcf.db
```

```sql
-- 查看所有估值结果（按高低估排序，每只股票取最新一次）
SELECT r.stock_code, r.valuation_date, r.latest_market_price,
       r.estimated_intrinsic_value, r.upside_downside_pct
FROM dcf_valuation_results r
INNER JOIN (
    SELECT stock_code, MAX(valuation_date) AS max_date
    FROM dcf_valuation_results GROUP BY stock_code
) latest ON r.stock_code = latest.stock_code AND r.valuation_date = latest.max_date
ORDER BY r.upside_downside_pct DESC;

-- 查看不同日期范围的历史估值对比（追加语义示例）
SELECT stock_code, start_date, valuation_date, estimated_intrinsic_value
FROM dcf_valuation_results
WHERE stock_code = '600519'
ORDER BY valuation_date DESC;

-- 查看贵州茅台最近 5 条收盘价
SELECT trade_date, close FROM stock_prices
WHERE stock_code = '600519'
ORDER BY trade_date DESC LIMIT 5;

-- 查看数据来源分布
SELECT source, COUNT(*) as cnt FROM stock_prices GROUP BY source;
```

---

## 项目结构

```
DCF估值计算系统/
├── app.py                        # Web 应用入口（Flask，推荐）
├── main.py                       # 命令行一键运行入口
├── README.md
├── requirements.txt              # akshare, pandas, numpy, plotly, flask
├── .gitignore
├── config/
│   └── settings.py               # 全局配置（股票池、STOCK_NAMES、日期、DCF 参数）
├── templates/
│   └── index.html                # Web 界面（Jinja2 + Plotly.js）
├── data/
│   ├── ah_dcf.db                 # SQLite 数据库（运行后生成，不提交到版本库）
│   └── dcf_report.html           # 静态 HTML 报告（main.py 生成，不提交到版本库）
├── src/
│   ├── __init__.py
│   ├── database.py               # 数据库连接、建表、读写（唯一 SQL 入口）
│   ├── data_downloader.py        # A 股 / H 股数据采集（AkShare）
│   ├── dcf_model.py              # DCF 估值算法（DCFModel 类）
│   ├── valuation_pipeline.py     # 估值流程编排，返回结果列表
│   ├── visualizer.py             # 静态 HTML 报告生成（Plotly）
│   └── utils.py                  # 通用工具（日志初始化、日期校验）
├── scripts/
│   ├── init_db.py                # 单独初始化数据库
│   ├── run_download.py           # 单独运行数据下载
│   ├── run_valuation.py          # 单独运行估值计算
│   └── run_report.py             # 单独生成静态 HTML 报告
└── docs/
    ├── architecture_design.md    # 系统架构设计
    ├── data_flow.md              # 数据流程说明
    └── collaboration_guideline.md # 协作规范
```

---

## 当前 Demo 的限制

1. **股票池规模**：A 股 5 只、H 股 5 只，可按上节"扩展到全市场"的步骤扩展
2. **财务数据**：`STOCK_FINANCIALS` 中的营收、股本均为年报近似值，未实时接入 AkShare 财务报表接口
3. **净负债**：暂未扣减净负债，EV 直接作为股权价值计算每股价值
4. **数据库**：SQLite 适合单机，不支持高并发；全市场版本建议迁移至 PostgreSQL

---

## 未来扩展方向

| 方向 | 具体内容 |
|------|----------|
| 全市场 A 股 | `ak.stock_info_a_code_name()` 获取全量代码，填入 `A_SHARE_STOCKS` |
| 全市场 H 股 | `ak.stock_hk_spot_em()` 获取全量港股代码 |
| 完整财务数据 | AkShare 财务报表接口替换虚拟营收，提升 DCF 准确性 |
| 行业化 WACC | 按申万/证监会行业分类，构建行业 WACC 矩阵 |
| 情景分析 | 蒙特卡洛模拟，输出悲观/基准/乐观三情景估值区间 |
| 自动化调度 | 接入 Airflow / cron，每日盘后自动触发估值 |
| 报告增强 | 可视化增加蜡烛图、成交量柱、估值历史趋势等 |
| 数据库升级 | 全市场版本迁移至 PostgreSQL + TimescaleDB |

---

## 协作规范

详见 [docs/collaboration_guideline.md](docs/collaboration_guideline.md)

---

## 许可证

MIT License
