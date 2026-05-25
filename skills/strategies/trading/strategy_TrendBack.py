import pymongo
import QUANTAXIS as qa
import pandas as pd
import numpy as np
import datetime
from dateutil.relativedelta import relativedelta
#===import db_utils
import os, sys
sys.path.append( os.path.abspath(os.path.join('..', '..', 'base', 'utils')) )
import mongodb_utils
#==================
CONST_PARAM_LABEL_ID_trend = 'trend'
CONST_PARAM_LABEL_ID_ispullback = 'ma_year_is_pullback'
CONST_PARAM_LABEL_ID_islongseq = 'ma_is_longseq'
CONST_PARAM_LABEL_ID_discrete_3m = 'ma_discrete_last3m'
CONST_PARAM_LABEL_ID_discrete_6m = 'ma_discrete_last6m'
CONST_PARAM_LABEL_ID = 'label_id'
CONST_PARAM_ASSET_ID = 'asset_id'
CONST_PARAM_LABEL_DATE = 'label_date'
CONST_PARAM_LABEL_VALUE = 'value'
CONST_PARAM_STRATEGY_EXECUTION = 'strategy_execution'
CONST_STRATEGY_ID = 'TrendBack'
CONST_STRATEGY_NAME = '趋势回调策略'
CONST_PARAM_MAXDD1M_threshold = 0.15
CONST_PARAM_3M_longseq_cnt_threshold = 22
CONST_PARAM_DISCRETE_3M_avg = 0.2041
CONST_PARAM_DISCRETE_3M_std = 0.1321
CONST_PARAM_DISCRETE_6M_avg = 0.2158
CONST_PARAM_DISCRETE_6M_std = 0.1223

class max_dd_calculator:
    def __init__(self, series_data: pd.Series([], dtype="float64")):
        """
        :param series_data:index为时间，column为"close"(股票收盘价)的Series
        """
        self.series_data=series_data

    def max_dd(self):
        """
        :return: Max drawdown of the financial series.
        """
        roll_max = self.series_data.expanding().max()
        max_dd = -1 * np.min(self.series_data / roll_max - 1)  # 计算得到最大回撤
        return max_dd
    
    def dyn_dd(self):
        """
        :return: Dynamic drawdown of the financial series.
        """
        roll_max = self.series_data.expanding().max()
        dyn_dd = -1 * (self.series_data / roll_max - 1)[-1] # 计算得到动态回撤
        return dyn_dd

    def max_dd_period(self):
        """
        :return: 最大回撤的持续期(单位：交易日)
        """
        roll_max = self.series_data.expanding().max()
        end_point = np.argmin(self.series_data / roll_max - 1)
        start_point = np.argmax(self.series_data[:end_point])# 找到最大回撤对应的起始index和终止index
        period = end_point - start_point
        if period <= 0:
            return
        else:
            return period

    def max_dd_repair(self):
        """
        :return: 最大回撤的修复期(单位：交易日)
        """
        roll_max = self.series_data.expanding().max()
        end_point = np.argmin(self.series_data / roll_max - 1)
        roll_max_value=max(self.series_data[:end_point])
        data=self.series_data[end_point:]
        if data[data>=roll_max_value].empty:
            #print('[max_dd_calculator]:期间最大回撤仍未修复')
            return
        else:
            repair_point = self.series_data.index.tolist().index(data[data >= roll_max_value].index[0])
            repair_period=repair_point-end_point
            return repair_period
    
    def top5_max_dd(self):
        """
        :return: 前5大回撤，包括最大回撤率,持续时间,以及修复时间
        """
        LEN = 5
        maxdd_list = []  #定义一个序列，存储不同排名的最大回撤
        maxdd_period_list = [] #定义一个序列，存储不同排名的最大回撤持续时间
        maxdd_repair_list = [] #定义一个序列，存储不同排名的最大回撤修复时间
        #self.series_data.to_csv('maxdd.csv')
        for i in range(LEN):
            # 计算最大回撤
            drawdown = self.max_dd()  # 计算得到当前阶段最大回撤
            if drawdown <= CONST_PARAM_MADDD_threshold:
                break
            maxdd_list.append(drawdown)
            maxdd_period_list.append(self.max_dd_period())
            maxdd_repair_list.append(self.max_dd_repair())

            # 找到最大回撤对应的起始index和终止index
            roll_max = self.series_data.expanding().max()
            end_point = np.argmin(self.series_data / roll_max - 1)
            start_point = np.argmax(self.series_data[:end_point])

            #self.series_data.to_csv('maxdd{}.csv'.format(i))
            #print(i)
            #print(start_point, end_point)
            # 将最大回撤阶段的数据去掉，将两端数据拼接，这里需要处理使得拼接点一致
            ser1 = self.series_data[:start_point]
            ser2 = self.series_data[end_point:]
            if not ser1.empty and not ser2.empty:
                ser2 = ser2 * (ser1[ser1.index[-1]] / ser2[ser2.index[0]])  # 将df2的第一个数据与df1的最后一个数据一致
                self.series_data = pd.concat([ser1, ser2])  # 将df1与df2拼接，得到新的df数据
            elif ser1.empty and not ser2.empty:
                self.series_data = ser2
            elif not ser1.empty and ser2.empty:
                self.series_data = ser1
            elif ser1.empty and ser2.empty:
                break
        return maxdd_list, maxdd_period_list,  maxdd_repair_list

def pre_processor(data, conf):
    if(('basic_pool' in conf) and conf['basic_pool']):
        stk_list = mongodb_utils.get_asset_pool('基础池')
        print('[Basic Pool]:')
        print(stk_list)
        data = data.loc[data[CONST_PARAM_ASSET_ID].isin(stk_list[CONST_PARAM_ASSET_ID].tolist())]

    return data


def run_strategy(td, conf, label_data, market_data=None):
    #0. 定义指标数据
    df_indicator = pd.DataFrame()
    #近1月
    td_last_1m = td - relativedelta(months=1)
    data_pro = pre_processor(label_data, conf)
    #2. 获取今天的所有标签数据
    label_data_td = data_pro.loc[data_pro[CONST_PARAM_LABEL_DATE] == td.strftime("%Y-%m-%d")]
    #近3月
    #fix: 因为总的数据为近3个月的数据，因此寻找3个月前的数据可能存在空，采用min的方式
    td_last_3m = data_pro.loc[data_pro[CONST_PARAM_LABEL_DATE] >= (td - relativedelta(months=3)).strftime("%Y-%m-%d"), CONST_PARAM_LABEL_DATE].min()
    label_data_last3m = data_pro.loc[data_pro[CONST_PARAM_LABEL_DATE] == td_last_3m]
    #print(td_last_3m)
    #1. 按照conf对数据进行预处理
    #3. 策略条件
    #Cond 1) 近3月趋势是上涨或者无趋势
    df_indicator = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_trend])].copy()
    df_indicator = df_indicator.loc[df_indicator[CONST_PARAM_LABEL_VALUE].isin(['close_3m_上涨', 'close_3m_无趋势']), [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    df_indicator.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_trend + '_3m'},  inplace=True)
    print(1)
    print(df_indicator)
    #Cond 2) 近1月存在回踩年线或者动态回撤超过15%
    # 获取近1月内存在回踩年线的标签数据
    label_data_is_pullback = data_pro.loc[(data_pro[CONST_PARAM_LABEL_DATE] >= td_last_1m.strftime("%Y-%m-%d")) & (data_pro[CONST_PARAM_LABEL_DATE] <= td.strftime("%Y-%m-%d")) & (data_pro[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_ispullback])), [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    label_data_is_pullback = label_data_is_pullback.groupby(CONST_PARAM_ASSET_ID).agg({CONST_PARAM_LABEL_VALUE: 'sum'})
    label_data_is_pullback = label_data_is_pullback.loc[label_data_is_pullback[CONST_PARAM_LABEL_VALUE] > 0]
    label_data_is_pullback.rename(columns = {CONST_PARAM_LABEL_VALUE: 'pullback_cnt_1m'},  inplace=True)
    label_data_is_pullback.reset_index(inplace=True)
    # 获取近1月的动态回撤数据
    tmpdf_dd = pd.DataFrame(columns=('asset_id', 'dyn_maxdd_1m'))
    tot_stk_list = qa.QA_fetch_stock_list_adv().index.tolist()
    stk_mkt_data_last1m = qa.QA_fetch_stock_day_adv(tot_stk_list, td_last_1m, td)
    stk_mkt_data_last1m = stk_mkt_data_last1m.to_qfq()
    for s in stk_mkt_data_last1m.index.levels[1].tolist():
        mkt_d = stk_mkt_data_last1m.close[:, s]
        try:
            max_dd_calc = max_dd_calculator(mkt_d)
            d = max_dd_calc.dyn_dd()
        except Exception as e:
            print('{}出现异常:{}'.format(s, e))
        else:
            tmpdf_dd = tmpdf_dd.append({'asset_id': s, 'dyn_maxdd_1m': d}, ignore_index=True)
    # 过滤出近1个月的动态回撤超过15%的股票
    tmpdf_dd = tmpdf_dd.loc[tmpdf_dd['dyn_maxdd_1m'] >= CONST_PARAM_MAXDD1M_threshold]
    # 近1月存在回踩年线 or 近1月动态回撤超过15%
    tmpdf_dd = pd.merge(tmpdf_dd, label_data_is_pullback, how = 'outer', on = CONST_PARAM_ASSET_ID)
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(2)
    print(df_indicator)
    #Cond 3) 近3月均线组发散程度在[avg-std, avg+std]并且整齐程度较高
    tmpdf_dd = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_discrete_3m])]
    tmpdf_dd = tmpdf_dd.loc[tmpdf_dd[CONST_PARAM_LABEL_VALUE].between(CONST_PARAM_DISCRETE_3M_avg - CONST_PARAM_DISCRETE_3M_std, CONST_PARAM_DISCRETE_3M_avg + CONST_PARAM_DISCRETE_3M_std, inclusive=True), [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    tmpdf_dd.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_discrete_3m},  inplace=True)
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(3)
    print(df_indicator)
    #Cond 4) 近3个月，存在多次多头排列
    label_data_is_longseq = data_pro.loc[(data_pro[CONST_PARAM_LABEL_DATE] >= td_last_3m) & (data_pro[CONST_PARAM_LABEL_DATE] <= td.strftime("%Y-%m-%d")) & (data_pro[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_islongseq])), [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    tmpdf_dd = label_data_is_longseq.groupby(CONST_PARAM_ASSET_ID).agg({CONST_PARAM_LABEL_VALUE: 'sum'})
    tmpdf_dd = tmpdf_dd.loc[tmpdf_dd[CONST_PARAM_LABEL_VALUE] >= CONST_PARAM_3M_longseq_cnt_threshold]
    tmpdf_dd.rename(columns = {CONST_PARAM_LABEL_VALUE: 'longseq_cnt_3m'},  inplace=True)
    tmpdf_dd.reset_index(inplace=True)
    #print('tmpdf_dd', tmpdf_dd)
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(4)
    print(df_indicator)
    #Cond 5) 3个月前的近6月均线粘合
    tmpdf_dd = label_data_last3m.loc[label_data_last3m[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_discrete_6m])]
    tmpdf_dd = tmpdf_dd.loc[tmpdf_dd[CONST_PARAM_LABEL_VALUE] <= (CONST_PARAM_DISCRETE_6M_avg - CONST_PARAM_DISCRETE_6M_std) * 1.2, [CONST_PARAM_ASSET_ID, CONST_PARAM_LABEL_VALUE]]
    tmpdf_dd.rename(columns = {CONST_PARAM_LABEL_VALUE: CONST_PARAM_LABEL_ID_discrete_6m},  inplace=True)
    #print('tmpdf_dd', tmpdf_dd)
    # 条件求并
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(5)
    print(df_indicator)
    
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
    print("run_strategy: TrendBack")

if __name__ == '__main__':
    main()

