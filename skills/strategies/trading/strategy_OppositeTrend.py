import pymongo
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
#===import db_utils
import os, sys
sys.path.append( os.path.abspath(os.path.join('..', '..', 'base', 'utils')) )
import mongodb_utils
#==================
CONST_PARAM_ASSET_ID = 'asset_id'
CONST_PARAM_ASSET_CODE = 'code'
CONST_PARAM_IND_pct_chg = 'pct_chg_td'
CONST_PARAM_START_MON = 2
CONST_PARAM_RES_NUM = 30
CONST_STRATEGY_ID_STRONG = 'OppositeTrendStrong'
CONST_STRATEGY_ID_WEAK = 'OppositeTrendWeak'
CONST_STRATEGY_NAME_STRONG = '逆势走强'
CONST_STRATEGY_NAME_WEAK = '逆势走弱'
CONST_PARAM_STRATEGY_EXECUTION = 'strategy_execution'

def pre_processor(data, conf):
    t_list = []
    if(('basic_pool' in conf) and conf['basic_pool']):
        stk_list = mongodb_utils.get_asset_pool('基础池')
        print('[Basic Pool]:')
        print(stk_list)
        t_list.extend(stk_list[CONST_PARAM_ASSET_ID].tolist())
    elif (('important_pool' in conf) and conf['important_pool']):
        stk_list = mongodb_utils.get_asset_pool('重点池')
        print('[Important Pool]:')
        print(stk_list)
        t_list.extend(stk_list[CONST_PARAM_ASSET_ID].tolist())
    elif (('deepvalue_pool' in conf) and conf['deepvalue_pool']):
        stk_list = mongodb_utils.get_asset_pool('策略-深度价值')
        print('[Deepvalue Pool]:')
        print(stk_list)
        t_list.extend(stk_list[CONST_PARAM_ASSET_ID].tolist())

    if(('index_sw_level2' in conf) and conf['index_sw_level2']):
        index_list = mongodb_utils.get_indexlist({'sse': 'sw', 'decimal_point': 2})
        print('[Sw Level2]:')
        print(index_list)
        t_list.extend(index_list[CONST_PARAM_ASSET_CODE].tolist())

    data = data.loc[data[CONST_PARAM_ASSET_ID].isin(t_list)]
    return data

def run_strategy(td, conf, label_data, ind_data=None, market_data=None):
    #0. 定义指标数据
    df_indicator = pd.DataFrame(columns=('exe_date', 'asset_id', 'index_id', 'skew'))
    #1. 按照conf对数据进行预处理
    data_pro = pre_processor(ind_data, conf)
    #1.1 过滤出近两个月的数据
    start_d = td - relativedelta(months=CONST_PARAM_START_MON)
    data_pro = data_pro.loc[(data_pro['indicator_date']<=td.strftime("%Y-%m-%d")) & (data_pro['indicator_date']>=start_d.strftime("%Y-%m-%d"))]
    #2. 获取最新指数对应的成份股
    ix_comp = mongodb_utils.get_index_comp()
    print(ix_comp)
    if len(ix_comp) <= 0:
        print('[OppositeTrend Strategy]: {} index component not found'.format(td.strftime("%Y-%m-%d")))
        return -1
    index_list = mongodb_utils.get_indexlist({'sse': 'sw', 'decimal_point': 2})
    ix_comp = ix_comp.loc[ix_comp[CONST_PARAM_ASSET_CODE].isin(index_list[CONST_PARAM_ASSET_CODE].tolist())]

    #3. 选择pct_chg_td的指标
    data_pct_chg = data_pro.loc[data_pro['indicator_id'] == CONST_PARAM_IND_pct_chg]
    #4. 遍历stk list，根据传入参数，表示基础池还是重点池
    if(('basic_pool' in conf) and conf['basic_pool']):
        stk_list = mongodb_utils.get_asset_pool('基础池')
    elif (('important_pool' in conf) and conf['important_pool']):
        stk_list =  mongodb_utils.get_asset_pool('重点池')
    elif (('deepvalue_pool' in conf) and conf['deepvalue_pool']):
        stk_list =  mongodb_utils.get_asset_pool('策略-深度价值')

    for stk in stk_list[CONST_PARAM_ASSET_ID].tolist():
        data_stk = data_pct_chg.loc[data_pct_chg[CONST_PARAM_ASSET_ID] == stk]
        if len(data_stk) <= 0:
            print('[OppositeTrend Strategy]: {} pct_chg_td not found'.format(stk))
            continue
        sw_index = ix_comp.loc[ix_comp['sec_code'] == stk]
        if len(sw_index) <= 0:
            print('[OppositeTrend Strategy]: SW level2 of {} not found'.format(stk))
            continue
        data_sw_index = data_pct_chg.loc[data_pct_chg[CONST_PARAM_ASSET_ID] == sw_index[CONST_PARAM_ASSET_CODE].values[0]]
        if len(data_sw_index) <= 0:
            print('[OppositeTrend Strategy]: {} pct_chg_td of not found'.format(sw_index[CONST_PARAM_ASSET_CODE].values[0]))
            continue
        data_merge = pd.merge(data_stk, data_sw_index[['asset_id', 'indicator_date', 'value']], how='inner', on=['indicator_date'])
        data_merge['n_value'] = data_merge['value_x'] - data_merge['value_y']
        stk_skew = data_merge['n_value'].skew(axis=0, skipna=True)
        
        df_indicator = df_indicator.append({
            'exe_date': td.strftime("%Y-%m-%d"),
            'asset_id': stk,
            'index_id': sw_index[CONST_PARAM_ASSET_CODE].values[0],
            'skew': stk_skew
            }, ignore_index=True)

    #按照skew排序
    df_indicator.sort_values(by='skew', ascending=True, inplace=True)
    #skew<0左偏，表示偏强
    res_strong = df_indicator.head(CONST_PARAM_RES_NUM)
    #skew>0右偏，表示偏弱
    res_weak = df_indicator.tail(CONST_PARAM_RES_NUM)

    # 5. 将选股结果保存
    strategy_execution = pd.DataFrame(columns=('strategy_id', 'strategy_name', 'exe_date', 'strategy_res', 'update_timestamp', 'user'))
    strategy_execution = strategy_execution.append([
        {
            'strategy_id': CONST_STRATEGY_ID_STRONG,
            'strategy_name': CONST_STRATEGY_NAME_STRONG,
            'exe_date':  td.strftime("%Y-%m-%d"),
            'strategy_res': res_strong.to_dict('records')
        },
        {
            'strategy_id': CONST_STRATEGY_ID_WEAK,
            'strategy_name': CONST_STRATEGY_NAME_WEAK,
            'exe_date':  td.strftime("%Y-%m-%d"),
            'strategy_res': res_weak.to_dict('records')
        }
    ], ignore_index=True)

    #print(strategy_execution)
    mongodb_utils.insert_stra_exe(CONST_PARAM_STRATEGY_EXECUTION, strategy_execution)
    return 0


def main():
    #td = datetime.date.today()
    td = datetime.date(2023, 7, 21)
    stk_label_data = pd.DataFrame()
    stk_market_data = pd.DataFrame()
    stk_ind_data = pd.DataFrame()
    stk_ind_data = mongodb_utils.get_labeldata('asset_indicator', {
        'indicator_date': {'$gte': (td - relativedelta(months=3)).strftime("%Y-%m-%d"), '$lte': td.strftime("%Y-%m-%d")}
    })

    print(run_strategy(td, {'basic_pool': True, 'index_sw_level2': True}, stk_label_data, stk_ind_data, stk_market_data))
    print("run_strategy: OppositeTrend")

if __name__ == '__main__':
    main()
