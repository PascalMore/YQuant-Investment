import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from datetime import datetime, timedelta
import datetime
import json,sys,os
import smtplib
from email.mime.text import MIMEText
#发送多种类型的邮件
from email.mime.multipart import MIMEMultipart

CONST_PARAM_HOTELS = "hotels.xlsx"
CONST_PARAM_BOOKING_URL_FORMAT = "https://www.booking.com/hotel/jp/{}.html?&checkin={}&checkout={}&group_adults={}&group_children={}&no_rooms={}&req_adults={}&req_children={}&room1=A%2CA&sb_price_type=total&sr_order=popularity&type=total&ucfs=1&dest_type=hotel&dist=0&selected_currency=JPY&lang=en-us#hotelTmpl"
CONST_PARAM_RETRY_MAX = 4
CONST_PARAM_TIMEOUT = 10

def gen_booking_url(n, s, e, q_ad, q_ch, q_ro):
    req_url = CONST_PARAM_BOOKING_URL_FORMAT.format(n, s, e, q_ad, q_ch, q_ro, q_ad, q_ch)
    return req_url

def parse_booking_hotel(soup):
    l=list()
    g=list()
    o={}
    k={}
    fac=[]
    fac_arr=[]
    #print(soup)
    #未获取到正确网页，直接退出
    if soup.find("h2",{"class":"pp-header__title"}) is None:
        print("未能抓取Title匹配数据")
        return -1, None

    o["name"]=soup.find("h2",{"class":"pp-header__title"}).text
    #2025/01/06 booing的address元素无法被定位，所以删除
    #o["address"]=soup.find("span",{"class":"hp_address_subtitle"}).text.strip("\n")
    #o["rating"]=soup.find("div",{"class":"d10a6220b4"}).text
    

    fac=soup.find_all("div",{"class":"important_facility"})
    for i in range(0,len(fac)):
        fac_arr.append(fac[i].text.strip("\n"))

    ids= list()
    targetId=list()
    try:
        tr = soup.find_all("tr")
    except:
        tr = None

    for y in range(0,len(tr)):
        try:
            id = tr[y].get('data-block-id')
        except:
            id = None
        if( id is not None):
            ids.append(id)
    print("ids are ",len(ids))
    
    for i in range(0,len(ids)):
        try:
            allData = soup.find("tr",{"data-block-id":ids[i]})
            try:
                rooms = allData.find("span",{"class":"hprt-roomtype-icon-link"})
            except:
                rooms=None
            
            if(rooms is not None):
                last_room = rooms.text.replace("\n","")
            try:
                k["room"]=rooms.text.replace("\n","")
            except:
                k["room"]=last_room

            price = allData.find("div",{"class":"bui-price-display__value prco-text-nowrap-helper prco-inline-block-maker-helper prco-f-font-heading"})
            k["price"]=price.text.replace("\n","")
            g.append(k)
            k={}
        except:
            k["room"]=None
            k["price"]=None

    l.append(g)
    l.append(o)
    l.append(fac_arr)

    return o["name"], g

def send_mail(m_addr, att_file):
    try:
        msg_from = '532484187@qq.com' # 发送方邮箱
        passwd = 'yhslfzabjguubgjc'
        msg_to= m_addr #接受方邮箱
        
        #设置邮件内容
        # #MIMEMultipart类可以放任何内容
        msg = MIMEMultipart()
        content="阿强的酒店价格服务"
        #把内容加进去
        msg.attach(MIMEText(content,'plain','utf-8'))
        #添加附件
        att1=MIMEText(open(att_file,'rb').read(), 'base64', 'utf-8') #打开附件
        #att1['Content-Type']='application/octet-stream'  #设置类型是流媒体格式
        att1.add_header('Content-Disposition', 'attachment', filename=att_file)
        #print(att1['Content-Disposition'])
        msg.attach(att1)  #加入到邮件中

        #设置邮件主题
        msg['Subject'] = "【阿强】Booking酒店价格_{}".format(datetime.date.today().strftime("%Y-%m-%d")) 
        #发送方信息
        msg['From'] = msg_from
        #开始发送
        #通过SSL方式发送，服务器地址和端口
        s = smtplib.SMTP_SSL("smtp.qq.com", 465)
        # 登录邮箱
        s.login(msg_from, passwd)
        #开始发送
        s.sendmail(msg_from,msg_to,msg.as_string())
        print("邮件发送成功")
        
        return 0
    except Exception as e:
        print(e)
        return -1

def main():
    htl_price = pd.DataFrame()
    #1. 读取所有酒店列表以及查询参数
    htls = pd.read_excel(CONST_PARAM_HOTELS, sheet_name="booking_urls")
    q = pd.read_excel(CONST_PARAM_HOTELS, sheet_name="setting")
    start_d = datetime.date.today()
    #start_d = datetime.date(2025, 9, 30)
    day_num = q.iloc[0]['day']
    end_d = start_d + timedelta(days=int(day_num))

    q_ad = q.iloc[0]['adults']
    q_ch = q.iloc[0]['children']
    q_ro = q.iloc[0]['rooms']
    q_cookie = q.iloc[0]['cookie']
    
    #2. 构建header
    headers = {
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh-TW;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6',    
    # You may want to change the user agent if you get blocked
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
    }

    sn = requests.session()
    sn.headers = headers
    #2024/8/12更新 通过设置session的cookie从而进行抓取
    sn.cookies = requests.utils.cookiejar_from_dict({i.split("=")[0]: i.split("=")[1] for i in q_cookie.split("; ")}, cookiejar=None, overwrite=True)

    #3. 获取酒店价格
    for h in htls['url_name'].to_list():
        current_d = start_d
        interval = timedelta(days=1)
        list_p = list()
        list_d = list()
        while current_d <= end_d:
            req_url = gen_booking_url(h, current_d.strftime("%Y-%m-%d"), (current_d +interval).strftime("%Y-%m-%d"), q_ad, q_ch, q_ro)
            print(req_url)
            list_d.append(current_d)
            #如果请求网页出现了异常，则进行重试
            keep = True
            retry_count = 0
            while keep and retry_count < CONST_PARAM_RETRY_MAX:
                try:
                    #resp = requests.get(req_url, headers=headers, timeout=CONST_PARAM_TIMEOUT)
                    resp = sn.get(req_url, timeout=CONST_PARAM_TIMEOUT)
                    #print(sn.cookies)
                    keep = False
                except Exception as e:
                    print(e)
                    #延时10秒后重试
                    time.sleep(10)
                    retry_count = retry_count + 1
                    if retry_count < CONST_PARAM_RETRY_MAX:
                        print('重试第{}次'.format(retry_count))
                        continue
                    else:
                        print('达到最大重试次数上限')

            #如果网络一直错误，直接下一个
            if keep:
                list_p.append("网络异常")
                current_d += interval
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            #print(soup)
            #解析网页，抓取酒店名字和价格
            name, price = parse_booking_hotel(soup)
            #如果是因为cookie过期了，提示抓取失败
            if name == -1:
                print("请更新Cookie")
                list_p.append("抓取失败")
            else:
                if len(price) > 0:
                    list_p.append(price[0]['price'])
                else:
                    list_p.append("满房")

                print(name, price)
                time.sleep(3)

            current_d += interval
        
        if(htl_price.empty):
            htl_price['日期'] = list_d
            htl_price.set_index('日期',inplace=True)

        htl_price[name] = list_p
        #4、保存结果为EXCEL(一个酒店抓取完就保存一次)
        print(htl_price)
        htl_price.to_excel("Booking酒店价格_{}.xlsx".format(start_d.strftime("%Y-%m-%d")))
    # 关闭session
    sn.close()
    
    if os.path.exists("Booking酒店价格_{}.xlsx".format(start_d.strftime("%Y-%m-%d"))):
        send_mail(["suxn@hyviewgroup.com"], "Booking酒店价格_{}.xlsx".format(start_d.strftime("%Y-%m-%d")))

    return 0

if __name__ == '__main__':
    #sys.stdout = Logger()
    output = open('Booking日志.txt', 'w', encoding='utf-8')
    sys.stdout= output
    main()
    output.close()
