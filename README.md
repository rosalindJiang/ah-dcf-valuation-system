# AH 股 DCF 估值计算系统

> 一个可扩展的全市场 A 股 + H 股 DCF（折现现金流）自动化估值系统，内置交互式可视化报告。  
> Demo 阶段以 5 只 A 股 + 5 只 H 股验证完整流程，架构设计支持扩展至全市场 5000+ 只 A 股和 2000+ 只港股。

---

## 项目背景

DCF（Discounted Cash Flow，折现现金流）是价值投资的核心估值方法之一，通过预测企业未来自由现金流并以适当折现率折现，得出股票内在价值，从而判断其相对市场价格是否被高估或低估。

本系统旨在自动化这一流程：通过 AkShare 免费接口同时采集 A 股和 H 股真实历史行情数据，基于统一的参数配置进行批量 DCF 估值，将结果持久化至本地 SQLite 数据库，并生成包含多张交互式图表的 HTML 可视化报告。

---

## 业务目标

- 通过统一数据接口（AkShare）自动化采集 A 股和 H 股真实历史行情
- 基于 DCF 模型批量计算股票内在价值
- 将估值结果存储于本地 SQLite 数据库，支持历史查询和追溯
- 生成交互式 HTML 可视化报告，直观呈现估值结果
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
          stock_prices 表  │  financial_assumptions 表
                        │
                        ▼
        估值计算层（src/dcf_model.py）
          FCFF 预测 → Terminal Value → WACC 折现 → 内在价值
                        │
                        ▼
        Pipeline 调度层（src/valuation_pipeline.py）
          读取股票池 → 批量估值 → 结果入库 → 打印汇总
                        │
                        ▼
        可视化层（src/visualizer.py）
          高低估图 │ 价值对比图 │ 走势图 → data/dcf_report.html
```

详细架构说明见 [docs/architecture_design.md](docs/architecture_design.md)

---

## 数据流程

```
settings.py（股票池 + 日期 + STOCK_FINANCIALS + DCF 全局参数）
    ↓
AkShare 下载 A 股 + H 股真实日线行情
    ↓
stock_prices 表（SQLite，source = akshare_a / akshare_hk）
    ↓
读取各股最新收盘价 + 从 STOCK_FINANCIALS 读取营收 / 股本 / WACC
    ↓
DCF 模型计算（FCFF + Terminal Value + WACC 折现 → EV / 总股本）
    ↓
dcf_valuation_results 表（估值结果 + 参数快照，每股仅保留最新一条）
    ↓
Plotly 生成交互式 HTML 报告（data/dcf_report.html）
```

详细数据流说明见 [docs/data_flow.md](docs/data_flow.md)

---

## 可视化报告

运行后自动生成 `data/dcf_report.html`，用浏览器打开即可查看：

### 交互式筛选面板

报告顶部提供实时筛选控件，选中变化后所有图表**立即联动更新**，无需刷新页面：

| 控件 | 功能 |
|------|------|
| 股票代码复选框 | 勾选/取消任意股票，所有图表同步更新 |
| 全选 / 全不选 | 一键选中或清空所有股票 |
| 仅 A 股 / 仅 H 股 | 快速切换市场视图 |
| 历史价格区间 | 起止日期选择器，仅影响历史走势图 |
| 重置日期 | 恢复完整历史区间 |

### 图表列表

| 模块 | 内容 |
|------|------|
| 顶部统计卡片 | 估值总数、低估数量、高估数量、平均高低估幅度（随筛选实时更新） |
| DCF 结果明细表 | 股票代码、市场价、内在价值、高低估%、WACC、综合评级，行颜色区分 |
| 高低估百分比图 | 水平条形图，绿=低估，红=高估，按幅度升序排列 |
| 价值对比图 | 市场价 vs DCF 内在价值分组条形图 |
| 历史走势图 | A 股 / H 股历史收盘价折线图（左右并排） |

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
| valuation_date | TEXT | 估值日期 |
| forecast_years | INTEGER | 预测年数 |
| wacc | REAL | 加权平均资本成本 |
| terminal_growth_rate | REAL | 终端增长率 |
| estimated_intrinsic_value | REAL | 估算内在价值（元 / 港元） |
| latest_market_price | REAL | 估值时最新市场价 |
| upside_downside_pct | REAL | 高低估百分比（正=低估，负=高估） |
| assumptions_json | TEXT | 估值参数快照（JSON，用于复现） |
| created_at | TEXT | 写入时间 |

### financial_assumptions 表

预留表，用于未来按股票/日期存储自定义估值假设，支持多版本参数回测。

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

### 2. 一键运行（推荐）

```bash
python main.py
```

自动按顺序执行：初始化数据库 → 下载数据 → DCF 估值 → 生成可视化报告。

**预期输出**：
```
[INFO] AH 股 DCF 估值系统启动
[INFO] 步骤 1/4：初始化数据库
[INFO] 步骤 2/4：下载 A 股数据（AkShare）
[INFO]   600519：写入 484 条记录
...
[INFO] 步骤 2/4：下载 H 股数据（AkShare）
[INFO]   00700：写入 489 条记录
...
[INFO] 步骤 3/4：运行 DCF 估值 Pipeline

================================================================================
                             DCF 估值结果汇总
================================================================================
600000              10.29      13.85    +34.6%    2024-12-31  ▲低估
000001              11.70      15.02    +28.4%    2024-12-31  ▲低估
...
600519            1524.00    2285.10    +49.9%    2024-12-31  ▲低估
00700              417.00     382.50     -8.3%    2024-12-31  ▼高估
================================================================================

[INFO] 步骤 4/4：生成可视化 HTML 报告
[INFO] 报告已生成，请用浏览器打开：data/dcf_report.html
```

### 3. 分步运行（可选）

```bash
python scripts/init_db.py       # 初始化数据库
python scripts/run_download.py  # 下载行情数据
python scripts/run_valuation.py # 运行 DCF 估值
python scripts/run_report.py    # 生成可视化报告
```

---

## 查看可视化报告

用任意浏览器打开 `data/dcf_report.html`，无需网络，无需服务器：

```bash
open data/dcf_report.html        # macOS
start data/dcf_report.html       # Windows
xdg-open data/dcf_report.html    # Linux
```

---

## 直接查询数据库

```bash
sqlite3 data/ah_dcf.db
```

```sql
-- 查看所有估值结果（按高低估排序）
SELECT stock_code, latest_market_price, estimated_intrinsic_value, upside_downside_pct
FROM dcf_valuation_results
ORDER BY upside_downside_pct DESC;

-- 查看贵州茅台最近 5 条收盘价
SELECT trade_date, close FROM stock_prices
WHERE stock_code = '600519'
ORDER BY trade_date DESC LIMIT 5;

-- 查看数据来源分布
SELECT source, COUNT(*) as cnt FROM stock_prices GROUP BY source;
```

---

## 当前 Demo 的限制

1. **股票池规模**：A 股 5 只、H 股 5 只，可在 `config/settings.py` 中扩展
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
| 自动化调度 | 接入 Airflow / cron，每日盘后自动触发 `main.py` |
| 报告增强 | 可视化增加蜡烛图、成交量柱、估值历史趋势等 |
| API 服务 | FastAPI 封装估值查询接口，供前端或其他系统调用 |

---

## 项目结构

```
ah_dcf_valuation_system/
├── main.py                       # 一键运行入口（推荐）
├── README.md
├── requirements.txt              # akshare, pandas, numpy, plotly
├── .gitignore
├── config/
│   └── settings.py               # 全局配置（股票池、日期、DCF 参数）
├── data/
│   ├── ah_dcf.db                 # SQLite 数据库（运行后生成，不提交到版本库）
│   └── dcf_report.html           # 可视化报告（运行后生成，不提交到版本库）
├── src/
│   ├── __init__.py
│   ├── database.py               # 数据库连接、建表、读写（唯一 SQL 入口）
│   ├── data_downloader.py        # A 股 / H 股数据采集（AkShare）
│   ├── dcf_model.py              # DCF 估值算法（DCFModel 类）
│   ├── valuation_pipeline.py     # 估值流程编排
│   ├── visualizer.py             # 可视化报告生成（Plotly → HTML）
│   └── utils.py                  # 通用工具（日志初始化、日期校验）
├── scripts/
│   ├── init_db.py                # 单独初始化数据库
│   ├── run_download.py           # 单独运行数据下载
│   ├── run_valuation.py          # 单独运行估值计算
│   └── run_report.py             # 单独生成可视化报告
└── docs/
    ├── architecture_design.md    # 系统架构设计
    ├── data_flow.md              # 数据流程说明
    └── collaboration_guideline.md # 协作规范
```

---

## 协作规范

详见 [docs/collaboration_guideline.md](docs/collaboration_guideline.md)

---

## 许可证

MIT License
