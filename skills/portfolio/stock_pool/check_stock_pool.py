import sys
sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')
from skills.data.data_interface import MongoReader
from skills.research.argus.config import ARGUS_CONFIG

db_name = ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents')
r = MongoReader(database=db_name)
db = r.db

# Stock pool zones
print("=== stock_pool counts by pool_zone ===")
for zone in db['05_portfolio_stock_pool'].distinct('pool_zone'):
    cnt = db['05_portfolio_stock_pool'].count_documents({'pool_zone': zone})
    print(f"  {zone}: {cnt}")

# Audit action counts
print()
print("=== audit counts by action ===")
for action in db['05_portfolio_stock_pool_audit'].distinct('action'):
    cnt = db['05_portfolio_stock_pool_audit'].count_documents({'action': action})
    print(f"  {action}: {cnt}")

# Active stocks (last action = entry/update, not exit)
pipeline = [{'$sort': {'created_at': 1}}, {'$group': {
    '_id': '$pool_id',
    'latest_action': {'$last': '$action'},
}}]
results = list(db['05_portfolio_stock_pool_audit'].aggregate(pipeline))
active = sum(1 for r in results if r['latest_action'] in ['entry', 'update'])
print()
print(f"Active stocks (last action entry/update): {active}")
print(f"Total stocks tracked: {len(results)}")

# Bayesian score range in stock_pool
print()
print("=== stock_pool bayesian_score range ===")
scores = list(db['05_portfolio_stock_pool'].aggregate([
    {'$project': {'bs': {'$ifNull': ['$entry_reason.metrics.bayesian_score', '$entry_reason.bayesian_score']}}},
    {'$group': {'_id': None, 'min': {'$min': '$bs'}, 'max': {'$max': '$bs'}, 'avg': {'$avg': '$bs'}}}
]))
if scores:
    print(f"  min: {scores[0]['min']:.3f}, max: {scores[0]['max']:.3f}, avg: {scores[0]['avg']:.3f}")

# Latest signal_pool date and bayesian range
latest_sp = db['08_research_argus_signal_pool'].find_one(sort=[('date', -1), ('_id', -1)])
if latest_sp:
    latest_date = latest_sp['date']
    scores_sp = list(db['08_research_argus_signal_pool'].aggregate([
        {'$match': {'date': latest_date}},
        {'$group': {'_id': None, 'min': {'$min': '$bayesian_score'}, 'max': {'$max': '$bayesian_score'}, 'avg': {'$avg': '$bayesian_score'}}}
    ]))
    print()
    print(f"=== signal_pool latest date: {latest_date} ===")
    if scores_sp:
        print(f"  min: {scores_sp[0]['min']:.3f}, max: {scores_sp[0]['max']:.3f}, avg: {scores_sp[0]['avg']:.3f}")
    print(f"  Records: {db['08_research_argus_signal_pool'].count_documents({'date': latest_date})}")

# Cross check: top stocks by bayesian in signal_pool vs stock_pool
print()
print("=== Top 10 by bayesian_score (signal_pool latest) ===")
top = db['08_research_argus_signal_pool'].find(
    {'date': latest_date}
).sort('bayesian_score', -1).limit(10)
for s in top:
    print(f"  {s['wind_code']} {s['stock_name']}: bayesian={s['bayesian_score']:.3f} consensus={s['consensus_direction']} crowding={s['crowding_level']}")

# Check stock_pool for same stocks
print()
print("=== Those stocks in stock_pool ===")
for s in db['08_research_argus_signal_pool'].find({'date': latest_date}).sort('bayesian_score', -1).limit(10):
    wc = s['wind_code']
    sp_record = db['05_portfolio_stock_pool'].find_one({'wind_code': wc, 'status': 'active'})
    if sp_record:
        er = sp_record.get('entry_reason') or {}
        metrics = er.get('metrics') or er
        print(f"  {wc}: bayesian={metrics['bayesian_score']:.3f} consensus={metrics['consensus_confidence']:.3f} crowding={metrics['crowding_level']}")
    else:
        print(f"  {wc}: NOT in stock_pool (status not active)")
