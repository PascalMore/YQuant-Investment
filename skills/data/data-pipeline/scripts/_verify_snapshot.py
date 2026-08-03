import json

with open('/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/2026-08-03/review_pending/sm004_2026-07-31_repair_r2_snapshot.json') as f:
    s = json.load(f)
print('keys:', list(s.keys()))
print('position rows keys:', list(s['position_2026-07-31_ZO-002_rows'][0].keys()))
print('nav row:', s['nav_2026-07-31_ZO-002_rows'][0])
print('basic 错误:', s['basic_错误_反向_ZO-002_nameSM004_rows'][0])
print('basic 合法:', s['basic_合法_SM004_nameZO-002_rows'][0])
codes = [r['asset_wind_code'] for r in s['position_2026-07-31_ZO-002_rows']]
print('001232.SZ in 23 rows?', '001232.SZ' in codes)
print('all codes count:', len(codes), 'unique:', len(set(codes)))
print('SM004 nav all =', s['nav_SM004_all_count'])
print('SM004 trade all =', s['trade_SM004_all_count'])
print('SM004 position all =', s['position_SM004_all_count'])
print('001232.SZ on 7/31 =', s['position_2026-07-31_001232.SZ_in_[SM004,ZO-002]_count'])
print('max nav_date:', s['portfolio_nav_max_nav_date'])