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
# Connections are created lazily inside the methods that need them (and only
# when isupdate>0). Export the QUANT_DB_* env vars to enable online fetching.
# wind_conn = conn2db('wind_conn')
# factors_conn = conn2db('factors_conn')
# market_conn = conn2db('market_conn')

import os, sys, inspect
import logging


from common_functions import conn2db
from settings import START_DATE, END_DATE, SPECIAL_DATE, UNIVERSES, INIT_AMOUNT, FEE_RATE, DAYS_PER_YEAR, BARRA_RENAME
from data_spec import NEU, DATA_DIR, LOG_DIR, ensure_parent

cpu_num = 10

import pdb

import warnings
warnings.filterwarnings('ignore')


# In[]
class Positions2Nav(object):
    """A class provides functions to calculate net values from positions."""
    def __init__(self, **kwargs):
        """This function, initializes an object in a class, Positions2Nav."""
        # version
        if "version" in kwargs.keys():
            self.version = kwargs["version"]
        else:
            self.version = 'debug'
            
        # the path of the script file
        newpaths = os.path.abspath(__file__).split(os.sep)
        self._FILE = newpaths[-1][:-3]
        
        # dictionaries
        if "datadir" in kwargs.keys():
            datadir = kwargs["datadir"]
        else:
            datadir = DATA_DIR
        self.user_data_dir = datadir
        self.configdir = datadir+'/config'
        self.org_dir = datadir+'/org_data'
        self.factor_data_dir = datadir+'/factor_data'
        self.market_dir = datadir+'/market_data'
        self.positions_dir = datadir+'/positions'
        self.navs_dir = datadir+'/navs'
        self.result_dir = datadir+'/results'
        self.factor_rotation_dir = datadir+'/factor_rotation'
        self.portfolio_dir = datadir+'/portfolios'
        self.g_positions_dir = datadir+'/g_positions'
        self.picture_dir = datadir+'/pics'
        # create log dir if not exists
        os.makedirs(self.user_data_dir, exist_ok=True)
        os.makedirs(self.configdir, exist_ok=True)
        os.makedirs(self.org_dir, exist_ok=True)
        os.makedirs(self.factor_data_dir, exist_ok=True)
        os.makedirs(self.market_dir, exist_ok=True)
        os.makedirs(self.positions_dir, exist_ok=True)
        os.makedirs(self.navs_dir, exist_ok=True)
        os.makedirs(self.factor_rotation_dir, exist_ok=True)
        os.makedirs(self.portfolio_dir, exist_ok=True)
        os.makedirs(self.g_positions_dir, exist_ok=True)
        os.makedirs(self.result_dir, exist_ok=True)
        os.makedirs(self.picture_dir, exist_ok=True)
        
        # sets up log dir
        if "logdir" in kwargs.keys():
            logdir = kwargs["logdir"]
        else:
            logdir = LOG_DIR
        # create log dir if not exists
        os.makedirs(logdir, exist_ok=True)
        self.log = logdir
        logger = self.set_logger()
        logger.info('%s operate on version %s.' %(__file__,self.version))
        logger.info('Write logs to %s' %logdir)
        self.logger = logger

    def __del__(self):
        """The function is the uninitializing function of the class."""
        self.logger.handlers.clear()

    def set_logger(self):
        """This function sets logger file."""
        logger = logging.getLogger(__name__)
        logger.setLevel(level = logging.INFO)
        # console output
        rf_handler = logging.StreamHandler(sys.stderr)
        rf_handler.setLevel(logging.DEBUG)
        rf_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(filename)s[:%(lineno)d] - %(message)s"))
        # log file output
        f_handler = logging.FileHandler(self.log+"/%s.log" %self._FILE)
        f_handler.setLevel(logging.INFO)
        f_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(filename)s[:%(lineno)d] - %(message)s"))
        # if already exist 
        if not logger.handlers:
            logger.addHandler(rf_handler)
            logger.addHandler(f_handler)
        return logger

    def config(self, isupdate, neu, **kwargs):
        '''This function loads data and makes configurations.'''
        # config
        logger = self.logger
        logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        
        # end_date
        if 'end_date' in kwargs.keys():
            self.end_date = kwargs['end_date']
        else:
            self.end_date = datetime.datetime.today().strftime('%Y%m%d')
        # start_date
        if 'start_date' in kwargs.keys():
            self.start_date = kwargs['start_date']
        else:
            # start_date = (pd.to_datetime(end_date) - pd.to_timedelta('1095 days')).strftime('%Y%m%d')
            self.start_date = '20201012'
        
        # special_date
        if 'special_date' in kwargs.keys():
            self.special_date = kwargs['special_date']
        else:
            self.special_date = pd.to_datetime('20240513')
            # self.special_date = pd.to_datetime('20231114')
        
        # parameters for group testing
        self.group_test_params = {}
        self.group_test_params['ngroups'] = isupdate['ngroups']
        self.group_test_params['init_amount'] = INIT_AMOUNT
        self.group_test_params['init_asset'] = self.group_test_params['init_amount']*0.95
        self.group_test_params['cash'] = self.group_test_params['init_amount']*0.05
        self.group_test_params['fee_rate'] = FEE_RATE
        # self.group_test_params['fee_rate'] = 0.0
        self.group_test_params['drawpic_1'] = isupdate['drawpic_1']
        self.group_test_params['drawpic_2'] = isupdate['drawpic_2']
        
        # number of groups
        ngroups = self.group_test_params['ngroups']
        group_limit = pd.DataFrame(np.arange(ngroups+1)/ngroups,columns=['start'])
        group_limit['end'] = group_limit['start'].shift(-1)
        self.group_limit = group_limit.dropna(how='any')
        
        # portfolio_info
        self.portfolio_info = pd.read_excel(self.configdir+f'/portfolio_info{neu}.xlsx', sheet_name='portfolio_info')

        return 0
    
    def generate_trading_dates(self, isupdate):
        '''This function generates trading dates.'''
        # config
        logger = self.logger
        logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        # seting frequency
        self.group_test_params['frequency'] = isupdate['frequency']
        # position changing parameters
        if isupdate['frequency_unit']=='week':
            len_week = self.group_test_params['frequency']
        else:
            len_week = 0

        test_type = isupdate['test_type']
        # datelist
        trading_days = pd.read_parquet(self.market_dir+'/trading_days.pq')
        datelist = trading_days[(trading_days['date']>=pd.to_datetime(self.start_date))].reset_index(drop=True)
        datelist['weekdays'] = datelist['date'].dt.weekday
        datelist['dateinmonth'] = datelist['date'].dt.day
        # if the date is the last day of the week
        datelist['last_tradingday_in_week'] = (datelist['weekdays'].diff() < 0).astype(int).shift(-1).fillna(0)
        # if the date is the first day of the week
        datelist['first_tradingday_in_week'] = (datelist['weekdays'].diff(periods=-1) > 0).astype(int).shift(1).fillna(1)
        # if date is the last day of the month
        datelist['last_tradingday_in_month'] = (datelist['dateinmonth'].diff() < 0).astype(int).shift(-1).fillna(0)
        # if date is the first day of the month
        datelist['first_tradingday_in_month'] = (datelist['dateinmonth'].diff(periods=-1) > 0).astype(int).shift(1).fillna(1)
        # if date is the second day of the month
        datelist['second_tradingday_in_month'] = datelist['first_tradingday_in_month'].astype(int).shift(1).fillna(0)
        # if date is the last day before a long season
        datelist['last_tradingday_before_vocation'] = (datelist['date'].diff().dt.days > 5).astype(int).shift(-1).fillna(0) * 100


        # set cycle length in weeks
        if len_week>1:
            datelist['is_stock_position_adjust'] = (datelist['last_tradingday_in_week'].cumsum()%len_week)*datelist['last_tradingday_in_week']
        elif len_week==1:
            datelist['is_stock_position_adjust'] = datelist['last_tradingday_in_week']

        if test_type == 1:
            datelist['is_stock_position_adjust'] = datelist['second_tradingday_in_month']
        elif test_type == 0:
            datelist['is_stock_position_adjust'] = ((datelist['is_stock_position_adjust'] + datelist[
                'last_tradingday_before_vocation']) > 0).astype(int)

        # set is_portfolio_adjust
        datelist['is_portfolio_adjust'] = datelist['is_stock_position_adjust']
            
        # is_portfolio_adjust_lastday
        datelist['is_portfolio_adjust_lastday'] = datelist['is_portfolio_adjust'].shift(-1).fillna(0)
        datelist = datelist[datelist['date']<=pd.to_datetime(self.end_date)]
        self.datelist = datelist
        
        return datelist

    def fetch_data(self, isupdate, **kwargs):
        '''This function loads data.'''
        # config
        logger = self.logger
        logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        market_dir = self.market_dir
        start_date = self.start_date
        end_date = self.end_date
        
        # stock_prices
        if isupdate['stock_prices']>0:
            # connection to database market_conn
            if not hasattr(self, 'market_conn'):
                self.market_conn = conn2db('market_conn')
            # connection to database wind_conn
            if not hasattr(self, 'wind_conn'):
                self.wind_conn = conn2db('wind_conn')
            stock_prices = self.fetch_market_data(start_date, end_date, isupdate['stock_prices'])
        elif isupdate['stock_prices']==0:
            stock_prices = pd.read_parquet(market_dir+'/stock_market.pq')
        self.stock_prices = stock_prices
        
        # index_prices
        if isupdate['index_prices']>0:
            # connection to database
            if not hasattr(self, 'wind_conn'):
                self.wind_conn = conn2db('wind_conn')
            self.index_prices = self.fetch_index_data(start_date, end_date, isupdate['index_prices'])
        elif isupdate['index_prices']==0:
            self.index_prices = pd.read_parquet(self.market_dir+'/index_prices.pq')
        
        # stock_prices to returns
        stock_prices['rets'] = stock_prices['adj_close']/stock_prices['adj_pre_close']-1
        rets = stock_prices.pivot(columns='stock_id',index='date',values='rets')
        rets = rets.dropna(axis=1,how='all')
        self.rets = rets
        
        return 0
    
    def fetch_index_data(self, start_date, end_date, update, **kwargs):
        # config
        logger = self.logger
        logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        index_info = pd.read_excel(self.configdir+'/index_info.xlsx')
        
        # fetch old data
        if update==1:
            mdata = pd.read_parquet(self.market_dir+'/index_prices.pq')
            last_date = mdata.index[-3]
            start_date = last_date.strftime('%Y%m%d')
        elif update==2:
            start_date = '19900101'
        
        # fetch or update data for common indexes
        index_info_1 = index_info[index_info['table_prices']=='AINDEXEODPRICES']
        code_str = "','".join(index_info_1['wind_code'].tolist())
        sqlstr = "select TRADE_DT, S_INFO_WINDCODE, S_DQ_CLOSE from WANDE.wande.dbo.AINDEXEODPRICES where TRADE_DT>='%s' and TRADE_DT<='%s' and S_INFO_WINDCODE IN ('%s') order by TRADE_DT,S_INFO_WINDCODE;" %(start_date, end_date, code_str)
        index_prices = pd.read_sql(sqlstr, self.wind_conn)
        index_prices.columns = ['date','stock_id','close']
        index_prices = index_prices.pivot(index='date',columns='stock_id',values='close')
        index_prices.index = pd.to_datetime(index_prices.index)
        
        # fetch or update data for wind indexes
        index_info_1 = index_info[index_info['table_prices']=='AINDEXWINDINDUSTRIESEOD']
        code_str = "','".join(index_info_1['wind_code'].tolist())
        sqlstr = "select TRADE_DT, S_INFO_WINDCODE, S_DQ_CLOSE from WANDE.wande.dbo.AINDEXWINDINDUSTRIESEOD where TRADE_DT>='%s' and TRADE_DT<='%s' and S_INFO_WINDCODE IN ('%s') order by TRADE_DT,S_INFO_WINDCODE;" %(start_date, end_date, code_str)
        index_prices_1 = pd.read_sql(sqlstr, self.wind_conn)
        index_prices_1.columns = ['date','stock_id','close']
        index_prices_1 = index_prices_1.pivot(index='date',columns='stock_id',values='close')
        index_prices_1.index = pd.to_datetime(index_prices_1.index)
        # combine index_prices and index_prices_1
        index_prices = index_prices.merge(index_prices_1,how='outer',left_index=True,right_index=True)
        
        # fetch or update data for wind fund indexes
        index_info_1 = index_info[index_info['table_prices']=='CMFINDEXEOD']
        code_str = "','".join(index_info_1['wind_code'].tolist())
        sqlstr = "select TRADE_DT, S_INFO_WINDCODE, S_DQ_CLOSE from WANDE.wande.dbo.CMFINDEXEOD where TRADE_DT>='%s' and TRADE_DT<='%s' and S_INFO_WINDCODE IN ('%s') order by TRADE_DT,S_INFO_WINDCODE;" %(start_date, end_date, code_str)
        index_prices_1 = pd.read_sql(sqlstr, self.wind_conn)
        index_prices_1.columns = ['date','stock_id','close']
        index_prices_1 = index_prices_1.pivot(index='date',columns='stock_id',values='close')
        index_prices_1.index = pd.to_datetime(index_prices_1.index)
        # combine index_prices and index_prices_1
        index_prices = index_prices.merge(index_prices_1,how='outer',left_index=True,right_index=True)
        
        # fetch or update data for bond indexes
        index_info_1 = index_info[index_info['table_prices']=='CBINDEXEODPRICES']
        code_str = "','".join(index_info_1['wind_code'].tolist())
        sqlstr = "select TRADE_DT, S_INFO_WINDCODE, S_DQ_CLOSE from WANDE.wande.dbo.CBINDEXEODPRICES where TRADE_DT>='%s' and TRADE_DT<='%s' and S_INFO_WINDCODE IN ('%s') order by TRADE_DT,S_INFO_WINDCODE;" %(start_date, end_date, code_str)
        index_prices_1 = pd.read_sql(sqlstr, self.wind_conn)
        index_prices_1.columns = ['date','stock_id','close']
        index_prices_1 = index_prices_1.pivot(index='date',columns='stock_id',values='close')
        index_prices_1.index = pd.to_datetime(index_prices_1.index)
        # combine index_prices and index_prices_1
        index_prices = index_prices.merge(index_prices_1,how='outer',left_index=True,right_index=True)
        
        # add old data
        if update==1:
            index_prices = pd.concat([mdata[mdata.index<last_date], index_prices], axis=0)
            
        # save
        index_prices = index_prices[index_prices.index<pd.to_datetime(self.end_date)]
        index_prices.to_parquet(self.market_dir+'/index_prices.pq')
        
        return index_prices

    def fetch_market_data(self, start_date, end_date, update, **kwargs):
        # config
        logger = self.logger
        logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        # fetch market data
        if update==1:
            mdata = pd.read_parquet(self.market_dir+'/stock_market.pq')
            last_date = mdata['date'].max()
            start_date = last_date.strftime('%Y%m%d')
        # fetch update data

        stock_prices = pd.read_sql('select date, stock_id, close, adj_pre_close, adj_close, volume, amt from stock_market where date >= %s and date <= %s' %(start_date, end_date), self.market_conn)
        # add old data
        if update==1:
            stock_prices = pd.concat([mdata[mdata['date']<last_date], stock_prices], axis=0)
        # save
        stock_prices.to_parquet(self.market_dir+'/stock_market.pq')
        
        return stock_prices

    def statistics_core_1(self, special_date, navs, benchmark_code):
        '''This function makes statistics from navs_comb.'''
        # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        # statistics
        number_days = (~navs.isna()).sum()
        factor_statistic = pd.DataFrame()
        factor_statistic['portfolio_id'] = navs.columns
        factor_statistic['trading_days'] = navs.shape[0]
        factor_statistic['ret_in_period'] = (navs.iloc[-1, :] - 1).values * 100
        idx_spc = navs.index.tolist().index(special_date)
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

        if len(benchmark_code) > 0:
            # fetch index prices
            index_prices = self.index_prices
            index_rets = index_prices.pct_change()
            index_rets = index_rets[benchmark_code]
            # adv_navs
            portfolio_rets = navs.pct_change()
            adv_navs = portfolio_rets.sub(index_rets.loc[portfolio_rets.index].values, axis=0)
            adv_navs.iloc[0, :] = 0
            adv_navs = (adv_navs + 1).cumprod()
            # adv_navs.loc[adv_navs.index, icol] = adv_navs.loc[adv_navs.index,icol]

            # advanced return
            adv_statistic = pd.DataFrame()
            adv_statistic['portfolio_id'] = adv_navs.columns
            if navs.shape[0] > DAYS_PER_YEAR:
                adv_statistic['adv_ret_recent1year'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-DAYS_PER_YEAR, :] - 1).values * 100
            else:
                adv_statistic['adv_ret_recent1year'] = np.nan
            if navs.shape[0] > 121:
                adv_statistic['adv_ret_recent6month'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-121, :] - 1).values * 100
            else:
                adv_statistic['adv_ret_recent6month'] = np.nan
            if navs.shape[0] > 64:
                adv_statistic['adv_ret_recent3month'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-64, :] - 1).values * 100
            else:
                adv_statistic['adv_ret_recent3month'] = np.nan
            adv_statistic['adv_ret_recent1month'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-22, :] - 1).values * 100
            adv_statistic['adv_ret_recent1week'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-6, :] - 1).values * 100
            adv_statistic['adv_ret_recent3day'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-4, :] - 1).values * 100
            adv_statistic['adv_ret_recent2day'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-3, :] - 1).values * 100
            adv_statistic['adv_ret_recent1day'] = (adv_navs.iloc[-1, :] / adv_navs.iloc[-2, :] - 1).values * 100
            adv_statistic['annualized_adv_ret'] = (adv_navs.iloc[-1, :] ** (DAYS_PER_YEAR / number_days) - 1).values * 100
            adv_statistic['adv_volatility'] = (np.log(adv_navs).diff().std() * np.sqrt(DAYS_PER_YEAR)).values * 100
            adv_statistic['adv_max_draw_down'] = (1 - (adv_navs / adv_navs.cummax()).min()).values * 100
            adv_statistic['adv_volatility_recent3month'] = (np.log(adv_navs.iloc[-64:, :]).diff().std() * np.sqrt(
                DAYS_PER_YEAR)).values * 100
            adv_statistic['adv_max_draw_down_recent3month'] = (1 - (
                    adv_navs.iloc[-64:, :] / adv_navs.iloc[-64:, :].cummax()).min()).values * 100
            adv_statistic['adv_volatility_recent1month'] = (np.log(adv_navs.iloc[-21:, :]).diff().std() * np.sqrt(
                DAYS_PER_YEAR)).values * 100
            adv_statistic['adv_max_draw_down_recent1month'] = (1 - (
                    adv_navs.iloc[-21:, :] / adv_navs.iloc[-21:, :].cummax()).min()).values * 100
            adv_statistic['adv_volatility_recent1week'] = (np.log(adv_navs.iloc[-5:, :]).diff().std() * np.sqrt(
                DAYS_PER_YEAR)).values * 100
            adv_statistic['adv_max_draw_down_recent1week'] = (1 - (
                    adv_navs.iloc[-5:, :] / adv_navs.iloc[-5:, :].cummax()).min()).values * 100
            factor_statistic = factor_statistic.merge(adv_statistic, how='left', on=['portfolio_id'])

            # information ratio
            factor_statistic['information_ratio'] = factor_statistic['annualized_adv_ret'] / factor_statistic[
                'adv_volatility']
            factor_statistic['return_mdd_ratio'] = factor_statistic['annualized_adv_ret'] / factor_statistic[
                'adv_max_draw_down']
            factor_statistic['information_ratio_r3month'] = factor_statistic['adv_ret_recent3month'] / factor_statistic[
                'adv_volatility'] * DAYS_PER_YEAR / 63
            factor_statistic['return_mdd_ratio_r3month'] = factor_statistic['adv_ret_recent3month'] / factor_statistic[
                'adv_max_draw_down'] * DAYS_PER_YEAR / 63
            factor_statistic['information_ratio_recent3month'] = factor_statistic['adv_ret_recent3month'] / \
                                                                 factor_statistic[
                                                                     'adv_volatility_recent3month'] * DAYS_PER_YEAR / 63
            factor_statistic['return_mdd_ratio_recent3month'] = factor_statistic['adv_ret_recent3month'] / \
                                                                factor_statistic[
                                                                    'adv_max_draw_down_recent3month'] * DAYS_PER_YEAR / 63
            factor_statistic['information_ratio_recent1month'] = factor_statistic['adv_ret_recent1month'] / \
                                                                 factor_statistic[
                                                                     'adv_volatility_recent1month'] * DAYS_PER_YEAR / 21
            factor_statistic['return_mdd_ratio_recent1month'] = factor_statistic['adv_ret_recent1month'] / \
                                                                factor_statistic[
                                                                    'adv_max_draw_down_recent1month'] * DAYS_PER_YEAR / 21
            factor_statistic['information_ratio_recent1week'] = factor_statistic['adv_ret_recent1week'] / \
                                                                factor_statistic['adv_volatility_recent1week'] * DAYS_PER_YEAR / 5
            factor_statistic['return_mdd_ratio_recent1week'] = factor_statistic['adv_ret_recent1week'] / \
                                                               factor_statistic[
                                                                   'adv_max_draw_down_recent1week'] * DAYS_PER_YEAR / 5

            # reformate
            factor_statistic = factor_statistic.sort_values(by=['information_ratio_r3month'],
                                                            ascending=False).reset_index(drop=True)

        return factor_statistic

    def daily_update_statistics(self, isupdate, nav_folder, portfolio_folder, barra, neu, **kwargs):
        '''This function makes statistics from navs.'''

        if isupdate['isupdate'] == 0:
            return 0

        nav_file = isupdate['nav_file']

        if 'special_date' in isupdate.keys():
            special_date = isupdate['special_date']
        else:
            special_date = self.special_date

        # benchmark_code
        if 'benchmark_code' in isupdate.keys():
            benchmark_code = isupdate['benchmark_code']
        else:
            benchmark_code = self.benchmark_code

        portfolio_info = self.portfolio_info

        portfolio_info = portfolio_info[
            ['portfolio_id', 'portfolio_name', 'portfolio_type', 'benchmark', 'barra_adjusted', 'frequency']].copy()
        portfolio_info['factor_name'] = [x.split('#')[0] for x in portfolio_info['portfolio_name']]

        # portfolio_list
        if 'portfolio_list' in isupdate.keys():
            portfolio_list = isupdate['portfolio_list']
            portfolio_info = portfolio_info[portfolio_info['portfolio_id'].isin(portfolio_list)]

        # fetch navs
        if isupdate['fetch_pq_file'] == 1:
            # navs = pd.read_parquet(self.navs_dir + '/navs.pq')
            navs = pd.read_parquet(self.navs_dir + nav_folder + '/%s.pq' % nav_file)
            # navs = pd.concat([navs, navs_new], axis=0)

        navs.sort_values(by=['portfolio_id', 'date'], inplace=True)
        navs = navs.reset_index(drop=True)

        ### 取因子交集
        portfolio_info = pd.merge(portfolio_info, navs[['portfolio_id']].drop_duplicates(), on=['portfolio_id'],
                                  how='inner')
        ###
        # navs_all
        # pdb.set_trace()
        navs_all = navs.pivot(columns='portfolio_id', index='date', values='nav')
        navs_all = navs_all[navs_all.index >= pd.to_datetime(self.start_date)]
        navs_all = navs_all[portfolio_info['portfolio_id']]

        # statistic
        factor_statistic = self.statistics_core_1(special_date, navs_all, benchmark_code)
        # add turnover
        turnover = navs.pivot(columns='portfolio_id', index='date', values='turn_over')
        turnover = (turnover.sum() * (DAYS_PER_YEAR / turnover.count())).to_frame('换手率').reset_index(drop=False)
        factor_statistic = factor_statistic.merge(turnover, how='left', on=['portfolio_id'])
        factor_statistic = factor_statistic.merge(portfolio_info[['portfolio_id', 'factor_name']], how='left',
                                                  on=['portfolio_id'])
        tlogi = factor_statistic['factor_name'].isna()
        factor_statistic.loc[tlogi, 'factor_name'] = factor_statistic.loc[tlogi, 'portfolio_id']
        # add portfolio_type and benchmark
        factor_statistic = factor_statistic.merge(
            portfolio_info[
                ['portfolio_id', 'portfolio_name', 'portfolio_type', 'benchmark', 'barra_adjusted', 'frequency']],
            how='left',
            on=['portfolio_id'])

        tcols = ['factor_name', 'barra_adjusted', 'portfolio_name', 'frequency', 'benchmark', 'portfolio_id',
                 'trading_days', 'ret_in_period', 'ret_special_date',
                 'ret_recent1year', 'ret_recent6month', 'ret_recent3month', 'ret_recent1month', 'ret_recent1week',
                 'ret_recent3day', 'ret_recent2day', 'ret_recent1day', 'annualized_ret', 'volatility', 'max_draw_down',
                 'adv_ret_recent1year', 'adv_ret_recent6month', 'adv_ret_recent3month', 'adv_ret_recent1month',
                 'adv_ret_recent1week',
                 'adv_ret_recent3day', 'adv_ret_recent2day', 'adv_ret_recent1day', 'annualized_adv_ret',
                 'adv_volatility',
                 'adv_max_draw_down', '换手率', 'information_ratio', 'return_mdd_ratio', 'information_ratio_r3month',
                 'return_mdd_ratio_r3month', 'information_ratio_recent3month', 'return_mdd_ratio_recent3month',
                 'information_ratio_recent1month', 'return_mdd_ratio_recent1month', 'adv_volatility_recent3month',
                 'adv_max_draw_down_recent3month', 'adv_volatility_recent1month', 'adv_max_draw_down_recent1month',
                 'adv_volatility_recent1week', 'adv_max_draw_down_recent1week', 'information_ratio_recent1week',
                 'return_mdd_ratio_recent1week',
                 'portfolio_type']
        factor_statistic = factor_statistic[tcols]

        if barra == True:
            sheet = isupdate['sheet']
            convert_info = pd.read_excel(self.configdir + f'/portfolio_info{neu}.xlsx',
                                         sheet_name=f'软约束限BARRA_{sheet}_01')
            tmp = pd.merge(factor_statistic[['portfolio_id']],
                           convert_info[['portfolio_name', 'original_portfolio']].rename(
                               columns={'original_portfolio': 'portfolio_id'}), on='portfolio_id', how='left')
            factor_statistic['portfolio_name'] = tmp['portfolio_name']

        # fetch index prices
        index_prices = self.index_prices
        index_rets = index_prices.pct_change()
        index_rets = index_rets[benchmark_code]

        # navs_all
        navs_all = navs_all[factor_statistic['portfolio_id']]
        navs_all.columns = factor_statistic['portfolio_name']
        # adv_navs
        portfolio_rets = navs_all.pct_change()
        adv_navs = portfolio_rets.sub(index_rets.loc[portfolio_rets.index].values, axis=0)
        adv_navs.iloc[0, :] = 0
        adv_navs = (adv_navs + 1).cumprod()

        # save to excel files
        save_name = 'factor_statistic_' + nav_file[5:]
        with pd.ExcelWriter(ensure_parent(self.portfolio_dir + portfolio_folder + '/%s.xlsx' % save_name)) as writer:
            factor_statistic.set_index('portfolio_name').to_excel(writer, sheet_name='factor_statistic', index=True)
            tcols = ['portfolio_name', 'ret_special_date', 'adv_ret_recent1day', 'adv_ret_recent2day',
                     'adv_ret_recent3day', 'adv_ret_recent1week', 'adv_max_draw_down_recent1week',
                     'adv_volatility_recent1week', 'adv_max_draw_down_recent1month', 'adv_volatility_recent1month',
                     'adv_max_draw_down_recent3month', 'adv_volatility_recent3month', 'max_draw_down',
                     'adv_ret_recent1year', 'adv_ret_recent6month', 'adv_ret_recent3month', 'adv_ret_recent1month',
                     'annualized_adv_ret', 'volatility', 'adv_max_draw_down', 'adv_volatility']
            factor_statistic[tcols].set_index('portfolio_name').to_excel(writer, sheet_name='factor_statistic_simple',
                                                                         index=True)
            navs_all.to_excel(writer, sheet_name='navs', index=True)
            adv_navs_pct = (adv_navs - 1) * 100
            adv_navs_pct.to_excel(writer, sheet_name='adv_navs', index=True)
            # performance during recent 3 months
            navs_r3m = navs_all[navs_all.index >= (navs_all.index[-1] - datetime.timedelta(days=90))]
            navs_r3m = navs_r3m.div(navs_r3m.iloc[0, :].values, axis=1)
            navs_r3m.to_excel(writer, sheet_name='navs_r3m', index=True)
            adv_navs_r3m = adv_navs[adv_navs.index >= (adv_navs.index[-1] - datetime.timedelta(days=90))]
            adv_navs_r3m = adv_navs_r3m.div(adv_navs_r3m.iloc[0, :].values, axis=1)
            adv_navs_r3m_pct = (adv_navs_r3m - 1) * 100
            adv_navs_r3m_pct.to_excel(writer, sheet_name='adv_navs_r3m', index=True)
            # performance from the special day
            adv_navs_fsd = adv_navs[adv_navs.index >= self.special_date]
            adv_navs_fsd = adv_navs_fsd.div(adv_navs_fsd.iloc[0, :].values, axis=1)
            adv_navs_fsd_pct = (adv_navs_fsd - 1) * 100
            adv_navs_fsd_pct.to_excel(writer, sheet_name='adv_navs_fsd', index=True)

        return 0


# In[]
if __name__=='__main__':
    # initialize Positions2Nav

    # dates, universes / benchmarks and neutral / raw are set in settings.py
    start_date = START_DATE
    end_date = END_DATE

    def main_process(benchmark, nav_folder, portfolio_folder, barra, neu):

        # 'benchmark' is the universe name (portfolio_info.stock_area); navs come from top_n_portfolio.py
        nav_path = DATA_DIR + '/navs' + nav_folder + f'/navs_{benchmark}.pq'
        if not os.path.exists(nav_path):
            print(f'{benchmark}: {nav_path} not found, run top_n_portfolio.py first; skipped')
            return

        obj_positions2nav = Positions2Nav()

        isupdate = {'frequency':1, 'ngroups':1, 'drawpic_1':0, 'drawpic_2':0}
        # obj_factortesting.config(isupdate, update_positions_files=1)
        obj_positions2nav.config(isupdate, special_date=pd.to_datetime(SPECIAL_DATE),start_date=start_date, end_date=end_date, neu=neu)

        # generate trading_dates
        isupdate_trading_dates = {'frequency':1, 'frequency_unit':'month', 'suffix2save':'100bp', 'test_type':1}
        datelist = obj_positions2nav.generate_trading_dates(isupdate_trading_dates)

        # fetch data
        isupdate_data = {'stock_prices':0,'index_prices':0,
                        'barra_exposure':0,'index_barra_exposure':0,
                        'index_exposure_daily':['hs300', 'zz500', 'zz1000']}
        # index_list = ['hs300', 'zz500', 'zz1000', 'gz2000']
        obj_positions2nav.fetch_data(isupdate_data)

        portfolio_list = obj_positions2nav.portfolio_info
        portfolio_list = portfolio_list[portfolio_list['stock_area'] == benchmark]['portfolio_id'].unique().tolist()

        # benchmark index code and barra sheet per universe come from settings.UNIVERSES
        isupdate_statistic = {'isupdate': 1, 'fetch_pq_file': 1, 'benchmark_code': UNIVERSES[benchmark]['benchmark'],
                              'portfolio_list': portfolio_list, 'add_fund': 0, 'nav_file': f'navs_{benchmark}',
                              'sheet': UNIVERSES[benchmark]['barra_sheet']}

        barra = barra
        obj_positions2nav.daily_update_statistics(isupdate_statistic, nav_folder, portfolio_folder, barra, neu)

        print('finish')

    ## 等权组合

    for universe in UNIVERSES:
        main_process(benchmark=universe, nav_folder=f'/navs{NEU}', portfolio_folder=f'/factor_statistic{NEU}', barra=BARRA_RENAME, neu=NEU)



