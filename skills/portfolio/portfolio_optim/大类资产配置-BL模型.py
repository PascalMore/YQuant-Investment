# -*- coding: utf-8 -*-

# 一、Black-Litterman模型概述
# ---
# 
#    Wealthfront、Betterment均使用Black-Litterman模型,为投资者实现资产组合配置。该模型最早于1990年,由高盛的两个交易员Fischer Black和Robert Litterman提出,随后发表于1992年。最初该模型被用于全球资本市场的配置。
#    
#  Black-Litterman模型是基于MPT基础上的资产配置理论。其主要的贡献是提供了一个理论框架，能够将市场均衡收益和个人观点整合到一块，用以重新估计更可靠的预期收益率，然后将预期收益率带入MVO，得出最优资产配置，使得优化结果更加稳定和准确。
#  
#  
# 二、公式
# ----
# ---
# 𝐸(𝑅)=[(𝜏𝛴)^(−1)+𝑃^𝑇 𝛺^(−1) 𝑃]^(−1) [(𝜏𝛴)^(−1) 𝜋+𝑃^𝑇 𝛺^(−1) 𝑞]
# 
# ---
#  
# 三、 在实践中应用Black-Litterman应用该模型，主要有如下步骤：
# ---
# 
# 1.	根据历史数据计算出历史收益率之均值及协方差矩阵
# 3.	求出先验预期收益之期望值
# 4.	融合投资人的个人观点
# 5.	根据公式计算出后验分布之期望值、协方差
# 6.	根据后验收益期望值与协方差矩阵，代入Markowitz模型进行资产配置
# 
# 

# 说明
# ---
# 𝜋：先验预期收益率之期望值
# •	一般来说以历史收益率均值作为先验预期收益之期望值
# •	根据市场现有价格、市场组合反推出市场隐含的均衡收益率来作为先验预期收益之期望值
# •	根据capm模型中的alpha(历史超额收益率)来估计先验预期收益之期望值




import numpy as np
import pandas as pd
from WindPy import w
from cvxopt import matrix, solvers
from scipy.stats.mstats import gmean
from matplotlib import pyplot as plt


#建立函数计算年化收益率、年化标准差、相关系数矩阵
def describe(return_table, is_print=True):
    """
    输出收益率矩阵的描述性统计量，包括：
        年化收益率
        年化标准差
        相关系数矩阵
    
    Args:
        return_table (DataFrame): 收益率矩阵，列为资产，值为按日期升序排列的收益率
        is_print (bool): 是否直接输出

    Returns:
        dict: 描述性统计量字典，键为"annualized_return", "annualized_volatility", "covariance_matrix"和"coefficient_matrix"

    Examples:
        >> describe(return_table)
        >> describe(return_table, is_print=True)
    """
    
    output = {}
    ann_rt = {}
    for col, arr in return_table.iteritems():
        ann_rt[col] = gmean(arr.dropna() + 1.) ** 252 - 1
    #output['annualized_return'] = pd.DataFrame(dict(zip(return_table.columns, gmean(return_table+1.)**252 - 1.)), index=[0], columns=return_table.columns)
    output['annualized_return'] = pd.DataFrame([ann_rt], index=[0])
    #print(pd.DataFrame([ann_rt], index=[0]))
    output['annualized_volatility'] = pd.DataFrame(return_table.std() * np.sqrt(250)).T
    output['covariance_matrix'] = return_table.cov() * 250.
    output['coefficient_matrix'] = return_table.corr()
        
    if is_print:
        for key, val in output.items():
            print("{}:\n{}\n".format(key, val))
    
    return output


# 计算最小方差组合
def get_BL_minimum_variance_portfolio(return_table,tau=0.05,P=None,Q=None,Omega=None, allow_short=False, show_details=True):
    """
    计算最小方差组合
    
    Args:
        return_table (DataFrame): 收益率矩阵，列为资产，值为按日期升序排列的收益率
        allow_short (bool): 是否允许卖空
        show_details (bool): 是否显示细节
        P(np.array): 观点矩阵
        Q(np.array): 观点收益矩阵
        Omega(np.array): 观点置信度矩阵
        tau(float): 为均衡收益方差的刻度值，体现了对个人观点在总体估计中的权重

    Returns:
        dict: 最小方差组合的权重信息，键为资产名，值为权重
    """
    
    assets = return_table.columns
    n_asset = len(assets)
    if n_asset < 2:
        weights = np.array([1.])
        weights_dict = {assets[0]: 1.}
    else:
        output = describe(return_table, is_print=False)
        covmat =(output['covariance_matrix'])
        expected_return = output['annualized_return'].iloc[0, :]
    
        # 求解调整后的期望收益、方差
        adjustedReturn = expected_return + tau*covmat.dot(P.transpose()).dot(np.linalg.inv(Omega+tau*(P.dot(covmat).dot(P.transpose())))).dot(Q - P.dot(expected_return))
        right = (tau)*covmat.dot(P.transpose()).dot(np.linalg.inv(Omega+P.dot(covmat).dot(P.transpose()))).dot(P.dot(tau*covmat))
        right = right.transpose()
        right = right.set_index(expected_return.index)
        M = tau*covmat - right
        Sigma_p = covmat + M
        adjustedReturn = adjustedReturn.values
        Sigma_p = matrix(Sigma_p.values)

        P = 2 * Sigma_p
        q = matrix(np.zeros(n_asset))

        if allow_short:
            G = matrix(0., (n_asset, n_asset))
        else:
            G = matrix(np.diag(-1 * np.ones(n_asset)))
        
        h = matrix(0., (n_asset, 1))
        A = matrix(np.ones(n_asset)).T
        b = matrix([1.0])
        solvers.options['show_progress'] = False
        sol = solvers.qp(P, q, G, h, A, b)
        weights = np.array(sol['x'].T)[0]
        weights_dict = dict(zip(assets, weights))

    r = np.dot(weights, output['annualized_return'].iloc[0, :].as_matrix())
    v = np.sqrt(np.dot(np.dot(weights, Sigma_p), weights.T))

    if show_details:
        print("""
    Minimum Variance Portfolio:
    Short Allowed: {}
    Portfolio Return: {}
    Portfolio Volatility: {}
    Portfolio Weights: {}
""".format(allow_short, r, v, "\n\t{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))).strip())
    
    return weights_dict


#计算最大效用组合，目标函数为：期望年化收益率 - 风险厌恶系数 * 期望年化方差，风险厌恶系数，越大表示对风险越厌恶，默认为3.0
def get_BL_maximum_utility_portfolio(return_table,tau=0.05,P=None,Q=None,Omega=None, risk_aversion=3., allow_short=False, show_details=True):
    """
    计算最大效用组合，目标函数为：期望年化收益率 - 风险厌恶系数 * 期望年化方差
    
    Args:0
        return_table (DataFrame): 收益率矩阵，列为资产，值为按日期升序排列的收益率
        risk_aversion (float): 风险厌恶系数，越大表示对风险越厌恶，默认为3.0
        allow_short (bool): 是否允许卖空
        show_details (bool): 是否显示细节
        P(np.array): 观点矩阵
        Q(np.array): 观点收益矩阵
        Omega(np.array): 观点置信度矩阵
        tau(float): 为均衡收益方差的刻度值，体现了对个人观点在总体估计中的权重

    Returns:
        dict: 最小方差组合的权重信息，键为资产名，值为权重
    """

    assets = return_table.columns
    n_asset = len(assets)
    if n_asset < 2:
        weights = np.array([1.])
        weights_dict = {assets[0]: 1.}
    else:
        output = describe(return_table, is_print=False)
        covmat =(output['covariance_matrix'])
        expected_return = output['annualized_return'].iloc[0, :]
    
        # 求解调整后的期望收益、方差
        adjustedReturn = expected_return + tau*covmat.dot(P.transpose()).dot(np.linalg.inv(Omega+tau*(P.dot(covmat).dot(P.transpose())))).dot(Q - P.dot(expected_return))
        right = (tau)*covmat.dot(P.transpose()).dot(np.linalg.inv(Omega+P.dot(covmat).dot(P.transpose()))).dot(P.dot(tau*covmat))
        right = right.transpose()
        right = right.set_index(expected_return.index)
        M = tau*covmat - right
        Sigma_p = covmat + M
        adjustedReturn = adjustedReturn.values
        Sigma_p = matrix(Sigma_p.values)
            
        if abs(risk_aversion) < 0.01:
            max_ret = max(adjustedReturn)
            weights = np.array([1. if adjustedReturn[i] == max_ret else 0. for i in range(n_asset)])
            weights_dict = {asset: weights[i] for i, asset in enumerate(assets)}
        else:
            P = risk_aversion * Sigma_p
            q = matrix(-adjustedReturn.T)

            if allow_short:
                G = matrix(0., (n_asset, n_asset))
            else:
                G = matrix(np.diag(-1 * np.ones(n_asset)))

            h = matrix(0., (n_asset, 1))
            A = matrix(np.ones(n_asset)).T
            b = matrix([1.0])
            solvers.options['show_progress'] = False
            sol = solvers.qp(P, q, G, h, A, b)
            weights = np.array(sol['x'].T)[0]
            weights_dict = dict(zip(assets, weights))

    r = np.dot(weights, output['annualized_return'].iloc[0, :].as_matrix())
    v = np.sqrt(np.dot(np.dot(weights, Sigma_p), weights.T))
    
    if show_details:
        print("""
Maximum Utility Portfolio:
    Risk Aversion: {}
    Short Allowed: {}
    Portfolio Return: {}
    Portfolio Volatility: {}
    Portfolio Weights: {}
""".format(risk_aversion, allow_short, r, v, "\n\t{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))).strip())
    
    return weights_dict

#计算目标收益率的组合
def get_BL_target_return_portfolio(return_table, target_return, riskfree_rate=0., tau=0.05, P=None, Q=None, Omega=None, low=None, high=None, allow_short=False, leverage=None, rg=None, show_details=True):
    """
    计算目标收益率的组合： 目标收益率 = target_return
    
    Args:
        return_table (DataFrame): 收益率矩阵，列为资产，值为按日期升序排列的收益率
        target_return (float): 目标收益率
        riskfree_rate (float): 无风险收益率
        allow_short (bool): 是否允许卖空
        show_details (bool): 是否显示细节
        P(np.array): 观点矩阵
        Q(np.array): 观点收益矩阵
        Omega(np.array): 观点置信度矩阵
        low(np.array): 资产权重下限约束
        high(np.array): 资产权重上限约束
        leverage (float): 杠杆比例上限
        rg(float): 检视范围
        tau(float): 为均衡收益方差的刻度值，体现了对个人观点在总体估计中的权重

    Returns:
        dict: 目标收益率组合的权重信息，键为资产名，值为权重
    """
    
    assets = return_table.columns
    n_asset = len(assets)
    if n_asset < 2:
        output = describe(return_table, is_print=False)
        r = output['annualized_return'].iat[0, 0]
        v = output['annualized_volatility'].iat[0, 0]
        weights_dict = {assets[0]: 1.}
    else:
        bl,efs = get_BL_efficient_frontier(return_table,tau,P=P,Q=Q,Omega=Omega,low=low,high=high,allow_short=allow_short, leverage=leverage, n_samples=CONST_N_SAMPLES)
        i_star = min(range(len(efs)), key=lambda x: abs(efs.at[x, "returns"] - target_return))
        r = efs.at[i_star, "returns"]
        v = efs.at[i_star, "risks"]
        stat = efs.at[i_star, "status"]
        weights_dict = efs.at[i_star, "weights"]
        #输出检视范围内的有效前沿
        i_returns, i_risks,i_weights = [], [], []
        if(not np.isnan(rg)):
            for i in range(len(efs)):
                if( r - rg <= efs.at[i, "returns"] <= r + rg):
                    i_returns.append(efs.at[i, "returns"])
                    i_risks.append(efs.at[i, "risks"])
                    i_weights.append(efs.at[i, "weights"])
                    
    s = (r - riskfree_rate) / v
    
    if show_details:
        print("""
Target Return Portfolio:
    Optimal Status: {}
    Riskfree Rate: {}
    Short Allowed: {}
    Portfolio Return: {}
    Portfolio Volatility: {}
    Portfolio Sharpe: {}
    Portfolio Weights: {}
""".format(stat, riskfree_rate, allow_short, r, v, s, "\n\t{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))).strip())
    
    output = {
        "overview": {
            "Target Return Portfolio": "",
            "Riskfree Rate": riskfree_rate,
            "Short Allowed": allow_short,
            "Portfolio Return": r,
            "Portfolio Volatility": v,
            "Portfolio Sharpe": s,
            "Portfolio Weights": "{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))
            },
        "weights": weights_dict,
        "adjusted_return": bl["adjusted_return"],
        "cov_mat": bl["cov_mat"],
        "inspect": {
            "i_retruns": i_returns,
            "i_risks": i_risks,
            "i_weights": i_weights
            }
        }
    
    return output

#计算目标波动率的组合
def get_BL_target_vol_portfolio(return_table, target_vol, riskfree_rate=0., tau=0.05, P=None, Q=None, Omega=None, low=None, high=None, allow_short=False, leverage=None, rg=None, show_details=True):
    """
    计算目标收益率的组合： 目标收益率 = target_return
    
    Args:
        return_table (DataFrame): 收益率矩阵，列为资产，值为按日期升序排列的收益率
        target_return (float): 目标收益率
        riskfree_rate (float): 无风险收益率
        allow_short (bool): 是否允许卖空
        show_details (bool): 是否显示细节
        P(np.array): 观点矩阵
        Q(np.array): 观点收益矩阵
        Omega(np.array): 观点置信度矩阵
        low(np.array): 资产权重下限约束
        high(np.array): 资产权重上限约束
        leverage(float): 杠杆比例上限
        rg(float): 检视范围
        tau(float): 为均衡收益方差的刻度值，体现了对个人观点在总体估计中的权重

    Returns:
        dict: 目标收益率组合的权重信息，键为资产名，值为权重
    """
    
    assets = return_table.columns
    n_asset = len(assets)
    if n_asset < 2:
        output = describe(return_table, is_print=False)
        r = output['annualized_return'].iat[0, 0]
        v = output['annualized_volatility'].iat[0, 0]
        weights_dict = {assets[0]: 1.}
    else:
        bl, efs = get_BL_efficient_frontier(return_table,tau,P=P,Q=Q,Omega=Omega,low=low,high=high,allow_short=allow_short, leverage=leverage, n_samples=CONST_N_SAMPLES)
        i_star = min(range(len(efs)), key=lambda x: abs(efs.at[x, "risks"] - target_vol))
        r = efs.at[i_star, "returns"]
        v = efs.at[i_star, "risks"]
        stat = efs.at[i_star, "status"]
        weights_dict = efs.at[i_star, "weights"]
        #输出检视范围内的有效前沿
        i_returns, i_risks,i_weights = [], [], []
        if(not np.isnan(rg)):
            for i in range(len(efs)):
                if( r - rg <= efs.at[i, "returns"] <= r + rg):
                    i_returns.append(efs.at[i, "returns"])
                    i_risks.append(efs.at[i, "risks"])
                    i_weights.append(efs.at[i, "weights"])
    
    s = (r - riskfree_rate) / v
    
    if show_details:
        print("""
Target Volatility Portfolio:
    Optimal Status: {}
    Riskfree Rate: {}
    Short Allowed: {}
    Portfolio Return: {}
    Portfolio Volatility: {}
    Portfolio Sharpe: {}
    Portfolio Weights: {}
""".format(stat, riskfree_rate, allow_short, r, v, s, "\n\t{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))).strip())
    
    output = {
        "overview": {
            "Target Volatility Portfolio": "",
            "Riskfree Rate": riskfree_rate,
            "Short Allowed": allow_short,
            "Portfolio Return": r,
            "Portfolio Volatility": v,
            "Portfolio Sharpe": s,
            "Portfolio Weights": "{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))
            },
        "weights": weights_dict,
        "adjusted_return": bl["adjusted_return"],
        "cov_mat": bl["cov_mat"],
        "inspect": {
            "i_retruns": i_returns,
            "i_risks": i_risks,
            "i_weights": i_weights
            }
        }
    
    return output

def get_maximum_sharpe_portfolio(return_table, riskfree_rate=0.,tau=0.05,P=None,Q=None,Omega=None, low=None, high=None, allow_short=False, leverage=None, rg=None, show_details=True):
    """
    计算最大效用组合，目标函数为：（期望年化收益率 - 无风险收益率）/ 期望年化方差
    
    Args:
        return_table (DataFrame): 收益率矩阵，列为资产，值为按日期升序排列的收益率
        riskfree_rate (float): 无风险收益率
        allow_short (bool): 是否允许卖空
        show_details (bool): 是否显示细节
        P(np.array): 观点矩阵
        Q(np.array): 观点收益矩阵
        Omega(np.array): 观点置信度矩阵
        low(np.array): 资产权重下限约束
        high(np.array): 资产权重上限约束
        leverage(float): 杠杆比例上限
        rg(float): 检视范围
        tau(float): 为均衡收益方差的刻度值，体现了对个人观点在总体估计中的权重

    Returns:
        dict: 最大Sharp组合的权重信息，键为资产名，值为权重
    """

    assets = return_table.columns
    n_asset = len(assets)
    if n_asset < 2:
        output = describe(return_table, is_print=False)
        r = output['annualized_return'].iat[0, 0]
        v = output['annualized_volatility'].iat[0, 0]
        weights_dict = {assets[0]: 1.}
    else:
        bl, efs = get_BL_efficient_frontier(return_table,tau,P=P,Q=Q,Omega=Omega,low = low, high = high, allow_short=allow_short, leverage=leverage, n_samples=CONST_N_SAMPLES)
        i_star = max(range(len(efs)), key=lambda x: (efs.at[x, "returns"] - riskfree_rate) / efs.at[x, "risks"])
        r = efs.at[i_star, "returns"]
        v = efs.at[i_star, "risks"]
        stat = efs.at[i_star, "status"]
        weights_dict = efs.at[i_star, "weights"]
        #输出检视范围内的有效前沿
        i_returns, i_risks,i_weights = [], [], []
        if(not np.isnan(rg)):
            for i in range(len(efs)):
                if( r - rg <= efs.at[i, "returns"] <= r + rg):
                    i_returns.append(efs.at[i, "returns"])
                    i_risks.append(efs.at[i, "risks"])
                    i_weights.append(efs.at[i, "weights"])    
                    
    s = (r - riskfree_rate) / v
    
    if show_details:
        print("""
Maximum Sharpe Portfolio:
    Optimal Status: {}
    Riskfree Rate: {}
    Short Allowed: {}
    Portfolio Return: {}
    Portfolio Volatility: {}
    Portfolio Sharpe: {}
    Portfolio Weights: {}
""".format(stat,riskfree_rate, allow_short, r, v, s, "\n\t{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))).strip())
    
    output = {
        "overview": {
            "Maximum Sharpe Portfolio": "",
            "Riskfree Rate": riskfree_rate,
            "Short Allowed": allow_short,
            "Portfolio Return": r,
            "Portfolio Volatility": v,
            "Portfolio Sharpe": s,
            "Portfolio Weights": "{}".format("\n\t".join("{}: {:.1%}".format(k, v) for k, v in weights_dict.items()))
            },
        "weights": weights_dict,
        "adjusted_return": bl["adjusted_return"],
        "cov_mat": bl["cov_mat"],
        "inspect": {
            "i_retruns": i_returns,
            "i_risks": i_risks,
            "i_weights": i_weights
            }
        }
    
    return output


def get_BL_efficient_frontier(return_table,tau=0.05,P=None,Q=None,Omega=None,low=None,high=None,allow_short=False, leverage=None, n_samples=100):
    """
    计算Efficient Frontier
    
    Args:
        return_table (DataFrame): 收益率矩阵，列为资产，值为按日期升序排列的收益率
        n_samples (int): 用于计算Efficient Frontier的采样点数量
        P(np.array): 观点矩阵
        Q(np.array): 观点收益矩阵
        Omega(np.array): 观点置信度矩阵
        low(np.array): 资产权重下限约束
        high(np.array): 资产权重上限约束
        leverage(float): 杠杆比例上限
        tau(float): 为均衡收益方差的刻度值，体现了对个人观点在总体估计中的权重

    Returns:
        DataFrame: Efficient Frontier的结果，列为"returns", "risks", "weights"
    """
    assets = return_table.columns
    n_asset = len(assets)
    if n_asset < 2:
        raise ValueError("There must be at least 2 assets to calculate the efficient frontier!")

    output = describe(return_table, is_print=False)
    covmat =(output['covariance_matrix'])
    expected_return = output['annualized_return'].iloc[0, :]
    #print(expected_return)
    
    # 求解调整后的期望收益、方差
    adjustedReturn = expected_return + tau*covmat.dot(P.transpose()).dot(np.linalg.inv(Omega+tau*(P.dot(covmat).dot(P.transpose())))).dot(Q - P.dot(expected_return))
    right = (tau)*covmat.dot(P.transpose()).dot(np.linalg.inv(Omega+P.dot(covmat).dot(P.transpose()))).dot(P.dot(tau*covmat))
    right = right.transpose()
    right = right.set_index(expected_return.index)
    M = tau*covmat - right
    Sigma_p = covmat + M
    
    adjustedReturn = adjustedReturn.values
    Sigma_p = matrix(Sigma_p.values)
	
    risks, returns, weights = [], [], []
    for level_return in np.linspace(min(adjustedReturn), max(adjustedReturn), n_samples):
        P = 2 * Sigma_p
        q = matrix(np.zeros(n_asset))
        
        #针对上下限约束，构造G和h
        if allow_short:
            G_low = matrix(np.diag( [0. if np.isnan(x) else -1. for x in low] ))          
            #G_low = matrix(0., (n_asset, n_asset))
        else:
            G_low = matrix(np.diag(-1 * np.ones(n_asset)))
        
        G_high = matrix(np.diag( [0. if np.isnan(x) else 1. for x in high] )) 
        
        h_low = matrix(np.nan_to_num(-1 * low, copy=True, nan=0.), (n_asset, 1))
        h_high = matrix(np.nan_to_num(high, copy=True, nan=0.), (n_asset, 1))
        
        G = matrix(np.vstack((G_low, G_high)))
        h = matrix(np.vstack((h_low, h_high)))
        
        if(np.isnan(leverage)):
            A = matrix(np.row_stack((np.ones(n_asset), adjustedReturn)))
            #[重要]：这里设定了所有权重之和加起来严格等于100%
            b = matrix([1.0, level_return])

        else:
            G_leverage = matrix(np.ones(n_asset), (1, n_asset))
            h_leverage = matrix(leverage, (1,1))
            G = matrix(np.vstack((G, G_leverage)))
            h = matrix(np.vstack((h, h_leverage)))
            
            A = matrix(adjustedReturn, (1, n_asset))
            b = matrix(level_return)
            
        solvers.options['show_progress'] = False
        try:
            sol = solvers.qp(P, q, G, h, A, b)
        except ValueError as e:
            #print("{0}没有找到最优解".format(level_return))
            pass
        else:
            risks.append(np.sqrt(sol['primal objective']))
            returns.append(level_return)
            weights.append(dict(zip(assets, list(sol['x'].T))))
    output = {
              "status": sol["status"],
              "returns": returns,
              "risks": risks,
              "weights": weights}
    
    bl = {"adjusted_return": adjustedReturn,
          "cov_mat": M
        }
    
    output = pd.DataFrame(output)
    return bl,output

def draw_efficient_frontier(effcient_frontier_output):
    """
    绘出Efficient Frontier
    
    Args:
        effcient_frontier_output: Efficient Frontier的计算结果，即get_efficient_frontier的输出
    """
    fig = plt.figure(figsize=(7, 4))
    ax = fig.add_subplot(111)
    ax.plot(effcient_frontier_output['risks'], effcient_frontier_output['returns'])
    ax.set_title('Efficient Frontier', fontsize=14)
    ax.set_xlabel('Standard Deviation', fontsize=12)
    ax.set_ylabel('Expected Return', fontsize=12)
    ax.tick_params(labelsize=12)
    plt.show()

def save_to_excel(s, path):
    #输出概览
    sum_df = pd.DataFrame(data=list(s["overview"].items()))
    #输出权重
    weight_df = pd.DataFrame(data=s["weights"], index=["权重(%)"])
    weight_df = (weight_df.T * 100)
    weight_df.to_excel(path, sheet_name="资产配置")
    #输出调整后预期收益率
    adjusted_return_df = pd.DataFrame(data=s["adjusted_return"], columns=["预期年化收益率（%）"], index = s["weights"].keys())
    adjusted_return_df = adjusted_return_df * 100
    #输出调整后协方差矩阵
    cov_mat_df = pd.DataFrame(data=s["cov_mat"])
    #输出有效前沿上的组合
    inspect_port = pd.DataFrame({"组合收益率(%)":[i*100 for i in s["inspect"]["i_retruns"]], "组合波动率(%)": [i*100 for i in s["inspect"]["i_risks"]]})
    #将权重数据按列输出
    dict_w = {}
    for i in s["inspect"]["i_weights"]:
        for k, v in i.items():
            if(k in dict_w):
                dict_w[k].append(v)
            else:
                dict_w[k] = [v]
    for k, v in dict_w.items():
        inspect_port[k] = v
    
    with pd.ExcelWriter(path) as writer:
        sum_df.to_excel(writer, sheet_name="总览", index=False, header=False)
        weight_df.to_excel(writer, sheet_name='资产配置')
        adjusted_return_df.to_excel(writer, sheet_name='调整后预期收益率')
        cov_mat_df.to_excel(writer, sheet_name='调整后协方差矩阵')
        if(len(inspect_port) > 0):
            inspect_port.to_excel(writer, sheet_name='有效前沿')

###################配置文件###########
excelFile = "BL模型参数.xlsx"
sheet1 = "参数配置"
sheet2 = "BL模型观点"
sheet3 = "收盘数据"
CONST_N_SAMPLES = 1000
#####################################

# 主程序入口
def main():
    df_conf = pd.read_excel(excelFile, sheet_name=sheet1)
    df_option = pd.read_excel(excelFile, sheet_name=sheet2, header=1, index_col=0)
    price_data = pd.read_excel(excelFile, sheet_name=sheet3, header=1, index_col=0)
    rt_data = pd.DataFrame()
    #参数设置
    conf = df_conf.set_index("Key").T.to_dict()
    start_date = str(int(conf["起始日期"]["Value"]))
    end_date = str(int(conf["结束日期"]["Value"]))
    tau = conf["tau"]["Value"]
    risk_free = conf["无风险利率"]["Value"]
    target_return = conf["目标年化收益率"]["Value"]
    target_vol = conf["目标年化波动率"]["Value"]
    is_short = False if conf["是否做空"]["Value"] == "否" else True
    leverage = conf["杠杆上限"]["Value"]
    inspect_range = conf["检视范围"]["Value"]
    
    assets_id = df_option.columns[:-1].tolist()
    missed_id = price_data.columns[price_data.isnull().any()].tolist()
    user_data = price_data.loc[:,~price_data.isnull().any()]

    #从wind获取数据
    w.start()
    errorCode,his_data = w.wsd(missed_id, "close", start_date, end_date,"PriceAdj=F",usedf=True)
    #合并用户输入数据和历史获取的数据
    his_data = pd.merge(his_data, user_data, how="outer", left_index=True, right_index=True)
    #按照assets_id来调整列顺序
    his_data = his_data.reindex(columns=assets_id)
    
    #计算收益率
    for i in assets_id:
        rt_data[i] = his_data[i] / his_data[i].shift() - 1.        
    #修改describe的算法，让年化收益和波动率可以在缺少的情况下也可以计算
    rt_data.dropna(inplace=True, how="all")
    output = describe(rt_data, is_print=False)

    #获取cov mat和年化收益率
    covariance_matrix = output['covariance_matrix']
    #expected_return = output['annualized_return'].iloc[0, :]
    
    #提取P、Q、Omega
    #将na填充为0
    df_option.fillna(0, inplace=True)
    P = df_option.iloc[:-2].drop(["Value"], axis=1).values
    Q = df_option.iloc[:-2]["Value"].tolist()
    Omega = tau*(P.dot(covariance_matrix).dot(P.transpose()))
    Omega = np.diag(np.diag(Omega,k=0))
    
    #获取投资比例上下限
    low_limit = df_option.loc["下限"].drop(["Value"]).values
    high_limit = df_option.loc["上限"].drop(["Value"]).values

    #优化资产配置1:（最大Sharp）
    aa1 = get_maximum_sharpe_portfolio(rt_data, riskfree_rate=risk_free,tau=tau,P=P,Q=Q,Omega=Omega,low=low_limit,high=high_limit,allow_short=is_short, leverage = leverage, rg = inspect_range, show_details=True)
    save_to_excel(aa1, "最优夏普率的资产配置.xlsx")
    #优化资产配置2：（目标收益率）
    if(not np.isnan(target_return)):
        aa2 = get_BL_target_return_portfolio(rt_data, target_return, riskfree_rate=risk_free, tau=tau, P=P,Q=Q,Omega=Omega,low=low_limit,high=high_limit,allow_short=is_short, leverage = leverage, rg = inspect_range, show_details=True)
        save_to_excel(aa2, "目标收益率的资产配置.xlsx")
    #优化资产配置3：（目标波动率）
    if(not np.isnan(target_vol)):
        aa3 = get_BL_target_vol_portfolio(rt_data, target_vol, riskfree_rate=risk_free, tau=tau, P=P,Q=Q,Omega=Omega,low=low_limit,high=high_limit,allow_short=is_short, leverage = leverage, rg = inspect_range, show_details=True)
        save_to_excel(aa3, "目标波动率的资产配置.xlsx")
    
if __name__ == "__main__":
    main()