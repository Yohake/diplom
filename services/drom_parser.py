import asyncio
import logging
import random
import json
from typing import List, Dict, Optional

from playwright.async_api import async_playwright
import aiohttp
from bs4 import BeautifulSoup

from config.settings import settings
from utils.utils import normalize_city_name

logger = logging.getLogger(__name__)

def load_cities_data(file_path: str) -> dict:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из {file_path}: {e}")
        return {}

class DromParser:
    def __init__(self, proxy=None, base_url="https://drom.ru"):
        self.headers = {
            'User-Agent': random.choice(settings.USER_AGENTS),
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        self.proxy = proxy
        self.base_url = base_url
        self.allowed_time = ['часов', 'часа', 'час', 'минут', 'минуту', 'минуты', 'секунд', 'сегодня']

    async def fetch_html(self, url: str) -> str:
        await asyncio.sleep(5)  # Задержка в 5 секунд
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка запроса: {response.status} для {url}")
                        return ""
                    return await response.text()
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка клиента aiohttp: {e}")
                return ""

    async def parse_brands_drom(self, html: Optional[str] = None) -> List[str]:
            """Парсит бренды с Drom: через HTML (если передан) или через Playwright+клик «Показать все»."""
            if html:
                # Старый режим: парсим готовый HTML
                soup = BeautifulSoup(html, 'html.parser')
                elems = soup.select('[data-ftid="component_cars-list-item_name"]')
                brands = [el.text.strip() for el in elems if el.text.strip()]
                logger.info(f"Найденные марки из HTML: {brands}")
                return sorted(set(brands))

            # Новый режим: Playwright + автоклик «Показать все»
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto("https://www.drom.ru/catalog/")

                # Ждём первичные элементы
                await page.wait_for_selector('[data-ftid="component_cars-list-item_name"]')

                # Если есть кнопка «Показать все» — кликаем
                show_all = await page.query_selector('[data-ftid="component_cars-list_expand-control"]')
                if show_all:
                    await show_all.click()
                    # Даём JS подгрузить остальные элементы
                    await page.wait_for_timeout(1000)

                # Снова собираем все элементы
                elems = await page.query_selector_all('[data-ftid="component_cars-list-item_name"]')
                brands = []
                for el in elems:
                    txt = await el.text_content()
                    if txt:
                        brands.append(txt.strip())

                await browser.close()
                logger.info(f"Найденные марки через Playwright (полный список): {brands}")
                return sorted(set(brands))


    async def get_location_id_by_city_name(self, city_name: str) -> Optional[str]:
        """Ищет путь города в базе данных."""
        cities_data = load_cities_data('storage/regions_and_cities.json')
        for region in cities_data:
            for city in region.get('cities', []):
                if city['name'].lower() == city_name.lower():
                    link = city['link']
                    city_path = link.split('https://')[-1].split('/')[0]
                    return city_path
        logger.warning(f"Город '{city_name}' не найден в базе данных.")
        return None

    async def find_all_matching_cities(self, city_name: str) -> List[Dict[str, str]]:
        cities_data = load_cities_data('storage/regions_and_cities.json')
        matches = []

        for region in cities_data:
            region_name = region.get('name')
            for city in region.get('cities', []):
                if city['name'].lower() == city_name.lower():
                    matches.append({
                        'region': region_name,
                        'city': city['name'],
                        'link': city['link']
                    })

        return matches

    async def parse_ads(self, brand: str, city: str, distance: int, min_price: int, max_price: int, city_link: Optional[str] = None) -> List[Dict]:
        logger.info(f"Парсим Drom для: {brand=} {city=} {distance=} {min_price=} {max_price=}")

        if not city_link:
            cities_data = load_cities_data('storage/regions_and_cities.json')
            for region in cities_data:
                for city_data in region.get('cities', []):
                    if city_data['name'].lower() == city.lower():
                        city_link = city_data['link']
                        break
                if city_link:
                    break

        if not city_link:
            logger.warning(f"Не удалось найти город '{city}' в базе данных.")
            return []

        base_url = city_link.split('go=')[-1].split('%2Fauto%2F')[0]
        full_url = f"{base_url}/{brand.lower()}/used/"
        params = {
            "minprice": min_price,
            "maxprice": max_price,
            "distance": distance
        }
        full_url = f"https://www.drom.ru/my_region/?go={full_url}?{'&'.join(f'{key}={value}' for key, value in params.items() if value)}"
        logger.info(f"Сгенерированная ссылка: {full_url}")

        html = await self.fetch_html(full_url)
        if not html:
            logger.error("Пустой HTML для парсинга")
            return []

        soup = BeautifulSoup(html, 'html.parser')
        ads = []

        ad_blocks = soup.find_all("div", {"data-ftid": "bulls-list_bull"}, limit=10)
        for ad in ad_blocks:
            try:
                a_tag = ad.find("a", {"data-ftid": "bull_title"})
                url = a_tag['href'] if a_tag else None
                title = a_tag.text.strip() if a_tag else "Без названия"

                price_tag = ad.find("span", {"data-ftid": "bull_price"})
                price = price_tag.text.strip() if price_tag else "Не указана"

                location_tag = ad.find("span", {"data-ftid": "bull_location"})
                location = location_tag.text.strip() if location_tag else "Не указан"

                date_div = ad.find("div", {"data-ftid": "bull_date"})
                date_text = date_div.text.strip().lower() if date_div else ""

                if any(t in date_text for t in self.allowed_time):
                    ads.append({
                        "title": title,
                        "url": url,
                        "price": price,
                        "location": location
                    })
            except Exception as e:
                logger.warning(f"Ошибка при парсинге объявления: {e}")

        return ads

# Пример использования
async def main():
    parser = DromParser()
    brands = await parser.parse_brands_drom()
    print(brands)

if __name__ == "__main__":
    asyncio.run(main())
