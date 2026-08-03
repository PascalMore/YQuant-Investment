from loaders.mongodb_loader import PortfolioMongoLoader
db = PortfolioMongoLoader()._db()

# Basic info all
print('All basic_info rows:')
for r in db['portfolio_basic_info'].find({}, {'_id':0,'updated_at':0}):
    print(' ', r)

print('portfolio_nav max nav_date:', db['portfolio_nav'].find_one({}, sort=[('nav_date',-1)], projection={'nav_date':1}))
print('basic_info total:', db['portfolio_basic_info'].count_documents({}))
print('basic_info with product_code in [SM004,ZO-002]:', db['portfolio_basic_info'].count_documents({'product_code':{'$in':['SM004','ZO-002']}}))

# final 7/31 SM004 nav row
print('Final nav 7/31 SM004:')
print(' ', db['portfolio_nav'].find_one({'nav_date':'2026-07-31','product_code':'SM004'}, {'_id':0,'updated_at':0}))