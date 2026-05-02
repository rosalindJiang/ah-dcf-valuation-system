# AH 股 DCF 估值计算系统

> 一个可扩展的全市场 A 股 + H 股 DCF（折现现金流）自动化估值系统，内置交互式 Web 可视化报告。  
> Demo 阶段以 5 只 A 股 + 5 只 H 股验证完整流程，架构设计支持扩展至全市场 5000+ 只 A 股和 2000+ 只港股。

---

## 项目背景

DCF（Discounted Cash Flow，折现现金流）是价值投资的核心估值方法之一，通过预测企业未来自由现金流并以适当折现率折现，得出股票内在价值，从而判断其相对市场价格是否被高估或低估。

本系统通过 AkShare 免费接口同时采集 A 股和 H 股真实历史行情数据，基于统一的参数配置进行批量 DCF 估值，将结果持久化至本地 SQLite 数据库，并通过 **Web 界面**呈现交互式图表。

---

## 业务目标

- 通过统一数据接口（AkShare）自动化采集 A 股和 H 股真实历史行情
- 基于 DCF 模型批量计算股票内在价值
- 将估值结果存储于本地 SQLite 数据库，支持按日期范围**追加**（不覆盖历史记录）
- 提供 Web 应用（选股 + 日期 + 一键估值 + 实时图表）
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
                        ▼
        Web 应用层（app.py + templates/index.html）
          Flask 服务 → Plotly.js 客户端图表渲染
          http://localhost:8080
```

详细架构说明见 [docs/architecture_design.md](docs/architecture_design.md)

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Web 应用

```bash
python app.py
```

浏览器访问 **http://localhost:8080**，即可看到以下操作界面：

1. **选择股票**：点击下拉箭头，从 10 只 Demo 股票中勾选（可多选，支持仅 A 股 / 仅 H 股 / 全选快捷按钮）
2. **选择日期范围**：设置数据起始日期和结束日期
3. **点击"运行估值"**：后端自动下载数据 → 计算 DCF → 将结果追加入库 → 返回可视化图表

每次运行以 `(stock_code, end_date)` 为唯一键追加一条记录，相同 end_date 重跑则幂等替换。

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

各股票的真实营收、总股本和 WACC 配置在 `config/settings.py` 的 `STOCK_FINANCIALS` 字典中。

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
| stock_code | TEXT | 股票代码（A 股 6 位数字 / H 股 5 位数字） |
| trade_date | TEXT | 交易日期（YYYY-MM-DD） |
| open / high / low / close | REAL | 开高低收盘价 |
| volume / amount | REAL | 成交量 / 成交额 |
| source | TEXT | 数据来源（`akshare_a` / `akshare_hk`） |

### dcf_valuation_results 表

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | TEXT | 股票代码 |
| valuation_date | TEXT | 估值日期（= 用户选择的结束日期） |
| start_date | TEXT | 数据起始日期 |
| estimated_intrinsic_value | REAL | 估算内在价值（元 / 港元） |
| latest_market_price | REAL | 估值时最新市场价 |
| upside_downside_pct | REAL | 高低估百分比（正=低估，负=高估） |
| assumptions_json | TEXT | 估值参数快照（JSON，用于复现） |

**追加语义**：`UNIQUE(stock_code, valuation_date)`——相同股票选择不同 `end_date` 时每次产生新行，历史估值记录完整保留；重跑相同 `end_date` 则幂等替换。

---

## 扩展到全市场

### 扩展到全部 A 股（5000+）

**第一步：获取全量 A 股代码**

```python
import akshare as ak
df = ak.stock_info_a_code_name()   # 返回全量 A 股代码 + 名称
all_a_codes = df["code"].tolist()
```

**第二步：更新 `config/settings.py`**

```python
A_SHARE_STOCKS = all_a_codes
STOCK_NAMES = dict(zip(df["code"], df["name"]))
```

### 扩展到全部 H 股（2000+）

```python
import akshare as ak
df_hk = ak.stock_hk_spot_em()
all_hk_codes = df_hk["代码"].tolist()
H_SHARE_STOCKS = all_hk_codes
```

### 全市场注意事项

| 事项 | 说明 |
|------|------|
| 下载耗时 | 5000 只 A 股 × 2 年 ≈ 250 万条，预计 2–4 小时（AkShare 限速） |
| 断点续传 | `INSERT OR REPLACE` 幂等写入，中断后重跑自动跳过已下载记录 |
| 数据库大小 | 约 500MB，全市场版本建议迁移至 PostgreSQL |
| 并发下载 | 可将 `data_downloader.py` 改为多线程，注意 AkShare 接口限流 |

---

## 直接查询数据库

```bash
sqlite3 data/ah_dcf.db
```

```sql
-- 每只股票取最新一次估值，按高低估排序
SELECT r.stock_code, r.start_date, r.valuation_date,
       r.latest_market_price, r.estimated_intrinsic_value, r.upside_downside_pct
FROM dcf_valuation_results r
INNER JOIN (
    SELECT stock_code, MAX(valuation_date) AS max_date
    FROM dcf_valuation_results GROUP BY stock_code
) latest ON r.stock_code = latest.stock_code AND r.valuation_date = latest.max_date
ORDER BY r.upside_downside_pct DESC;

-- 同一股票不同日期范围的历史估值
SELECT stock_code, start_date, valuation_date, estimated_intrinsic_value
FROM dcf_valuation_results WHERE stock_code = '600519' ORDER BY valuation_date DESC;
```

---

## 项目结构

```
DCF估值计算系统/
├── app.py                        # Web 应用入口（Flask）
├── README.md
├── requirements.txt              # akshare, pandas, numpy, plotly, flask
├── .gitignore
├── config/
│   └── settings.py               # 全局配置（股票池、STOCK_NAMES、日期、DCF 参数）
├── templates/
│   └── index.html                # Web 界面（Jinja2 + Plotly.js）
├── data/
│   └── ah_dcf.db                 # SQLite 数据库（运行后生成，不提交到版本库）
├── src/
│   ├── database.py               # 数据库连接、建表、读写
│   ├── data_downloader.py        # A 股 / H 股数据采集（AkShare）
│   ├── dcf_model.py              # DCF 估值算法（DCFModel 类）
│   ├── valuation_pipeline.py     # 估值流程编排，返回结果列表
│   └── utils.py                  # 日志初始化、日期校验
└── docs/
    ├── architecture_design.md
    ├── data_flow.md
    └── collaboration_guideline.md
```

---

## 许可证

MIT License
