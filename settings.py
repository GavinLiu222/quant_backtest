# -*- coding: utf-8 -*-
"""
回测框架的全部可调参数。修改这里即可，不需要改动各脚本。

数据文件的目录与格式规则见 data_spec.py 和 README.md。
"""
import os

# ---------------------------------------------------------------------------
# 数据根目录
# ---------------------------------------------------------------------------
# 优先读取环境变量 BACKTEST_DATA_DIR；未设置时使用仓库下的 data/ 目录。
DATA_DIR = os.environ.get(
    'BACKTEST_DATA_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))

# ---------------------------------------------------------------------------
# 回测区间
# ---------------------------------------------------------------------------
START_DATE = '20200930'      # 回测开始日 (YYYYMMDD)
END_DATE = '20250630'        # 回测结束日 (YYYYMMDD)
SPECIAL_DATE = '20241231'    # 统计指标 ret_special_date / adv_navs_fsd 的起点，必须是区间内的交易日

# ---------------------------------------------------------------------------
# 因子是否中性化
# ---------------------------------------------------------------------------
# True : 先运行 factor_neutralize.py 生成 factor_data/factors_neutral/，
#        后续步骤读取中性化因子，配置表使用 *_neutral.xlsx，结果目录带 _neutral 后缀
# False: 直接使用 factor_data/factors/ 下的原始因子
NEUTRAL = False

# ---------------------------------------------------------------------------
# 股票池 (universe)
# ---------------------------------------------------------------------------
# 键 = 股票池名称，必须与 market_data/stock_status.pq 中对应的 0/1 标记列同名。
#   benchmark         : 基准指数代码，必须是 market_data/index_prices.pq 的一列
#   top_n             : positions2nav_update.py 构建因子多头组合时的持股数
#   weighting         : 'equal'    等权
#                       'float_mv' 按流通市值加权，单票权重上限 WEIGHT_CAP（需要 stock_market.pq 含 float_mv 列）
#   exclude_new_stock : 是否剔除次新股 (stock_status.pq 中 is_new_stock == 1)
#   barra_sheet       : 仅 BARRA_RENAME = True 时使用，对应 portfolio_info 中的 sheet '软约束限BARRA_{barra_sheet}_01'
# 不需要的股票池直接删除或注释掉对应行即可。
UNIVERSES = {
    'hs300':  {'benchmark': '000300.SH', 'top_n': 100, 'weighting': 'equal',    'exclude_new_stock': True,  'barra_sheet': '300'},
    'zz500':  {'benchmark': '000905.SH', 'top_n': 150, 'weighting': 'equal',    'exclude_new_stock': True,  'barra_sheet': '500'},
    'zz1000': {'benchmark': '000852.SH', 'top_n': 300, 'weighting': 'equal',    'exclude_new_stock': True,  'barra_sheet': '1000'},
    'winda':  {'benchmark': '000852.SH', 'top_n': 300, 'weighting': 'equal',    'exclude_new_stock': True,  'barra_sheet': 'winda'},
    'kc':     {'benchmark': '000680.SH', 'top_n': 100, 'weighting': 'float_mv', 'exclude_new_stock': False, 'barra_sheet': 'kc'},
}

# ---------------------------------------------------------------------------
# 回测参数
# ---------------------------------------------------------------------------
N_GROUPS = 10            # 分组回测的组数，组合编号为 1000 .. 1000+N_GROUPS-1（1000 = 因子值最小的一组）
INIT_AMOUNT = 1e7        # 初始资金
FEE_RATE = 1.5e-3        # 单边交易费率（按调仓金额收取）
WEIGHT_CAP = 0.05        # weighting='float_mv' 时的单票权重上限
DAYS_PER_YEAR = 242      # 年化用的年交易日数（A股 242；美股等可改为 252）

# ---------------------------------------------------------------------------
# 中性化
# ---------------------------------------------------------------------------
INDUSTRY_PREFIX = 'ind_'  # stock_status.pq 中行业哑变量列的统一前缀

# ---------------------------------------------------------------------------
# 股票代码清洗（原框架针对 A 股 Wind 代码的规则）
# ---------------------------------------------------------------------------
# 代码以这些后缀/前缀结尾/开头、或在 EXCLUDE_IDS 中的股票会被剔除。
# 使用美股等其他市场数据时请全部改为空元组 ()，否则例如 'AAPL' 会因前缀 'A' 被剔除。
EXCLUDE_ID_SUFFIXES = ('.BJ', '.NE', '.WI')   # 北交所、新三板、Wind 指数
EXCLUDE_ID_PREFIXES = ('A',)
EXCLUDE_IDS = ('000024.SZ',)

# ---------------------------------------------------------------------------
# nav2stats.py
# ---------------------------------------------------------------------------
# True 时用 portfolio_info 中 sheet '软约束限BARRA_{barra_sheet}_01' 的
# (original_portfolio -> portfolio_name) 映射重命名输出中的组合名。
BARRA_RENAME = False
