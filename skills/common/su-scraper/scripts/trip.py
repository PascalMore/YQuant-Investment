import pandas as pd
import time
from datetime import datetime, timedelta
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import json,os,sys
import smtplib
from email.mime.text import MIMEText
#发送多种类型的邮件
from email.mime.multipart import MIMEMultipart

CONST_PARAM_HOTELS = "hotels.xlsx"
CONST_PARAM_BOOKING_URL_FORMAT = "https://www.trip.com/hotels/detail/?hotelId={}&checkIn={}&checkOut={}&adult={}&children={}&crn={}&curr=JPY"
CONST_PARAM_RETRY_MAX = 3
CONST_PARAM_TIMEOUT = 10
#备注=============>下面三个path参数经常换，如果程序不好跑可以尝试修改这三个参数
#2025-03-18 fix：改成相对路径，定位class是commonRoomCard__BpNjl
CONST_ROOM_CARD_XPATH = '//div[@data-test-id="mainRoomList"]//div[@class="commonRoomCard__BpNjl"]'
CONST_ROOM_TYPE_XPATH = 'commonRoomCard-title__iYBn2'
CONST_ROOM_PRICE_XPATH = "saleRoomItemBox-priceBox-displayPrice__gWiOr"
#==================
CONST_HOTEL_TITLE_XPATH = '//h1[@class="headInit_headInit-title_nameA__EE_LB"]'
CONST_HOTEL_ADDR_XPATH = '//span[@class="headInit_headInit-address_text__D_Atv"]'

# 谷歌浏览器位置
#CONST_PARAM_chrome_location = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# 谷歌浏览器驱动地址
#CONST_PARAM_chrome_path = "D:\\Applications\\anaconda3\\envs\\crawler\\chromedriver.exe"


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
        msg['Subject'] = "【阿强】携程酒店价格_{}".format(datetime.date.today().strftime("%Y-%m-%d")) 
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

def init_cookie(url):
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.3')
        chrome_options.add_argument('Upgrade-Insecure-Requests=1')
        driver = webdriver.Chrome(options=chrome_options)
        # 打开携程酒店主页并手动登录
        driver.get(url)
        time.sleep(60)  # 给用户足够的时间手动登录

        # 获取登录后的 cookie
        cookies = driver.get_cookies()

        # 打印当前工作目录
        print("Current working directory: ", os.getcwd())
        # 将 cookie 保存到文件
        with open("trip_cookies.json", "w") as file:
            json.dump(cookies, file)
        print("Cookies saved successfully.")

    except Exception as e:
        print(e)
    finally:
        driver.quit()

def gen_trip_url(n, s, e, q_ad, q_ch, q_ro):
    req_url = CONST_PARAM_BOOKING_URL_FORMAT.format(n, s, e, q_ad, q_ch, q_ro)
    return req_url

def parse_trip_hotel(web):
    l=list()
    g=list()
    o={}
    k={}
    #print(soup)
    #未获取到正确网页，直接退出
    if web.find_element(By.XPATH, CONST_HOTEL_TITLE_XPATH) is None:
        print("未能抓取Title匹配数据")
        return -1, None

    o["name"] = web.find_element(By.XPATH, CONST_HOTEL_TITLE_XPATH).text
    print(o["name"])
    o["address"]=web.find_element(By.XPATH, CONST_HOTEL_ADDR_XPATH).text.strip("\n")
    #print(o["address"])

    ids= list()
    targetId=list()
    try:
        div = web.find_elements(By.XPATH, CONST_ROOM_CARD_XPATH)
    except:
        div = None

    for y in range(0,len(div)):
        try: 
            #1、获取房型
            room_type = div[y].find_element(By.CLASS_NAME, CONST_ROOM_TYPE_XPATH).text
            #print(room_type)
            #2、获取所有房间价格
            room_prices = div[y].find_elements(By.CLASS_NAME, CONST_ROOM_PRICE_XPATH)
            for j in range(0, len(room_prices)):
                k["room"] = "{}-{}".format(room_type, j+1)
                k["price"] = room_prices[j].text.strip().replace("\n","")
                g.append(k)
                ids.append(k["room"])

                k={}
        except:
            k["room"]=None
            k["price"]=None

    print("Prices are ",len(ids))
    
    l.append(g)
    l.append(o)

    return o["name"], g

def init_driver(url, c):
    notTimeOut = True
    while notTimeOut:
        # c_service = Service("D:\\Applications\\anaconda3\\envs\\crawler\\chromedriver.exe")
        # c_service.command_line_args()
        # c_service.start()

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.3')
        chrome_options.add_argument('Upgrade-Insecure-Requests=1')
        
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors')

        prefs = {'profile.managed_default_content_settings.images': 2}
        #chrome_options.add_experimental_option('prefs',prefs)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        #chrome_options.binary_location = CONST_PARAM_chrome_location
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(CONST_PARAM_TIMEOUT)
        driver.set_script_timeout(CONST_PARAM_TIMEOUT)

        try:
            driver.get(url)
 
            # 从文件加载 cookie
            with open("trip_cookies.json", "r") as file:
                cookies = json.load(file)
            # 注入 cookie
            for cookie in cookies:
                driver.add_cookie(cookie)
            time.sleep(1)
            driver.refresh()

            print("找到了可用的driver")
            notTimeOut = False
        except Exception as e:
            print(e)
            driver.quit()
            time.sleep(10)
            # os.system('taskkill /im chromedriver.exe /F')
            # os.system('taskkill /im chrome.exe /F')

    return driver

def main():
    htl_price = pd.DataFrame()
    #1. 读取所有酒店列表以及查询参数
    htls = pd.read_excel(CONST_PARAM_HOTELS, sheet_name="trip_urls")
    q = pd.read_excel(CONST_PARAM_HOTELS, sheet_name="setting")
    start_d = datetime.date.today()
    #start_d = datetime.date(2025, 9, 30)
    day_num = q.iloc[2]['day']
    end_d = start_d + timedelta(days=int(day_num))

    q_ad = q.iloc[2]['adults']
    q_ch = q.iloc[2]['children']
    q_ro = q.iloc[2]['rooms']
    q_cookie = q.iloc[2]['cookie']

    #3. 获取酒店价格
    for h in htls['url_name'].to_list():
        current_d = start_d
        interval = timedelta(days=1)
        list_p = list()
        list_d = list()
        # 找到不超时的driver才返回
        driver = init_driver(gen_trip_url(h, current_d.strftime("%Y-%m-%d"), (current_d +interval).strftime("%Y-%m-%d"), q_ad, q_ch, q_ro), q_cookie)
        while current_d <= end_d:
            req_url = gen_trip_url(h, current_d.strftime("%Y-%m-%d"), (current_d +interval).strftime("%Y-%m-%d"), q_ad, q_ch, q_ro)
            print(req_url)
            list_d.append(current_d)
            #如果请求网页出现了异常，则进行重试
            keep = True
            retry_count = 0
            while keep and retry_count < CONST_PARAM_RETRY_MAX:
                try:
                    driver.get(req_url)
                    print("请求返回了响应")
                    #等待标题或者报价出现
                    el = WebDriverWait(driver, CONST_PARAM_TIMEOUT).until(EC.presence_of_all_elements_located((By.XPATH, CONST_ROOM_CARD_XPATH)), message="没有找到酒店报价")
                    print("出现{}个有效酒店房型报价".format(len(el)))
                    keep = False
                except Exception as e:
                    print(e)
                    #延时3秒后重试
                    time.sleep(3)
                    retry_count = retry_count + 1
                    if retry_count < CONST_PARAM_RETRY_MAX:
                        print('重试第{}次'.format(retry_count))
                        continue
                    else:
                        try:
                            #根据是否有titel来判断是否是网络错误
                            if driver.find_element(By.XPATH, CONST_HOTEL_TITLE_XPATH) is None:
                                print('由于网络异常，达到最大重试次数上限')
                            else:
                                print('由于无法获取酒店报价，达到最大重试次数上限')
                                keep = False
                        except Exception as e:
                            print(e)
                            print('由于网络异常，达到最大重试次数上限')

            #如果网络一直错误，直接下一个
            if keep:
                list_p.append("网络异常")
                current_d += interval
                continue

            #解析网页，抓取酒店名字和价格
            name, price = parse_trip_hotel(driver)
            #如果是标题都没有抓到，提示抓取失败
            if name == -1:
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
        htl_price.to_excel("携程酒店价格_{}.xlsx".format(start_d.strftime("%Y-%m-%d")))
        
        #浏览器刷新 删除cookie 以免崩溃
        #driver.refresh()
        #driver.delete_all_cookies()
        driver.quit()
        time.sleep(10)
    
    if os.path.exists("携程酒店价格_{}.xlsx".format(start_d.strftime("%Y-%m-%d"))):
        send_mail(["suxn@hyviewgroup.com"], "携程酒店价格_{}.xlsx".format(start_d.strftime("%Y-%m-%d")))

    return 0

if __name__ == '__main__':
    #sys.stdout = Logger()
    output = open('Trip日志.txt', 'w', encoding='utf-8')
    sys.stdout= output
    main()
    output.close()

    #手工初始化cookie，每当cookie失效了，就手动调用下面的功能初始化cookie。
    #init_cookie("https://www.trip.com/hotels/detail/?hotelId=107897404&checkIn=2024-07-16&checkOut=2024-07-17&adult=2&children=0&crn=1&curr=JPY")
