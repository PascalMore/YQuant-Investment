import QUANTAXIS as qa
import pandas as pd
import numpy as np
import datetime
import importlib
from dateutil.relativedelta import relativedelta
#===import db_utils
import os, sys
sys.path.append( os.path.abspath(os.path.join('..', '..', 'base', 'utils')) )
import mongodb_utils
#==================
class Logger(object):
    def __init__(self, filename="strategy.log"):
        self.terminal = sys.stdout
        self.log = open(filename, "a")
 
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
 
    def flush(self):
        pass

qa.QA_util_log_info('QUANTAXIS Version: ' + qa.__version__)
# 近6个月的数据作为策略输入
CONST_PARAM_START_MON = 3
CONST_PARAM_ASSET_LABEL = 'asset_label'
CONST_PARAM_ASSET_INDICATOR = 'asset_indicator'
# 近3年的行情数据作为策略数据
CONST_PARAM_MARKET_START_YEAR = 3
# 需要生产的标签列表
strategy_list = [
    'BottomLaunch',
    #'TrendBack',
    'ShockBottom',
    'OppositeTrend'
    ]

def main():
    #如果是周末则不运行
    wk = datetime.datetime.now().weekday() + 1
    if wk == 6 or wk ==7:
        print('周{}不执行策略'.format(wk))
        return 0
    
    td = datetime.date.today()
    #td = datetime.date(2024, 9, 25)
    td_last_6m = td - relativedelta(months=CONST_PARAM_START_MON)
    # 0.获取全市场股票列表及今天的行情数据
    tot_stk_list = qa.QA_fetch_stock_list_adv().index.tolist()
    stk_market_data = qa.QA_fetch_stock_day_adv(tot_stk_list, td, td)
    # 判断是否获取到最新数据，如果没有获取则直接返回
    if stk_market_data is None:
        print('未能获取最新日期({})的行情数据'.format(td))
        return 0

    # 0.1 获取近3年行情数据作为输入
    td_last_3y = td - relativedelta(years=CONST_PARAM_MARKET_START_YEAR)
    stk_market_data = qa.QA_fetch_stock_day_adv(tot_stk_list, td_last_3y, td)
    # 1. 获取策略输入标签数据
    #stk_label_data = mongodb_utils.get_labeldata(CONST_PARAM_ASSET_LABEL, {
    #    'label_date': {'$gte': td_last_6m.strftime("%Y-%m-%d"), '$lte': td.strftime("%Y-%m-%d")}
    #    })
    stk_label_data = pd.DataFrame()
    for i in range(1, CONST_PARAM_START_MON+1):
        if i == CONST_PARAM_START_MON:
            print('[{},{}]'.format( td - relativedelta(months=CONST_PARAM_START_MON - i + 1), td - relativedelta(months=CONST_PARAM_START_MON - i)))
            tmp_label_data = mongodb_utils.get_labeldata(CONST_PARAM_ASSET_LABEL, {
                'label_date': {'$gte': (td - relativedelta(months=CONST_PARAM_START_MON - i + 1)).strftime("%Y-%m-%d"), '$lte': (td - relativedelta(months=CONST_PARAM_START_MON - i)).strftime("%Y-%m-%d")}
                })
            if len(stk_label_data) == 0:
                stk_label_data = tmp_label_data
            else:
                stk_label_data = pd.concat([stk_label_data, tmp_label_data], ignore_index=True)
        else:
            print('[{},{})'.format(td - relativedelta(months=CONST_PARAM_START_MON - i + 1), td - relativedelta(months=CONST_PARAM_START_MON - i)))
            tmp_label_data = mongodb_utils.get_labeldata(CONST_PARAM_ASSET_LABEL, {
                'label_date': {'$gte': (td - relativedelta(months=CONST_PARAM_START_MON - i + 1)).strftime("%Y-%m-%d"), '$lt': (td - relativedelta(months=CONST_PARAM_START_MON - i)).strftime("%Y-%m-%d")}
                })
            if len(stk_label_data) == 0:
                stk_label_data = tmp_label_data
            else:
                stk_label_data = pd.concat([stk_label_data, tmp_label_data], ignore_index=True)
    #print(stk_label_data)
    #2. 获取策略输入指标数据
    stk_ind_data = pd.DataFrame()
    stk_ind_data = mongodb_utils.get_labeldata(CONST_PARAM_ASSET_INDICATOR, {
        'indicator_date': {'$gte': (td - relativedelta(months=CONST_PARAM_START_MON)).strftime("%Y-%m-%d"), '$lte': td.strftime("%Y-%m-%d")}
    })
    qa.QA_util_log_info('成功获取[{}, {}]标签数据{}条,指标数据{}条'.format(td_last_6m.strftime("%Y-%m-%d"), td.strftime("%Y-%m-%d"), len(stk_label_data), len(stk_ind_data)))
    # 2.执行每日的策略
    for l in strategy_list:
        print("正在执行{}的[{}]策略...".format(td, l))
        strategy_exe = importlib.import_module('strategy_{}'.format(l))
        res = strategy_exe.run_strategy(td, {'basic_pool': True, 'index_sw_level2': True}, stk_label_data, stk_ind_data, stk_market_data)
        if res == 0:
            print("执行{}的[{}]策略成功".format(td, l))
        else:
            print("执行{}的[{}]策略失败".format(td, l))

if __name__ == '__main__':
    main()

