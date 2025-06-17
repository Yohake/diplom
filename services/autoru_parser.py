import aiohttp
from bs4 import BeautifulSoup
import logging
import re
import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timedelta
from transliterate import translit
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoRuParser:
    def __init__(self):
        self.base_url = "https://auto.ru"
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://auto.ru/'
        }

    async def parse_brands(self) -> list:
        brands = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"{self.base_url}/catalog/cars/", timeout=60000)
            await page.wait_for_selector("div.CatalogFilterSearchList__link-ebL7j", timeout=15000)

            elements = await page.query_selector_all("div.CatalogFilterSearchList__link-ebL7j")

            for element in elements:
                try:
                    a_tag = await element.query_selector("a")
                    if a_tag:
                        brand_name = (await a_tag.inner_text()).strip()
                        if brand_name and brand_name.lower() != "все марки":
                            brands.append(brand_name)
                except Exception as e:
                    logger.error(f"Error parsing brand link: {e}")

            await browser.close()

        unique_brands = sorted(set(brands))
        logger.info(f"✅ Найдено марок на Auto.ru: {len(unique_brands)}")
        return unique_brands

    async def parse_ads(self, brand: str, city: str, min_price: int, max_price: int, radius: int = 200) -> list:
        city_translit = translit(city.lower(), 'ru', reversed=True)
        city_slug = city_translit.replace(" ", "_")  # Replace spaces with underscores
        brand_slug = brand.lower().replace(" ", "_")

        url = f"{self.base_url}/{city_slug}/cars/{brand_slug}/used/"
        query_params = f"sort=cr_date-desc&top_days=1"
        
        if min_price > 0:
            query_params += f"&price_from={min_price}"
        if max_price > 0:
            query_params += f"&price_to={max_price}"
        if radius > 0:
            query_params += f"&geo_radius={radius}"

        full_url = f"{url}?{query_params}"
        logger.info(f"🌐 Сформированная ссылка для запроса: {full_url}")

        await asyncio.sleep(random.uniform(0.5, 1.5))

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(full_url, timeout=60000)
                await page.wait_for_selector('div.ListingItem', timeout=15000)
            except Exception as e:
                logger.error(f"Ошибка загрузки объявлений: {e}")
                await browser.close()
                return []

            car_elements = await page.query_selector_all('div.ListingItem')
            ads = []

            for el in car_elements:
                try:
                    # Check for distance in address
                    place_el = await el.query_selector('span.MetroListPlace__regionName')
                    if place_el:
                        location_text = await place_el.inner_text()
                        if "км от" in location_text:
                            continue

                    # Get title and link
                    title_el = await el.query_selector('a.ListingItemTitle__link')
                    title = await title_el.inner_text() if title_el else "Без названия"
                    link = await title_el.get_attribute('href') if title_el else None
                    
                    # Get price
                    price_el = await el.query_selector('div.ListingItemPrice__content')
                    price = await price_el.inner_text() if price_el else "Без цены"
                    price = re.sub(r'[^\d]', '', price)
                    
                    # Get year
                    year_el = await el.query_selector('div.ListingItem__year')
                    year = await year_el.inner_text() if year_el else ""
                    
                    # Get mileage
                    kmage_el = await el.query_selector('div.ListingItem__kmAge')
                    kmage = await kmage_el.inner_text() if kmage_el else ""
                    
                    # Get location and date
                    place_el = await el.query_selector('span.MetroListPlace')
                    location = ""
                    date_text = ""
                    if place_el:
                        region_el = await place_el.query_selector('span.MetroListPlace__regionName')
                        location = await region_el.inner_text() if region_el else ""
                        
                        content_el = await place_el.query_selector('span.MetroListPlace__content')
                        date_text = await content_el.inner_text() if content_el else ""
                    
                    # Get image
                    img_el = await el.query_selector('img.LazyImage__image')
                    image_url = await img_el.get_attribute('src') if img_el else ""
                    
                    if link and not link.startswith("http"):
                        link = self.base_url + link
                    
                    date = self._parse_date(date_text.strip()) if date_text else "Не указана"
                    
                    ads.append({
                        'id': link.split('/')[-2] if link else "",
                        'title': title.strip(),
                        'price': int(price) if price.isdigit() else 0,
                        'year': int(year) if year and year.isdigit() else 0,
                        'kmage': kmage.strip().replace('\xa0', ' ') if kmage else "",
                        'date': date,
                        'address': location.strip(),
                        'url': link,
                        'image_url': image_url,
                        'source': 'autoru'
                    })
                except Exception as e:
                    logger.error(f"Ошибка парсинга одного объявления: {e}")

            await browser.close()
            return ads
                  
    def _parse_date(self, date_text: str) -> str:
        today = datetime.now()

        if 'сегодня' in date_text.lower():
            return today.strftime('%Y-%m-%d')
        elif 'вчера' in date_text.lower():
            return (today - timedelta(days=1)).strftime('%Y-%m-%d')

        match = re.search(r'(\d{1,2})\s+([а-я]+)', date_text.lower())
        if match:
            day = match.group(1)
            month = match.group(2)
            month_map = {
                'января': '01', 'февраля': '02', 'марта': '03',
                'апреля': '04', 'мая': '05', 'июня': '06',
                'июля': '07', 'августа': '08', 'сентября': '09',
                'октября': '10', 'ноября': '11', 'декабря': '12'
            }
            if month in month_map:
                return f"{today.year}-{month_map[month]}-{day.zfill(2)}"

        return date_text
