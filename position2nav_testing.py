# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import datetime
from scipy.stats import spearmanr

import matplotlib.pyplot as plt
from pylab import mpl
mpl.rcParams['font.sans-serif'] = ['Songti SC']
mpl.rcParams['axes.unicode_minus'] = False
# plt config
plt.rcParams['figure.figsize'] = (30,16)
plt.rcParams['axes.titlesize'] = 36
plt.rcParams['axes.titleweight'] = 3

# from CommonFunctions import conn2db
# wind_conn = conn2db('wind_conn')
# factors_conn = conn2db('factors_conn')
# market_conn = conn2db('market_conn')

import os, sys, inspect



# from scipy.optimize import minimize, Bounds
# cvxopt was imported here but never used in this module; it is left out so the
# framework runs without a solver stack. Re-add it if an optimiser is added.

from CommonFunctions import conn2db
from settings import (START_DATE, END_DATE, SPECIAL_DATE, UNIVERSES, N_GROUPS, INIT_AMOUNT, FEE_RATE, WEIGHT_CAP,
                      DAYS_PER_YEAR)
from data_spec import (NEU, DATA_DIR, STOCK_MARKET, STOCK_STATUS, REBALANCE_DATES, factors_dict_path, factor_path,
                       ensure_parent, drop_excluded_stocks)

import multiprocessing as mp
cpu_num = 8
from functools import partial
import pdb

import warnings
warnings.filterwarnings('ignore')

def assign_groups_and_weights(factor):
    def process_group(df):
        #df['factor_value'] += np.random.normal(0, 1e-12, len(df))
        df = df.sort_values(by='factor_value')
        df['rank'] = df['factor_value'].rank(method='first')
        #df['group_id'] = pd.qcut(df['rank'], 5, labels=['1000', '1001', '1002', '1003', '1004'])
        if df['rank'].nunique() == 1:
            df['group_id'] = '1000'
        else:
            df['group_id'] = pd.qcut(df['rank'], N_GROUPS, labels=[str(1000 + i) for i in range(N_GROUPS)], duplicates='drop')
            #df['group_id'] = pd.qcut(df['factor_value'], 5, labels=['1000', '1001', '1002', '1003', '1004'])
        df = df.drop_duplicates()
        df['weight'] = df.groupby('group_id')['stock_id'].transform(lambda x: (1 / len(x)) if len(x)> 0 else 0)
        return df

    result = factor.groupby('date').apply(process_group).reset_index(drop=True)
    try:
        result['group_id'] = result['group_id'].astype(int)
    except:
        pdb.set_trace()
    result = pd.merge(result, trading_days, on=['date'], how='inner')
    return result

def calculate_annualized_return(group, trading_days_in_year):
    # Sort by date
    group = group.sort_values('date')
    group['nav'] = group['nav'] / group['nav'][0]
    # Get the start and end NAV and total days
    start_nav = group['nav'].iloc[0]
    end_nav = group['nav'].iloc[-1]
    total_days = (group['date'].iloc[-1] - group['date'].iloc[0]).days
    # Calculate annualized return
    annualized_return = (end_nav / start_nav) ** (trading_days_in_year / total_days) - 1
    volatility = (np.log(group['nav']).diff().std() * np.sqrt(DAYS_PER_YEAR))
    sharpe = annualized_return / volatility
    return sharpe

def calculate_weights(group):
    # Make a copy to avoid modifying the original
    thres = WEIGHT_CAP
    group = group.copy()
    print(group['group_id'].unique().tolist()[0], '  ---  ', group['date'].unique().tolist()[0])
    if len(group) <= 1 / thres:
        group['weight'] = 1 / len(group)
        return group

    # Initial calculation
    total_mv = group['float_mv'].sum()
    group['weight'] = group['float_mv'] / total_mv

    # Track which stocks have been capped at 0.2
    capped_mask = pd.Series(False, index=group.index)

    while True:
        # Find stocks exceeding 0.2 weight (excluding already capped stocks)
        exceeds = (~capped_mask) & (group['weight'] > thres)

        if not exceeds.any():
            break  # No more adjustments needed

        # Mark these as capped
        capped_mask |= exceeds

        # Count how many exceed and calculate remaining weight
        n_capped = capped_mask.sum()
        remaining_weight = 1 - thres * n_capped

        # Set capped weights to exactly 0.2
        group.loc[capped_mask, 'weight'] = thres

        # Calculate weights for remaining stocks
        remaining_stocks = ~capped_mask
        remaining_mv = group.loc[remaining_stocks, 'float_mv'].sum()

        if remaining_mv > 0:
            # Distribute remaining weight proportionally to remaining stocks
            group.loc[remaining_stocks, 'weight'] = ( group.loc[remaining_stocks, 'float_mv'] / remaining_mv * remaining_weight)
        else:
            # If all remaining have zero float_mv, distribute remaining weight equally
            n_remaining = remaining_stocks.sum()
            if n_remaining > 0:
                group.loc[remaining_stocks, 'weight'] = remaining_weight / n_remaining

    return group



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
        # localOS = sys.platform
        # if localOS=='linux':
        #     newpaths = os.path.abspath(__file__).split('/')
        # else:
        #     newpaths = os.path.abspath(__file__).split('\\')
        localOS = sys.platform
        if 'win' in localOS.lower():  # Windows使用'\\'
            newpaths = os.path.abspath(__file__).split('\\')
        else:  # macOS (darwin)、Linux等使用'/'
            newpaths = os.path.abspath(__file__).split('/')
        self._FILE = newpaths[-1][:-3]
        
        # dictionaries
        if "datadir" in kwargs.keys():
            datadir = kwargs["datadir"]
        else:
            datadir = DATA_DIR

        self.user_data_dir = datadir # Used to be os.environ.get('USER_DATA_DIR') causing issues
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
        
        # Create directories if they don't exist
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



    def config(self, isupdate, **kwargs):
        '''This function loads data and makes configurations.'''
        # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        
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
            self.start_date = '20200930'
        
        # special_date
        if 'special_date' in kwargs.keys():
            self.special_date = kwargs['special_date']
        else:
            self.special_date = pd.to_datetime('20231229')
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
        
        # portfolio_info: the group portfolios 1000.. produced by assign_groups_and_weights
        # (previously listed by hand in config/portfolio_info_onetime.xlsx)
        self.portfolio_info = pd.DataFrame({'portfolio_id': [1000 + i for i in range(N_GROUPS)],
                                            'portfolio_type': 'smart_beta'})

        return 0
    
    def generate_trading_dates(self, isupdate):
        '''This function generates trading dates.'''
        # # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
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
            datelist['is_stock_position_adjust'] = datelist['first_tradingday_in_month']
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
        # # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
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

        # stock_prices['stock_id'] = stock_prices['stock_id'].str[0:6]
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
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
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
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        # fetch market data
        if update==1:
            mdata = pd.read_parquet(self.market_dir+'/stock_market.pq')
            # mdata['stock_id'] = mdata['stock_id'].str[0:6]
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
    
    def calculate_position_core(self, report_date, g_positions):
        '''This function generate the group testing for a single factor.'''
        # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        rets = self.rets
        report_date = min(rets.index.max(),pd.to_datetime(report_date))
        rets = rets[rets.index<=report_date]
        datelist = self.datelist
        datelist = datelist[datelist['date']<=report_date]
        init_amount = self.group_test_params['init_amount']
        init_asset = self.group_test_params['init_asset']
        cash = self.group_test_params['cash']
        fee_rate = self.group_test_params['fee_rate']
        g_positions.index = pd.to_datetime(g_positions.index)
        g_positions = g_positions[(g_positions.index<=report_date)&(g_positions.index>=datelist['date'].min())]
        nrows = g_positions.shape[0]
        
        # main
        # initialize
        positions = pd.DataFrame(columns=['date','instrument','pre_weight','weight','pre_value','value','fee','cash'])
        lidx = nrows-1
        # cycle between the first cycle and last cycle
        for idx in range(nrows):
            # dates
            isdate = g_positions.index[idx]
            if idx<lidx:
                iedate = g_positions.index[idx+1]
            elif idx==lidx:
                iedate = datelist['date'].iloc[-1]
            # stocks
            pg_positions = g_positions.loc[isdate,:].dropna()
            
            # rets
            tlogi = (rets.index>=isdate)&(rets.index<=iedate)
            sub_rets = rets.loc[tlogi, pg_positions.index]
            sub_rets.iloc[0] = 0
            sub_nav = (sub_rets+1).cumprod()
            if idx==0:
                t_sub_nav = sub_nav*pg_positions*init_asset
                if pg_positions.shape[0]==0:
                    cash = init_amount
            elif idx>0:
                pre_value = positions.loc[positions['date']==isdate,'pre_value'].sum()
                if positions.loc[positions['date']==isdate,'cash'].shape[0]>0:
                    # cash = positions.loc[positions['date']==positions['date'].max(),'cash'].iloc[0]
                    cash = positions.loc[positions['date']==isdate,'cash'].iloc[0]
                t_sub_nav = sub_nav*pg_positions*(pre_value+cash)*0.95
            sub_value = t_sub_nav.stack().reset_index(drop=False)
            sub_value.columns = ['date','instrument','pre_value']
            sub_value['value'] = sub_value['pre_value']
            if idx==0:
                sub_value.loc[sub_value['date']==isdate, 'pre_value'] = 0
            
            # pre_weight and weight
            tlogi = (datelist['date']>=isdate)&(datelist['date']<=iedate)
            part_positions = pd.DataFrame(columns=pg_positions.index, index=datelist.loc[tlogi, 'date'])
            part_positions.loc[isdate,:] = pg_positions
            part_positions = part_positions.ffill()
            part_positions = part_positions.stack().reset_index(drop=False)
            part_positions.columns = ['date','instrument','pre_weight']
            part_positions['weight'] = part_positions['pre_weight']
            part_positions.loc[part_positions['date']==isdate, 'pre_weight'] = 0
            if idx<lidx:
                part_positions.loc[part_positions['date']==iedate, 'weight'] = 0
            # add pre_value and value
            part_positions = part_positions.merge(sub_value,how='outer',on=['date','instrument'])
                
            if idx>0:
                # position in adjusting date and pre_value and value
                tcols = ['date','instrument','pre_weight','weight']
                t_pos1 = positions.loc[positions['date']==isdate,tcols+['pre_value']]
                t_pos2 = part_positions.loc[part_positions['date']==isdate,tcols+['value']]
                if (t_pos1.shape[0]>0) or (t_pos2.shape[0]>0):
                    t_pos = t_pos1.merge(t_pos2,how='outer',on=['date','instrument']).fillna(0)
                    t_pos['pre_weight'] = t_pos[['pre_weight_x','pre_weight_y']].max(axis=1)
                    t_pos['weight'] = t_pos[['weight_x','weight_y']].max(axis=1)
                    t_pos = t_pos[['date','instrument','pre_weight','weight','pre_value','value']]
                    # concat to part_positions
                    part_positions = pd.concat([t_pos, part_positions[part_positions['date']>isdate]],axis=0)
            
            if part_positions.shape[0]>0:
                # fee
                part_positions['fee'] = 0
                if idx==0:
                    tlogi = part_positions['date']==isdate
                    part_positions.loc[tlogi, 'fee'] = part_positions.loc[tlogi, 'value']*fee_rate
                    fee = part_positions.loc[tlogi, 'fee'].sum()
                elif idx>0:
                    tlogi = part_positions['date']==isdate
                    part_positions.loc[tlogi, 'fee'] = (part_positions.loc[tlogi, 'pre_value']-part_positions.loc[tlogi, 'value']).abs()*fee_rate
                    fee = part_positions.loc[tlogi, 'fee'].sum()
                    
                # cash
                if idx==0:
                    cash = cash-fee
                elif idx>0:
                    value = part_positions.loc[part_positions['date']==isdate,'value'].sum()
                    cash = cash-fee+pre_value-value
                part_positions['cash'] = cash
                
            # concate on positions
            if idx==0:
                positions = pd.concat([positions,part_positions],axis=0)
            elif idx>0:
                positions = pd.concat([positions[positions['date']<isdate], part_positions],axis=0)
                
            # 
            tcols = ['pre_weight', 'weight', 'pre_value', 'value', 'fee', 'cash']
            positions[tcols] = positions[tcols].astype(float)
        
        return positions

    def add_portfolio_navs(self, portfolio_info_eff, g_positions, onavs, **kwargs):
        '''This function updates the g_positions for factors and factor portfolios and writes to database.'''
        # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        init_amount = self.group_test_params['init_amount']
        fee_rate = self.group_test_params['fee_rate']

        cnavs = pd.DataFrame()
        for idx in portfolio_info_eff.index:
            pid = portfolio_info_eff.loc[idx,'portfolio_id']
            t_last_nav_date = portfolio_info_eff.loc[idx,'last_date']
            t_onavs = onavs[onavs['portfolio_id']==pid].sort_values('date')
            report_date = portfolio_info_eff.loc[idx,'end_date']
            
            # g_position
            g_position = g_positions[g_positions['portfolio_id']==pid]
            g_position = g_position.drop_duplicates()
            g_position = g_position.pivot(columns='instrument', index='date', values='weight')

            # positions
            if t_last_nav_date==pd.to_datetime('18000101'):
                positions = self.calculate_position_core(report_date, g_position)
            elif t_last_nav_date>pd.to_datetime('18000101'):
                # adjust g_position
                pre_g_position = g_position[g_position.index>=t_last_nav_date]
                if pre_g_position.shape[0]<3:
                    g_position = g_position.iloc[-3:,:]
                else:
                    g_position = pre_g_position
                positions = self.calculate_position_core(report_date, g_position)
            
            # navs and fees
            tnavs, tfees = self.position2navs(positions, 94)
            tnavs = tnavs.merge(tfees,how='left',left_index=True,right_index=True).dropna()
            tnavs.columns = ['nav','turn_over']
            tnavs['turn_over'] = tnavs['turn_over']/tnavs['nav']/fee_rate/init_amount
            tnavs = tnavs.astype(float).reset_index(drop=False)
            tnavs.columns = ['date','nav','turn_over']
            # add old navs
            if t_last_nav_date>pd.to_datetime('18000101'):
                try:
                    t_value = tnavs.loc[tnavs['date']==t_last_nav_date,'nav'].iloc[0]
                except:
                    pdb.set_trace()
                o_value = t_onavs.loc[t_onavs['date']==t_last_nav_date,'nav'].iloc[0]
                tnavs['nav'] = tnavs['nav']/t_value*o_value
                tnavs = tnavs[tnavs['date']>t_last_nav_date]
            
            tnavs['portfolio_id'] = pid
            tcols = ['portfolio_id','date','nav','turn_over']
            tnavs = tnavs[tcols]
            cnavs = pd.concat([cnavs,tnavs],axis=0)
            
        return cnavs
            
    def update_portfolio_navs(self, isupdate, **kwargs):
        '''This function updates the g_positions for factors and factor portfolios and writes to database.'''
        # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        if isupdate['isupdate']==0:
            return 0
        
        portfolio_info = self.portfolio_info
        tlogi = portfolio_info['portfolio_type'].isin(['portfolio','factor','smart_beta','index_enhance'])
        portfolio_info = portfolio_info[tlogi].copy()
        g_positions = self.g_positions
        table_name = 'portfolio_navs'
        if 'report_date' in isupdate.keys():
            report_date = pd.to_datetime(isupdate['report_date'])
        else:
            datelist = self.datelist
            report_date = datelist.loc[datelist['date']<self.end_date,'date'].max()
        
        # specify the portfolio_info
        if 'portfolio_names' in kwargs.keys():
            portfolio_names = kwargs['portfolio_names']
            portfolio_info = portfolio_info[portfolio_info['portfolio_names'].isin(portfolio_names)]
        else:
            portfolio_info = portfolio_info.merge(g_positions[['portfolio_id']].drop_duplicates(),how='inner',on=['portfolio_id'])
        
        # conection
        # if not hasattr(self, 'factor_testing_conn'):
        #     self.factor_testing_conn = conn2db('factor_testing_conn')
        
        # onavs_db
        if isupdate['old_navs']=='database':
            sqlstr = 'select * from %s;' %table_name
            onavs = pd.read_sql(sqlstr, self.factor_testing_conn)
        elif isupdate['old_navs']=='local':
            if isupdate['isupdate']==1:
                onavs = pd.read_parquet(self.navs_dir+'/navs.pq')
            elif isupdate['isupdate']==2:
                onavs = pd.DataFrame(columns=['portfolio_id', 'date', 'nav', 'turn_over'])
                
        # fetch navs from database

        navs_info = onavs[['portfolio_id', 'date']].groupby(by=['portfolio_id']).max().reset_index(drop=False)
        navs_info.columns = ['portfolio_id', 'last_date']

        portfolio_info = portfolio_info.merge(navs_info,how='left',on=['portfolio_id']).fillna(pd.to_datetime('18000101'))

        portfolio_info['end_date'] = report_date

        # portfolio by portfolio and save
        portfolio_info_eff = portfolio_info[portfolio_info['end_date']>portfolio_info['last_date']]
        if portfolio_info_eff.shape[0]>0:
            cnavs = self.add_portfolio_navs(portfolio_info_eff, g_positions, onavs)

            if cnavs.shape[0]>0:                
                # save to pq file
                cnavs = pd.concat([onavs,cnavs],axis=0)
                cnavs.to_parquet(self.navs_dir+'/navs.pq')
        
        return cnavs

    def position2navs(self, positions, group_index):
        '''This function generate the group testing for a single factor.'''
        # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        datelist = self.datelist
        report_date = positions['date'].max()
        datelist = datelist[datelist['date']<=pd.to_datetime(report_date)]
        init_amount = self.group_test_params['init_amount']
        
        vposition = positions[['date','value']].groupby('date').sum(numeric_only=True).reset_index(drop=False)
        vposition1 = positions[['date','fee']].groupby('date').sum(numeric_only=True).reset_index(drop=False)
        vposition = vposition.merge(vposition1,how='left',on=['date'])
        vposition = vposition.merge(positions[['date','cash']].drop_duplicates(subset=['date']),how='left',on=['date'])
        vposition['amount'] = vposition['value']+vposition['cash']
        vposition['nav'] = vposition['amount']/init_amount
        tcname = 'g_%03d' %group_index
        t_datelist = vposition['date']
        
        navs = pd.DataFrame(columns=[tcname],index=datelist['date'])
        navs.loc[t_datelist,tcname] = vposition['nav'].values
        fees = pd.DataFrame(columns=[tcname],index=datelist['date'])
        fees.loc[t_datelist,tcname] = vposition['fee'].values
        
        return navs, fees

    def update_portfolio_g_position(self, table_names, **kwargs):
        '''This function updates the g_positions for factors and factor portfolios and writes to database.'''
        # config
        # logger = self.logger
        # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
        if table_names['isupdate']==0:
            return 0
            
        # fetch data
        table_list = ['g_positions_portfolio', 'g_positions_original_ai', 'g_positions_smart_beta', 'g_positions_index']
        if 'table_list' in kwargs.keys():
            table_list = kwargs['table_list']
        if table_names['update_pq_files']==2:
            if not hasattr(self, 'factor_testing_conn'):
                self.factor_testing_conn = conn2db('factor_testing_conn')
            # table list
            g_positions = pd.DataFrame()
            for itable in table_list:
                sqlstr = 'select * from %s;' %itable
                tdata = pd.read_sql(sqlstr, self.factor_testing_conn)
                tdata.to_parquet(self.g_positions_dir+'/%s.pq' %itable)
                g_positions = pd.concat([g_positions, tdata],axis=0)
        elif table_names['update_pq_files']==1:
            if not hasattr(self, 'factor_testing_conn'):
                self.factor_testing_conn = conn2db('factor_testing_conn')
            # table list
            g_positions = pd.DataFrame()
            for itable in table_list:
                odata = pd.read_parquet(self.g_positions_dir+'/%s.pq' %itable)
                last_date = odata['date'].max().strftime('%Y%m%d')
                sqlstr = 'select * from %s where date>%s;' %(itable, last_date)
                tdata = pd.read_sql(sqlstr, self.factor_testing_conn)
                if tdata.shape[0]>0:
                    tdata = pd.concat([odata,tdata],axis=0)
                    tdata.to_parquet(self.g_positions_dir+'/%s.pq' %itable)
                    g_positions = pd.concat([g_positions, tdata],axis=0)
                else:
                    g_positions = pd.concat([g_positions, odata],axis=0)
        elif table_names['update_pq_files']==0:
            g_positions = pd.DataFrame()
            for itable in table_list:
                odata = pd.read_parquet(self.g_positions_dir+'/%s.pq' %itable)
                g_positions = pd.concat([g_positions, odata],axis=0)
        self.g_positions = g_positions
        
        return 0
    
# In[]
if __name__=='__main__':
    # data directory, neutral / raw factors, dates and universes are set in settings.py
    root = DATA_DIR
    neu = NEU

    start_date = START_DATE
    end_date = END_DATE

    stock_status = pd.read_parquet(STOCK_STATUS)
    stock_market = pd.read_parquet(STOCK_MARKET)

    stock_status = stock_status[stock_status['date'] >= pd.to_datetime(start_date)]
    stock_market = stock_market[stock_market['date'] >= pd.to_datetime(start_date)]

    # float_mv (only needed by weighting='float_mv' universes) is a column of stock_market.pq;
    # it replaces the separate market_data/ashare_deri.pq of the original layout
    market_cols = ['date', 'stock_id', 'open', 'high', 'low', 'close', 'trade_status']
    if 'float_mv' in stock_market.columns:
        market_cols.append('float_mv')
    stock_market = stock_market[market_cols]
    stock_market = drop_excluded_stocks(stock_market)
    stock_status = stock_status.merge(stock_market, on=['date', 'stock_id'], how='inner')
    stock_status = stock_status.loc[~((stock_status['open'] == stock_status['high']) & (stock_status['open'] == stock_status['low']) & (stock_status['open'] == stock_status['close']))]
    stock_status = stock_status[(stock_status['trade_status'] == 1) & (stock_status['is_ST'] == 0)]

    factor_info = pd.read_excel(factors_dict_path())
    factor_info_copy = factor_info.copy()

    '''
    datelist = pd.read_parquet(f'{root}/config/datelist.pq')
    datelist['date'] = pd.to_datetime(datelist['date'])
    trading_days = pd.read_parquet(f'{root}/market_data/tradying_days.pq')
    trading_days['position_adjust_date'] = trading_days['date'].shift(-1)
    trading_days = trading_days.merge(datelist, on=['date'], how='inner')
    '''

    trading_days = pd.read_parquet(REBALANCE_DATES)

    def main_process(sample_symbol):        # 传入分域的symbol

        stock_status_sample = stock_status[['date', 'stock_id', sample_symbol, 'is_new_stock']]
        if UNIVERSES[sample_symbol]['exclude_new_stock']:
            stock_status_sample = stock_status_sample[stock_status_sample['is_new_stock'] == 0]
            del stock_status_sample['is_new_stock']
        else:
            del stock_status_sample['is_new_stock']

        for factor_name in factor_info['factor_name'].unique():
            print(f'{factor_name} begin!')

            try:

                factor_subset = pd.read_parquet(factor_path(factor_name))
                # conditions = [
                #     factor_subset['instrument'].str.startswith('6'),  # 上海 (主板, 科创板 688/689)
                #     factor_subset['instrument'].str.startswith('0'),  # 深圳 (主板, 中小板)
                #     factor_subset['instrument'].str.startswith('3'),  # 深圳 (创业板)
                #     factor_subset['instrument'].str.startswith('8'),  # 北京 (北交所)
                #     factor_subset['instrument'].str.startswith('4')   # 北京 (北交所, 老三板)
                # ]
                # 定义对应的选择（添加后缀）
                # choices = [
                #     factor_subset['instrument'] + '.SH',
                #     factor_subset['instrument'] + '.SZ',
                #     factor_subset['instrument'] + '.SZ',
                #     factor_subset['instrument'] + '.BJ',
                #     factor_subset['instrument'] + '.BJ'
                # ]
                # 应用规则，默认保持原样 (default=factor_subset['stock_id'])
                # factor_subset['instrument'] = np.select(conditions, choices, default=factor_subset['instrument'])
                factor_subset = factor_subset[['date', 'stock_id', 'factor_value']]
                factor_subset['date'] = pd.to_datetime(factor_subset['date'])
                factor_subset = factor_subset[factor_subset['date'] >= pd.to_datetime(start_date)]
                factor_subset = factor_subset.sort_values(by=['date', 'stock_id']).reset_index(drop=True)

            except Exception as e:
                print(f'{factor_name} skipped: {e!r}')
                continue
            if len(factor_subset) == 0:
                continue

            # stock_status_sample_copy = stock_status_sample.copy()
            # stock_status_sample_copy['stock_id'] = stock_status_sample_copy['stock_id'].str[:6]
            factor_subset = pd.merge(factor_subset, stock_status_sample, on=['date', 'stock_id'], how='left')

            factor_subset = factor_subset[factor_subset[sample_symbol] == 1]
            factor_subset = factor_subset.dropna(subset=['factor_value'])

            if factor_subset.shape[0] == 0:
                continue
            result_df = assign_groups_and_weights(factor_subset)
            result_df = result_df[['group_id', 'position_adjust_date', 'stock_id', 'weight']].rename(
                columns={'group_id': 'portfolio_id', 'position_adjust_date': 'date', 'stock_id': 'instrument'}).reset_index(drop=True).dropna(subset='date')

            result_df.to_parquet(ensure_parent(f'{root}/g_positions/g_positions_smart_beta.pq'))
            result_df.to_parquet(ensure_parent(f'{root}/g_positions/g_positions_testing{neu}/{sample_symbol}/g_positions_{factor_name}.pq'))

            obj_positions2nav = Positions2Nav(datadir=root)

            isupdate = {'frequency':2, 'ngroups':10, 'drawpic_1':0, 'drawpic_2':0}
            # obj_factortesting.config(isupdate, update_positions_files=1)
            obj_positions2nav.config(isupdate, special_date=pd.to_datetime(SPECIAL_DATE),start_date=start_date, end_date=end_date)

            # generate trading_dates
            isupdate_trading_dates = {'frequency':2, 'frequency_unit':'week', 'suffix2save':'100bp', 'test_type':0}
            datelist = obj_positions2nav.generate_trading_dates(isupdate_trading_dates)

            # fetch data
            isupdate_data = {'stock_prices':0,'index_prices':0,
                             'barra_exposure':0,'index_barra_exposure':0,
                             'index_exposure_daily':['zz500', 'zz1000', 'gz2000']}
            # index_list = ['hs300', 'zz500', 'zz1000', 'gz2000']
            obj_positions2nav.fetch_data(isupdate_data)

            # update portfolio g_position
            table_names = {'isupdate':1, 'update_pq_files':0}
            table_list = ['g_positions_smart_beta']
            obj_positions2nav.update_portfolio_g_position(table_names, table_list=table_list)

            # update portfolio navs
            isupdate_nav = {'isupdate':2, 'save':1, 'old_navs':'local'}
            obj_positions2nav.update_portfolio_navs(isupdate_nav)

            navs = pd.read_parquet(f'{root}/navs/navs.pq')
            navs.to_parquet(ensure_parent(f'{root}/navs/navs_testing{neu}/{sample_symbol}/navs_{factor_name}.pq'))

            plt.figure(figsize=(10, 6))

            for key, grp in navs.groupby('portfolio_id'):
                plt.plot(grp['date'], grp['nav'], label=f'Portfolio {key}')

            plt.title(f'{factor_name} nav')
            plt.xlabel('Date')
            plt.ylabel('NAV')
            plt.legend(title='Portfolio_id')
            plt.savefig(ensure_parent(f'{root}/pics/pics{neu}/{sample_symbol}/navs_{factor_name}.jpg'), dpi=300, bbox_inches='tight')
            plt.close()

            print(f'{factor_name} finish!')
            del factor_subset

            trading_days_in_year = DAYS_PER_YEAR
            # Apply the function to each portfolio_id
            result = (
                navs.groupby('portfolio_id')
                .apply(calculate_annualized_return, trading_days_in_year)
                .reset_index(name='sharpe')
            )

            result['original_rank'] = result['portfolio_id'].rank(method='first').astype(int)
            result['return_rank'] = result['sharpe'].rank(method='min', ascending=False)

            spearman_corr, _ = spearmanr(result['original_rank'], result['return_rank'])
            factor_info.loc[factor_info['factor_name'] == factor_name, sample_symbol] = round(spearman_corr, 2)
            print(spearman_corr)
        factor_info.to_excel(factors_dict_path(), index=False)

    # used for universes with weighting='float_mv' (originally only 'kc'): float_mv-weighted groups capped at WEIGHT_CAP
    def main_process_kc(sample_symbol):
        stock_status_sample = stock_status[['date', 'stock_id', sample_symbol, 'is_new_stock', 'float_mv']]

        #stock_status_sample = stock_status_sample[stock_status_sample['is_new_stock'] == 0]
        if UNIVERSES[sample_symbol]['exclude_new_stock']:
            stock_status_sample = stock_status_sample[stock_status_sample['is_new_stock'] == 0]
            del stock_status_sample['is_new_stock']
        else:
            del stock_status_sample['is_new_stock']
        stock_status_sample = stock_status_sample.dropna(subset='float_mv')

        for factor_name in factor_info['factor_name'].unique():
            print(f'{factor_name} begin!')

            try:

                # factor_subset = pd.read_parquet(root + f'/factor_data/factors{neu}/{factor_name}.pq')
                factor_subset = pd.read_parquet(factor_path(factor_name))
                # conditions = [
                #     factor_subset['instrument'].str.startswith('6'),  # 上海 (主板, 科创板 688/689)
                #     factor_subset['instrument'].str.startswith('0'),  # 深圳 (主板, 中小板)
                #     factor_subset['instrument'].str.startswith('3'),  # 深圳 (创业板)
                #     factor_subset['instrument'].str.startswith('8'),  # 北京 (北交所)
                #     factor_subset['instrument'].str.startswith('4')   # 北京 (北交所, 老三板)
                # ]
                # 定义对应的选择（添加后缀）
                # choices = [
                #     factor_subset['instrument'] + '.SH',
                #     factor_subset['instrument'] + '.SZ',
                #     factor_subset['instrument'] + '.SZ',
                #     factor_subset['instrument'] + '.BJ',
                #     factor_subset['instrument'] + '.BJ'
                # ]
                # 应用规则，默认保持原样 (default=factor_subset['stock_id'])
                # factor_subset['instrument'] = np.select(conditions, choices, default=factor_subset['instrument'])
                factor_subset = factor_subset[['date', 'stock_id', 'factor_value']]
                factor_subset['date'] = pd.to_datetime(factor_subset['date'])
                factor_subset = factor_subset[factor_subset['date'] >= pd.to_datetime(start_date)]
                factor_subset = factor_subset.sort_values(by=['date', 'stock_id']).reset_index(drop=True)

            except Exception as e:
                print(f'{factor_name} skipped: {e!r}')
                continue
            if len(factor_subset) == 0:
                continue

            factor_subset = pd.merge(factor_subset, stock_status_sample, on=['date', 'stock_id'], how='left')

            factor_subset = factor_subset[factor_subset[sample_symbol] == 1]
            factor_subset = factor_subset.dropna(subset=['factor_value'])

            if factor_subset.shape[0] == 0:
                continue
            result_df = assign_groups_and_weights(factor_subset)
            del result_df['weight']

            result_df = result_df.groupby(['group_id', 'date']).apply(calculate_weights).reset_index(drop=True)

            result_df = result_df.sort_values(by=['group_id', 'date']).reset_index(drop=True)

            result_df = result_df[['group_id', 'position_adjust_date', 'stock_id', 'weight']].rename(
                columns={'group_id': 'portfolio_id', 'position_adjust_date': 'date', 'stock_id': 'instrument'}).reset_index(drop=True).dropna(subset='date')

            result_df.to_parquet(ensure_parent(f'{root}/g_positions/g_positions_smart_beta.pq'))
            result_df.to_parquet(ensure_parent(f'{root}/g_positions/g_positions_testing{neu}/{sample_symbol}/g_positions_{factor_name}.pq'))

            obj_positions2nav = Positions2Nav(datadir=root)

            isupdate = {'frequency':1, 'ngroups':5, 'drawpic_1':0, 'drawpic_2':0}
            # obj_factortesting.config(isupdate, update_positions_files=1)
            obj_positions2nav.config(isupdate, special_date=pd.to_datetime(SPECIAL_DATE),start_date=start_date, end_date=end_date)

            # generate trading_dates
            isupdate_trading_dates = {'frequency':1, 'frequency_unit':'month', 'suffix2save':'100bp', 'test_type':1}
            datelist = obj_positions2nav.generate_trading_dates(isupdate_trading_dates)


            # fetch data
            isupdate_data = {'stock_prices':0,'index_prices':0,
                             'barra_exposure':0,'index_barra_exposure':0,
                             'index_exposure_daily':['zz500', 'zz1000', 'gz2000']}
            # index_list = ['hs300', 'zz500', 'zz1000', 'gz2000']
            obj_positions2nav.fetch_data(isupdate_data)

            # update portfolio g_position
            table_names = {'isupdate':1, 'update_pq_files':0}
            table_list = ['g_positions_smart_beta']
            obj_positions2nav.update_portfolio_g_position(table_names, table_list=table_list)

            # update portfolio navs
            isupdate_nav = {'isupdate':2, 'save':1, 'old_navs':'local'}
            obj_positions2nav.update_portfolio_navs(isupdate_nav)

            navs = pd.read_parquet(f'{root}/navs/navs.pq')
            navs.to_parquet(ensure_parent(f'{root}/navs/navs_testing{neu}/{sample_symbol}/navs_{factor_name}.pq'))

            plt.figure(figsize=(10, 6))

            for key, grp in navs.groupby('portfolio_id'):
                plt.plot(grp['date'], grp['nav'], label=f'Portfolio {key}')

            plt.title(f'{factor_name} nav')
            plt.xlabel('Date')
            plt.ylabel('NAV')
            plt.legend(title='Portfolio_id')
            plt.savefig(ensure_parent(f'{root}/pics/pics{neu}/{sample_symbol}/navs_{factor_name}.jpg'), dpi=300, bbox_inches='tight')
            plt.close()

            print(f'{factor_name} finish!')
            del factor_subset

            trading_days_in_year = DAYS_PER_YEAR
            # Apply the function to each portfolio_id
            result = (
                navs.groupby('portfolio_id')
                .apply(calculate_annualized_return, trading_days_in_year)
                .reset_index(name='sharpe')
            )

            result['original_rank'] = result['portfolio_id'].rank(method='first').astype(int)
            result['return_rank'] = result['sharpe'].rank(method='min', ascending=False)

            spearman_corr, _ = spearmanr(result['original_rank'], result['return_rank'])
            factor_info.loc[factor_info['factor_name'] == factor_name, sample_symbol] = round(spearman_corr, 2)
            print(spearman_corr)
        factor_info.to_excel(factors_dict_path(), index=False)


    for universe, params in UNIVERSES.items():
        if params['weighting'] == 'float_mv':
            main_process_kc(universe)
        else:
            main_process(universe)