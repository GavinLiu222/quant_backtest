# 欢迎使用 backtest 👋

![Version](https://img.shields.io/badge/version-0.1.0-blue.svg?cacheSeconds=2592000)
![Prerequisite](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)

简体中文 | [English](README.en.md)

> 基于持仓的日频股票因子回测框架：因子中性化、Rank IC、分组回测、多空组合、Top N 组合与绩效统计。

覆盖一个因子从研究到组合评估的完整流程：

```
                     ┌─────────────────────────┐
 原始因子 ──(可选)──▶ │ ① factor_neutralize.py  │ 去极值 → 标准化 → 行业中位数填充 → 行业+市值中性化
                     └───────────┬─────────────┘
                                 ▼
          ② ic_tests.py               Rank IC / ICIR
          ③ positions2nav_testing.py  N 分组回测，自动判定因子方向
          ④ long_short.py             头尾两组构建多空组合并统计
          ⑤ positions2nav_update.py   按因子方向选 Top N 构建多头组合（支持增量更新）
          ⑥ nav2stats.py              组合相对基准指数的绩效统计
```

所有脚本只读写本地 parquet / Excel 文件，**不依赖任何数据库**。按照[数据规则](#数据规则)准备数据，
在 [`settings.py`](settings.py) 中设置参数，然后运行 `python main.py` 即可。

## 目录

- [前置条件](#前置条件)
- [安装](#安装)
- [使用](#使用)
- [目录结构](#目录结构)
- [数据规则](#数据规则)
- [参数设置](#参数设置)
- [各步骤的输入与输出](#各步骤的输入与输出)
- [回测引擎的计算口径](#回测引擎的计算口径)
- [与原框架相比的改动](#与原框架相比的改动)

## 前置条件

- python >=3.12
- [uv](https://docs.astral.sh/uv/)

## 安装

```sh
uv sync
```

依赖见 [`pyproject.toml`](pyproject.toml)。pandas 限定为 `<3`，原因见[与原框架相比的改动](#与原框架相比的改动)。

## 使用

### 用模拟数据试跑

```sh
uv run python make_demo_data.py
```

```sh
uv run python main.py
```

`make_demo_data.py` 会在 `data/` 下生成一套随机模拟的 A 股数据（800 只股票、约 5 年、2 个因子）。数据格式完全符合数据规则，
可以直接跑通全部流程（约 1–2 分钟），也可以作为准备自己数据时的样例。

### 使用自己的数据

1. 按[数据规则](#数据规则)把文件放到数据目录（默认 `./data`，或设置环境变量 `BACKTEST_DATA_DIR`）；
2. 修改 [`settings.py`](settings.py)（回测区间、股票池、基准等，见[参数设置](#参数设置)）；
3. 检查数据：`uv run python data_spec.py`；
4. 运行：`uv run python main.py`。

### 单独运行某一步

```sh
uv run python main.py testing long_short
```

步骤名为 `neutralize ic testing long_short update stats`。也可以直接运行脚本（如 `uv run python ic_tests.py`），但这样不会先做数据检查。

单因子 5 分组测试不在 `main.py` 流程中，需要单独运行：

```sh
uv run python positions2nav.py alpha_signal
```

## 目录结构

### 代码

| 文件 | 作用 |
|---|---|
| [`settings.py`](settings.py) | **全部可调参数**，一般只需要修改这个文件 |
| [`data_spec.py`](data_spec.py) | **数据规则**：数据目录结构、文件名、必需字段，以及数据检查 `validate()` |
| [`main.py`](main.py) | 一键运行：先检查数据，再依次运行 ①–⑥ |
| [`make_demo_data.py`](make_demo_data.py) | 生成符合规则的模拟数据 |
| [`factor_neutralize.py`](factor_neutralize.py) | ① 因子中性化 |
| [`ic_tests.py`](ic_tests.py) | ② Rank IC / ICIR |
| [`positions2nav_testing.py`](positions2nav_testing.py) | ③ 分组回测 + 因子方向判定 |
| [`long_short.py`](long_short.py) | ④ 多空组合统计 |
| [`positions2nav_update.py`](positions2nav_update.py) | ⑤ Top N 因子多头组合 |
| [`nav2stats.py`](nav2stats.py) | ⑥ 组合绩效统计（相对基准） |
| [`positions2nav.py`](positions2nav.py) | 回测引擎原型 + 单因子 5 分组测试 |
| [`common_functions.py`](common_functions.py) | 数据库连接等公共函数（离线运行用不到） |

③⑤⑥ 和 `positions2nav.py` 中各有一份 `Positions2Nav` 类，即"持仓 → 净值"的回测引擎，逻辑见[回测引擎的计算口径](#回测引擎的计算口径)。

### 数据目录（`DATA_DIR`）

```
data/
├── config/                          # ── 输入：配置表 ──
│   ├── factors_dict.xlsx            # 因子清单
│   ├── factors_dict_neutral.xlsx    # 因子清单（NEUTRAL=True 时使用）
│   ├── portfolio_info.xlsx          # Top N 组合定义（⑤⑥ 使用）
│   ├── portfolio_info_neutral.xlsx  # 同上（NEUTRAL=True 时使用）
│   └── rebalance_dates.pq           # 调仓日历
├── market_data/                     # ── 输入：行情与股票属性 ──
│   ├── trading_days.pq
│   ├── stock_market.pq
│   ├── stock_status.pq
│   ├── barra_factors.pq             # 仅中性化需要
│   └── index_prices.pq
├── factor_data/
│   ├── factors/<因子名>.pq           # ── 输入：原始因子 ──
│   └── factors_neutral/<因子名>.pq   # 输出：① 生成
├── results/                         # 输出：②④
├── g_positions/                     # 输出：③⑤ 每期持仓
├── navs/                            # 输出：③⑤ 净值
├── pics/                            # 输出：③ 分组净值图
├── portfolios/                      # 输出：⑥
└── logs/                            # 运行日志
```

`data/` 已写入 `.gitignore`。引擎还会自动建立 `org_data/`、`positions/`、`factor_rotation/` 三个空目录（原框架遗留，无内容）。

## 数据规则

规则同时写在 [`data_spec.py`](data_spec.py) 中。运行 `python data_spec.py` 会按规则检查数据目录并列出所有问题，
`main.py` 运行前也会自动检查。

### 通用约定

- 所有 `.pq` 文件都是 **parquet** 格式。
- `date` 列（以及 `position_adjust_date`）必须是 **datetime64**（不带时区），只包含交易日。
- `stock_id` 列是**字符串**，所有文件使用同一种代码格式（如 `600000.SH`）。
- 除 `index_prices.pq` 外，行情类文件都是**长表**：每行一个 `(date, stock_id)`，且不能重复。
- 0/1 标记列用整数 0 / 1，不能有缺失值。

### `market_data/trading_days.pq`：交易日历

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | datetime64 | 全部交易日，需覆盖回测区间 |

### `market_data/stock_market.pq`：日行情

| 列 | 类型 | 说明 |
|---|---|---|
| `date`, `stock_id` | | 主键 |
| `open`, `high`, `low`, `close` | float | 当日开高低收（不复权即可）。`open == high == low == close` 的"一字板"当天不进入选股样本 |
| `adj_close` | float | 复权收盘价 |
| `adj_pre_close` | float | 同一复权口径下的前收盘价。**日收益率 = `adj_close / adj_pre_close - 1`** |
| `trade_status` | int | 1 = 当日正常交易，其余 = 停牌等不可交易 |
| `float_mv` | float | 流通市值。**仅当某个股票池 `weighting='float_mv'` 时必需** |

没有 `adj_pre_close` 时，可以用 `df.groupby('stock_id')['adj_close'].shift(1)` 生成（上市首日需另行填充）。

### `market_data/stock_status.pq`：股票属性

| 列 | 类型 | 说明 |
|---|---|---|
| `date`, `stock_id` | | 主键 |
| `is_ST` | int | 1 = ST 等需剔除的股票（非 A 股可全填 0） |
| `is_new_stock` | int | 1 = 次新股；股票池 `exclude_new_stock=True` 时被剔除 |
| `<股票池名>` | int | **`settings.UNIVERSES` 中每个股票池一列**，1 = 当日属于该股票池，例如 `hs300`、`zz500`、`kc` |
| `<INDUSTRY_PREFIX><行业名>` | int | 行业哑变量（默认前缀 `ind_`，如 `ind_banks`），每行恰好一个 1。**仅中性化需要** |

### `market_data/barra_factors.pq`：风格暴露（仅中性化需要）

| 列 | 类型 | 说明 |
|---|---|---|
| `date`, `stock_id` | | 主键 |
| `size` | float | 市值因子暴露，例如 `log(流通市值)` |

### `market_data/index_prices.pq`：指数收盘价（宽表）

- 索引：`DatetimeIndex`（交易日）；
- 列：指数代码，**必须包含 `settings.UNIVERSES` 中所有 `benchmark`**；
- 值：收盘点位。

```python
index_prices = long_df.pivot(index='date', columns='index_code', values='close')
index_prices.to_parquet('data/market_data/index_prices.pq')
```

### `factor_data/factors/<因子名>.pq`：因子值

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | datetime64 | 因子日期，因子值只能使用该日收盘及之前的信息 |
| `stock_id` | str | |
| `factor_value` | float | 因子值，缺失可为 NaN（会被剔除） |

文件名（不含 `.pq`）就是因子名，必须与 `factors_dict.xlsx` 中的 `factor_name` 一致。IC 测试使用文件中的所有日期；
分组回测和 Top N 组合只使用 `rebalance_dates.pq` 中信号日的因子值。

### `config/rebalance_dates.pq`：调仓日历

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | datetime64 | 信号日：用这一天的因子值选股 |
| `position_adjust_date` | datetime64 | 生效日：按新权重以收盘价调仓（通常为信号日的下一交易日） |

例：每月最后一个交易日出信号，下一交易日调仓

```python
days = pd.read_parquet('data/market_data/trading_days.pq')['date']
last_in_month = days.groupby(days.dt.to_period('M')).transform('max') == days
rebalance = pd.DataFrame({'date': days, 'position_adjust_date': days.shift(-1)})[last_in_month]
rebalance.dropna().to_parquet('data/config/rebalance_dates.pq')
```

### `config/factors_dict.xlsx`：因子清单

| 列 | 说明 |
|---|---|
| `factor_id` | 整数编号（多空统计中作为组合编号） |
| `factor_name` | 因子名，对应 `factor_data/factors/<factor_name>.pq` |

`NEUTRAL=True` 时读取 `factors_dict_neutral.xlsx`（内容相同即可，复制一份）；中性化步骤本身始终读取 `factors_dict.xlsx`。
③ 运行后会在该表中**为每个股票池追加一列因子方向得分**（见[因子方向约定](#因子方向约定)）。

### `config/portfolio_info.xlsx`：Top N 组合定义（⑤⑥ 使用）

sheet 名必须为 `portfolio_info`，每行一个组合：

| 列 | 说明 |
|---|---|
| `portfolio_id` | 整数，唯一 |
| `portfolio_name` | 组合名，格式 `因子名#任意后缀`，`#` 前的部分在统计表中作为因子名 |
| `portfolio_type` | `factor` / `portfolio` / `smart_beta` / `index_enhance` 之一，其他类型不计算净值 |
| `factor_name` | 使用的因子 |
| `factor_direction` | `1` = 选因子值最小的 N 只；`-1` = 选最大的 N 只；`0` = 跳过 |
| `stock_area` | 股票池名，必须在 `settings.UNIVERSES` 中；每个股票池内每个因子只取第一行 |
| `benchmark`, `barra_adjusted`, `frequency` | 描述字段，原样写入统计结果 |

`NEUTRAL=True` 时读取 `portfolio_info_neutral.xlsx`。

### 可选：数据库模式

原框架的数据库拉数功能完整保留（各脚本 `isupdate_data` 中 `stock_prices` / `index_prices` > 0 时启用），
需要设置 `QUANT_DB_*` 环境变量（见 [`common_functions.py`](common_functions.py)）以及 `config/index_info.xlsx`。
SQL 针对原公司的 Wind 库表结构编写，默认全部关闭，离线运行不需要。

## 参数设置

所有参数都在 [`settings.py`](settings.py) 中：

| 参数 | 默认值 | 作用 |
|---|---|---|
| `DATA_DIR` | `./data` | 数据根目录；设置环境变量 `BACKTEST_DATA_DIR` 可覆盖 |
| `START_DATE` / `END_DATE` | `20200930` / `20250630` | 回测区间 |
| `SPECIAL_DATE` | `20241231` | `ret_special_date`、`adv_navs_fsd` 的起点，必须是区间内交易日 |
| `NEUTRAL` | `False` | 是否使用中性化因子；`True` 时 `main.py` 先运行 ①，其后所有输入输出带 `_neutral` 后缀 |
| `UNIVERSES` | 5 个 A 股股票池 | 见下 |
| `N_GROUPS` | `10` | ③ 分组数，组号 `1000`（因子值最小）… `1000+N_GROUPS-1`（最大）；④ 用两端的组 |
| `INIT_AMOUNT` | `1e7` | 初始资金 |
| `FEE_RATE` | `1.5e-3` | 单边费率，按每只股票调仓金额收取 |
| `WEIGHT_CAP` | `0.05` | `weighting='float_mv'` 时的单票权重上限 |
| `DAYS_PER_YEAR` | `242` | 年化天数（A 股 242，美股可改 252） |
| `INDUSTRY_PREFIX` | `'ind_'` | 行业哑变量列前缀 |
| `EXCLUDE_ID_SUFFIXES` / `EXCLUDE_ID_PREFIXES` / `EXCLUDE_IDS` | `('.BJ','.NE','.WI')` / `('A',)` / `('000024.SZ',)` | 原框架对 A 股 Wind 代码的清洗规则。**使用非 A 股数据时请全部改成 `()`**，否则如 `AAPL` 会因前缀 `A` 被剔除 |
| `BARRA_RENAME` | `False` | ⑥ 是否用 `portfolio_info` 中 sheet `软约束限BARRA_{barra_sheet}_01` 的映射重命名组合 |

`UNIVERSES` 的每一项：

```python
'hs300': {'benchmark': '000300.SH',   # 基准指数代码（index_prices.pq 的列）
          'top_n': 100,               # ⑤ 持股数
          'weighting': 'equal',       # 'equal' 等权；'float_mv' 流通市值加权并限制单票上限
          'exclude_new_stock': True,  # 是否剔除 is_new_stock == 1
          'barra_sheet': '300'},      # 仅 BARRA_RENAME=True 时使用
```

增删股票池只需增删这一项，并在 `stock_status.pq` 中提供同名的 0/1 列。所有步骤都会遍历 `UNIVERSES` 中的全部股票池。

**写在代码中、未放入 `settings.py` 的常数**（属于计算逻辑本身，保持原样）：

| 位置 | 常数 |
|---|---|
| 回测引擎 `calculate_position_core` / `config` | 建仓与每次调仓时投资 95%，保留 5% 现金 |
| `ic_tests.py` | 未来收益窗口：`t+1` 到 `t+21` 收盘（`ret_20D`）；`Rank_ICIR = mean(IC) / (std(IC)·√252)` |
| `factor_neutralize.py` | MAD 去极值阈值 3×1.4826×MAD，截面唯一值少于 100 时跳过去极值 |
| 各 `statistics_core_1` | 近 6 月 / 3 月 / 1 月 / 1 周 / 3 日 / 2 日 / 1 日收益分别以倒数第 121 / 64 / 22 / 6 / 4 / 3 / 2 个净值为起点（近 1 年为倒数第 `DAYS_PER_YEAR` 个） |
| `positions2nav.py` | 单因子测试固定为 5 组 |

## 各步骤的输入与输出

`{neu}` 表示 `NEUTRAL=True` 时为 `_neutral`，否则为空；`{u}` 为股票池名；`{f}` 为因子名。所有输出目录会自动创建。

### ① `factor_neutralize.py`：因子中性化

- **输入**：`factors_dict.xlsx`、`factors/{f}.pq`、`stock_status.pq`（行业哑变量）、`barra_factors.pq`
- **处理**（每个交易日截面）：MAD 去极值 → z-score → 行业中位数填充缺失 → 对「行业哑变量 + size」做 OLS，取残差
- **输出**：`factor_data/factors_neutral/{f}.pq`（`date, stock_id, factor_value`）

### ② `ic_tests.py`：Rank IC

- **输入**：`factors_dict{neu}.xlsx`、`factors{neu}/{f}.pq`、`stock_market.pq`（`adj_close`）、`stock_status.pq`（股票池列）
- **输出**：`results/icir{neu}/icir_stats_{u}.xlsx`
  - `日度Rank_IC`：每日股票池内因子值与未来 20 日收益的 Spearman 相关系数，每个因子一列
  - `累计Rank_IC`：日度 IC 的累加
  - `Rank_ICIR`：`mean / (std·√252)`

### ③ `positions2nav_testing.py`：分组回测

- **输入**：`factors_dict{neu}.xlsx`、`factors{neu}/{f}.pq`、`stock_market.pq`、`stock_status.pq`、`rebalance_dates.pq`、`trading_days.pq`、`index_prices.pq`
- **样本**：信号日属于该股票池、`trade_status == 1`、`is_ST == 0`、非一字板、（可选）非次新股、因子值非空
- **分组**：每个信号日按因子值排序（同值按出现顺序），等分为 `N_GROUPS` 组，组内等权（`weighting='float_mv'` 时流通市值加权并封顶 `WEIGHT_CAP`）
- **输出**
  - `g_positions/g_positions_testing{neu}/{u}/g_positions_{f}.pq`：`portfolio_id`（组号）、`date`（生效日）、`instrument`、`weight`
  - `navs/navs_testing{neu}/{u}/navs_{f}.pq`：`portfolio_id, date, nav, turn_over`
  - `pics/pics{neu}/{u}/navs_{f}.jpg`：各组净值曲线
  - `factors_dict{neu}.xlsx` 增加一列 `{u}`：因子方向得分

#### 因子方向约定

方向得分 = 组号排名（1000 → 1）与夏普比率排名（最高 → 1）的 Spearman 相关系数：

- **得分 > 0**：因子值**越小**越好 → ④ 做多 1000 组、做空最后一组；⑤ 中对应 `factor_direction = 1`
- **得分 < 0**：因子值**越大**越好 → ④ 做多最后一组、做空 1000 组；⑤ 中对应 `factor_direction = -1`

### ④ `long_short.py`：多空组合

- **输入**：`factors_dict{neu}.xlsx`（需含 ③ 写入的方向列）、③ 的 `navs_testing{neu}`、`index_prices.pq`
- **计算**：多头组日收益 − 空头组日收益，累乘得多空净值
- **输出**：`results/long_short{neu}/long_short_stats_{u}.xlsx`
  - `factor_statistic`：每个因子一行，指标见[统计指标说明](#统计指标说明)（仅绝对收益部分）
  - `navs`：多空净值；`navs_r3m`：最近 90 天归一化净值

### ⑤ `positions2nav_update.py`：Top N 因子组合

- **输入**：`portfolio_info{neu}.xlsx`、`factors{neu}/{f}.pq`、`stock_market.pq`、`stock_status.pq`、`rebalance_dates.pq`、`trading_days.pq`、`index_prices.pq`
- **选股**：样本同 ③；按 `factor_direction` 排序取前 `top_n` 只，等权（或流通市值加权封顶）
- **增量**：若 `g_positions{neu}/g_positions_{u}.pq` 已存在，只为上次之后的信号日追加持仓，然后重算全部净值
- **输出**
  - `g_positions/g_positions{neu}/g_positions_{u}.pq`：`portfolio_id, date, instrument, weight`
  - `navs/navs{neu}/navs_{u}.pq`：`portfolio_id, date, nav, turn_over`

  （`NEUTRAL=False` 时目录名为 `navs/navs/`、`g_positions/g_positions/`，与原框架一致）

### ⑥ `nav2stats.py`：组合绩效

- **输入**：⑤ 的 `navs/navs{neu}/navs_{u}.pq`、`portfolio_info{neu}.xlsx`、`index_prices.pq`、`trading_days.pq`、`stock_market.pq`
- **输出**：`portfolios/factor_statistic{neu}/factor_statistic_{u}.xlsx`

| sheet | 内容 |
|---|---|
| `factor_statistic` | 全部指标 |
| `factor_statistic_simple` | 常用指标 |
| `navs` | 组合净值 |
| `adv_navs` | 超额累计收益（%），超额日收益 = 组合日收益 − 基准日收益 |
| `navs_r3m` / `adv_navs_r3m` | 最近 90 天（归一化）净值 / 超额（%） |
| `adv_navs_fsd` | `SPECIAL_DATE` 以来的超额（%） |

### 统计指标说明

收益、波动、回撤均以 **%** 表示。

| 指标 | 含义 |
|---|---|
| `trading_days` | 净值天数 |
| `ret_in_period` | 区间累计收益 |
| `ret_special_date` | `SPECIAL_DATE` 至今收益 |
| `ret_recent1year` … `ret_recent1day` | 最近 1 年 / 6 月 / 3 月 / 1 月 / 1 周 / 3 日 / 2 日 / 1 日收益 |
| `annualized_ret` | 年化收益 `nav^(DAYS_PER_YEAR/天数) − 1` |
| `volatility` | 年化波动（对数收益标准差 × √DAYS_PER_YEAR） |
| `max_draw_down` | 最大回撤 |
| `adv_*` | 同上，基于超额净值 |
| `换手率` | 年化换手：日均（买入 + 卖出金额）/ 组合市值 × DAYS_PER_YEAR |
| `information_ratio` | `annualized_adv_ret / adv_volatility`（④ 中为 `annualized_ret / volatility`） |
| `return_mdd_ratio` | 年化（超额）收益 / 最大回撤 |
| `*_r3month` | 近 3 月超额收益年化后，除以**全区间**超额波动 / 回撤 |
| `*_recent3month` / `*_recent1month` / `*_recent1week` | 近期超额收益年化后，除以**同期**超额波动 / 回撤 |

## 回测引擎的计算口径

`Positions2Nav.calculate_position_core` 把每期目标权重转成每日持仓市值：

1. 期初资金 `INIT_AMOUNT`，首次建仓投入 95%，5% 为现金；
2. 生效日按收盘价调仓，当天不计收益；持仓期内每只股票按 `adj_close / adj_pre_close − 1` 逐日复利；
3. 每次调仓把"持仓市值 + 现金"的 95% 按新权重分配，交易费用 = `FEE_RATE × |调仓金额|`，从现金中扣除，现金不计息；
4. 净值 = （持仓市值 + 现金）/ `INIT_AMOUNT`；`turn_over` = 当日（买入 + 卖出）金额 / 组合市值。

Top N 选股时会给因子值加上 1e-12 量级的随机扰动以打破并列（原框架逻辑），因此因子值存在大量并列时，多次运行结果可能有极小差异。

## 与原框架相比的改动

计算函数的逻辑没有修改。改动只涉及输入输出：

| 原框架 | 现在 |
|---|---|
| 数据路径来自 `USER_DATA_DIR/projects/<目录名>`（用 Windows 的 `\` 拆分路径，macOS/Linux 上直接报错）或写死的 `/Volumes/GAVIN/...` | 统一为 `settings.DATA_DIR`（可用环境变量 `BACKTEST_DATA_DIR` 覆盖） |
| 各脚本 `__main__` 中分散写死日期、股票池、基准、持股数、中性化开关 | 集中到 `settings.py` |
| 文件名 `CommonFunctions.py`、`IC_tests.py`、`position2nav_testing.py` 大小写、单复数不统一 | 改为 `common_functions.py`、`ic_tests.py`、`positions2nav_testing.py`：全部小写，统一用 `positions` |
| `common/` 或 `market_data/` 下的 `tradying_days.pq` | `market_data/trading_days.pq` |
| `config/` 或 `market_data/` 下的 `datelist.pq` | `config/rebalance_dates.pq` |
| `stock_prices.pq` + `stock_market.pq` + Wind 字段的 `ashare_deri.pq` | 合并为 `stock_market.pq`，流通市值为 `float_mv` 列 |
| 因子文件列格式不统一（③ 为 5 列，其余按位置改名） | 统一按列名读取 `date, stock_id, factor_value` |
| `positions2nav.py` 读取逐年宽表 `factors_<年>0101.pq` | 读取一个标准因子文件：`python positions2nav.py <因子名>` |
| ③ 需要 `portfolio_info_onetime.xlsx`；各引擎还读取未使用的 `factor_info` sheet 和 `index_info.xlsx` | 分组组合由 `N_GROUPS` 自动生成；`index_info.xlsx` 只在数据库模式下读取 |
| 科创板股票池由代码 `688` 开头自动生成 | 在 `stock_status.pq` 中与其他股票池一样提供 `kc` 列 |
| 行业列固定为 31 个 `zx_` 前缀的中信行业 | 所有以 `INDUSTRY_PREFIX` 开头的列 |
| 代码过滤（`.BJ` / `.NE` / `.WI` / `A` 开头 / `000024.SZ`）分散在各脚本且各不相同 | `settings.EXCLUDE_*`，在原来做过滤的位置统一使用 |
| 科创板专用的 `2021-12-30` 日期修补 | 删除：它只针对原数据，且在 pandas 2.x 下会把日期列变成 object 类型导致合并报错 |
| ⑤ 离线运行时也强制连接数据库；科创板部分从数据库拉行情 | 只在 `old_navs='database'` 时连接；全部默认读取本地文件 |
| 读因子失败时静默跳过；输出目录需手工创建 | 打印跳过原因；输出目录自动创建；运行前检查数据 |
| 未声明 `pyarrow` / `openpyxl`，`pandas>=3` | 补充依赖；pandas 限定 `<3`（原代码的 `groupby().apply()` 依赖分组列保留在结果中，pandas 3 已移除该行为，结果会丢失 `date` 列） |

**一致性验证**：在模拟数据上，用原版脚本（只修改路径、日期和离线开关）与本框架分别运行全部步骤，
中性化因子、IC、分组持仓与净值、因子方向、多空统计、Top N 持仓与净值、绩效统计以及 `positions2nav.py` 的
共 103 个输出文件 / sheet 在 1e-12 精度内完全一致。

## 支持

如果这个项目对你有帮助，欢迎点一个 ⭐️！

***
_本 README 基于 [readme-md-generator](https://github.com/kefranabg/readme-md-generator) 生成_
