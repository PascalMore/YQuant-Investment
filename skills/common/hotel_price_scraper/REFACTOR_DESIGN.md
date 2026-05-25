# su-scraper 重构详细设计

## 1. 现状解读

现有代码目录：

`~/.openclaw/workspace-yquant/skills/common/su-scraper/scripts/`

文件规模：

- `jalan.py`：205 行。
- `booking.py`：234 行。
- `trip.py`：302 行。

三者合计约 741 行，核心流程相似：

1. 从 `hotels.xlsx` 读取平台酒店 ID 和 `setting`。
2. 从当天开始遍历若干入住日期。
3. 构造平台 URL。
4. 请求页面并解析酒店名、房型、价格。
5. 将第一条价格写入平台独立 Excel。
6. 调用本文件内重复实现的 `send_mail()` 发送附件。

### 1.1 Jalan

- 文件：`jalan.py`
- 技术：`requests.get + BeautifulSoup`
- 编码：`resp.content.decode("cp932")`
- 配置：
  - `hotels.xlsx` sheet `jalan_urls`
  - `setting` 第 2 行
- Cookie：从 `setting.cookie` 读入并直接放入 headers。
- 解析：
  - 酒店名：`div.yado_header_hotel#yado_header_hotel_name`
  - 房型：`a.p-searchResultItem__planName`
  - 价格：`span.p-searchResultItem__total`
- 失败行为：
  - 找不到标题时返回 `-1`，提示更新 Cookie。
  - 请求异常写入 `"网站异常"`。
  - 无价格写入 `"满房"`。

### 1.2 Booking

- 文件：`booking.py`
- 技术：`requests.Session + BeautifulSoup`
- 配置：
  - `hotels.xlsx` sheet `booking_urls`
  - `setting` 第 1 行
- Cookie：从 `setting.cookie` 拆分后写入 session cookiejar。
- 解析：
  - 酒店名：`h2.pp-header__title`
  - 房型：`span.hprt-roomtype-icon-link`
  - 价格：`div.bui-price-display__value...`
- 重试：网络请求最多 4 次，每次失败 sleep 10 秒。
- 币种：URL 中设置 `selected_currency=JPY`。
- 失败行为：
  - 找不到标题时返回 `-1`，提示更新 Cookie。
  - 网络一直失败写入 `"网络异常"`。
  - 无价格写入 `"满房"`。

### 1.3 Trip

- 文件：`trip.py`
- 技术：`Selenium WebDriver`
- 配置：
  - `hotels.xlsx` sheet `trip_urls`
  - `setting` 第 3 行
  - `trip_cookies.json`
- Cookie：
  - `init_cookie()` 打开页面，等待 60 秒人工登录，保存 cookie。
  - `init_driver()` 读取 `trip_cookies.json` 并注入 driver。
- 解析：
  - 酒店名 XPath：`//h1[@class="headInit_headInit-title_nameA__EE_LB"]`
  - 地址 XPath：`//span[@class="headInit_headInit-address_text__D_Atv"]`
  - 房型卡片 XPath：`//div[@data-test-id="mainRoomList"]//div[@class="commonRoomCard__BpNjl"]`
  - 房型 class：`commonRoomCard-title__iYBn2`
  - 价格 class：`saleRoomItemBox-priceBox-displayPrice__gWiOr`
- 重试：单日期最多 3 次。
- 失败行为：
  - 无房型但有标题时按无法获取报价处理。
  - 无标题时按网络异常或抓取失败处理。

## 2. 共同问题

必须在重构中解决：

- 邮件账号和授权码硬编码。
- 输出文件名和日志文件名硬编码。
- 每个平台独立运行、独立 Excel 文件、独立邮件。
- 没有统一数据模型，无法稳定做跨平台汇总。
- Cookie 过期只能通过日志人工发现，没有统一状态和刷新机制。
- `requests` 与 `Selenium` 混用，但调度层没有统一错误处理。
- `send_mail()` 在每个文件重复实现。
- 日期范围、成人数、儿童数、房间数和 cookie 均塞在 `hotels.xlsx` 的 `setting` 行中，可维护性差。
- 解析逻辑吞掉大量异常，错误类型不可观测。
- 每抓完一个酒店就覆盖保存 Excel，失败恢复和最终一致性较弱。

## 3. 重构目标

将现有脚本重构为统一平台适配器架构：

- `BaseHotelScraper`：平台爬虫抽象基类。
- `JalanScraper`、`BookingScraper`、`TripScraper`：平台适配器。
- `HotelPriceScheduler`：统一调度器。
- `EmailService`：统一邮件服务。
- `ExcelReportWriter`：统一 Excel 输出。
- `CookieManager`：统一 cookie 加载、保存、失效检测和刷新入口。
- `RateLimiter`：统一请求间隔 3-5 秒。
- `RetryPolicy`：统一重试和退避策略。

## 4. 目标目录结构

```text
hotel_price_scraper/
├── SKILL.md
├── RFC.md
├── REFACTOR_DESIGN.md
├── config/
│   ├── hotels.yaml
│   └── cookies.example.yaml
├── cookies/
│   └── trip_cookies.json
├── logs/
│   └── .gitkeep
├── output/
│   └── .gitkeep
└── scripts/
    ├── run_hotel_price_scraper.py
    └── hotel_price_scraper/
        ├── __init__.py
        ├── config.py
        ├── models.py
        ├── scheduler.py
        ├── email_service.py
        ├── excel_writer.py
        ├── cookie_manager.py
        ├── rate_limit.py
        ├── retry.py
        └── scrapers/
            ├── __init__.py
            ├── base.py
            ├── jalan.py
            ├── booking.py
            └── trip.py
```

## 5. 配置外置化

旧版 `hotels.xlsx` 可作为迁移输入，但运行配置应迁移到 YAML/JSON。

### 5.1 `config/hotels.yaml`

```yaml
query:
  days_ahead: 30
  nights: 1
  adults: 2
  children: 0
  rooms: 1
  currency: JPY
  target_room_keywords:
    - standard double
    - double room
    - スタンダードダブル
    - 双人

runtime:
  request_timeout_seconds: 10
  retry_max: 3
  min_delay_seconds: 3
  max_delay_seconds: 5
  output_dir: output
  log_dir: logs

platforms:
  jalan:
    enabled: true
    cookie_file: cookies/jalan_cookie.txt
  booking:
    enabled: true
    cookie_file: cookies/booking_cookie.txt
  trip:
    enabled: true
    cookie_file: cookies/trip_cookies.json

hotels:
  - hotel_key: kyoto_hotel_a
    display_name: Kyoto Hotel A
    platforms:
      jalan:
        hotel_id: "336386"
      booking:
        slug: hua-zhu-jing-du-he-yuan-ting-hoteru
      trip:
        hotel_id: "107897404"
```

### 5.2 `.env`

邮件变量只从：

`~/.openclaw/workspace-yquant/skills/.env`

读取：

```dotenv
EMAIL_SENDER=...
EMAIL_PASSWORD=...
EMAIL_RECEIVERS=...
```

## 6. 数据模型伪实现

```python
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

@dataclass(frozen=True)
class QueryConfig:
    days_ahead: int = 30
    nights: int = 1
    adults: int = 2
    children: int = 0
    rooms: int = 1
    currency: str = "JPY"
    target_room_keywords: tuple[str, ...] = ()

@dataclass(frozen=True)
class HotelConfig:
    hotel_key: str
    display_name: str
    platform_ids: dict[str, str]

@dataclass
class PriceRecord:
    run_date: date
    platform: str
    hotel_key: str
    hotel_name: str
    platform_hotel_id: str
    checkin_date: date
    checkout_date: date
    nights: int
    adults: int
    children: int
    rooms: int
    room_name: str | None
    room_rank: int | None
    is_target_room: bool
    price_amount: Decimal | None
    currency: str
    raw_price: str | None
    status: str
    source_url: str
    error_message: str | None
    scraped_at: datetime

@dataclass
class ScrapeError:
    platform: str
    hotel_key: str
    checkin_date: date | None
    error_type: str
    message: str
    source_url: str | None = None
```

## 7. BaseHotelScraper 伪实现

```python
from abc import ABC, abstractmethod
from datetime import date, timedelta

class BaseHotelScraper(ABC):
    platform: str

    def __init__(self, config, cookie_manager, rate_limiter, retry_policy, logger):
        self.config = config
        self.cookie_manager = cookie_manager
        self.rate_limiter = rate_limiter
        self.retry_policy = retry_policy
        self.logger = logger

    @abstractmethod
    def prepare(self) -> None:
        """Initialize session, headers, cookies, or Selenium driver."""

    @abstractmethod
    def build_url(self, hotel: HotelConfig, checkin: date, checkout: date, query: QueryConfig) -> str:
        """Build platform-specific hotel URL."""

    @abstractmethod
    def fetch_price(self, hotel: HotelConfig, checkin: date, query: QueryConfig) -> list[PriceRecord]:
        """Fetch and parse one hotel for one check-in date."""

    @abstractmethod
    def refresh_cookie(self) -> bool:
        """Refresh cookie if possible."""

    def checkout_date(self, checkin: date, query: QueryConfig) -> date:
        return checkin + timedelta(days=query.nights)

    def close(self) -> None:
        pass
```

## 8. 平台适配器伪实现

### 8.1 JalanScraper

```python
class JalanScraper(BaseHotelScraper):
    platform = "jalan"

    def prepare(self):
        self.session = requests.Session()
        self.session.headers.update(default_headers(host="www.jalan.net"))
        self.session.headers["Cookie"] = self.cookie_manager.load_cookie_header("jalan")

    def build_url(self, hotel, checkin, checkout, query):
        hotel_id = hotel.platform_ids["jalan"]
        return (
            f"https://www.jalan.net/yad{hotel_id}/plan/"
            f"?screenId=UWW3101&yadNo={hotel_id}"
            f"&stayYear={checkin.year}&stayMonth={checkin.month}&stayDay={checkin.day}"
            f"&stayCount={query.nights}&roomCount={query.rooms}"
            f"&adultNum={query.adults}&child1Num={query.children or ''}"
            "&reSearchFlg=1&roomCrack=200000&smlCd=260205&distCd=01"
            "&minPrice=0&maxPrice=999999&activeSort=17"
        )

    def fetch_price(self, hotel, checkin, query):
        url = self.build_url(hotel, checkin, self.checkout_date(checkin, query), query)
        response = self.retry_policy.call(lambda: self.session.get(url, timeout=self.config.timeout))
        html = response.content.decode("cp932", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("div", {"class": "yado_header_hotel", "id": "yado_header_hotel_name"})
        if not title:
            return [cookie_or_parse_error_record(self.platform, hotel, checkin, url)]
        return parse_jalan_records(soup, hotel, checkin, query, url)
```

### 8.2 BookingScraper

```python
class BookingScraper(BaseHotelScraper):
    platform = "booking"

    def prepare(self):
        self.session = requests.Session()
        self.session.headers.update(default_headers())
        self.session.cookies = self.cookie_manager.load_cookiejar("booking")

    def build_url(self, hotel, checkin, checkout, query):
        slug = hotel.platform_ids["booking"]
        return (
            f"https://www.booking.com/hotel/jp/{slug}.html"
            f"?checkin={checkin:%Y-%m-%d}&checkout={checkout:%Y-%m-%d}"
            f"&group_adults={query.adults}&group_children={query.children}"
            f"&no_rooms={query.rooms}&req_adults={query.adults}&req_children={query.children}"
            "&room1=A%2CA&sb_price_type=total&sr_order=popularity&type=total"
            "&ucfs=1&dest_type=hotel&dist=0&selected_currency=JPY&lang=en-us#hotelTmpl"
        )

    def fetch_price(self, hotel, checkin, query):
        url = self.build_url(hotel, checkin, self.checkout_date(checkin, query), query)
        response = self.retry_policy.call(lambda: self.session.get(url, timeout=self.config.timeout))
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.find("h2", {"class": "pp-header__title"})
        if not title:
            return [cookie_or_parse_error_record(self.platform, hotel, checkin, url)]
        return parse_booking_records(soup, hotel, checkin, query, url)
```

### 8.3 TripScraper

```python
class TripScraper(BaseHotelScraper):
    platform = "trip"

    def prepare(self):
        self.driver = create_chrome_driver(timeout=self.config.timeout)
        cookies = self.cookie_manager.load_selenium_cookies("trip")
        seed_url = self.config.trip_seed_url
        self.driver.get(seed_url)
        for cookie in cookies:
            self.driver.add_cookie(cookie)
        self.driver.refresh()

    def build_url(self, hotel, checkin, checkout, query):
        hotel_id = hotel.platform_ids["trip"]
        return (
            "https://www.trip.com/hotels/detail/"
            f"?hotelId={hotel_id}&checkIn={checkin:%Y-%m-%d}&checkOut={checkout:%Y-%m-%d}"
            f"&adult={query.adults}&children={query.children}&crn={query.rooms}&curr=JPY"
        )

    def fetch_price(self, hotel, checkin, query):
        url = self.build_url(hotel, checkin, self.checkout_date(checkin, query), query)
        self.retry_policy.call(lambda: self.driver.get(url))
        wait_for_title_or_rooms(self.driver)
        if not has_hotel_title(self.driver):
            return [error_record("cookie_expired", self.platform, hotel, checkin, url)]
        return parse_trip_records(self.driver, hotel, checkin, query, url)

    def refresh_cookie(self):
        return self.cookie_manager.init_trip_cookie(self.config.trip_seed_url)

    def close(self):
        self.driver.quit()
```

## 9. HotelPriceScheduler 伪实现

```python
class HotelPriceScheduler:
    def __init__(self, scrapers, excel_writer, email_service, logger):
        self.scrapers = scrapers
        self.excel_writer = excel_writer
        self.email_service = email_service
        self.logger = logger

    def run(self, hotels, query, send_email=False):
        all_records = []
        all_errors = []

        for scraper in self.scrapers:
            try:
                scraper.prepare()
                records, errors = self.run_platform(scraper, hotels, query)
                all_records.extend(records)
                all_errors.extend(errors)
            except Exception as exc:
                self.logger.exception("platform failed: %s", scraper.platform)
                all_errors.append(platform_error(scraper.platform, exc))
            finally:
                scraper.close()

        output_file = self.excel_writer.write(all_records, all_errors)

        if send_email:
            self.email_service.send_report(output_file, all_records, all_errors)

        return output_file, all_records, all_errors

    def run_platform(self, scraper, hotels, query):
        records = []
        errors = []
        for hotel in hotels:
            if scraper.platform not in hotel.platform_ids:
                continue
            for checkin in date_range(date.today(), query.days_ahead):
                try:
                    records.extend(scraper.fetch_price(hotel, checkin, query))
                    scraper.rate_limiter.wait()
                except Exception as exc:
                    self.logger.exception("hotel/date failed")
                    errors.append(scrape_error(scraper.platform, hotel, checkin, exc))
        return records, errors
```

容错策略：

- `try/except` 包裹平台级运行，平台失败不影响其他平台。
- `try/except` 包裹酒店和日期级运行，单点失败继续下一日期。
- 所有异常统一转成 `ScrapeError` 并写入 `errors` sheet。

## 10. EmailService 伪实现

```python
class EmailService:
    def __init__(self, env_path: Path):
        env = load_dotenv_values(env_path)
        self.sender = env["EMAIL_SENDER"]
        self.password = env["EMAIL_PASSWORD"]
        self.receivers = parse_receivers(env["EMAIL_RECEIVERS"])

    def send_report(self, attachment: Path, records: list[PriceRecord], errors: list[ScrapeError]) -> None:
        subject = f"【YQuant】酒店价格周报 {date.today():%Y-%m-%d}"
        body = render_summary(records, errors)
        message = build_multipart_message(self.sender, self.receivers, subject, body, attachment)

        with smtplib.SMTP_SSL("smtp.qq.com", 465) as smtp:
            smtp.login(self.sender, self.password)
            smtp.sendmail(self.sender, self.receivers, message.as_string())
```

改造点：

- 删除三个脚本内重复的 `send_mail()`。
- 禁止硬编码邮箱、授权码、收件人。
- 支持多个收件人。
- 邮件失败要被记录，但不删除已生成 Excel。

## 11. Cookie 自动刷新机制

### 11.1 CookieManager

```python
class CookieManager:
    def __init__(self, config_dir: Path, cookie_dir: Path, logger):
        self.config_dir = config_dir
        self.cookie_dir = cookie_dir
        self.logger = logger

    def load_cookie_header(self, platform: str) -> str:
        return (self.cookie_dir / f"{platform}_cookie.txt").read_text().strip()

    def load_cookiejar(self, platform: str):
        raw = self.load_cookie_header(platform)
        return requests.utils.cookiejar_from_dict(parse_cookie_header(raw))

    def load_selenium_cookies(self, platform: str) -> list[dict]:
        return json.loads((self.cookie_dir / f"{platform}_cookies.json").read_text())

    def init_trip_cookie(self, seed_url: str, wait_seconds: int = 60) -> bool:
        driver = create_chrome_driver()
        try:
            driver.get(seed_url)
            time.sleep(wait_seconds)
            cookies = driver.get_cookies()
            (self.cookie_dir / "trip_cookies.json").write_text(json.dumps(cookies, indent=2))
            return True
        finally:
            driver.quit()
```

### 11.2 失效检测

- Jalan：标题节点缺失，且页面出现登录、session、cookie、认证相关文本。
- Booking：标题节点缺失，且出现 WAF、sign in、captcha、blocked、verify 等文本。
- Trip：Selenium 找不到酒店标题，或跳转登录/验证页面。

### 11.3 刷新策略

- Jalan/Booking：第一阶段不自动登录，只标记 `cookie_expired` 并提示更新 cookie 文件。
- Trip：提供 `--init-cookie`，通过人工登录刷新。
- 调度器遇到 `cookie_expired`：
  - 当前平台停止继续请求，避免无意义访问。
  - 其他平台继续。
  - Excel `errors` 和邮件正文列出 cookie 失效平台。

## 12. 限流与重试

### 12.1 RateLimiter

```python
class RateLimiter:
    def __init__(self, min_seconds=3, max_seconds=5):
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds

    def wait(self):
        time.sleep(random.uniform(self.min_seconds, self.max_seconds))
```

### 12.2 RetryPolicy

```python
class RetryPolicy:
    def __init__(self, max_attempts=3, base_delay=3):
        self.max_attempts = max_attempts
        self.base_delay = base_delay

    def call(self, fn):
        last_exc = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if attempt == self.max_attempts:
                    raise
                time.sleep(self.base_delay * 2 ** (attempt - 1))
        raise last_exc
```

## 13. ExcelReportWriter 设计

```python
class ExcelReportWriter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def write(self, records: list[PriceRecord], errors: list[ScrapeError]) -> Path:
        report_path = self.output_dir / f"hotel_price_report_{date.today():%Y-%m-%d}.xlsx"
        records_df = records_to_dataframe(records)
        summary_df = build_summary(records_df)
        errors_df = errors_to_dataframe(errors)
        meta_df = build_run_meta(records, errors)

        with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="summary", index=False)
            for platform in ["jalan", "booking", "trip"]:
                records_df[records_df["platform"] == platform].to_excel(writer, sheet_name=platform, index=False)
            errors_df.to_excel(writer, sheet_name="errors", index=False)
            meta_df.to_excel(writer, sheet_name="run_meta", index=False)
        return report_path
```

汇总规则：

- 优先 `is_target_room=True` 的最低价。
- 若无目标房型但有报价，展示最低价并标记 `room_match_status=unmatched_fallback`。
- 若满房或失败，保留状态，不填数值价格。

## 14. 从旧版迁移步骤

1. 从 `hotels.xlsx` 读取：
   - `booking_urls.url_name` → `platforms.booking.slug`
   - `jalan_urls.url_name` → `platforms.jalan.hotel_id`
   - `trip_urls.url_name` → `platforms.trip.hotel_id`
   - `setting.day/adults/children/rooms` → `query`
2. 将 `setting.cookie` 拆分保存：
   - Jalan → `cookies/jalan_cookie.txt`
   - Booking → `cookies/booking_cookie.txt`
   - Trip → 保留 `cookies/trip_cookies.json`
3. 删除脚本内硬编码邮箱和授权码，改用 `EmailService`。
4. 将三个 `parse_*_hotel()` 拆成平台私有 parser，但返回统一 `PriceRecord`。
5. 将三个 `main()` 合并为 `HotelPriceScheduler.run()`。
6. 将三个独立 Excel 改成一个多 sheet Excel。
7. 将 stdout 重定向日志改为 `logging`，输出到 `logs/hotel_price_scraper_YYYY-MM-DD.log`。

## 15. 测试策略

### 15.1 单元测试

- URL 构造：
  - Jalan 日期、人数、房间数参数正确。
  - Booking checkout 为 checkin + 1 天。
  - Trip curr 固定 JPY。
- Cookie 解析：
  - `a=1; b=2` 转 cookiejar。
  - 空 cookie 报配置错误。
- 价格解析：
  - `￥12,345`、`JPY 12,345`、`12,345円` 转 Decimal。
- 房型匹配：
  - 标准双人间关键词命中。
  - 无匹配时 fallback 到最低价。

### 15.2 集成测试

- 使用保存的 HTML fixture 测试 Jalan/Booking parser。
- 使用 Selenium mock 或最小页面 fixture 测试 Trip parser。
- 模拟单平台失败，确认其他平台仍输出。
- 模拟邮件失败，确认 Excel 已生成。

### 15.3 运行验收

- 生成 `hotel_price_report_YYYY-MM-DD.xlsx`。
- Excel 至少包含 `summary/jalan/booking/trip/errors/run_meta` 六个 sheet。
- 邮件附件能打开，价格列为数值格式。
- 日志中能看到每个平台开始、结束、记录数、错误数。

## 16. 后续增强

- 增加历史报告归档和环比变动分析。
- 增加 HTML 邮件正文，展示 Top N 涨跌幅。
- 接入 SQLite 或 DuckDB 保存长期历史，Excel 只作为交付格式。
- 将 selector 配置化，降低页面结构变化时的代码修改成本。
- 增加人工维护的酒店名映射和房型标准化字典。

