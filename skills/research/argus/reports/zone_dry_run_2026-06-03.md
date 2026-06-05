# Argus ZoneRuleEngine Dry Run - 2026-06-03

Source: MongoDB `172.25.240.1:27017/tradingagents.08_research_argus_signal_pool`.
Note: collection schema uses `date`; `target_date` is absent/null, so dry-run queried `date = "2026-06-03"`.

## Summary

- Records: 149
- Changed: 129 (86.58%)
- Safety verdict: NOT SAFE for silent migration; change rate exceeds 20% threshold.

## Zone Distribution

| Zone | Current | Dry-run | Delta |
|---|---:|---:|---:|
| SCAN | 0 | 129 | +129 |
| WATCH | 149 | 20 | -129 |
| CANDIDATE | 0 | 0 | +0 |
| CONVICTION | 0 | 0 | +0 |

## Changed Reason Counts

| Rule | Count | Interpretation |
|---|---:|---|
| scan | 129 | Failed WATCH minimum, fell through to residual SCAN |

## Dry-run Results

| wind_code | stock_name | 当前zone | dry-run zone | 是否变化 | 原因 |
|---|---|---|---|---|---|
| 000039.SZ | 中集集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 000333.SZ | 美的集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 000338.SZ | 潍柴动力 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 000415.SZ | 渤海租赁 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 000425.SZ | 徐工机械 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 000657.SZ | 中钨高新 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 000960.SZ | 锡业股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 000962.SZ | 东方钽业 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 001233.SZ | 海安集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 001979.SZ | 招商蛇口 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002142.SZ | 宁波银行 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002155.SZ | 湖南黄金 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002222.SZ | 福晶科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002353.SZ | 杰瑞股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002371.SZ | 北方华创 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002384.SZ | 东山精密 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002409.SZ | 雅克科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002436.SZ | 兴森科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002444.SZ | 巨星科技 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.515 >= 0.2; products 2 >= 1 |
| 002448.SZ | 中原内配 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002475.SZ | 立讯精密 | WATCH | WATCH | NO | bayesian 0.45 >= 0.35; consensus 0.514 >= 0.2; products 3 >= 1 |
| 002487.SZ | 大金重工 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002497.SZ | 雅化集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002602.SZ | 世纪华通 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002850.SZ | 科达利 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 002916.SZ | 深南电路 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 0148.HK | 建滔集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 0425.HK | 敏实集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 0700.HK | 腾讯控股 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 0836.HK | 华润电力 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 0883.HK | 中国海洋石油 | WATCH | WATCH | NO | bayesian 0.45 >= 0.35; consensus 0.518 >= 0.2; products 3 >= 1 |
| 0941.HK | 中国移动 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 0981.HK | 中芯国际 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.513 >= 0.2; products 2 >= 1 |
| 1024.HK | 快手-W | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1030.HK | 新城发展 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1109.HK | 华润置地 | WATCH | WATCH | NO | bayesian 0.45 >= 0.35; consensus 0.518 >= 0.2; products 3 >= 1 |
| 1164.HK | 中广核矿业 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1318.HK | 东方证券 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1347.HK | 华虹半导体 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1378.HK | 中国宏桥 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1519.HK | 极兔速递-W | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1530.HK | 三生制药 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1776.HK | 广发证券 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1836.HK | 九兴控股 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1888.HK | 建滔积层板 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 1908.HK | 建发国际集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 2259.HK | 紫金黄金国际 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 2328.HK | 中国财险 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 2588.HK | 中银航空租赁 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 2643.HK | 曹操出行 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300001.SZ | 特锐德 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300014.SZ | 亿纬锂能 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300017.SZ | 网宿科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300037.SZ | 新宙邦 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300083.SZ | 创世纪 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300246.SZ | 宝莱特 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300274.SZ | 阳光电源 | WATCH | WATCH | NO | bayesian 0.43 >= 0.35; consensus 0.517 >= 0.2; products 3 >= 1 |
| 300285.SZ | 国瓷材料 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300308.SZ | 中际旭创 | WATCH | WATCH | NO | bayesian 0.45 >= 0.35; consensus 0.518 >= 0.2; products 3 >= 1 |
| 300316.SZ | 晶盛机电 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300394.SZ | 天孚通信 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300432.SZ | 富临精工 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300476.SZ | 胜宏科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300502.SZ | 新易盛 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300620.SZ | 光库科技 | WATCH | WATCH | NO | bayesian 0.575 >= 0.35; consensus 0.525 >= 0.2; products 1 >= 1 |
| 300666.SZ | 江丰电子 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300672.SZ | 国科微 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300747.SZ | 锐科激光 | WATCH | WATCH | NO | bayesian 0.635 >= 0.35; consensus 0.525 >= 0.2; products 1 >= 1 |
| 300750.SZ | 宁德时代 | WATCH | WATCH | NO | bayesian 0.45 >= 0.35; consensus 0.517 >= 0.2; products 4 >= 1 |
| 300757.SZ | 罗博特科 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 300776.SZ | 帝尔激光 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.514 >= 0.2; products 2 >= 1 |
| 301188.SZ | 力诺药包 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 301217.SZ | 铜冠铜箔 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 301486.SZ | 致尚科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 301666.SZ | 大普微-UW | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 3668.HK | 兖煤澳大利亚 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 3858.HK | 佳鑫国际资源 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 3900.HK | 绿城中国 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 3933.HK | 联邦制药 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 3958.HK | 东方证券 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.515 >= 0.2; products 2 >= 1 |
| 600031.SH | 三一重工 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600078.SH | 澄星股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600301.SH | 华锡有色 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600309.SH | 万华化学 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600415.SH | 小商品城 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600482.SH | 中国动力 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600487.SH | 亨通光电 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600519.SH | 贵州茅台 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600590.SH | 泰豪科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600732.SH | 爱旭股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600763.SH | 通策医疗 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600919.SH | 江苏银行 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 600961.SH | 株冶集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601058.SH | 赛轮轮胎 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601126.SH | 四方股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601138.SH | 工业富联 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601168.SH | 西部矿业 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601231.SH | 环旭电子 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601288.SH | 农业银行 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601636.SH | 旗滨集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601899.SH | 紫金矿业 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.515 >= 0.2; products 2 >= 1 |
| 601939.SH | 建设银行 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 601958.SH | 金钼股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603225.SH | 新凤鸣 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603268.SH | 松发股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603298.SH | 杭叉集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603435.SH | 嘉德利 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603699.SH | 纽威股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603737.SH | DR三棵树 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603806.SH | 福斯特 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603855.SH | 华荣股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603893.SH | 瑞芯微 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 603986.SH | 兆易创新 | WATCH | WATCH | NO | bayesian 0.415 >= 0.35; consensus 0.513 >= 0.2; products 1 >= 1 |
| 603993.SH | 洛阳钼业 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 605117.SH | 德业股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 605499.SH | 东鹏饮料 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 605589.SH | 圣泉集团 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 6855.HK | 亚盛医药-B | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688008.SH | 澜起科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688019.SH | 安集科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688041.SH | 海光信息 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688072.SH | 拓荆科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688205.SH | 德科立 | WATCH | WATCH | NO | bayesian 0.575 >= 0.35; consensus 0.525 >= 0.2; products 1 >= 1 |
| 688213.SH | 思特威-W | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688249.SH | 晶合集成 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688256.SH | 寒武纪 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.519 >= 0.2; products 2 >= 1 |
| 688290.SH | 景业智能 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688301.SH | 奕瑞科技 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688347.SH | 华虹公司 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688390.SH | 固德威 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.513 >= 0.2; products 2 >= 1 |
| 688403.SH | 汇成股份 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688508.SH | 芯朋微 | WATCH | SCAN | YES | bayesian 0.265 < WATCH 0.35 |
| 688525.SH | 佰维存储 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688545.SH | 兴福电子 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688548.SH | 广钢气体 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688630.SH | 芯碁微装 | WATCH | WATCH | NO | bayesian 0.415 >= 0.35; consensus 0.513 >= 0.2; products 1 >= 1 |
| 688677.SH | 海泰新光 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688777.SH | 中控技术 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688778.SH | 厦钨新能 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688789.SH | 宏华数科 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688808.SH | 联讯仪器 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688813.SH | 泰金新能 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688818.SH | 电科蓝天 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 688981.SH | 中芯国际 | WATCH | WATCH | NO | bayesian 0.375 >= 0.35; consensus 0.513 >= 0.2; products 2 >= 1 |
| 689009.SH | 九号公司-WD | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 9633.HK | 农夫山泉 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 9699.HK | 顺丰同城 | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 9988.HK | 阿里巴巴-W | WATCH | SCAN | YES | bayesian 0.325 < WATCH 0.35 |
| 9992.HK | 泡泡玛特 | WATCH | WATCH | NO | bayesian 0.45 >= 0.35; consensus 0.514 >= 0.2; products 3 >= 1 |

## Changed Stocks

| wind_code | stock_name | 当前zone | dry-run zone | bayesian | consensus | products | crowding | reason |
|---|---|---|---|---:|---:|---:|---|---|
| 000039.SZ | 中集集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 000333.SZ | 美的集团 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 000338.SZ | 潍柴动力 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 000415.SZ | 渤海租赁 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 000425.SZ | 徐工机械 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 000657.SZ | 中钨高新 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 000960.SZ | 锡业股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 000962.SZ | 东方钽业 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 001233.SZ | 海安集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 001979.SZ | 招商蛇口 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002142.SZ | 宁波银行 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002155.SZ | 湖南黄金 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002222.SZ | 福晶科技 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002353.SZ | 杰瑞股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002371.SZ | 北方华创 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002384.SZ | 东山精密 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002409.SZ | 雅克科技 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002436.SZ | 兴森科技 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002448.SZ | 中原内配 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002487.SZ | 大金重工 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002497.SZ | 雅化集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002602.SZ | 世纪华通 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002850.SZ | 科达利 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 002916.SZ | 深南电路 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 0148.HK | 建滔集团 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 0425.HK | 敏实集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 0700.HK | 腾讯控股 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 0836.HK | 华润电力 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 0941.HK | 中国移动 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1024.HK | 快手-W | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1030.HK | 新城发展 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1164.HK | 中广核矿业 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1318.HK | 东方证券 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1347.HK | 华虹半导体 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1378.HK | 中国宏桥 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1519.HK | 极兔速递-W | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1530.HK | 三生制药 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1776.HK | 广发证券 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1836.HK | 九兴控股 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1888.HK | 建滔积层板 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 1908.HK | 建发国际集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 2259.HK | 紫金黄金国际 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 2328.HK | 中国财险 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 2588.HK | 中银航空租赁 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 2643.HK | 曹操出行 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300001.SZ | 特锐德 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300014.SZ | 亿纬锂能 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300017.SZ | 网宿科技 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300037.SZ | 新宙邦 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300083.SZ | 创世纪 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300246.SZ | 宝莱特 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300285.SZ | 国瓷材料 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300316.SZ | 晶盛机电 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300394.SZ | 天孚通信 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300432.SZ | 富临精工 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300476.SZ | 胜宏科技 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300502.SZ | 新易盛 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300666.SZ | 江丰电子 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300672.SZ | 国科微 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 300757.SZ | 罗博特科 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 301188.SZ | 力诺药包 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 301217.SZ | 铜冠铜箔 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 301486.SZ | 致尚科技 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 301666.SZ | 大普微-UW | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 3668.HK | 兖煤澳大利亚 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 3858.HK | 佳鑫国际资源 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 3900.HK | 绿城中国 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 3933.HK | 联邦制药 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600031.SH | 三一重工 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600078.SH | 澄星股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600301.SH | 华锡有色 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600309.SH | 万华化学 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600415.SH | 小商品城 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600482.SH | 中国动力 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600487.SH | 亨通光电 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600519.SH | 贵州茅台 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600590.SH | 泰豪科技 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600732.SH | 爱旭股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600763.SH | 通策医疗 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600919.SH | 江苏银行 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 600961.SH | 株冶集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601058.SH | 赛轮轮胎 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601126.SH | 四方股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601138.SH | 工业富联 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601168.SH | 西部矿业 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601231.SH | 环旭电子 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601288.SH | 农业银行 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601636.SH | 旗滨集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601939.SH | 建设银行 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 601958.SH | 金钼股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603225.SH | 新凤鸣 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603268.SH | 松发股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603298.SH | 杭叉集团 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603435.SH | 嘉德利 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603699.SH | 纽威股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603737.SH | DR三棵树 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603806.SH | 福斯特 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603855.SH | 华荣股份 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603893.SH | 瑞芯微 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 603993.SH | 洛阳钼业 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 605117.SH | 德业股份 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 605499.SH | 东鹏饮料 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 605589.SH | 圣泉集团 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 6855.HK | 亚盛医药-B | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688008.SH | 澜起科技 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688019.SH | 安集科技 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688041.SH | 海光信息 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688072.SH | 拓荆科技 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688213.SH | 思特威-W | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688249.SH | 晶合集成 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688290.SH | 景业智能 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688301.SH | 奕瑞科技 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688347.SH | 华虹公司 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688403.SH | 汇成股份 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688508.SH | 芯朋微 | WATCH | SCAN | 0.265 | 0.513 | 1 | MEDIUM | bayesian 0.265 < WATCH 0.35 |
| 688525.SH | 佰维存储 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688545.SH | 兴福电子 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688548.SH | 广钢气体 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688677.SH | 海泰新光 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688777.SH | 中控技术 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688778.SH | 厦钨新能 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688789.SH | 宏华数科 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688808.SH | 联讯仪器 | WATCH | SCAN | 0.325 | 0.513 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688813.SH | 泰金新能 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 688818.SH | 电科蓝天 | WATCH | SCAN | 0.325 | 0.525 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 689009.SH | 九号公司-WD | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 9633.HK | 农夫山泉 | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 9699.HK | 顺丰同城 | WATCH | SCAN | 0.325 | 0.514 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
| 9988.HK | 阿里巴巴-W | WATCH | SCAN | 0.325 | 0.516 | 1 | MEDIUM | bayesian 0.325 < WATCH 0.35 |
