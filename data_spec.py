# -*- coding: utf-8 -*-
"""
数据规则 (data specification)：所有脚本读写的文件位置与格式都在这里定义。

    python data_spec.py [stage ...]     # 检查 DATA_DIR 下的数据是否符合规则

输入数据（用户准备）
--------------------
所有 .pq 文件均为 parquet；date 列为 datetime64（不带时区），stock_id 列为字符串，
同一 (date, stock_id) 只能出现一次。

config/factors_dict.xlsx        factor_id, factor_name
config/factors_dict_neutral.xlsx  同上，NEUTRAL=True 时使用
config/portfolio_info.xlsx      sheet 'portfolio_info'：portfolio_id, portfolio_name, portfolio_type,
                                factor_name, factor_direction, stock_area, benchmark, barra_adjusted, frequency
config/portfolio_info_neutral.xlsx  同上，NEUTRAL=True 时使用
config/rebalance_dates.pq       date（信号日）, position_adjust_date（新权重生效日）
market_data/trading_days.pq     date
market_data/stock_market.pq     date, stock_id, open, high, low, close, adj_close, adj_pre_close,
                                trade_status [, float_mv]
market_data/stock_status.pq     date, stock_id, is_ST, is_new_stock, <每个股票池一列 0/1>
                                [, <INDUSTRY_PREFIX>* 行业哑变量]
market_data/barra_factors.pq    date, stock_id, size             （仅中性化需要）
market_data/index_prices.pq     宽表：索引为日期 (DatetimeIndex)，每列一个指数代码，值为收盘价
factor_data/factors/<factor_name>.pq   date, stock_id, factor_value

各字段的含义见 README.zh-CN.md「数据规则」一节。
"""
import os
import sys

import pandas as pd

from settings import (DATA_DIR, NEUTRAL, UNIVERSES, INDUSTRY_PREFIX, START_DATE, END_DATE, SPECIAL_DATE,
                      EXCLUDE_ID_SUFFIXES, EXCLUDE_ID_PREFIXES, EXCLUDE_IDS)

NEU = '_neutral' if NEUTRAL else ''

# directories
CONFIG_DIR = os.path.join(DATA_DIR, 'config')
MARKET_DIR = os.path.join(DATA_DIR, 'market_data')
FACTOR_DIR = os.path.join(DATA_DIR, 'factor_data')
LOG_DIR = os.path.join(DATA_DIR, 'logs')

# input files
TRADING_DAYS = os.path.join(MARKET_DIR, 'trading_days.pq')
STOCK_MARKET = os.path.join(MARKET_DIR, 'stock_market.pq')
STOCK_STATUS = os.path.join(MARKET_DIR, 'stock_status.pq')
BARRA_FACTORS = os.path.join(MARKET_DIR, 'barra_factors.pq')
INDEX_PRICES = os.path.join(MARKET_DIR, 'index_prices.pq')
REBALANCE_DATES = os.path.join(CONFIG_DIR, 'rebalance_dates.pq')

# required columns of each long-format parquet input
COLUMNS = {
    TRADING_DAYS: ['date'],
    REBALANCE_DATES: ['date', 'position_adjust_date'],
    STOCK_MARKET: ['date', 'stock_id', 'open', 'high', 'low', 'close', 'adj_close', 'adj_pre_close', 'trade_status'],
    STOCK_STATUS: ['date', 'stock_id', 'is_ST', 'is_new_stock'] + list(UNIVERSES),
    BARRA_FACTORS: ['date', 'stock_id', 'size'],
}
FACTOR_COLUMNS = ['date', 'stock_id', 'factor_value']
FACTORS_DICT_COLUMNS = ['factor_id', 'factor_name']
PORTFOLIO_INFO_COLUMNS = ['portfolio_id', 'portfolio_name', 'portfolio_type', 'factor_name', 'factor_direction',
                          'stock_area', 'benchmark', 'barra_adjusted', 'frequency']

STAGES = ['neutralize', 'ic', 'testing', 'long_short', 'update', 'stats']


def factors_dict_path(neu=NEU):
    return os.path.join(CONFIG_DIR, f'factors_dict{neu}.xlsx')


def portfolio_info_path(neu=NEU):
    return os.path.join(CONFIG_DIR, f'portfolio_info{neu}.xlsx')


def factor_path(factor_name, neu=NEU):
    return os.path.join(FACTOR_DIR, f'factors{neu}', f'{factor_name}.pq')


def ensure_parent(path):
    """Create the parent directory of an output file and return the path unchanged."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def drop_excluded_stocks(df):
    """Remove rows whose stock_id matches the EXCLUDE_* rules in settings.py."""
    ids = df['stock_id'].astype(str)
    excluded = ids.isin(EXCLUDE_IDS)
    if EXCLUDE_ID_SUFFIXES:
        excluded |= ids.str.endswith(tuple(EXCLUDE_ID_SUFFIXES))
    if EXCLUDE_ID_PREFIXES:
        excluded |= ids.str.startswith(tuple(EXCLUDE_ID_PREFIXES))
    return df[~excluded]


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def _rel(path):
    return os.path.relpath(path, DATA_DIR)


def _check_parquet(path, columns, errors):
    import pyarrow as pa
    import pyarrow.parquet as pq
    if not os.path.exists(path):
        errors.append(f'缺少文件 {_rel(path)}')
        return
    schema = pq.read_schema(path)
    missing = [c for c in columns if c not in schema.names]
    if missing:
        errors.append(f'{_rel(path)} 缺少列 {missing}')
    for c in ('date', 'position_adjust_date'):
        if c in schema.names and not pa.types.is_timestamp(schema.field(c).type):
            errors.append(f'{_rel(path)} 的 {c} 列必须是 datetime64，实际为 {schema.field(c).type}')
    if 'stock_id' in schema.names:
        t = schema.field('stock_id').type
        if not (pa.types.is_string(t) or pa.types.is_large_string(t)):
            errors.append(f'{_rel(path)} 的 stock_id 列必须是字符串，实际为 {t}')


def _check_excel(path, columns, errors, sheet_name=0):
    if not os.path.exists(path):
        errors.append(f'缺少文件 {_rel(path)}')
        return None
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
    except ValueError as e:
        errors.append(f'{_rel(path)}: {e}')
        return None
    missing = [c for c in columns if c not in df.columns]
    if missing:
        errors.append(f'{_rel(path)} 缺少列 {missing}')
        return None
    return df


def validate(stages=STAGES):
    """Check the files the given pipeline stages read. Returns a list of problems (empty = OK)."""
    stages = set(stages)
    errors = []
    uses = lambda *names: bool(stages & set(names))

    if uses('ic', 'testing', 'update', 'stats'):
        columns = COLUMNS[STOCK_MARKET]
        if uses('testing', 'update') and any(u['weighting'] == 'float_mv' for u in UNIVERSES.values()):
            columns = columns + ['float_mv']
        _check_parquet(STOCK_MARKET, columns, errors)
    if uses('neutralize', 'ic', 'testing', 'update'):
        _check_parquet(STOCK_STATUS, COLUMNS[STOCK_STATUS], errors)
    if uses('testing', 'update', 'stats'):
        _check_parquet(TRADING_DAYS, COLUMNS[TRADING_DAYS], errors)
    if uses('testing', 'update'):
        _check_parquet(REBALANCE_DATES, COLUMNS[REBALANCE_DATES], errors)

    if uses('neutralize'):
        _check_parquet(BARRA_FACTORS, COLUMNS[BARRA_FACTORS], errors)
        if os.path.exists(STOCK_STATUS):
            import pyarrow.parquet as pq
            if not any(c.startswith(INDUSTRY_PREFIX) for c in pq.read_schema(STOCK_STATUS).names):
                errors.append(f'{_rel(STOCK_STATUS)} 没有以 {INDUSTRY_PREFIX!r} 开头的行业哑变量列（中性化需要）')

    # factor list and factor files
    lists = []
    if uses('neutralize'):
        lists.append('')                       # neutralize reads the raw list and raw factor files
    if uses('ic', 'testing', 'long_short', 'update'):
        lists.append(NEU)
    for neu in dict.fromkeys(lists):
        factors_dict = _check_excel(factors_dict_path(neu), FACTORS_DICT_COLUMNS, errors)
        # neutral factor files are produced by the neutralize stage itself
        if factors_dict is not None and not (neu == '_neutral' and uses('neutralize')):
            for name in factors_dict['factor_name']:
                _check_parquet(factor_path(name, neu), FACTOR_COLUMNS, errors)

    if uses('update', 'stats'):
        portfolio_info = _check_excel(portfolio_info_path(), PORTFOLIO_INFO_COLUMNS, errors,
                                      sheet_name='portfolio_info')
        if portfolio_info is not None:
            unknown = set(portfolio_info['stock_area']) - set(UNIVERSES)
            if unknown:
                errors.append(f'{_rel(portfolio_info_path())} 的 stock_area {sorted(unknown)} 不在 settings.UNIVERSES 中')

    if uses('testing', 'long_short', 'update', 'stats'):
        if not os.path.exists(INDEX_PRICES):
            errors.append(f'缺少文件 {_rel(INDEX_PRICES)}')
        else:
            index_prices = pd.read_parquet(INDEX_PRICES)
            if not isinstance(index_prices.index, pd.DatetimeIndex):
                errors.append(f'{_rel(INDEX_PRICES)} 的索引必须是日期 (DatetimeIndex)')
            missing = sorted({u['benchmark'] for u in UNIVERSES.values()} - set(index_prices.columns))
            if missing:
                errors.append(f'{_rel(INDEX_PRICES)} 缺少基准指数列 {missing}')

    if uses('long_short', 'stats') and os.path.exists(TRADING_DAYS):
        days = pd.read_parquet(TRADING_DAYS)['date']
        special = pd.to_datetime(SPECIAL_DATE)
        if special not in set(days) or not (pd.to_datetime(START_DATE) <= special <= pd.to_datetime(END_DATE)):
            errors.append(f'settings.SPECIAL_DATE={SPECIAL_DATE} 必须是 START_DATE 与 END_DATE 之间的交易日')

    return errors


if __name__ == '__main__':
    stages = sys.argv[1:] or STAGES
    problems = validate(stages)
    print(f'DATA_DIR = {DATA_DIR}')
    if problems:
        print('数据不符合规则：')
        for p in problems:
            print('  - ' + p)
        sys.exit(1)
    print('数据检查通过：' + ', '.join(stages))
