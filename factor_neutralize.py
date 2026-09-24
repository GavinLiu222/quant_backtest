# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import datetime

import statsmodels.api as sm

import matplotlib.pyplot as plt
from pylab import mpl
mpl.rcParams['font.sans-serif'] = ['SimHei']   # 设置字体为黑体
mpl.rcParams['axes.unicode_minus'] = False     # 解决中文字体负号显示不正常问题
# plt config
plt.rcParams['figure.figsize'] = (30,16)
plt.rcParams['axes.titlesize'] = 36
plt.rcParams['axes.titleweight'] = 3

# Connections are created lazily where needed (and only when isupdate>0).
# Export the QUANT_DB_* env vars to enable online fetching.
# wind_conn = conn2db('wind_conn')
# factors_conn = conn2db('factors_conn')
# market_conn = conn2db('market_conn')

import os, sys, inspect
import logging


# from scipy.optimize import minimize, Bounds
# cvxopt was imported here but never used in this module; it is left out so the
# framework runs without a solver stack. Re-add it if an optimiser is added.

from common_functions import conn2db
from settings import INDUSTRY_PREFIX
from data_spec import (STOCK_STATUS, BARRA_FACTORS, factors_dict_path, factor_path, ensure_parent,
                       drop_excluded_stocks)

import multiprocessing as mp
cpu_num = 10
from functools import partial
import pdb

import warnings
warnings.filterwarnings('ignore')

def cross_sectional_z_score(group):
    mean = group['factor_value'].mean()
    std = group['factor_value'].std()
    if std == 0:
        std = 1e-12
    group['factor_value'] = (group['factor_value'] - mean) / std
    return group

def fill_nan_with_industry_mean(group):
    for industry in [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)]:         # stock_status.columns[2:]
        industry_group = group[group[industry] == 1]
        industry_mean = industry_group['factor_value'].mean()
        group.loc[industry_group.index, 'factor_value'] = group.loc[industry_group.index, 'factor_value'].fillna(industry_mean)
    return group

def fill_nan_with_industry_median(group):
    for industry in [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)]:         # stock_status.columns[2:]
        industry_group = group[group[industry] == 1]
        industry_mean = industry_group['factor_value'].median()
        group.loc[industry_group.index, 'factor_value'] = group.loc[industry_group.index, 'factor_value'].fillna(industry_mean)
    return group

def truncate_mad(group):
    if len(group['factor_value'].unique()) < 100:
        return group

    md = group['factor_value'].median()
    diff = group['factor_value'] - md
    md_diff = diff.abs().median() * 1.4826

    upper_bound = md + 3 * md_diff
    lower_bound = md - 3 * md_diff
    group['factor_value'] = group['factor_value'].apply(lambda x: min(max(x, lower_bound), upper_bound))

    return group

def truncate_zscore(group):
    mean = group['factor_value'].mean()
    std = group['factor_value'].std()

    upper_bound = mean + 3 * std
    lower_bound = mean - 3 * std
    group['factor_value'] = group['factor_value'].apply(lambda x: min(max(x, lower_bound), upper_bound))

    return group

def truncate_quantile(group):
    lower_bound = group['factor_value'].quantile(0.025)
    upper_bound = group['factor_value'].quantile(0.975)

    group['factor_value'] = group['factor_value'].apply(lambda x: min(max(x, lower_bound), upper_bound))

    return group

def neutralize_size_industry(group):

    for industry in [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)]:         # stock_status.columns[2:]
        industry_group = group[group[industry] == 1]
        industry_mean = industry_group['size'].mean()
        group.loc[industry_group.index, 'size'] = group.loc[industry_group.index, 'size'].fillna(industry_mean)
        group_copy = group.copy()
    try:
        group = group.dropna()    #4728031

        predictors = [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)] + ['size']

        X = group[predictors]
        X = sm.add_constant(X)

        y = group['factor_value']

        model = sm.OLS(y, X).fit()
        group['factor_value'] = model.resid
    except:

        print("中性化出错 in ", group_copy['date'].unique()[0])
        return group_copy

    return group

def neutralize_industry(group):

    for industry in [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)]:         # stock_status.columns[2:]
        industry_group = group[group[industry] == 1]
        industry_mean = industry_group['size'].mean()
        group.loc[industry_group.index, 'size'] = group.loc[industry_group.index, 'size'].fillna(industry_mean)
    pdb.set_trace()
    group = group.dropna()    #4728031

    predictors = [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)]

    X = group[predictors]
    X = sm.add_constant(X)

    y = group['factor_value']

    model = sm.OLS(y, X).fit()
    group['factor_value'] = model.resid

    return group


def neutralize_size(group):
    for industry in [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)]:         # stock_status.columns[2:]
        industry_group = group[group[industry] == 1]
        industry_mean = industry_group['size'].mean()
        group.loc[industry_group.index, 'size'] = group.loc[industry_group.index, 'size'].fillna(industry_mean)

    group = group.dropna()    #4728031

    predictors = ['size']

    X = group[predictors]
    X = sm.add_constant(X)

    y = group['factor_value']

    model = sm.OLS(y, X).fit()
    group['factor_value'] = model.resid

    return group

def neutralize_size_industry_layer(group):
    # Identify all industry columns
    industry_columns = [col for col in group.columns if col.startswith(INDUSTRY_PREFIX)]

    for industry in industry_columns:
        industry_group = group[group[industry] == 1]
        industry_mean = industry_group['factor_value'].mean()
        industry_group.loc[industry_group.index, 'factor_value'] = industry_group.loc[industry_group.index, 'factor_value'].fillna(industry_mean)
        industry_group = industry_group.dropna(subset=['size'])

        if not industry_group.empty:
            X = industry_group[['size']]
            X = sm.add_constant(X)  # Add intercept
            y = industry_group['factor_value']

            # Perform OLS regression if there are enough valid rows
            if len(y) > 1:
                model = sm.OLS(y, X).fit()

                group.loc[industry_group.index, 'factor_value'] = model.resid

    return group


def Method1(factors, factor_name):

    # MAD法处理异常值
    factors = factors.groupby(['date']).apply(truncate_mad)
    factors = factors.reset_index(drop=True)
    print('MAD finish')

    # z-score标准化
    factors = factors.groupby(['date']).apply(cross_sectional_z_score)
    factors = factors.reset_index(drop=True)
    print('z-score finish')

    # 行业中位数填充
    factors = factors.groupby(['date']).apply(fill_nan_with_industry_median)
    factors = factors.reset_index(drop=True)
    print('fillna finish')

    # 行业市值中性化
    factors = factors.groupby(['date']).apply(neutralize_size_industry)
    factors = factors.reset_index(drop=True)
    print('neutralize finish')

    return factors



if __name__ == '__main__':

    # Always reads the raw factors listed in config/factors_dict.xlsx and writes
    # factor_data/factors_neutral/, independent of settings.NEUTRAL.
    stock_status = pd.read_parquet(STOCK_STATUS)
    stock_status = stock_status[['date', 'stock_id'] + [col for col in stock_status.columns if col.startswith(INDUSTRY_PREFIX)]]
    barra_factors = pd.read_parquet(BARRA_FACTORS)

    factor_info = pd.read_excel(factors_dict_path(''))

    for factor_name in factor_info['factor_name']: #factor_info['factor_name']

        print(f'{factor_name} begin!')
        try:
            factors = pd.read_parquet(factor_path(factor_name, ''))
            factors = factors[['date', 'stock_id', 'factor_value']]

            factors['date'] = pd.to_datetime(factors['date'])
            #factors = factors[factors['date'] >= '2020-12-01']
            factors = drop_excluded_stocks(factors)
            factors = factors.sort_values(by=['date', 'stock_id']).reset_index(drop=True)
            factors = factors.merge(stock_status, on=['date', 'stock_id'], how='inner')
            factors = factors.merge(barra_factors[['date', 'stock_id', 'size']], on=['date', 'stock_id'], how='inner')

            factors_neutralize = Method1(factors, factor_name)

            print(f'{factor_name} finish!')
            factors_neutralize = factors_neutralize[['date', 'stock_id', 'factor_value']]

            factors_neutralize.to_parquet(ensure_parent(factor_path(factor_name, '_neutral')))

        except Exception as e:
            print(f'{factor_name} skipped: {e!r}')
            continue























