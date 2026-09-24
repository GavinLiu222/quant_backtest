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

import pandas as pd
from scipy.stats import spearmanr

import os, sys, inspect
import logging

from common_functions import conn2db
from settings import START_DATE, END_DATE, UNIVERSES
from data_spec import NEU, DATA_DIR, STOCK_MARKET, STOCK_STATUS, factors_dict_path, factor_path, ensure_parent

import pdb

import warnings
warnings.filterwarnings('ignore')


if __name__=='__main__':

    # neutral / raw factors, dates and universes are set in settings.py
    neu = NEU
    datadir = DATA_DIR

    start_date = START_DATE
    end_date = END_DATE

    factors_dict = pd.read_excel(factors_dict_path(), index_col=None)

    stock_market = pd.read_parquet(STOCK_MARKET)
    stock_status = pd.read_parquet(STOCK_STATUS)
    stock_market = stock_market[stock_market['date'] >= pd.to_datetime(start_date)][['date', 'stock_id', 'adj_close']]
    stock_status = stock_status[stock_status['date'] >= pd.to_datetime(start_date)][['date', 'stock_id'] + list(UNIVERSES)]

    stock_market = stock_market.merge(stock_status, on=['date', 'stock_id'], how='inner')
    stock_market = stock_market.sort_values(['date', 'stock_id']).reset_index(drop=True)

    stock_market['adj_close_1D'] = stock_market.groupby('stock_id')['adj_close'].shift(-1)
    stock_market['adj_close_21D'] = stock_market.groupby('stock_id')['adj_close'].shift(-21)
    stock_market['ret_20D'] = stock_market['adj_close_21D'] / stock_market['adj_close_1D'] - 1

    stock_market = stock_market[stock_market['date'] <= pd.to_datetime(end_date)]
    stock_market = stock_market.dropna(subset='ret_20D')

    for sample_symbol in UNIVERSES:

        ic_df_combined = pd.DataFrame()
        for factor_name in factors_dict['factor_name'].unique():
            factors = pd.read_parquet(factor_path(factor_name))[['date', 'stock_id', 'factor_value']]
            factors = factors[factors['date'] >= pd.to_datetime(start_date)]
            factors = factors.merge(stock_market, on=['date', 'stock_id'], how='inner')
            factors_subset = factors[['date', 'stock_id', 'factor_value', 'ret_20D', sample_symbol]]
            factors_subset = factors_subset[factors_subset[sample_symbol] == 1]
            ic_df = factors_subset.groupby('date').apply(
                lambda x: spearmanr(x['factor_value'], x['ret_20D'])[0]
            ).reset_index()
            ic_df.columns=['date', f'RankIC_{factor_name}']
            if len(ic_df_combined) == 0:
                ic_df_combined = ic_df
            else:
                ic_df_combined = ic_df_combined.merge(ic_df, on=['date'], how='left')

        ic_df_combined_cumsum = ic_df_combined.copy()

        for col in ic_df_combined_cumsum.columns[1:]:
            ic_df_combined_cumsum[col] = ic_df_combined_cumsum[col].cumsum()

        icir = pd.DataFrame(columns=ic_df_combined_cumsum.columns[1:], index=['Rank_ICIR'])

        for col in icir.columns:

            icir.loc['Rank_ICIR', col] = ic_df_combined[col].mean() / (ic_df_combined[col].std() * np.sqrt(252))

        with pd.ExcelWriter(ensure_parent(datadir + f'/results/icir{neu}/icir_stats_{sample_symbol}.xlsx')) as writer:
            ic_df_combined_cumsum.to_excel(writer, sheet_name='累计Rank_IC', index=False)
            icir.to_excel(writer, sheet_name='Rank_ICIR', index=False)
            ic_df_combined.to_excel(writer, sheet_name='日度Rank_IC', index=False)



















