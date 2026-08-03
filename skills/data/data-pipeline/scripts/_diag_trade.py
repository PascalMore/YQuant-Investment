from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()
# Check the trade row on 2026-07-31
rows = list(db['portfolio_trade'].find(
    {'trade_date': '2026-07-31', 'product_code': 'SM004'},
    {'_id': 0}
))
print('2026-07-31 SM004 trade rows:')
for r in rows:
    print(r)
# Also trade total
print('SM004 trade all =', db['portfolio_trade'].count_documents({'product_code':'SM004'}))
print('SM004 trade non-2026-07-31 =', db['portfolio_trade'].count_documents({'product_code':'SM004','trade_date':{'$ne':'2026-07-31'}}))
# SM004 trade dates breakdown
import collections
dates = collections.Counter()
for r in db['portfolio_trade'].find({'product_code':'SM004'}, {'trade_date':1}):
    dates[r['trade_date']] += 1
print('distinct trade_date count for SM004:', len(dates))
print('dates with most rows:')
for d,c in sorted(dates.items(), key=lambda x: -x[1])[:5]:
    print(' ', d, c)
# Check if there's a row with non-string nav_date format
print('trade SM004 sample 5:')
for r in db['portfolio_trade'].find({'product_code':'SM004'}).limit(3):
    print(r)