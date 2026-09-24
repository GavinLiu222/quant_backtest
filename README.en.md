# Welcome to backtest 👋

![Version](https://img.shields.io/badge/version-0.1.0-blue.svg?cacheSeconds=2592000)
![Prerequisite](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)

[简体中文](README.md) | English

> Position-based daily stock factor backtesting framework: factor neutralization, Rank IC, group tests, long-short portfolios, top-N portfolios and performance statistics.

It covers the full path of a factor from research to portfolio evaluation:

```
                     ┌─────────────────────────┐
 raw factors ─(opt)─▶ │ ① factor_neutralize.py  │ winsorize → standardize → fill with industry median → industry + size neutralization
                     └───────────┬─────────────┘
                                 ▼
          ② ic_tests.py               Rank IC / ICIR
          ③ positions2nav_testing.py  N-group backtest, detects the factor direction
          ④ long_short.py             long-short portfolio from the top and bottom groups
          ⑤ positions2nav_update.py   long-only top-N portfolio per factor direction (incremental updates)
          ⑥ nav2stats.py              portfolio performance relative to a benchmark index
```

Every script reads and writes local parquet / Excel files only; **no database is needed**. Prepare your data according to the
[data specification](#data-specification), set parameters in [`settings.py`](settings.py), then run `python main.py`.

## Table of contents

- [Prerequisites](#prerequisites)
- [Install](#install)
- [Usage](#usage)
- [Project layout](#project-layout)
- [Data specification](#data-specification)
- [Settings](#settings)
- [Inputs and outputs of each step](#inputs-and-outputs-of-each-step)
- [How the backtest engine computes NAV](#how-the-backtest-engine-computes-nav)
- [Changes from the original framework](#changes-from-the-original-framework)

## Prerequisites

- python >=3.12
- [uv](https://docs.astral.sh/uv/)

## Install

```sh
uv sync
```

Dependencies are listed in [`pyproject.toml`](pyproject.toml). pandas is pinned to `<3`; see
[Changes from the original framework](#changes-from-the-original-framework) for why.

## Usage

### Try it with demo data

```sh
uv run python make_demo_data.py
```

```sh
uv run python main.py
```

`make_demo_data.py` writes a randomly simulated A-share dataset to `data/` (800 stocks, about 5 years, 2 factors). It follows the
data specification exactly, runs through the whole pipeline (about 1–2 minutes), and doubles as a template for preparing your own data.

### Use your own data

1. Put your files in the data directory (`./data` by default, or set the `BACKTEST_DATA_DIR` environment variable) following the [data specification](#data-specification);
2. Edit [`settings.py`](settings.py) (backtest period, universes, benchmarks, …; see [Settings](#settings));
3. Check the data: `uv run python data_spec.py`;
4. Run: `uv run python main.py`.

### Run individual steps

```sh
uv run python main.py testing long_short
```

Step names are `neutralize ic testing long_short update stats`. You can also run a script directly (e.g. `uv run python ic_tests.py`),
but then the data check is skipped.

The single-factor 5-group test is not part of the `main.py` pipeline and is run on its own:

```sh
uv run python positions2nav.py alpha_signal
```

## Project layout

### Code

| File | Purpose |
|---|---|
| [`settings.py`](settings.py) | **All tunable parameters**; usually the only file you edit |
| [`data_spec.py`](data_spec.py) | **Data specification**: directory layout, file names, required columns, and the data check `validate()` |
| [`main.py`](main.py) | One-command run: checks the data, then runs ①–⑥ in order |
| [`make_demo_data.py`](make_demo_data.py) | Generates demo data that follows the specification |
| [`factor_neutralize.py`](factor_neutralize.py) | ① Factor neutralization |
| [`ic_tests.py`](ic_tests.py) | ② Rank IC / ICIR |
| [`positions2nav_testing.py`](positions2nav_testing.py) | ③ Group backtest + factor direction |
| [`long_short.py`](long_short.py) | ④ Long-short statistics |
| [`positions2nav_update.py`](positions2nav_update.py) | ⑤ Top-N long-only factor portfolios |
| [`nav2stats.py`](nav2stats.py) | ⑥ Portfolio performance statistics (vs benchmark) |
| [`positions2nav.py`](positions2nav.py) | Backtest engine prototype + single-factor 5-group test |
| [`common_functions.py`](common_functions.py) | Database connection and other helpers (not needed offline) |

③, ⑤, ⑥ and `positions2nav.py` each contain a copy of the `Positions2Nav` class, the "positions → NAV" backtest engine; see
[How the backtest engine computes NAV](#how-the-backtest-engine-computes-nav).

### Data directory (`DATA_DIR`)

```
data/
├── config/                          # ── input: configuration tables ──
│   ├── factors_dict.xlsx            # factor list
│   ├── factors_dict_neutral.xlsx    # factor list (used when NEUTRAL=True)
│   ├── portfolio_info.xlsx          # top-N portfolio definitions (used by ⑤⑥)
│   ├── portfolio_info_neutral.xlsx  # same (used when NEUTRAL=True)
│   └── rebalance_dates.pq           # rebalance calendar
├── market_data/                     # ── input: prices and stock attributes ──
│   ├── trading_days.pq
│   ├── stock_market.pq
│   ├── stock_status.pq
│   ├── barra_factors.pq             # neutralization only
│   └── index_prices.pq
├── factor_data/
│   ├── factors/<factor>.pq          # ── input: raw factors ──
│   └── factors_neutral/<factor>.pq  # output of ①
├── results/                         # output of ②④
├── g_positions/                     # output of ③⑤: holdings per rebalance
├── navs/                            # output of ③⑤: NAVs
├── pics/                            # output of ③: group NAV charts
├── portfolios/                      # output of ⑥
└── logs/                            # run logs
```

`data/` is in `.gitignore`. The engine also creates three empty directories, `org_data/`, `positions/` and `factor_rotation/`
(left over from the original framework).

## Data specification

The rules are also encoded in [`data_spec.py`](data_spec.py). `python data_spec.py` checks the data directory against them and lists
every problem; `main.py` runs the same check before starting.

### General conventions

- All `.pq` files are **parquet**.
- `date` columns (and `position_adjust_date`) must be **datetime64** without a time zone and contain trading days only.
- `stock_id` is a **string** and uses the same code format in every file (e.g. `600000.SH`).
- Apart from `index_prices.pq`, market files are **long tables**: one row per `(date, stock_id)`, with no duplicates.
- 0/1 flag columns hold integers 0 / 1 with no missing values.

### `market_data/trading_days.pq`: trading calendar

| Column | Type | Description |
|---|---|---|
| `date` | datetime64 | All trading days; must cover the backtest period |

### `market_data/stock_market.pq`: daily prices

| Column | Type | Description |
|---|---|---|
| `date`, `stock_id` | | Key |
| `open`, `high`, `low`, `close` | float | Daily OHLC (unadjusted is fine). On days with `open == high == low == close` (a limit-locked bar) the stock is excluded from selection |
| `adj_close` | float | Adjusted close |
| `adj_pre_close` | float | Previous close on the same adjustment basis. **Daily return = `adj_close / adj_pre_close - 1`** |
| `trade_status` | int | 1 = traded normally that day; anything else = suspended / not tradable |
| `float_mv` | float | Free-float market value. **Required only if a universe uses `weighting='float_mv'`** |

If you have no `adj_pre_close`, build it with `df.groupby('stock_id')['adj_close'].shift(1)` (fill the listing day separately).

### `market_data/stock_status.pq`: stock attributes

| Column | Type | Description |
|---|---|---|
| `date`, `stock_id` | | Key |
| `is_ST` | int | 1 = ST or otherwise excluded stock (use all 0 outside China A-shares) |
| `is_new_stock` | int | 1 = recently listed; excluded when the universe has `exclude_new_stock=True` |
| `<universe>` | int | **One column per universe in `settings.UNIVERSES`**; 1 = member on that day, e.g. `hs300`, `zz500`, `kc` |
| `<INDUSTRY_PREFIX><industry>` | int | Industry dummies (default prefix `ind_`, e.g. `ind_banks`), exactly one 1 per row. **Neutralization only** |

### `market_data/barra_factors.pq`: style exposures (neutralization only)

| Column | Type | Description |
|---|---|---|
| `date`, `stock_id` | | Key |
| `size` | float | Size exposure, e.g. `log(free-float market value)` |

### `market_data/index_prices.pq`: index closes (wide table)

- Index: `DatetimeIndex` (trading days);
- Columns: index codes, **which must include every `benchmark` in `settings.UNIVERSES`**;
- Values: closing levels.

```python
index_prices = long_df.pivot(index='date', columns='index_code', values='close')
index_prices.to_parquet('data/market_data/index_prices.pq')
```

### `factor_data/factors/<factor>.pq`: factor values

| Column | Type | Description |
|---|---|---|
| `date` | datetime64 | Factor date; the value may only use information available at that day's close |
| `stock_id` | str | |
| `factor_value` | float | Factor value; NaN allowed (dropped) |

The file name without `.pq` is the factor name and must match `factor_name` in `factors_dict.xlsx`. The IC test uses every date in
the file; the group backtest and top-N portfolios only use factor values on the signal dates in `rebalance_dates.pq`.

### `config/rebalance_dates.pq`: rebalance calendar

| Column | Type | Description |
|---|---|---|
| `date` | datetime64 | Signal date: stocks are selected with this day's factor values |
| `position_adjust_date` | datetime64 | Effective date: the portfolio is rebalanced to the new weights at the close (usually the next trading day) |

Example: signal on the last trading day of each month, rebalance on the next trading day

```python
days = pd.read_parquet('data/market_data/trading_days.pq')['date']
last_in_month = days.groupby(days.dt.to_period('M')).transform('max') == days
rebalance = pd.DataFrame({'date': days, 'position_adjust_date': days.shift(-1)})[last_in_month]
rebalance.dropna().to_parquet('data/config/rebalance_dates.pq')
```

### `config/factors_dict.xlsx`: factor list

| Column | Description |
|---|---|
| `factor_id` | Integer id (used as the portfolio id in the long-short statistics) |
| `factor_name` | Factor name, matching `factor_data/factors/<factor_name>.pq` |

With `NEUTRAL=True` the file `factors_dict_neutral.xlsx` is read instead (a copy with the same content is enough); the
neutralization step itself always reads `factors_dict.xlsx`. Step ③ **appends one factor-direction column per universe** to this
table (see [Factor direction convention](#factor-direction-convention)).

### `config/portfolio_info.xlsx`: top-N portfolio definitions (used by ⑤⑥)

The sheet must be named `portfolio_info`, one portfolio per row:

| Column | Description |
|---|---|
| `portfolio_id` | Unique integer |
| `portfolio_name` | Portfolio name in the form `factor#any_suffix`; the part before `#` is shown as the factor name in the statistics |
| `portfolio_type` | One of `factor` / `portfolio` / `smart_beta` / `index_enhance`; other types get no NAV |
| `factor_name` | Factor to use |
| `factor_direction` | `1` = pick the N smallest factor values; `-1` = pick the N largest; `0` = skip |
| `stock_area` | Universe name, must be in `settings.UNIVERSES`; within a universe only the first row per factor is used |
| `benchmark`, `barra_adjusted`, `frequency` | Descriptive fields copied into the statistics as is |

With `NEUTRAL=True` the file `portfolio_info_neutral.xlsx` is read instead.

### Optional: database mode

The original framework's database fetching is kept intact (enabled when `stock_prices` / `index_prices` > 0 in a script's
`isupdate_data`). It needs the `QUANT_DB_*` environment variables (see [`common_functions.py`](common_functions.py)) and
`config/index_info.xlsx`. The SQL targets the original company's Wind database schema; it is off by default and not needed offline.

## Settings

All parameters live in [`settings.py`](settings.py):

| Parameter | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `./data` | Data root; override with the `BACKTEST_DATA_DIR` environment variable |
| `START_DATE` / `END_DATE` | `20200930` / `20250630` | Backtest period |
| `SPECIAL_DATE` | `20241231` | Start of `ret_special_date` and `adv_navs_fsd`; must be a trading day inside the period |
| `NEUTRAL` | `False` | Use neutralized factors; when `True`, `main.py` runs ① first and every later input/output gets a `_neutral` suffix |
| `UNIVERSES` | 5 A-share universes | See below |
| `N_GROUPS` | `10` | Number of groups in ③, ids `1000` (smallest factor values) … `1000+N_GROUPS-1` (largest); ④ uses the two ends |
| `INIT_AMOUNT` | `1e7` | Initial capital |
| `FEE_RATE` | `1.5e-3` | One-way fee rate, charged on each stock's traded amount |
| `WEIGHT_CAP` | `0.05` | Per-stock weight cap for `weighting='float_mv'` |
| `DAYS_PER_YEAR` | `242` | Trading days per year for annualization (242 for A-shares; 252 for e.g. US stocks) |
| `INDUSTRY_PREFIX` | `'ind_'` | Prefix of the industry dummy columns |
| `EXCLUDE_ID_SUFFIXES` / `EXCLUDE_ID_PREFIXES` / `EXCLUDE_IDS` | `('.BJ','.NE','.WI')` / `('A',)` / `('000024.SZ',)` | The original framework's cleaning rules for A-share Wind codes. **Set all of them to `()` for non-A-share data**, otherwise e.g. `AAPL` is dropped for its `A` prefix |
| `BARRA_RENAME` | `False` | ⑥ renames portfolios using the mapping in sheet `软约束限BARRA_{barra_sheet}_01` of `portfolio_info` |

Each entry of `UNIVERSES`:

```python
'hs300': {'benchmark': '000300.SH',   # benchmark index code (a column of index_prices.pq)
          'top_n': 100,               # number of holdings in ⑤
          'weighting': 'equal',       # 'equal' = equal weight; 'float_mv' = float-cap weighted with a per-stock cap
          'exclude_new_stock': True,  # drop is_new_stock == 1
          'barra_sheet': '300'},      # only used when BARRA_RENAME=True
```

To add or remove a universe, add or remove its entry and provide a 0/1 column with the same name in `stock_status.pq`. Every step
loops over all universes in `UNIVERSES`.

**Constants kept in the code rather than `settings.py`** (they are part of the calculation logic and left unchanged):

| Where | Constant |
|---|---|
| Engine `calculate_position_core` / `config` | 95% invested at the first build and at every rebalance, 5% kept in cash |
| `ic_tests.py` | Forward-return window: close `t+1` to close `t+21` (`ret_20D`); `Rank_ICIR = mean(IC) / (std(IC)·√252)` |
| `factor_neutralize.py` | MAD winsorization at 3×1.4826×MAD; skipped when a cross-section has fewer than 100 unique values |
| each `statistics_core_1` | Recent 6-month / 3-month / 1-month / 1-week / 3-day / 2-day / 1-day returns start from the 121st / 64th / 22nd / 6th / 4th / 3rd / 2nd NAV from the end (1 year: the `DAYS_PER_YEAR`-th) |
| `positions2nav.py` | The single-factor test always uses 5 groups |

## Inputs and outputs of each step

`{neu}` is `_neutral` when `NEUTRAL=True` and empty otherwise; `{u}` is the universe name; `{f}` is the factor name. All output
directories are created automatically.

### ① `factor_neutralize.py`: factor neutralization

- **Inputs**: `factors_dict.xlsx`, `factors/{f}.pq`, `stock_status.pq` (industry dummies), `barra_factors.pq`
- **Processing** (per trading-day cross-section): MAD winsorization → z-score → fill missing values with the industry median → OLS on industry dummies + size, keep the residual
- **Output**: `factor_data/factors_neutral/{f}.pq` (`date, stock_id, factor_value`)

### ② `ic_tests.py`: Rank IC

- **Inputs**: `factors_dict{neu}.xlsx`, `factors{neu}/{f}.pq`, `stock_market.pq` (`adj_close`), `stock_status.pq` (universe columns)
- **Output**: `results/icir{neu}/icir_stats_{u}.xlsx`
  - `日度Rank_IC` (daily Rank IC): Spearman correlation between factor values and the next 20-day return within the universe, one column per factor
  - `累计Rank_IC` (cumulative Rank IC): running sum of the daily IC
  - `Rank_ICIR`: `mean / (std·√252)`

### ③ `positions2nav_testing.py`: group backtest

- **Inputs**: `factors_dict{neu}.xlsx`, `factors{neu}/{f}.pq`, `stock_market.pq`, `stock_status.pq`, `rebalance_dates.pq`, `trading_days.pq`, `index_prices.pq`
- **Sample**: on the signal date the stock is in the universe, `trade_status == 1`, `is_ST == 0`, not limit-locked, (optionally) not newly listed, and has a factor value
- **Grouping**: on each signal date stocks are sorted by factor value (ties in order of appearance) and split into `N_GROUPS` equal-count groups; equal weights within a group (float-cap weights capped at `WEIGHT_CAP` when `weighting='float_mv'`)
- **Outputs**
  - `g_positions/g_positions_testing{neu}/{u}/g_positions_{f}.pq`: `portfolio_id` (group id), `date` (effective date), `instrument`, `weight`
  - `navs/navs_testing{neu}/{u}/navs_{f}.pq`: `portfolio_id, date, nav, turn_over`
  - `pics/pics{neu}/{u}/navs_{f}.jpg`: NAV chart of every group
  - `factors_dict{neu}.xlsx` gets a column `{u}` with the factor-direction score

#### Factor direction convention

Direction score = Spearman correlation between the group-id rank (1000 → 1) and the Sharpe-ratio rank (highest → 1):

- **score > 0**: **smaller** factor values are better → ④ goes long group 1000 and short the last group; in ⑤ use `factor_direction = 1`
- **score < 0**: **larger** factor values are better → ④ goes long the last group and short group 1000; in ⑤ use `factor_direction = -1`

### ④ `long_short.py`: long-short portfolio

- **Inputs**: `factors_dict{neu}.xlsx` (with the direction columns written by ③), `navs_testing{neu}` from ③, `index_prices.pq`
- **Calculation**: daily return of the long group minus that of the short group, compounded into a long-short NAV
- **Output**: `results/long_short{neu}/long_short_stats_{u}.xlsx`
  - `factor_statistic`: one row per factor; see [Statistics](#statistics) (absolute-return metrics only)
  - `navs`: long-short NAVs; `navs_r3m`: NAVs over the last 90 days, rebased to 1

### ⑤ `positions2nav_update.py`: top-N factor portfolios

- **Inputs**: `portfolio_info{neu}.xlsx`, `factors{neu}/{f}.pq`, `stock_market.pq`, `stock_status.pq`, `rebalance_dates.pq`, `trading_days.pq`, `index_prices.pq`
- **Selection**: same sample as ③; sort by `factor_direction` and take the first `top_n` stocks, equal weighted (or float-cap weighted with the cap)
- **Incremental**: if `g_positions{neu}/g_positions_{u}.pq` already exists, holdings are appended only for signal dates after the last run, then all NAVs are recomputed
- **Outputs**
  - `g_positions/g_positions{neu}/g_positions_{u}.pq`: `portfolio_id, date, instrument, weight`
  - `navs/navs{neu}/navs_{u}.pq`: `portfolio_id, date, nav, turn_over`

  (with `NEUTRAL=False` the directories are `navs/navs/` and `g_positions/g_positions/`, as in the original framework)

### ⑥ `nav2stats.py`: portfolio performance

- **Inputs**: `navs/navs{neu}/navs_{u}.pq` from ⑤, `portfolio_info{neu}.xlsx`, `index_prices.pq`, `trading_days.pq`, `stock_market.pq`
- **Output**: `portfolios/factor_statistic{neu}/factor_statistic_{u}.xlsx`

| Sheet | Contents |
|---|---|
| `factor_statistic` | All metrics |
| `factor_statistic_simple` | Commonly used metrics |
| `navs` | Portfolio NAVs |
| `adv_navs` | Cumulative excess return (%); daily excess return = portfolio return − benchmark return |
| `navs_r3m` / `adv_navs_r3m` | Last 90 days: rebased NAV / excess return (%) |
| `adv_navs_fsd` | Excess return since `SPECIAL_DATE` (%) |

### Statistics

Returns, volatilities and drawdowns are in **%**.

| Metric | Meaning |
|---|---|
| `trading_days` | Number of NAV days |
| `ret_in_period` | Cumulative return over the period |
| `ret_special_date` | Return since `SPECIAL_DATE` |
| `ret_recent1year` … `ret_recent1day` | Return over the last 1 year / 6 months / 3 months / 1 month / 1 week / 3 days / 2 days / 1 day |
| `annualized_ret` | Annualized return `nav^(DAYS_PER_YEAR/days) − 1` |
| `volatility` | Annualized volatility (std of log returns × √DAYS_PER_YEAR) |
| `max_draw_down` | Maximum drawdown |
| `adv_*` | Same as above, on the excess-return NAV |
| `换手率` (turnover) | Annualized turnover: mean daily (buy + sell amount) / portfolio value × DAYS_PER_YEAR |
| `information_ratio` | `annualized_adv_ret / adv_volatility` (in ④: `annualized_ret / volatility`) |
| `return_mdd_ratio` | Annualized (excess) return / maximum drawdown |
| `*_r3month` | Last-3-month excess return, annualized, divided by the **full-period** excess volatility / drawdown |
| `*_recent3month` / `*_recent1month` / `*_recent1week` | Recent excess return, annualized, divided by the excess volatility / drawdown **of the same window** |

## How the backtest engine computes NAV

`Positions2Nav.calculate_position_core` turns each period's target weights into daily position values:

1. Start with `INIT_AMOUNT`; the first build invests 95% and keeps 5% in cash;
2. Rebalancing happens at the close of the effective date, which earns no return; during the holding period each stock compounds daily at `adj_close / adj_pre_close − 1`;
3. At every rebalance, 95% of (position value + cash) is allocated to the new weights; the fee is `FEE_RATE × |traded amount|`, paid from cash; cash earns nothing;
4. NAV = (position value + cash) / `INIT_AMOUNT`; `turn_over` = that day's (buy + sell) amount / portfolio value.

When selecting the top N, factor values get a random perturbation of order 1e-12 to break ties (original framework behavior), so
with many tied factor values, repeated runs can differ very slightly.

## Changes from the original framework

The logic of the calculation functions is unchanged; only inputs and outputs were modified:

| Original framework | Now |
|---|---|
| Data paths came from `USER_DATA_DIR/projects/<dir name>` (split on the Windows `\`, which fails on macOS/Linux) or the hard-coded `/Volumes/GAVIN/...` | One `settings.DATA_DIR` (override with the `BACKTEST_DATA_DIR` environment variable) |
| Dates, universes, benchmarks, holding counts and the neutralization switch were hard-coded in each script's `__main__` | Centralized in `settings.py` |
| File names `CommonFunctions.py`, `IC_tests.py` and `position2nav_testing.py` mixed case styles and singular/plural | Renamed to `common_functions.py`, `ic_tests.py` and `positions2nav_testing.py`: all lowercase, `positions` throughout |
| `tradying_days.pq` under `common/` or `market_data/` | `market_data/trading_days.pq` |
| `datelist.pq` under `config/` or `market_data/` | `config/rebalance_dates.pq` |
| `stock_prices.pq` + `stock_market.pq` + `ashare_deri.pq` with Wind column names | Merged into `stock_market.pq`; free-float market value is the `float_mv` column |
| Factor files had inconsistent columns (5 in ③, renamed by position elsewhere) | Read by name everywhere: `date, stock_id, factor_value` |
| `positions2nav.py` read yearly wide files `factors_<year>0101.pq` | Reads one standard factor file: `python positions2nav.py <factor>` |
| ③ needed `portfolio_info_onetime.xlsx`; every engine also read the unused `factor_info` sheet and `index_info.xlsx` | Group portfolios are generated from `N_GROUPS`; `index_info.xlsx` is read only in database mode |
| The STAR Market (`kc`) universe was derived from codes starting with `688` | Provided as a `kc` column in `stock_status.pq`, like any other universe |
| Industry columns were fixed to 31 CITIC industries with a `zx_` prefix | Any column starting with `INDUSTRY_PREFIX` |
| Code filters (`.BJ` / `.NE` / `.WI` / starts with `A` / `000024.SZ`) were scattered and differed between scripts | `settings.EXCLUDE_*`, applied where the original scripts filtered |
| A STAR-Market-specific patch for `2021-12-30` | Removed: it only applied to the original data, and under pandas 2.x it turned the date column into object dtype and broke the merge |
| ⑤ connected to the database even offline; its STAR Market part pulled prices from the database | Connects only when `old_navs='database'`; everything reads local files by default |
| Factor read failures were skipped silently; output directories had to exist | The skip reason is printed; output directories are created; data is checked before running |
| `pyarrow` / `openpyxl` were not declared; `pandas>=3` | Dependencies added; pandas pinned `<3` (the original `groupby().apply()` calls rely on the grouping column staying in the result, which pandas 3 removed, so `date` would be lost) |

**Equivalence check**: on the demo data, the original scripts (with only paths, dates and offline switches patched) and
this framework were run through every step. All 103 output files / sheets (neutralized factors, IC, group holdings and NAVs,
factor directions, long-short statistics, top-N holdings and NAVs, performance statistics, and `positions2nav.py`) match within 1e-12.

## Show your support

Give a ⭐️ if this project helped you!

***
_This README was generated with ❤️ by [readme-md-generator](https://github.com/kefranabg/readme-md-generator)_
