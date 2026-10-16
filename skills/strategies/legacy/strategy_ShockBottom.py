import pymongo
import pandas as pd
import numpy as np
import datetime
from dateutil.relativedelta import relativedelta
#===import db_utils
import os, sys
sys.path.append( os.path.abspath(os.path.join('..', '..', 'base', 'utils')) )
import mongodb_utils
#==================
CONST_PARAM_ASSET_ID = 'asset_id'
CONST_PARAM_MKT_LONG_YEAR = 2
CONST_PARAM_MKT_SHORT_MON = 4
CONST_PARAM_KLINE_YR_COUNT = 247
CONST_PARAM_KLINE_MON_COUNT = 21
CONST_PARAM_LABEL_ID_vol_level_last2m = 'vol_level_last2m'
CONST_PARAM_LABEL_ID_vol_trend_last2m = 'vol_trend_last2m'
CONST_PARAM_VOL_LEVEL_up_threshold = 1.4
CONST_PARAM_MAXDD_threshold = 0.37
CONST_PARAM_2YRISE_threshold = 0.4 
CONST_PARAM_DIFF_LOW_threshold = 0.07
CONST_PARAM_DIFF_HIGH_threshold = 0.05
CONST_PARAM_LOW_INTER_len = 10
CONST_PARAM_MADDD_threshold = 0.01 #低于1%的最大回撤，视为异常，不计入最大回撤
CONST_PARAM_LABEL_ID = 'label_id'
CONST_PARAM_ASSET_ID = 'asset_id'
CONST_PARAM_LABEL_DATE = 'label_date'
CONST_PARAM_LABEL_VALUE = 'value'
CONST_PARAM_STRATEGY_EXECUTION = 'strategy_execution'
CONST_STRATEGY_ID = 'ShockBottom'
CONST_STRATEGY_NAME = '多重底策略'

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

def pre_processor(data, conf, dt='qa_data'):
    if(('basic_pool' in conf) and conf['basic_pool']):
        stk_list = mongodb_utils.get_asset_pool('基础池')
        print('[Basic Pool]:')
        print(stk_list)
        if dt=='qa_data':
            data = data.select_code(stk_list[CONST_PARAM_ASSET_ID].tolist())
        else:
            data = data.loc[data[CONST_PARAM_ASSET_ID].isin(stk_list[CONST_PARAM_ASSET_ID].tolist())]

    return data

def cal_interval_change(mkt_data, start, end):
    res = pd.DataFrame(columns=['code', 'chg'])
    for c in mkt_data.index.levels[1].tolist():
        mkt_d = mkt_data.select_code(c)
        s_price = mkt_d.select_time(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        e_price = mkt_d.select_time(end.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if(s_price.len < 1 or e_price.len < 1):
            res = res.append({'code': c, 'chg': -1 }, ignore_index=True)
        else:
            res = res.append({'code': c, 'chg': e_price.close.values[0] / s_price.close.values[0] -1  }, ignore_index=True)

    return res

def get_interval_maxdd(mkt_data, inter):
    res = pd.DataFrame(columns=['code', 'maxdd'])
    for c in mkt_data.index.levels[1].tolist():
        mkt_d = mkt_data.select_code(c)
        #mkt_d.show()
        # 如果数据完整度小于20% ，直接跳过
        if len(mkt_d) < inter * 0.2:
            print("{}行情数据少于{%d}天或者最新行情未获取".format(c, inter * 0.2))
            continue
        max_dd_calc = max_dd_calculator(mkt_d.close)
        res = res.append({'code': c, 'maxdd': max_dd_calc.max_dd()}, ignore_index=True)

    return res

def low_high_stat(mkt_data, inter):
    res = pd.DataFrame(columns=['code', 'count', 'pos', 'avg_low', 'avg_high', 'inter_high', 'avg_high_dif'])
    for c in mkt_data.index.levels[1].tolist():
        mkt_d = mkt_data.select_code(c)
        # 如果数据完整度小于20% ，直接跳过
        if len(mkt_d) < inter * 0.2:
            print("{}行情数据少于{%d}天或者最新行情未获取".format(c, inter * 0.2))
            continue
        # 统计区间低点次数，以及每一次反弹的高点
        mkt_d_cp = mkt_d.close.copy(deep=True)
        mkt_d_cp.reset_index(drop=True, inplace=True)
        lowest = mkt_d_cp.min()
        pos = [mkt_d_cp.idxmin()]
        inter_high = []
        cnt = 1
        # a. 获取所有低点
        for i, v in mkt_d_cp.iteritems():
            if i != mkt_d_cp.idxmin() and (v - lowest) / lowest <= CONST_PARAM_DIFF_LOW_threshold:
                pos.append(i)
        pos.sort()
        # b. 统计有效低点及平均值
        pos_vaild = [pos[0]]
        tot_low = 0
        for i in pos:
            if i - pos_vaild[-1] >= CONST_PARAM_LOW_INTER_len:
                pos_vaild.append(i)
                cnt = cnt + 1
            else:
                if mkt_d_cp.iloc[i] < mkt_d_cp.iloc[pos_vaild[-1]]:
                    pos_vaild[-1] = i
        for i in pos_vaild:
            tot_low = tot_low + mkt_d_cp.iloc[i]
        avg_low = tot_low / len(pos_vaild)
        # c. 统计低点之间的反弹高度
        s = 1
        while (s < cnt):
            inter_high.append(mkt_d_cp.iloc[pos_vaild[s-1]:pos_vaild[s]+1].max())
            s = s + 1
        # d. 计算平均反弹高点均值及偏差
        avg_dif = -1
        avg_high = 0
        if len(inter_high) > 0:
            avg_high = np.mean(inter_high)
            tot_dif = 0
            for x in inter_high:
                tot_dif = tot_dif + abs(x - avg_high)
            avg_dif = tot_dif / len(inter_high)
            avg_dif = avg_dif / avg_high

        res = res.append({'code': c, 'count': cnt, 'pos': ",".join([str(x) for x in pos_vaild]), 'avg_low':avg_low, 'avg_high':avg_high, 'inter_high': ','.join([str(x) for x in inter_high]), 'avg_high_dif': avg_dif}, ignore_index=True)

    return res

def run_strategy(td, conf, label_data,  ind_data=None, market_data=None):
    # 1. 筛选出基础池数据
    mkt_data_pro = pre_processor(market_data, conf, 'qa_data')
    label_data_pro = pre_processor(label_data, conf, 'dataframe')
    # 2.1 转换为前复权数据
    mkt_data_pro = mkt_data_pro.to_qfq()
    td_last_2y = td - relativedelta(years=CONST_PARAM_MKT_LONG_YEAR)
    td_last_4m = td - relativedelta(months=CONST_PARAM_MKT_SHORT_MON)
    # 2.2 获取今天的所有标签数据
    label_data_td = label_data_pro.loc[label_data_pro[CONST_PARAM_LABEL_DATE] == td.strftime("%Y-%m-%d")]
    #Cond 1) 【2年前,4个月前】的最大回撤 >= 【2年前, 今天】最大回撤 && 【2年前,4月前】的最大回撤 >= 37%
    maxdd_2y_4m = get_interval_maxdd(mkt_data_pro.select_time(td_last_2y.strftime("%Y-%m-%d"), td_last_4m.strftime("%Y-%m-%d")), CONST_PARAM_MKT_LONG_YEAR * CONST_PARAM_KLINE_YR_COUNT - CONST_PARAM_MKT_SHORT_MON * CONST_PARAM_KLINE_MON_COUNT)
    maxdd_2y_td = get_interval_maxdd(mkt_data_pro.select_time(td_last_2y.strftime("%Y-%m-%d"), td.strftime("%Y-%m-%d")), CONST_PARAM_MKT_LONG_YEAR * CONST_PARAM_KLINE_YR_COUNT)
    df_indicator = pd.merge(maxdd_2y_4m, maxdd_2y_td, on='code', how='inner')
    df_indicator.rename(columns = {'maxdd_x': 'maxdd_2y_4m', 'maxdd_y': 'maxdd_2y_td'},  inplace=True)
    df_indicator = df_indicator.loc[(df_indicator['maxdd_2y_4m'] >= CONST_PARAM_MAXDD_threshold) & (df_indicator['maxdd_2y_4m'] >= df_indicator['maxdd_2y_td'])]
    print(1)
    print(df_indicator)
    #Cond 2) 收盘价在区间（4个月前，今天）最低价附近（阈值7%）的有效次数超过2次 && 反弹高点之间的平均偏差小于5%
    tmp_df = low_high_stat(mkt_data_pro.select_time(td_last_4m.strftime("%Y-%m-%d"), td.strftime("%Y-%m-%d")), CONST_PARAM_MKT_SHORT_MON * CONST_PARAM_KLINE_MON_COUNT)
    tmp_df = tmp_df.loc[(tmp_df['count'] >= 2) & (tmp_df['avg_high_dif'] != 0) & (tmp_df['avg_high_dif'] <= CONST_PARAM_DIFF_HIGH_threshold)]
    df_indicator = pd.merge(df_indicator, tmp_df, on='code', how='inner')
    print(2)
    print(df_indicator)
    #Cond 3) 【4个月前，今天】反弹的平均高点，不能大于【2年前，4个月前的】最高收盘价
    last_close = mkt_data_pro.select_time(td_last_2y.strftime("%Y-%m-%d"), td_last_4m.strftime("%Y-%m-%d")).close.to_frame()
    last_close.reset_index(inplace=True)
    last_close.rename(columns = {'close': 'last_high'},  inplace=True)
    last_high = last_close.groupby('code')['last_high'].max().to_frame()
    last_high.reset_index(inplace=True)
    df_indicator = pd.merge(df_indicator, last_high, on='code', how='inner')
    df_indicator = df_indicator.loc[df_indicator['avg_high'] < df_indicator['last_high']]
    print(3)
    print(df_indicator)
    #last_close = pd.DataFrame({'date': last_close.index.levels[0], 'code': last_close.index.levels[1], 'last_close': last_close.values})
    #last_high = last_close.groupby('code')['last_close'].max()
    #
    # print(last_high)
    #Cond 4) 最新收盘价介于avg_low和avg_high之间
    td_close = mkt_data_pro.select_time(td.strftime("%Y-%m-%d")).close
    td_close = pd.DataFrame({'code': td_close.index.levels[1], 'td_close': td_close.values})
    df_indicator = pd.merge(df_indicator, td_close, on='code', how='inner')
    df_indicator = df_indicator.loc[(df_indicator['td_close'] <= df_indicator['avg_high']) & (df_indicator['td_close'] >= df_indicator['avg_low'])]
    print(4)
    print(df_indicator)
    #Cond 5) 近两年涨跌幅小于40%
    rise2y = cal_interval_change(mkt_data_pro, td_last_2y, td)
    df_indicator = pd.merge(df_indicator, rise2y, on='code', how='inner')
    df_indicator = df_indicator.loc[df_indicator['chg'] <= CONST_PARAM_2YRISE_threshold]
    df_indicator.rename(columns = {'code': CONST_PARAM_ASSET_ID},  inplace=True)
    print(5)
    print(df_indicator)
    #Cond 6) 近2月成交额水平在1.4以上
    tmpdf_dd = label_data_td.loc[label_data_td[CONST_PARAM_LABEL_ID].isin([CONST_PARAM_LABEL_ID_vol_level_last2m, CONST_PARAM_LABEL_ID_vol_trend_last2m])].copy()
    tmpdf_dd.loc[:, CONST_PARAM_LABEL_VALUE] = tmpdf_dd[CONST_PARAM_LABEL_VALUE].astype('float')
    tmpdf_dd = tmpdf_dd.pivot(index=CONST_PARAM_ASSET_ID, columns=CONST_PARAM_LABEL_ID, values=CONST_PARAM_LABEL_VALUE)
    tmpdf_dd = tmpdf_dd[(tmpdf_dd[CONST_PARAM_LABEL_ID_vol_level_last2m] >= CONST_PARAM_VOL_LEVEL_up_threshold)]
    df_indicator = pd.merge(df_indicator, tmpdf_dd, how='inner', on=CONST_PARAM_ASSET_ID)
    print(6)
    print(df_indicator)
    #df_indicator.to_csv('df_in.csv')
    # 3. 将选股结果保存
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
    print("run_strategy: ShockBottom")

if __name__ == '__main__':
    main()
