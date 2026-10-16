import pymongo
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
#===import db_utils
import os, sys
sys.path.append( os.path.abspath(os.path.join('..', '..', 'base', 'utils')) )
import mongodb_utils
#==================
CONST_PARAM_LABEL_ID_1st_maxdd = '1st_maxdd'
CONST_PARAM_LABEL_ID_2nd_maxdd = '2nd_maxdd'
CONST_PARAM_LABEL_ID_3th_maxdd = '3th_maxdd'
CONST_PARAM_LABEL_ID_4th_maxdd = '4th_maxdd'
CONST_PARAM_LABEL_ID_5th_maxdd = '5th_maxdd'
CONST_PARAM_LABEL_ID_dyn_maxdd = 'dyn_maxdd_last2y' # 2022/1/2修正为近两年的动态回撤
CONST_PARAM_LABEL_ID_vol_level_last2w = 'vol_level_last2w'
CONST_PARAM_LABEL_ID_vol_trend_last2w = 'vol_trend_last2w'
#CONST_PARAM_LABEL_ID_vol_level_last6m = 'vol_level_last6m'
CONST_PARAM_LABEL_ID_trend = 'trend'
CONST_PARAM_LABEL_ID_boll_level_last2w = 'boll_level_last2w'
CONST_PARAM_LABEL_ID = 'label_id'
CONST_PARAM_ASSET_ID = 'asset_id'
CONST_PARAM_LABEL_DATE = 'label_date'
CONST_PARAM_LABEL_VALUE = 'value'
CONST_PARAM_STRATEGY_EXECUTION = 'strategy_execution'
CONST_STRATEGY_ID = 'BottomLaunch'
CONST_STRATEGY_NAME = '底部启动策略'
CONST_PARAM_VOL_TREND_threshold = 0.28
CONST_PARAM_MAXDD_threshold = 0.05
CONST_PARAM_MAXDD_min_threshold = 0.1
CONST_PARAM_VOL_LEVEL_up_threshold = 1.75
#CONST_PARAM_VOL_LEVEL_down_threshold = 0.95
CONST_PARAM_VOL_BOLL_threshold = 2

def pre_processor(data, conf):
    if(('basic_pool' in conf) and conf['basic_pool']):
        stk_list = mongodb_utils.get_asset_pool('基础池')
        print('[Basic Pool]:')
        print(stk_list)
        data = data.loc[data[CONST_PARAM_ASSET_ID].isin(stk_list[CONST_PARAM_ASSET_ID].tolist())]
    elif (('important_pool' in conf) and conf['important_pool']):
        stk_list = mongodb_utils.get_asset_pool('重点池')
        print('[Important Pool]:')
        print(stk_list)
        data = data.loc[data[CONST_PARAM_ASSET_ID].isin(stk_list[CONST_PARAM_ASSET_ID].tolist())]
    elif (('deepvalue_pool' in conf) and conf['deepvalue_pool']):
        stk_list = mongodb_utils.get_asset_pool('策略-深度价值')
        print('[Deepvalue Pool]:')
        print(stk_list)
        data = data.loc[data[CONST_PARAM_ASSET_ID].isin(stk_list[CONST_PARAM_ASSET_ID].tolist())]
    return data

def run_strategy(td, conf, label_data, ind_data=None, market_data=None):
    #0. 定义指标数据
    df_indicator = pd.DataFrame()
    #1. 按照conf对数据进行预处理
    data_pro = pre_processor(label_data, conf)
    td_last_2w = data_pro.loc[data_pro[CONST_PARAM_LABEL_DATE] <= (td - relativedelta(weeks=2)).strftime("%Y-%m-%d"), CONST_PARAM_LABEL_DATE].max()
    #2. 获取今天的所有标签数据
    label_data_td = data_pro.loc[data_pro[CONST_PARAM_LABEL_DATE] == td.strftime("%Y-%m-%d")]
    label_data_2w = data_pro.loc[data_pro[CONST_PARAM_LABEL_DATE] == td_last_2w]
    #3. 策略条件
    #Cond 1) 当前的动态回撤，在历史前3大回撤均值的正负[-5%, 10%]之间
    #FIX: 2012/01/02, 为了避免股价反弹很多，才被筛选出来，策略做如下修正：a) 历史前5大回撤变为历史前3大回撤 b) 当前动态回撤，改成近2年动态回撤
    
    #tmpdf_dd = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_1st_maxdd, CONST_PARAM_LABEL_ID_2nd_maxdd, CONST_PARAM_LABEL_ID_3th_maxdd, CONST_PARAM_LABEL_ID_4th_maxdd, CONST_PARAM_LABEL_ID_5th_maxdd])].copy()
    tmpdf_dd = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_1st_maxdd, CONST_PARAM_LABEL_ID_2nd_maxdd, CONST_PARAM_LABEL_ID_3th_maxdd])].copy()
    tmpdf_dd.loc[:, CONST_PARAM_LABEL_VALUE] = tmpdf_dd[CONST_PARAM_LABEL_VALUE].astype('float')
    # 过滤掉最大回撤小于10%的记录
    tmpdf_dd = tmpdf_dd[tmpdf_dd[CONST_PARAM_LABEL_VALUE] >= CONST_PARAM_MAXDD_min_threshold]
    tmpdf_dd = tmpdf_dd.groupby(CONST_PARAM_ASSET_ID)[CONST_PARAM_LABEL_VALUE].mean()
    df_indicator = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID] == CONST_PARAM_LABEL_ID_dyn_maxdd, [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    df_indicator = df_indicator.loc[df_indicator.apply(lambda x: x[CONST_PARAM_ASSET_ID] in tmpdf_dd and tmpdf_dd[x[CONST_PARAM_ASSET_ID]] - CONST_PARAM_MAXDD_threshold <= x[CONST_PARAM_LABEL_VALUE] <= tmpdf_dd[x[CONST_PARAM_ASSET_ID]] + 2 * CONST_PARAM_MAXDD_threshold, axis=1)]
    df_indicator.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_dyn_maxdd},  inplace=True)
    print(1)
    print(df_indicator)
    #Cond 2) 近2周交易额水平在1.75以上
    tmpdf_dd = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_vol_level_last2w, CONST_PARAM_LABEL_ID_vol_trend_last2w])].copy()
    tmpdf_dd.loc[:, CONST_PARAM_LABEL_VALUE] = tmpdf_dd[CONST_PARAM_LABEL_VALUE].astype('float')
    tmpdf_dd = tmpdf_dd.pivot(index=CONST_PARAM_ASSET_ID, columns=CONST_PARAM_LABEL_ID, values=CONST_PARAM_LABEL_VALUE)
    tmpdf_dd = tmpdf_dd[(tmpdf_dd[CONST_PARAM_LABEL_ID_vol_level_last2w] >= CONST_PARAM_VOL_LEVEL_up_threshold)]
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(2)
    print(df_indicator)
    #Cond 3) 近1个月趋势上涨或者震荡
    tmpdf_dd = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_trend])].copy()
    tmpdf_dd = tmpdf_dd.loc[tmpdf_dd[CONST_PARAM_LABEL_VALUE].isin(['close_1m_上涨', 'close_1m_无趋势']), [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    tmpdf_dd.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_trend + '_1m'},  inplace=True)
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(3)
    print(df_indicator)
    #Cond 4) 当前布林开口较2周前水平 大于等于1.75
    tmpdf_dd = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_boll_level_last2w])].copy()
    tmpdf_dd.loc[:, CONST_PARAM_LABEL_VALUE] = tmpdf_dd[CONST_PARAM_LABEL_VALUE].astype('float')
    tmpdf_dd = tmpdf_dd.loc[tmpdf_dd[CONST_PARAM_LABEL_VALUE] >= CONST_PARAM_VOL_BOLL_threshold, [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    tmpdf_dd.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_boll_level_last2w},  inplace=True)
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(4)
    print(df_indicator)
    # Cond 5) 2周前的近6个月趋势是震荡或者下跌
    tmpdf_dd = label_data_2w.loc[label_data_2w[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_trend])].copy()
    tmpdf_dd = tmpdf_dd.loc[tmpdf_dd[CONST_PARAM_LABEL_VALUE].isin(['close_6m_下跌', 'close_6m_无趋势']), [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    tmpdf_dd.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_trend + '_6m'},  inplace=True)
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(5)
    print(df_indicator)
    #tmpdf_dd = label_data_2w.loc[label_data_2w[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_vol_level_last6m])].copy()
    #tmpdf_dd.loc[:, CONST_PARAM_LABEL_VALUE] = tmpdf_dd[CONST_PARAM_LABEL_VALUE].astype('float')
    #tmpdf_dd = tmpdf_dd.loc[(tmpdf_dd[CONST_PARAM_LABEL_VALUE] <= CONST_PARAM_VOL_LEVEL_down_threshold), [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    #tmpdf_dd.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_vol_level_last6m},  inplace=True)
    # 条件求并
    #df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)

    # 4. 将选股结果保存
    strategy_execution = pd.DataFrame(columns=('strategy_id', 'strategy_name', 'exe_date', 'strategy_res', 'update_timestamp', 'user'))
    strategy_execution = strategy_execution.append({
        'strategy_id': CONST_STRATEGY_ID,
        'strategy_name': CONST_STRATEGY_NAME,
        'exe_date':  td.strftime("%Y-%m-%d"),
        'strategy_res': df_indicator.to_dict('records')
    }, ignore_index=True)
    mongodb_utils.insert_stra_exe(CONST_PARAM_STRATEGY_EXECUTION, strategy_execution)

    return 0

def main():

    print("run_strategy: BottomLaunch")

if __name__ == '__main__':
    main()
