#!/usr/bin/env python3
"""
股票名称校准映射表

用于修正 OCR 识别易出错的股票名称。
当代码在映射表中时，只认映射表中对应的正确名称，其他名称都会被替换。

Usage:
    from stock_name_corrections import STOCK_NAME_CORRECTIONS
"""

# 格式: {股票代码: 正确股票名称}
# OCR 识别到的名称如果与此处不一致，会被替换为正确名称

STOCK_NAME_CORRECTIONS = {
    # 港股
    "0425.HK": "敏实集团",
    "0670.HK": "中国东方航空股份",
    "0700.HK": "腾讯控股",
    "0753.HK": "中国国航",
    "1030.HK": "新城发展",
    "1164.HK": "中广核矿业",
    "1277.HK": "力量发展",
    "1398.HK": "工商银行",
    "1519.HK": "极兔速递-W",
    "1729.HK": "汇聚科技",
    "1888.HK": "建滔积层板",
    "1908.HK": "建发国际集团",
    "2097.HK": "蜜雪集团",
    "2328.HK": "中国财险",
    "2380.HK": "中国财险",
    "2588.HK": "中银航空租赁",
    "6181.HK": "老铺黄金",
    "6990.HK": "科伦博泰生物",
    "9868.HK": "小鹏集团-W",
    "3899.HK": "中集安瑞科",
    "2259.HK": "紫金黄金国际",
    "2517.HK": "锅圈",
    "2611.HK": "国泰君安",
    "2643.HK": "曹操出行",
    "3668.HK": "兖煤澳大利亚",
    "3858.HK": "佳鑫国际资源",
    "3900.HK": "绿城中国",
    "3958.HK": "东方证券",
    "6855.HK": "亚盛医药-B",
    "6869.HK": "长飞光纤光缆",
    "9699.HK": "顺丰同城",
    "9988.HK": "阿里巴巴-W",
    "9998.HK": "阿里巴巴-W",
}

# Some holdings screenshots use common brand names while the Wind security name
# follows the listed company name. Treat these as aliases, then store the
# standardized name from STOCK_NAME_CORRECTIONS.
STOCK_NAME_ALIASES = {
    "2097.HK": {"蜜雪冰城"},
}
