import QUANTAXIS as qa
import pandas as pd
import numpy as np
import datetime
from dateutil.relativedelta import relativedelta
#===import db_utils
import os, sys
sys.path.append( os.path.abspath(os.path.join('..', '..', 'base', 'utils')) )
import mongodb_utils

CONST_PARAM_ANNUAL_PROFIT_threshold = 20000000
CONST_PARAM_DEBT_RATIO_threshold = 40
CONST_PARAM_TOP5CUST_PCT_threshold = 80
CONST_PARAM_ROE_threshold = 7
CONST_PARAM_GROWTH_threshold = 0.2
CONST_PARAM_PEG_threshold = 2
CONST_PARAM_ASSET_ID = 'asset_id'
CONST_PARAM_ASSET_POOL = 'asset_pool'
CONST_PARAM_ASSET_LABEL = 'asset_label'
#==================
#日志输出
#==================
class Logger(object):
    def __init__(self, filename="stockpool.log"):
        self.terminal = sys.stdout
        self.log = open(filename, "a")
 
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
 
    def flush(self):
        pass

def nextReportDate(startDate, direct, inteval):
    nextDate = ""
    d=['0331','0630','0930','1231']
    pos = d.index(startDate[-4:]) + direct * inteval
    if pos < 0:
        nextDate = str(int(startDate[:4]) - 1) +  d[4 - abs(pos) % 4]
    elif pos >= 4:
        nextDate = str(int(startDate[:4]) + 1) +  d[abs(pos) % 4]
    else:
        nextDate = startDate[:4] +  d[abs(pos) % 4]
        
    return nextDate

def last_rpt_date(td):
    md = td.strftime("%m%d")
    if md >= '0331' and md < '0630':
        return str(td.year) + '0331'
    elif md >= '0630' and md < '0930':
        return str(td.year) + '0630'
    elif md >= '0930' and md < '1231':
        return str(td.year) + '0930'
    elif md < '0331':
        return str(td.year -1) + '1231'
    else:
        return str(td.year) + '1231'


def avg_annual_profit(start, end):
    income_df = mongodb_utils.get_fsincome(start, end)
    income_df = income_df.loc[income_df['rpt_date'].str.contains('1231'), ['stock_id', 'rpt_date', 'np_belongto_parcomsh']]
    income_df = income_df.pivot(index='stock_id', columns='rpt_date', values='np_belongto_parcomsh')
    income_df['avg_profit_3y'] = income_df.mean(axis=1)
    #income_df.to_excel('income_df.xlsx')
    #print(income_df)
    return income_df

def avg_debt_ratio(start, end):
    debt_df = mongodb_utils.get_debt(start, end)
    debt_ba = mongodb_utils.get_fsbalance(start, end)
    # 2022/05/03 修正使用"有息负债率"
    debt_ba = debt_ba[['stock_id', 'rpt_date', 'tot_assets', 'minority_int']]
    debt_ba['minority_int']=debt_ba['minority_int'].fillna(0)
    debt_df = debt_df[['stock_id', 'rpt_date', 'debttoassets', 'equitytointerestdebt']]
    debt_df = pd.merge(debt_df, debt_ba, how="inner", on=['stock_id', 'rpt_date'])
    #print(debt_df)
    debt_df['res'] = debt_df.apply(lambda row: row['debttoassets'] if pd.isnull(row['equitytointerestdebt']) or row['equitytointerestdebt']==0 else (1 - row['debttoassets'] * 0.01 - row['minority_int'] / row['tot_assets']) / row['equitytointerestdebt'] * 100, axis=1)
    debt_df = debt_df.pivot(index='stock_id', columns='rpt_date', values='res')
    debt_df['avg_debt_3y'] = debt_df.mean(axis=1)
    #debt_df.to_csv('123.csv')
    #income_df.to_excel('income_df.xlsx')
    #print(income_df)
    return debt_df

def avg_cust_top5(start, end):
    cust_df = mongodb_utils.get_cust_vendor(start, end)
    cust_df = cust_df.loc[cust_df['rpt_date'].str.contains('1231'), ['stock_id', 'rpt_date', 'stmnote_salestop5_pct']]
    cust_df = cust_df.pivot(index='stock_id', columns='rpt_date', values='stmnote_salestop5_pct')
    cust_df['avg_custtop5_3y'] = cust_df.mean(axis=1)

    return cust_df

def cashflow_direct(start, end):
    cf_df = mongodb_utils.get_cashflow_direct(start, end)
    cf_df = cf_df.loc[cf_df['rpt_date'].str.contains('1231'), ['stock_id', 'rpt_date', 'net_cash_flows_oper_act', 'net_cash_flows_inv_act', 'net_cash_flows_fnc_act']]
    opcf_df = cf_df.pivot(index='stock_id', columns='rpt_date', values='net_cash_flows_oper_act')
    invcf_df = cf_df.pivot(index='stock_id', columns='rpt_date', values='net_cash_flows_inv_act')
    fnccf_df = cf_df.pivot(index='stock_id', columns='rpt_date', values='net_cash_flows_fnc_act')
    opcf_df = opcf_df.map(lambda x: False if pd.isnull(x) else x < 0)
    opcf_df['opneg_cnt'] = opcf_df.sum(axis=1) / opcf_df.shape[1]
    invcf_df = invcf_df.map(lambda x: False if pd.isnull(x) else x < 0)
    invcf_df['invneg_cnt'] = invcf_df.sum(axis=1) / invcf_df.shape[1]
    fnccf_df = fnccf_df.map(lambda x: True if pd.isnull(x) else x >= 0)
    fnccf_df['fncpos_cnt'] = fnccf_df.sum(axis=1) / fnccf_df.shape[1]
    #print(opcf_df)
    #print(invcf_df)
    #print(fnccf_df)
    res_df = pd.merge(opcf_df['opneg_cnt'], invcf_df['invneg_cnt'], how='left', left_index=True, right_index=True)
    res_df = pd.merge(res_df, fnccf_df['fncpos_cnt'], how='left', left_index=True, right_index=True)

    return res_df

def stock_sector():
    sec_df = mongodb_utils.get_sector()
    sec_df = sec_df[['stock_id','industry_citic']]

    return sec_df

def laset_YR(td):
    if td.strftime('%m%d') <= '0430':
        return datetime.date(td.year - 2, 12, 31)
    else:
        return datetime.date(td.year - 1, 12, 31)
#==============================
#构建基础池股票
# 1. 排除ST
# 2. 上市超过1年
# 3. 近3年平均年归母净利润需要大于2000万
# 4. (非金融行业)近3年平均有息负债率需要小于40%
# 5. 近3年经营现金流、投资现金流为负，筹资现金流是正
#==============================
def generate_basic_pool(td):
    lyr_ago = td - relativedelta(years=1)
    #年度报告期
    #【已完成】1.这里需要改进，目前是直接取得去年的年报，但是实际上一年度年报最晚可以在4/30之后披露，所以这边需要判断当前时间是否大于4/30，从而来判断到底取上一年度年报（-1）还是上上年度（-2）
    end_year = laset_YR(td)
    start_year = end_year - relativedelta(years=2)
    #滚动报告期
    last_rpt = datetime.datetime.strptime(last_rpt_date(td), '%Y%m%d')
    last_rpt_3y = last_rpt - relativedelta(years=3)

    stk_list = mongodb_utils.get_stocklist()
    stk_list.drop(columns=['_id'], inplace=True)
    #1. 排除ST
    stk_list = stk_list.loc[~stk_list['name'].str.contains('ST')]
    #print(1)
    #print(stk_list)
    #2. 上市超过1年
    stk_basic_info = mongodb_utils.get_stockinfo()
    stk_basic_info['stock_id_tdx'] = stk_basic_info['stock_id'].str[:-3]
    stk_basic_info = stk_basic_info[stk_basic_info['s_ipo_listeddate'] <= lyr_ago.strftime("%Y-%m-%d")]
    # 条件求并
    stk_list = pd.merge(stk_list, stk_basic_info, how='inner', left_on='code', right_on='stock_id_tdx')
    stk_list.drop(columns=['stock_id', 'stock_id_tdx'], inplace=True)
    #print(2)
    #print(stk_list)
    #3. 近3年平均年归母净利润大于2000万
    stk_ann_profit_3y = avg_annual_profit(start_year.strftime("%Y%m%d"), end_year.strftime("%Y%m%d"))
    stk_ann_profit_3y = stk_ann_profit_3y.loc[stk_ann_profit_3y['avg_profit_3y'] >= CONST_PARAM_ANNUAL_PROFIT_threshold, ['avg_profit_3y']]
    stk_ann_profit_3y.reset_index(inplace=True)
    stk_ann_profit_3y['stock_id_tdx'] = stk_ann_profit_3y['stock_id'].str[:-3]
    # 条件求并
    stk_list = pd.merge(stk_list, stk_ann_profit_3y, how='inner', left_on='code', right_on='stock_id_tdx')
    stk_list.drop(columns=['stock_id', 'stock_id_tdx'], inplace=True)
    #print(3)
    #print(stk_list)
    #4. (非金融行业)近3年平均有息负债率需要小于40%
    #2022/05/03, 负债率使用有息负债率而不是资产负债率
    stk_debt_3y = avg_debt_ratio(last_rpt_3y.strftime("%Y%m%d"), last_rpt.strftime("%Y%m%d"))
    stk_debt_3y = stk_debt_3y[['avg_debt_3y']]
    stk_debt_3y.reset_index(inplace=True)
    stk_sector = stock_sector()
    stk_debt_3y = pd.merge(stk_debt_3y, stk_sector, how='left', on='stock_id')
    stk_debt_3y = stk_debt_3y.loc[~((stk_debt_3y['industry_citic'].str.contains('银行|非银行金融') == False) & (stk_debt_3y['avg_debt_3y'] > CONST_PARAM_DEBT_RATIO_threshold))]
    stk_debt_3y['stock_id_tdx'] = stk_debt_3y['stock_id'].str[:-3]
    # 条件求并
    stk_list = pd.merge(stk_list, stk_debt_3y, how='inner', left_on='code', right_on='stock_id_tdx')
    stk_list.drop(columns=['stock_id', 'stock_id_tdx'], inplace=True)
    #print(4)
    #print(stk_list)
    #print(stk_list)
    #5. 排除近3年经营现金流方向(经营现金流都是负，投资现金流都是负，筹资现金流都是正)
    stk_cf_direct = cashflow_direct(start_year.strftime("%Y%m%d"), end_year.strftime("%Y%m%d"))
    stk_cf_direct = stk_cf_direct.loc[~((stk_cf_direct['opneg_cnt']==1.0) & (stk_cf_direct['invneg_cnt']==1.0) & (stk_cf_direct['fncpos_cnt']==1.0))]
    stk_cf_direct.reset_index(inplace=True)
    stk_cf_direct['stock_id_tdx'] = stk_cf_direct['stock_id'].str[:-3]
    # 条件求并
    stk_list = pd.merge(stk_list, stk_cf_direct, how='inner', left_on='code', right_on='stock_id_tdx')
    stk_list.drop(columns=['stock_id', 'stock_id_tdx'], inplace=True)
    #print(stk_list)
    #print(5)
    #print(stk_list)
    #6. 排除前5大客户集中度超过80%的民营企业
    stk_top5cust_pct = avg_cust_top5(start_year.strftime("%Y%m%d"), end_year.strftime("%Y%m%d"))
    stk_top5cust_pct.reset_index(inplace=True)
    stk_top5cust_pct['stock_id_tdx'] = stk_top5cust_pct['stock_id'].str[:-3]
    # 条件求并
    stk_list = pd.merge(stk_list, stk_top5cust_pct[['stock_id_tdx', 'avg_custtop5_3y']], how='left', left_on='code', right_on='stock_id_tdx')
    stk_list.drop(columns=['stock_id_tdx'], inplace=True)
    stk_list = stk_list.loc[~( (stk_list['s_info_nature1'] == '民营企业') & (stk_list['avg_custtop5_3y'] >= CONST_PARAM_TOP5CUST_PCT_threshold))]
    #stk_list.to_excel('stk_list.xlsx')
    #print(stk_list)
    #保存到数据库
    stk_list = stk_list[['code']]
    stk_list['pool_type'] = '基础池'
    stk_list['import_date'] = td.strftime("%Y-%m-%d")
    stk_list.rename(columns={'code': 'asset_id'}, inplace = True)
    print(stk_list)
    mongodb_utils.insert_stk_pool(CONST_PARAM_ASSET_POOL, stk_list)

    return 0

#==============================
#构建重点池股票
# 1. 获取最新的基础池
# 2. 条件1：近3年的平均ROE或者ROE（TTM）大于7%
#==============================
def generate_import_pool(td):
    #1. 获取最新日期的基础池
    basic_stk_list = mongodb_utils.get_asset_pool('基础池')
    # 获取最新报告期及上一个报告期，最新报告期没有就取上一个报告期
    last_rpt = last_rpt_date(td)
    last_rpt_1 = nextReportDate(last_rpt, -1, 1)
    # 获取最新年报日期以及3年前的年报日期
    end_year = laset_YR(td)
    start_year = end_year - relativedelta(years=2)
    stk_profit = mongodb_utils.get_profit(start_year.strftime("%Y%m%d"), last_rpt)
    stk_profit = stk_profit.loc[stk_profit['stock_id'].str[:-3].isin(basic_stk_list[CONST_PARAM_ASSET_ID].tolist())]
    # a. 计算最近报告期的ROE(TTM) 
    if len(stk_profit.loc[stk_profit['rpt_date'] == last_rpt]) > 0:
        stk_profit_roe_ttm = stk_profit.loc[stk_profit['rpt_date'] == last_rpt, ['stock_id', 'roe_ttm2']]
    else:
         stk_profit_roe_ttm = stk_profit.loc[stk_profit['rpt_date'] == last_rpt_1, ['stock_id', 'roe_ttm2']]
    # b. 计算近3年的平均ROE
    stk_profit_roe_3y = stk_profit.loc[stk_profit['rpt_date'].str.contains('1231'), ['stock_id', 'rpt_date', 'roe_avg']]
    stk_profit_roe_3y = stk_profit_roe_3y.pivot(index='stock_id', columns='rpt_date', values='roe_avg')
    stk_profit_roe_3y['avg_roe_3y'] = stk_profit_roe_3y.mean(axis=1)
    stk_profit_roe_3y.reset_index(inplace=True)
    stk_profit_roe_3y = stk_profit_roe_3y.loc[:, ['stock_id','avg_roe_3y']]
    # 2. ROE > 7%
    stk_profit_roe = pd.merge(stk_profit_roe_ttm, stk_profit_roe_3y, how='outer', on='stock_id')
    stk_profit_roe = stk_profit_roe.loc[(stk_profit_roe['roe_ttm2'] >= CONST_PARAM_ROE_threshold) | (stk_profit_roe['avg_roe_3y'] >= CONST_PARAM_ROE_threshold)]
    print(stk_profit_roe)

    # 3. 保存重点池
    import_stk_list = pd.DataFrame()
    import_stk_list['stock_id_tdx'] = stk_profit_roe['stock_id'].str[:-3]
    import_stk_list['pool_type'] = '重点池'
    import_stk_list['import_date'] = td.strftime("%Y-%m-%d")
    import_stk_list.rename(columns={'stock_id_tdx': 'asset_id'}, inplace = True)
    print(import_stk_list)
    mongodb_utils.insert_stk_pool(CONST_PARAM_ASSET_POOL, import_stk_list)
    
    return

#==============================
#构建高成长池股票
# 1. 获取最新的基础池
# 2. 条件1： 预测未来2年的净利润平均增速大于等于20%(如果净利润增速为空 则用总营收近两年增速)
# 3. 条件2： PE(TTM) / 未来2年净利润复合增速 <= 2
#==============================
def generate_grow_pool(td):
    #1. 获取最新日期的重点池
    important_stk_list = mongodb_utils.get_asset_pool('重点池')
    #2. 获取未来2年业绩增长率
    growth_label_data_rev = mongodb_utils.get_labeldata(CONST_PARAM_ASSET_LABEL, {'label_arch_id': 'stock_frame', 'label_date': td.strftime("%Y-%m-%d"), 'label_id': {"$in": ['revenue_growth_2y']}})
    growth_label_data_profit = mongodb_utils.get_labeldata(CONST_PARAM_ASSET_LABEL, {'label_arch_id': 'stock_frame', 'label_date': td.strftime("%Y-%m-%d"), 'label_id': {"$in": ['netprofit_growth_2y']}})
    growth_label_data_rev = growth_label_data_rev[['asset_id', 'value']]
    growth_label_data_profit = growth_label_data_profit[['asset_id', 'value']]
    growth_df = pd.merge(growth_label_data_rev, growth_label_data_profit, how='outer', on='asset_id')
    growth_df.rename(columns={'value_x': 'revenue_growth_2y', 'value_y':'netprofit_growth_2y'}, inplace=True)
    growth_df['avg_growth'] = growth_df.apply(lambda x: x['revenue_growth_2y'] if pd.isnull(x['netprofit_growth_2y']) else x['netprofit_growth_2y'],  axis=1)
    # 条件1： 未来业绩增速大于等于20%
    growth_df = growth_df.loc[growth_df['avg_growth'] >= CONST_PARAM_GROWTH_threshold, ['asset_id', 'revenue_growth_2y','netprofit_growth_2y', 'avg_growth']]
    #求并
    important_stk_list = pd.merge(important_stk_list, growth_df, how='inner', on='asset_id')
    important_stk_list = important_stk_list[['asset_id', 'revenue_growth_2y', 'netprofit_growth_2y', 'avg_growth']]
    # print(growth_df)
    # print(important_stk_list)
    #3. 获取最新的PE(TTM)
    stk_pettm = mongodb_utils.get_stock_extend({'date': td.strftime("%Y-%m-%d")})
    stk_pettm = stk_pettm[['code', 'pe_ttm']]
    #求并
    important_stk_list = pd.merge(important_stk_list, stk_pettm, how='inner', left_on='asset_id', right_on='code')
    important_stk_list['peg'] = important_stk_list['pe_ttm'] * 0.01 / important_stk_list['avg_growth']
    # 条件2： PEG <= 2
    important_stk_list = important_stk_list.loc[important_stk_list['peg'] <= CONST_PARAM_PEG_threshold, ['asset_id', 'revenue_growth_2y', 'netprofit_growth_2y', 'avg_growth', 'pe_ttm', 'peg']]
    print(important_stk_list)

    # 3. 保存策略-深度价值
    stra_stk_list = pd.DataFrame()
    stra_stk_list['asset_id'] = important_stk_list['asset_id']
    stra_stk_list['pool_type'] = '策略-深度价值'
    stra_stk_list['import_date'] = td.strftime("%Y-%m-%d")
    print(stra_stk_list)
    mongodb_utils.insert_stk_pool(CONST_PARAM_ASSET_POOL, stra_stk_list)

    return

def main():

    #如果是周末则不运行
    wk = datetime.datetime.now().weekday() + 1
    if wk == 6 or wk ==7:
        print('周{}不更新A股数据'.format(wk))
        return 0

    td = datetime.date.today()
    #td = datetime.date(2024, 11, 11)
    generate_basic_pool(td)
    generate_import_pool(td)
    generate_grow_pool(td)

if __name__ == '__main__':
    #sys.stdout = Logger()
    main()