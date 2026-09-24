# -*- coding: utf-8 -*-
import os
import pandas as pd
import numpy as np
# sqlalchemy is imported inside conn2db: it is only needed when actually pulling
# from the Wind/market databases, and a pure backtest over pre-materialised data
# should not require the driver stack to be installed at all.

# import pdb

# Logical database name -> environment variable holding the FULL SQLAlchemy URI.
# Credentials, hosts and ports are NEVER stored in source. Each user exports
# their own, e.g.:
#   export QUANT_DB_MARKET="mysql+pymysql://user:password@host:3306/market?charset=utf8"
#   export QUANT_DB_WIND="mssql+pyodbc://user:password@host:1433/master?driver=SQL+Server"
# If you run the framework fully offline from local parquet caches (set the
# various ``isupdate`` flags to 0), no database is needed and conn2db is never
# called.
_DB_ENV = {
    'wind_conn':           'QUANT_DB_WIND',
    'info_conn':           'QUANT_DB_INFO',
    'zyyxbk_conn':         'QUANT_DB_ZYYXBK',
    'market_conn':         'QUANT_DB_MARKET',
    'factors_conn':        'QUANT_DB_FACTORS',
    'factor_testing_conn': 'QUANT_DB_FACTOR_TESTING',
    'factors_2024_conn':   'QUANT_DB_FACTORS_2024',
}


def conn2db(dbname):
    """Return a SQLAlchemy connection for a logical database name.

    The connection URI is read from an environment variable (see _DB_ENV);
    nothing sensitive is hard-coded. Provide your own data source, or run the
    backtest offline (isupdate=0) against local parquet files.
    """
    from sqlalchemy import create_engine   # lazy: only the DB path needs it
    env_name = _DB_ENV.get(dbname)
    if env_name is None:
        raise ValueError(f"Unknown database name: {dbname!r}. Known: {list(_DB_ENV)}")
    uri = os.environ.get(env_name)
    if not uri:
        raise RuntimeError(
            f"Environment variable {env_name} is not set. Export it with your own "
            f"connection URI, or run offline (isupdate=0) using local parquet files."
        )
    return create_engine(uri).connect()


def update_tradying_days():
    # update trading_days from wind database to market_data/trading_days.pq (see data_spec.py)
    import os, datetime
    from data_spec import TRADING_DAYS, ensure_parent
    # fetch from wind
    wind_conn = conn2db('wind_conn')
    sqlstr = "select TRADE_DAYS as date, S_INFO_EXCHMARKET from WANDE.wande.dbo.ASHARECALENDAR where S_INFO_EXCHMARKET='SSE';"
    tradying_days = pd.read_sql(sqlstr ,wind_conn).sort_values('date')
    tradying_days['date'] = pd.to_datetime(tradying_days['date'])
    current_year = datetime.datetime.now().year
    tradying_days = tradying_days[tradying_days['date'].dt.year<=(current_year+1)]
    tradying_days = tradying_days[['date']]
    
    # save
    tradying_days.to_parquet(ensure_parent(TRADING_DAYS))
    
    return tradying_days


def statistics_core_1(special_date, navs, index_prices, benchmark_code,
                      days_per_year=242):
    '''This function makes statistics from navs_comb.

    `days_per_year` annualises the return and volatility figures. It stays at
    242 for the A-share calendar this framework was written against; pass 252
    for US sessions, otherwise annualised return and volatility are quietly
    understated by about 4%.
    '''
    # config
    # logger = self.logger
    # logger.info("----------------Start %s.%s().----------------" %(self.__class__.__name__,inspect.stack()[0][3]))
    # statistics
    factor_statistic = pd.DataFrame()
    factor_statistic['portfolio_id'] = navs.columns
    factor_statistic['trading_days'] = navs.shape[0]
    factor_statistic['ret_in_period'] = (navs.iloc[-1,:]-1).values*100
    idx_spc = navs.index.tolist().index(special_date)
    factor_statistic['ret_special_date'] = (navs.iloc[-1,:]/navs.iloc[idx_spc,:]-1).values*100
    if navs.shape[0]>days_per_year:
        factor_statistic['ret_recent1year'] = (navs.iloc[-1,:]/navs.iloc[-days_per_year,:]-1).values*100
    else:
        factor_statistic['ret_recent1year'] = np.nan
    if navs.shape[0]>121:
        factor_statistic['ret_recent6month'] = (navs.iloc[-1,:]/navs.iloc[-121,:]-1).values*100
    else:
        factor_statistic['ret_recent6month'] = np.nan
    if navs.shape[0]>64:
        factor_statistic['ret_recent3month'] = (navs.iloc[-1,:]/navs.iloc[-64,:]-1).values*100
    else:
        factor_statistic['ret_recent3month'] = np.nan
    factor_statistic['ret_recent1month'] = (navs.iloc[-1,:]/navs.iloc[-22,:]-1).values*100
    factor_statistic['ret_recent1week'] = (navs.iloc[-1,:]/navs.iloc[-6,:]-1).values*100
    factor_statistic['ret_recent3day'] = (navs.iloc[-1,:]/navs.iloc[-4,:]-1).values*100
    factor_statistic['ret_recent2day'] = (navs.iloc[-1,:]/navs.iloc[-3,:]-1).values*100
    factor_statistic['ret_recent1day'] = (navs.iloc[-1,:]/navs.iloc[-2,:]-1).values*100
    factor_statistic['annualized_ret'] = (navs.iloc[-1,:]**(days_per_year/navs.shape[0])-1).values*100
    factor_statistic['volatility'] = (np.log(navs).diff().std()*np.sqrt(days_per_year)).values*100
    factor_statistic['max_draw_down'] = (1-(navs/navs.cummax()).min()).values*100
    
    if len(benchmark_code)>0:
        # fetch index prices
        index_prices = index_prices[benchmark_code]
        index_rets = index_prices.pct_change()
        # adv_navs
        portfolio_rets = navs.pct_change()
        adv_navs = portfolio_rets.sub(index_rets.loc[portfolio_rets.index].values,axis=0)
        adv_navs.iloc[0,:] = 0
        adv_navs = (adv_navs+1).cumprod()
        # adv_navs.loc[adv_navs.index, icol] = adv_navs.loc[adv_navs.index,icol]
        
        # advanced return
        adv_statistic = pd.DataFrame()
        adv_statistic['portfolio_id'] = adv_navs.columns
        if navs.shape[0]>days_per_year:
            adv_statistic['adv_ret_recent1year'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-days_per_year,:]-1).values*100
        else:
            adv_statistic['adv_ret_recent1year'] = np.nan
        if navs.shape[0]>121:
            adv_statistic['adv_ret_recent6month'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-121,:]-1).values*100
        else:
            adv_statistic['adv_ret_recent6month'] = np.nan
        if navs.shape[0]>64:
            adv_statistic['adv_ret_recent3month'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-64,:]-1).values*100
        else:
            adv_statistic['adv_ret_recent3month'] = np.nan
        adv_statistic['adv_ret_recent1month'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-22,:]-1).values*100
        adv_statistic['adv_ret_recent1week'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-6,:]-1).values*100
        adv_statistic['adv_ret_recent3day'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-4,:]-1).values*100
        adv_statistic['adv_ret_recent2day'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-3,:]-1).values*100
        adv_statistic['adv_ret_recent1day'] = (adv_navs.iloc[-1,:]/adv_navs.iloc[-2,:]-1).values*100
        adv_statistic['annualized_adv_ret'] = (adv_navs.iloc[-1,:]**(days_per_year/adv_navs.shape[0])-1).values*100
        adv_statistic['adv_volatility'] = (np.log(adv_navs).diff().std()*np.sqrt(days_per_year)).values*100
        adv_statistic['adv_max_draw_down'] = (1-(adv_navs/adv_navs.cummax()).min()).values*100
        adv_statistic['adv_volatility_recent3month'] = (np.log(adv_navs.iloc[-64:,:]).diff().std()*np.sqrt(days_per_year)).values*100
        adv_statistic['adv_max_draw_down_recent3month'] = (1-(adv_navs.iloc[-64:,:]/adv_navs.iloc[-64:,:].cummax()).min()).values*100
        adv_statistic['adv_volatility_recent1month'] = (np.log(adv_navs.iloc[-21:,:]).diff().std()*np.sqrt(days_per_year)).values*100
        adv_statistic['adv_max_draw_down_recent1month'] = (1-(adv_navs.iloc[-21:,:]/adv_navs.iloc[-21:,:].cummax()).min()).values*100
        adv_statistic['adv_volatility_recent1week'] = (np.log(adv_navs.iloc[-5:,:]).diff().std()*np.sqrt(days_per_year)).values*100
        adv_statistic['adv_max_draw_down_recent1week'] = (1-(adv_navs.iloc[-5:,:]/adv_navs.iloc[-5:,:].cummax()).min()).values*100
        factor_statistic = factor_statistic.merge(adv_statistic, how='left', on=['portfolio_id'])
        
        # information ratio
        factor_statistic['information_ratio'] = factor_statistic['annualized_adv_ret']/factor_statistic['adv_volatility']
        factor_statistic['return_mdd_ratio'] = factor_statistic['annualized_adv_ret']/factor_statistic['adv_max_draw_down']
        factor_statistic['information_ratio_r3month'] = factor_statistic['adv_ret_recent3month']/factor_statistic['adv_volatility']*days_per_year/63
        factor_statistic['return_mdd_ratio_r3month'] = factor_statistic['adv_ret_recent3month']/factor_statistic['adv_max_draw_down']*days_per_year/63
        factor_statistic['information_ratio_recent3month'] = factor_statistic['adv_ret_recent3month']/factor_statistic['adv_volatility_recent3month']*days_per_year/63
        factor_statistic['return_mdd_ratio_recent3month'] = factor_statistic['adv_ret_recent3month']/factor_statistic['adv_max_draw_down_recent3month']*days_per_year/63
        factor_statistic['information_ratio_recent1month'] = factor_statistic['adv_ret_recent1month']/factor_statistic['adv_volatility_recent1month']*days_per_year/21
        factor_statistic['return_mdd_ratio_recent1month'] = factor_statistic['adv_ret_recent1month']/factor_statistic['adv_max_draw_down_recent1month']*days_per_year/21
        factor_statistic['information_ratio_recent1week'] = factor_statistic['adv_ret_recent1week']/factor_statistic['adv_volatility_recent1week']*days_per_year/5
        factor_statistic['return_mdd_ratio_recent1week'] = factor_statistic['adv_ret_recent1week']/factor_statistic['adv_max_draw_down_recent1week']*days_per_year/5
    
        # reformate
        factor_statistic = factor_statistic.sort_values(by=['information_ratio_r3month'],ascending=False).reset_index(drop=True)
    
    return factor_statistic