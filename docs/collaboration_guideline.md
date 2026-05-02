# 协作规范文档

## 1. 总览

本文档规定了 AH 股 DCF 估值系统项目的协作规范，适用于所有团队成员。
遵循此规范有助于保持代码质量、降低沟通成本、支持多人并行开发。

---

## 2. Git 分支管理

### 2.1 分支命名规范

采用 **Gitflow 变体**，保持主干稳定、功能隔离：

| 分支类型 | 命名格式 | 用途 |
|----------|----------|------|
| 主分支 | `main` | 稳定可发布版本，禁止直接 push |
| 开发分支 | `develop` | 集成分支，功能完成后合并至此 |
| 功能分支 | `feature/<简短描述>` | 单一功能开发 |
| 修复分支 | `fix/<简短描述>` | Bug 修复 |
| 文档分支 | `docs/<简短描述>` | 文档更新 |
| 发布分支 | `release/<版本号>` | 发布准备 |

**命名示例**：
```
feature/dcf-sensitivity-analysis
feature/full-market-stock-list
feature/akshare-financial-report
fix/akshare-empty-dataframe-handling
fix/hk-date-range-filter
docs/update-data-flow-diagram
release/v1.0.0
```

### 2.2 分支操作规范

```bash
# 从 develop 创建功能分支
git checkout develop
git pull origin develop
git checkout -b feature/dcf-sensitivity-analysis

# 开发完成后推送并创建 PR
git push origin feature/dcf-sensitivity-analysis
# 在 GitHub 创建 Pull Request，目标分支：develop

# 合并后删除功能分支
git branch -d feature/dcf-sensitivity-analysis
git push origin --delete feature/dcf-sensitivity-analysis
```

### 2.3 保护规则

- `main` 分支：禁止直接 push，必须通过 PR + 至少 1 人 Review
- `develop` 分支：推荐通过 PR，紧急修复可直接 push 并补 PR
- 功能分支：开发者自由操作

---

## 3. Commit Message 规范

采用 **Conventional Commits** 规范，格式如下：

```
<type>(<scope>): <简短描述>

[可选：详细描述]

[可选：关联 Issue]
```

### 3.1 Type 类型

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `refactor` | 重构（不改变功能） |
| `test` | 测试相关 |
| `chore` | 构建/依赖/配置更新 |
| `data` | 数据相关变更（股票池、参数调整） |

### 3.2 Scope 范围（可选）

`config` / `downloader` / `database` / `dcf` / `pipeline` / `docs` / `scripts` / `main`

### 3.3 示例

```bash
# 新功能
git commit -m "feat(dcf): add Monte Carlo sensitivity analysis"

# Bug 修复
git commit -m "fix(downloader): handle empty DataFrame from akshare hk hist"

# 配置变更（扩展股票池）
git commit -m "chore(config): expand A_SHARE_STOCKS to top 50 by market cap"

# 文档
git commit -m "docs: update data flow diagram to reflect akshare integration"

# 重构
git commit -m "refactor(dcf): extract WACC calculation to separate method"

# 依赖更新
git commit -m "chore: upgrade akshare to 1.13.0"
```

### 3.4 禁止事项

```
# ✗ 不允许的提交信息
git commit -m "update"
git commit -m "fix bug"
git commit -m "WIP"
git commit -m "test123"

# ✓ 应改为
git commit -m "fix(downloader): skip stock when akshare returns None dataframe"
```

---

## 4. 代码风格规范

### 4.1 Python 版本与格式

- 最低版本：Python 3.8
- 代码格式化：推荐使用 `black`（行宽 100）
- 导入排序：`isort`
- 类型注解：函数参数和返回值应标注类型（参考现有代码风格）

```bash
pip install black isort
black src/ scripts/ config/ main.py --line-length 100
isort src/ scripts/ config/ main.py
```

### 4.2 命名规范

| 对象 | 规范 | 示例 |
|------|------|------|
| 模块/文件 | `snake_case` | `data_downloader.py` |
| 函数/方法 | `snake_case` | `download_a_share_data()` |
| 类 | `PascalCase` | `DCFModel`, `DCFAssumptions` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_WACC`, `DB_PATH` |
| 变量 | `snake_case` | `stock_code`, `market_price` |

### 4.3 注释规范

- 每个模块顶部必须有模块级 docstring（说明职责和使用场景）
- 每个公有函数/方法必须有 docstring（Args、Returns、Raises）
- 非显而易见的逻辑需要行内注释说明原因（为什么，不是做了什么）
- 禁止无意义注释

```python
# ✗ 无意义注释
# 计算 FCFF
fcff = nopat + da - capex - delta_wc

# ✓ 有价值注释（解释决策）
# demo：以市场价×1亿代理基准营收，生产环境应替换为真实财报营收
self.base_revenue = market_price * 1e8

# ✓ AkShare 日期格式要求 YYYYMMDD，settings 中存储为 YYYY-MM-DD
start = _to_akshare_date(settings.START_DATE)
```

---

## 5. 目录规范

```
ah_dcf_valuation_system/
├── main.py             # 一键入口（4步串联），只做调用，不写业务逻辑
├── config/             # 配置文件，只放参数常量，不放业务逻辑
├── data/               # 运行产出（.db 和 .html），不提交到版本库
├── src/                # 核心业务模块
│   ├── database.py         # 数据库操作（项目中唯一操作 SQLite 的文件）
│   ├── data_downloader.py  # 数据采集（项目中唯一调用 AkShare 的文件）
│   ├── dcf_model.py        # 估值算法（纯计算，不依赖数据库和外部 API）
│   ├── valuation_pipeline.py # 流程编排（协调其他模块，不含计算逻辑）
│   ├── visualizer.py       # 可视化（项目中唯一使用 Plotly 的文件）
│   └── utils.py            # 通用工具（日志、日期校验，无业务依赖）
├── scripts/            # 分步可执行脚本（入口点，轻逻辑，重调用）
│   ├── init_db.py
│   ├── run_download.py
│   ├── run_valuation.py
│   └── run_report.py       # 单独生成 HTML 报告
├── docs/               # 设计文档
└── tests/              # 单元测试（待扩展）
```

**模块职责边界规则**：
- `src/database.py` 是项目中**唯一**操作 SQLite 的文件，其他模块不直接执行 SQL
- `src/data_downloader.py` 是项目中**唯一**调用 AkShare 的文件
- `src/dcf_model.py` 是纯计算模块，不 import database 也不 import data_downloader
- `src/visualizer.py` 是项目中**唯一**使用 Plotly 的文件，只读数据库，不写入
- `config/settings.py` 只放常量，禁止有副作用的代码（如网络请求、文件读写）

---

## 6. Issue 规范

创建 Issue 时请使用以下模板：

### Bug Report

```markdown
**问题描述**
运行 main.py 时 AkShare 下载 H 股数据报错

**复现步骤**
1. pip install -r requirements.txt
2. python main.py

**实际结果**
下载 00700 时抛出 KeyError: '日期'

**预期结果**
正常下载数据并写入数据库

**环境**
- OS: macOS 14.0
- Python: 3.11.2
- akshare: 1.12.5
```

### Feature Request

```markdown
**功能描述**
接入 AkShare 财务报表接口，替换虚拟基准营收

**业务价值**
当前 DCF 使用市价×1亿作为代理营收，导致估值误差较大

**建议实现方案**
在 src/data_downloader.py 中新增 download_financial_data()
调用 ak.stock_financial_report_sina() 获取真实营收数据
在 dcf_model.py 中接收真实 base_revenue 参数

**验收标准**
- [ ] 财务数据写入 financial_assumptions 表
- [ ] DCFModel 优先使用真实营收，无数据时回退到代理值
- [ ] main.py 一键运行包含财务数据下载步骤
```

---

## 7. Pull Request 规范

### 7.1 PR 标题格式

`[type] 简短描述`，如 `[feat] Add financial report data downloader`

### 7.2 PR 正文模板

```markdown
## 变更说明
- 在 `data_downloader.py` 中新增 `download_financial_data()` 函数
- 更新 `dcf_model.py` 接收可选的 `base_revenue` 参数
- 更新 `settings.py` 新增财务数据日期范围配置

## 测试方法
```bash
python main.py
# 预期：看到财务数据下载日志，估值结果中 base_revenue 非虚拟值
sqlite3 data/ah_dcf.db "SELECT COUNT(*) FROM financial_assumptions;"
```

## 关联 Issue
Closes #15

## Checklist
- [ ] 代码通过 black 格式化
- [ ] 新函数有 docstring
- [ ] 没有硬编码参数（参数全在 settings.py）
- [ ] 已在本地完整运行 `python main.py` 验证全流程
- [ ] 已更新相关文档（如涉及架构或数据流变更）
```

---

## 8. 数据库文件管理

### 8.1 .gitignore 规则

`data/*.db` 已加入 `.gitignore`，**数据库文件不提交到版本库**。

原因：
- 数据库包含大量真实行情数据（全市场可达数百 MB）
- 数据库可通过 `python main.py` 重新生成
- 避免不同成员因下载时间不同导致数据版本冲突

### 8.2 多人协作数据同步

**方案 A（推荐/个人/小团队）**：每人独立运行 `python main.py` 生成本地数据库

**方案 B（团队共享数据库）**：将数据库存放在共享存储，运行前先同步

```bash
# 示例：从 S3 同步数据库（需配置 AWS CLI）
aws s3 cp s3://your-bucket/ah_dcf.db data/ah_dcf.db
python scripts/run_valuation.py  # 只跑估值，不重复下载
```

---

## 9. 参数配置管理

### 9.1 单人开发

直接修改 `config/settings.py`，提交到版本库（参数变更是需要 review 的配置变更）。

### 9.2 多人协作

当不同成员需要不同参数时：

**方法 A**：创建 `config/settings_local.py`（加入 `.gitignore`），在其中覆盖默认值：
```python
# config/settings_local.py（本地专用，不提交）
from config.settings import *   # 继承所有默认值
DEFAULT_WACC = 0.12             # 覆盖单个参数
```

**方法 B**：支持环境变量覆盖（适合 CI/CD 环境）：
```python
# settings.py 中的写法
DEFAULT_WACC = float(os.getenv("DCF_WACC", "0.10"))
```

**方法 C**：将参数迁移到 `config/params.yaml`，通过脚本参数指定配置文件路径（适合多套参数并行回测）。

---

## 10. 扩展到全市场的协作建议

当系统扩展到全市场时，推荐以下团队分工：

| 模块 | 负责角色 | 说明 |
|------|----------|------|
| `config/settings.py` | 研究团队 | 维护 DCF 参数和股票池 |
| `src/data_downloader.py` | 数据工程师 | 维护 AkShare 接口调用和数据清洗 |
| `src/database.py` | 数据工程师 | 维护 DDL、索引和查询性能 |
| `src/dcf_model.py` | 量化研究员 | 维护 DCF 算法、参数模型和情景分析 |
| `src/valuation_pipeline.py` | 全栈工程师 | 维护调度逻辑和并行化 |
| `src/visualizer.py` | 全栈工程师 | 维护图表类型和报告样式 |
| `main.py` / `scripts/` | 全栈工程师 | 维护入口和运行流程 |
| `docs/` | 所有成员 | 每次功能变更同步更新相关文档 |

**Code Review 要求**：
- `dcf_model.py` 的 DCF 参数变更：必须经量化研究员 approve
- `database.py` 的 schema 变更（新增/删除字段）：必须经数据工程师 approve
- 所有 PR 至少 1 人 review；全市场生产代码要求 2 人 review
- `settings.py` 中的股票池和 DCF 参数变更：必须在 PR 描述中说明变更原因
