# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import datetime

import matplotlib.pyplot as plt
from pylab import mpl
mpl.rcParams['font.sans-serif'] = ['SimHei']   # 设置字体为黑体
mpl.rcParams['axes.unicode_minus'] = False     # 解决中文字体负号显示不正常问题
# plt config
plt.rcParams['figure.figsize'] = (30,16)
plt.rcParams['axes.titlesize'] = 36
plt.rcParams['axes.titleweight'] = 3

from common_functions import conn2db
from settings import SPECIAL_DATE, UNIVERSES, N_GROUPS, DAYS_PER_YEAR
from data_spec import NEU, DATA_DIR, INDEX_PRICES, factors_dict_path, ensure_parent

import os, sys, inspect
import logging

import pdb

import warnings
warnings.filterwarnings('ignore')


def statistics_core_1(navs, special_date):
    '''This function makes statistics from navs_comb.'''

    number_days = (~navs.isna()).sum()
    factor_statistic = pd.DataFrame()
    factor_statistic['portfolio_id'] = navs.columns
    factor_statistic['trading_days'] = navs.shape[0]
    factor_statistic['ret_in_period'] = (navs.iloc[-1, :] - 1).values * 100
    idx_spc = navs.index.tolist().index(pd.to_datetime(special_date))

    factor_statistic['ret_special_date'] = (navs.iloc[-1, :] / navs.iloc[idx_spc, :] - 1).values * 100
    navs = navs.dropna(axis=1, how='all')
    if navs.shape[0] > DAYS_PER_YEAR:
        factor_statistic['ret_recent1year'] = (navs.iloc[-1, :] / navs.iloc[-DAYS_PER_YEAR, :] - 1).values * 100
    else:
        factor_statistic['ret_recent1year'] = np.nan
    if navs.shape[0] > 121:
        factor_statistic['ret_recent6month'] = (navs.iloc[-1, :] / navs.iloc[-121, :] - 1).values * 100
    else:
        factor_statistic['ret_recent6month'] = np.nan
    if navs.shape[0] > 64:
        factor_statistic['ret_recent3month'] = (navs.iloc[-1, :] / navs.iloc[-64, :] - 1).values * 100
    else:
        factor_statistic['ret_recent3month'] = np.nan
    factor_statistic['ret_recent1month'] = (navs.iloc[-1, :] / navs.iloc[-22, :] - 1).values * 100
    factor_statistic['ret_recent1week'] = (navs.iloc[-1, :] / navs.iloc[-6, :] - 1).values * 100
    factor_statistic['ret_recent3day'] = (navs.iloc[-1, :] / navs.iloc[-4, :] - 1).values * 100
    factor_statistic['ret_recent2day'] = (navs.iloc[-1, :] / navs.iloc[-3, :] - 1).values * 100
    factor_statistic['ret_recent1day'] = (navs.iloc[-1, :] / navs.iloc[-2, :] - 1).values * 100
    factor_statistic['annualized_ret'] = (navs.iloc[-1, :] ** (DAYS_PER_YEAR / number_days) - 1).values * 100
    factor_statistic['volatility'] = (np.log(navs).diff().std() * np.sqrt(DAYS_PER_YEAR)).values * 100
    factor_statistic['max_draw_down'] = (1 - (navs / navs.cummax()).min()).values * 100
    # information ratio
    factor_statistic['information_ratio'] = factor_statistic['annualized_ret'] / factor_statistic[
        'volatility']
    factor_statistic['return_mdd_ratio'] = factor_statistic['annualized_ret'] / factor_statistic[
        'max_draw_down']

    # reformate
    factor_statistic = factor_statistic.sort_values(by=['information_ratio'],
                                                    ascending=False).reset_index(drop=True)

    return factor_statistic


def daily_update_statistics(neu, navs, benchmark_code, index_prices, special_date, factors_dict_copy, sample_symbol):
    '''This function makes statistics from navs.'''

    navs.sort_values(by=['portfolio_id', 'date'], inplace=True)
    navs = navs.reset_index(drop=True)

    navs_all = navs.pivot(columns='portfolio_id', index='date', values='nav')

    # statistic
    factor_statistic = statistics_core_1(navs_all, special_date)
    factor_statistic = factor_statistic.merge(factors_dict_copy[['factor_id', 'factor_name']].rename(columns={'factor_id': 'portfolio_id'}), on=['portfolio_id'], how='left')
    factor_statistic['benchmark'] = sample_symbol
    factor_statistic['portfolio_name'] = factor_statistic['factor_name'] + '#' + factor_statistic['benchmark']

    tcols = ['factor_name', 'portfolio_name', 'benchmark', 'portfolio_id',
             'trading_days', 'ret_in_period', 'ret_special_date',
             'ret_recent1year', 'ret_recent6month', 'ret_recent3month', 'ret_recent1month', 'ret_recent1week',
             'ret_recent3day', 'ret_recent2day', 'ret_recent1day', 'annualized_ret', 'volatility', 'max_draw_down',
             'information_ratio', 'return_mdd_ratio']
    factor_statistic = factor_statistic[tcols]

    # navs_all
    navs_all = navs_all[factor_statistic['portfolio_id']]
    navs_all.columns = factor_statistic['portfolio_name']

    # save to excel files
    save_name = 'long_short_stats_' + sample_symbol
    with pd.ExcelWriter(ensure_parent(datadir + f'/results/long_short{neu}' + '/%s.xlsx' % save_name)) as writer:
        factor_statistic.set_index('portfolio_name').to_excel(writer, sheet_name='factor_statistic', index=True)

        navs_all.to_excel(writer, sheet_name='navs', index=True)

        # performance during recent 3 months
        navs_r3m = navs_all[navs_all.index >= (navs_all.index[-1] - datetime.timedelta(days=90))]
        navs_r3m = navs_r3m.div(navs_r3m.iloc[0, :].values, axis=1)
        navs_r3m.to_excel(writer, sheet_name='navs_r3m', index=True)

    return 0


if __name__=='__main__':

    # neutral / raw factors and universes are set in settings.py
    neu = NEU
    datadir = DATA_DIR

    factors_dict = pd.read_excel(factors_dict_path(), index_col=None)
    index_prices = pd.read_parquet(INDEX_PRICES)

    # lowest / highest factor-value groups written by group_backtest.py
    bottom_group, top_group = 1000, 1000 + N_GROUPS - 1

    def main(sample_symbol, benchmark_code, index_prices, special_date):

        factors_dict_copy = factors_dict[['factor_id', 'factor_name', sample_symbol]]
        navs_combined = pd.DataFrame()

        for factor_name in factors_dict_copy['factor_name']:

            factor_id = factors_dict_copy.loc[factors_dict_copy['factor_name'] == factor_name, 'factor_id'].values[0]
            corr = factors_dict_copy.loc[factors_dict_copy['factor_name'] == factor_name, sample_symbol].values[0]

            nav_file = datadir + f'/navs/navs_testing{neu}/{sample_symbol}/navs_{factor_name}.pq'
            if not os.path.exists(nav_file):
                print(f'{sample_symbol}/{factor_name}: {nav_file} not found, run group_backtest.py first; skipped')
                continue
            navs = pd.read_parquet(nav_file)

            if corr>0:
                navs_long = navs[navs['portfolio_id'] == bottom_group]
                navs_short = navs[navs['portfolio_id'] == top_group]
            else:
                navs_long = navs[navs['portfolio_id'] == top_group]
                navs_short = navs[navs['portfolio_id'] == bottom_group]

            navs_long = navs_long[['date', 'nav']].rename(columns={'nav': 'nav_long'})
            navs_long['ret_long'] = navs_long['nav_long'] / navs_long['nav_long'].shift(1) - 1
            navs_long['ret_long'] = navs_long['ret_long'].fillna(0)

            navs_short = navs_short[['date', 'nav']].rename(columns={'nav': 'nav_short'})
            navs_short['ret_short'] = navs_short['nav_short'] / navs_short['nav_short'].shift(1) - 1
            navs_short['ret_short'] = navs_short['ret_short'].fillna(0)

            navs_long_short = pd.merge(navs_long[['date', 'ret_long']], navs_short[['date', 'ret_short']], on=['date'], how='inner')
            navs_long_short['ret_long_short'] = navs_long_short['ret_long'] - navs_long_short['ret_short']
            navs_long_short['nav_long_short'] = (1 + navs_long_short['ret_long_short']).cumprod()
            navs_long_short['portfolio_id'] = factor_id
            navs_long_short = navs_long_short[['portfolio_id', 'date', 'nav_long_short']].rename(columns={'nav_long_short': 'nav'})
            navs_combined = pd.concat([navs_combined, navs_long_short], axis=0).reset_index(drop=True)

        if navs_combined.empty:
            return 0
        daily_update_statistics(neu, navs_combined, benchmark_code, index_prices, special_date, factors_dict_copy, sample_symbol)

        return 0


    for universe, params in UNIVERSES.items():
        main(universe, params['benchmark'], index_prices, SPECIAL_DATE)













