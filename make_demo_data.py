# -*- coding: utf-8 -*-
"""
生成一套符合 data_spec.py 规则的模拟数据，用来试跑整个框架，也可作为自备数据的格式样例。

    python make_demo_data.py        # 写入 settings.DATA_DIR（默认 ./data），已有同名文件会被覆盖

数据由随机模型生成，不代表任何真实市场。股票池、基准指数、回测区间取自 settings.py。
"""
import numpy as np
import pandas as pd

from settings import START_DATE, END_DATE, UNIVERSES, INDUSTRY_PREFIX, DATA_DIR
from data_spec import (TRADING_DAYS, STOCK_MARKET, STOCK_STATUS, BARRA_FACTORS, INDEX_PRICES, REBALANCE_DATES,
                       factors_dict_path, portfolio_info_path, factor_path, ensure_parent)

N_STOCKS = 800
N_KC = 120                      # the last N_KC stocks get STAR-market style 688xxx.SH codes
INDUSTRIES = ['petro', 'coal', 'metals', 'power', 'steel', 'chemicals', 'construct_eng', 'construct_mat',
              'light_man', 'machinery', 'electr_equip', 'defense', 'automobiles', 'retail', 'hotels_lei',
              'household_dur', 'textile', 'medical', 'food_bev', 'agriculture', 'banks', 'real_estate',
              'transportation', 'electronic_comp', 'communication', 'computers', 'media', 'compre',
              'securites', 'insurance', 'diversified_fin']
FACTORS = ['alpha_signal', 'momentum_20d']

rng = np.random.default_rng(42)

# ---------------------------------------------------------------- calendar and stocks
# extra history before START_DATE for look-back factors, extra days after END_DATE for IC forward returns
days = pd.bdate_range(pd.to_datetime(START_DATE) - pd.offsets.BDay(60), pd.to_datetime(END_DATE) + pd.offsets.BDay(30))
T, N = len(days), N_STOCKS
codes = [f'{600000 + i:06d}.SH' if i % 2 == 0 else f'{i:06d}.SZ' for i in range(N - N_KC)] + \
        [f'{688001 + i:06d}.SH' for i in range(N_KC)]

# listing: most stocks exist for the whole sample, 40 list during it (is_new_stock = 1 for 120 days)
list_day = np.zeros(N, dtype=int)
late = rng.choice(N, 40, replace=False)
list_day[late] = rng.integers(60, int(T * 0.6), 40)
listed = np.arange(T)[:, None] >= list_day[None, :]
is_new = listed & (np.arange(T)[:, None] < list_day[None, :] + 120) & (list_day[None, :] > 0)

# ST: 15 stocks flagged for a 150-day window
is_st = np.zeros((T, N), dtype=bool)
for i in rng.choice(N, 15, replace=False):
    s = rng.integers(0, T - 150)
    is_st[s:s + 150, i] = True

industry = rng.integers(0, len(INDUSTRIES), N)

# ---------------------------------------------------------------- returns and prices
market = rng.normal(0.0003, 0.011, T)
beta = rng.uniform(0.7, 1.3, N)
ind_ret = rng.normal(0, 0.006, (T, len(INDUSTRIES)))[:, industry]
alpha = np.zeros((T, N))                      # persistent stock-specific drift, observed noisily by 'alpha_signal'
alpha[0] = rng.normal(0, 0.0005, N)
for t in range(1, T):
    alpha[t] = 0.97 * alpha[t - 1] + rng.normal(0, 0.0005 * np.sqrt(1 - 0.97 ** 2), N)
rets = market[:, None] * beta[None, :] + ind_ret + alpha + rng.normal(0, 0.018, (T, N))
rets = np.clip(rets, -0.1, 0.1)

suspended = rng.random((T, N)) < 0.003
rets[suspended] = 0.0
close = rng.uniform(5, 50, N)[None, :] * np.cumprod(1 + rets, axis=0)
pre_close = close / (1 + rets)
open_ = pre_close * (1 + rng.normal(0, 0.005, (T, N)))
high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, (T, N))))
low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, (T, N))))
one_price = rng.random((T, N)) < 0.002         # limit-up/down style bars: open == high == low == close
for arr in (open_, high, low):
    arr[one_price] = close[one_price]

float_shares = np.exp(rng.normal(np.log(3e9) - 2.5 * np.arange(N) / N, 0.3))   # earlier stocks are larger
float_mv = close * float_shares[None, :]


def to_long(**cols):
    """T x N matrices -> long table keyed by (date, stock_id), keeping listed stocks only."""
    t_idx, n_idx = np.nonzero(listed)
    df = pd.DataFrame({'date': days[t_idx], 'stock_id': np.array(codes)[n_idx]})
    for name, mat in cols.items():
        df[name] = mat[t_idx, n_idx]
    return df


# ---------------------------------------------------------------- market_data/
pd.DataFrame({'date': days}).to_parquet(ensure_parent(TRADING_DAYS))

stock_market = to_long(open=open_, high=high, low=low, close=close, adj_close=close, adj_pre_close=pre_close,
                       trade_status=(~suspended).astype(int), float_mv=float_mv)
stock_market.to_parquet(ensure_parent(STOCK_MARKET))

members = {'hs300': np.arange(N) < 150,
           'zz500': (np.arange(N) >= 150) & (np.arange(N) < 400),
           'zz1000': np.arange(N) >= 400,
           'winda': np.ones(N, dtype=bool),
           'kc': np.arange(N) >= N - N_KC}
status_cols = {'is_ST': is_st.astype(int), 'is_new_stock': is_new.astype(int)}
for u in UNIVERSES:
    flag = members[u] if u in members else rng.random(N) < 0.4
    status_cols[u] = np.broadcast_to(flag, (T, N)).astype(int)
for k, name in enumerate(INDUSTRIES):
    status_cols[INDUSTRY_PREFIX + name] = np.broadcast_to(industry == k, (T, N)).astype(int)
to_long(**status_cols).to_parquet(ensure_parent(STOCK_STATUS))

to_long(size=np.log(float_mv)).to_parquet(ensure_parent(BARRA_FACTORS))

# benchmark indexes: float_mv-weighted return of the first universe using each code
index_prices = pd.DataFrame(index=pd.DatetimeIndex(days, name='date'))
weights = np.vstack([float_mv[:1], float_mv[:-1]]) * listed
for u, params in UNIVERSES.items():
    if params['benchmark'] in index_prices:
        continue
    w = weights * (members[u] if u in members else 1)
    index_ret = (w * rets).sum(axis=1) / w.sum(axis=1)
    index_prices[params['benchmark']] = 1000 * np.cumprod(1 + index_ret)
index_prices.to_parquet(ensure_parent(INDEX_PRICES))

# ---------------------------------------------------------------- factor_data/factors/
momentum = pd.DataFrame(close).pct_change(20).values
for name, values in {'alpha_signal': alpha + rng.normal(0, 0.0005, (T, N)), 'momentum_20d': momentum}.items():
    factor = to_long(factor_value=values).dropna(subset=['factor_value'])
    factor.to_parquet(ensure_parent(factor_path(name, '')))

# ---------------------------------------------------------------- config/
# signal on the last trading day of each month, new weights effective on the next trading day
calendar = pd.Series(days)
month_end = calendar.groupby(calendar.dt.to_period('M')).transform('max') == calendar
rebalance = pd.DataFrame({'date': calendar, 'position_adjust_date': calendar.shift(-1)})[month_end.values]
rebalance = rebalance[(rebalance['date'] >= pd.to_datetime(START_DATE)) & (rebalance['date'] <= pd.to_datetime(END_DATE))]
rebalance.reset_index(drop=True).to_parquet(ensure_parent(REBALANCE_DATES))

factors_dict = pd.DataFrame({'factor_id': range(1, len(FACTORS) + 1), 'factor_name': FACTORS})
rows = []
for u, params in UNIVERSES.items():
    for f in FACTORS:
        rows.append({'portfolio_id': len(rows) + 1, 'portfolio_name': f'{f}#{u}_top{params["top_n"]}',
                     'portfolio_type': 'factor', 'factor_name': f,
                     'factor_direction': -1,            # -1: larger factor values are better (see README)
                     'stock_area': u, 'benchmark': params['benchmark'], 'barra_adjusted': 0, 'frequency': 'month'})
portfolio_info = pd.DataFrame(rows)
for neu in ('', '_neutral'):
    factors_dict.to_excel(ensure_parent(factors_dict_path(neu)), index=False)
    portfolio_info.to_excel(ensure_parent(portfolio_info_path(neu)), sheet_name='portfolio_info', index=False)

print(f'demo data written to {DATA_DIR}: {N} stocks, {T} trading days, {len(rebalance)} rebalances, factors {FACTORS}')
