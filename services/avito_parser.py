import asyncio
import random
import logging
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from typing import List, Optional
from config.settings import settings
from models.data_models import Advertisement
from utils.utils import normalize_city_name
from storage.cities import locations_dict

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class Advertisement:
    def __init__(self, id=None, title=None, price=None, address=None, url=None, date=None, **kwargs):
        self.id = id
        self.title = title
        self.price = price
        self.address = address
        self.url = url
        self.date = date
        # Игнорируем дополнительные параметры, которые могут прийти от Avito
        self.location = kwargs.get('location')  # Добавляем поддержку location

class AvitoParser:
    def __init__(self) -> None:
        self.current_user_agent: int = 0
        self.headers: dict = {
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.avito.ru/"
        }
        self.allowed_time = ['часов', 'часа', 'час', 'минут', 'минуту', 'минуты', 'секунд']

    async def fetch_html(self, url: str, retry_count: int = 8) -> Optional[str]:
        logger.info(f"Начинаю загрузку страницы: {url}")
        for attempt in range(retry_count):
            try:
                await asyncio.sleep(random.uniform(1, 3))
                self.headers["User-Agent"] = settings.USER_AGENTS[self.current_user_agent]
                self.current_user_agent = (self.current_user_agent + 1) % len(settings.USER_AGENTS)

                logger.info(f"Попытка {attempt + 1}: Загружаем {url} с User-Agent: {self.headers['User-Agent']}")

                async with ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=30) as response:
                        if response.status == 429:
                            retry_after = int(response.headers.get('Retry-After', 10))
                            logger.warning(f"Достигнут лимит запросов! Ожидание {retry_after} секунд перед повторной попыткой.")
                            await asyncio.sleep(retry_after)
                            continue

                        response.raise_for_status()
                        logger.info(f"Успешно загружено: {url} (Статус {response.status})")
                        return await response.text()

            except Exception as e:
                logger.error(f"Ошибка при загрузке страницы (попытка {attempt + 1}): {str(e)}")
                if attempt == retry_count - 1:
                    logger.critical(f"Не удалось загрузить {url} после {retry_count} попыток.")
                    return None
                await asyncio.sleep(5 * (attempt + 1))

        return None

    async def get_location_id_by_city_name(self, city_name: str) -> Optional[int]:
        """Ищет locationId по названию города в locations_dict."""
        normalized_name = normalize_city_name(city_name)
        logger.info(f"Поиск locationId для: {normalized_name}")

        # Сначала ищем полное совпадение
        for path, loc_id in locations_dict.items():
            if normalized_name == path:
                return loc_id

        # Если нет полного совпадения, ищем частичное совпадение по названию города
        possible_matches = []
        for path, loc_id in locations_dict.items():
            if normalized_name in path.split("_"):
                possible_matches.append((path, loc_id))

        if len(possible_matches) == 1:
            logger.info(f"Найдено совпадение: {possible_matches[0][0]}")
            return possible_matches[0][1]
        elif len(possible_matches) > 1:
            match_names = [match[0].replace("_", " ").title() for match in possible_matches]
            logger.warning(f"Найдено несколько совпадений для '{city_name}': {[match[0] for match in possible_matches]}")
            # Логика для обработки нескольких совпадений (например, возвращаем первое или запрашиваем уточнение)
            logger.info(f"Возможные варианты: {match_names}")
            return possible_matches[0][1]  # Здесь можно запросить уточнение у пользователя

        logger.warning(f"Location ID для '{city_name}' не найден!")
        return None

    def get_url_path_by_location_id(self, location_id: int) -> Optional[str]:
        for path, loc_id in locations_dict.items():
            if loc_id == location_id:
                return path
        return None

    async def parse_brands(self, html: str) -> List[str]:
        logger.info("Парсинг популярных брендов...")
        soup = BeautifulSoup(html, 'html.parser')
        brands = [link['title'].strip() for link in
                  soup.select('div.popular-rubricator-row-Q5kSL a[data-marker="popular-rubricator/link"]')
                  if link.get('title')]
        logger.info(f"Найдено {len(brands)} брендов.")
        return brands

    async def parse_ads(self, brand: str, city: str, radius_km: int = 0,
                    min_price: int = 0, max_price: int = 0) -> List[Advertisement]:
        url = await self.generate_url(brand, city, min_price, max_price, radius_km)
        if not url:
            return []

        html = await self.fetch_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        ads: List[Advertisement] = []

        for item in soup.select('div[data-marker="item"]'):
            try:
                link = item.select_one('a[data-marker="item-title"]')
                if not link:
                    continue

                title = link.get('title', '').strip()
                url = f"https://www.avito.ru{link.get('href', '')}"
                price_element = item.select_one('meta[itemprop="price"]')
                price = f"{price_element['content']} ₽" if price_element else "Не указана"

                time_element = item.select_one('[data-marker="item-date"]')
                time = time_element.text.strip() if time_element else "Не указано"
                
                # Extract location
                location_element = item.select_one('.geo-root-NrkbV span.styles-module-noAccent-XIvJm')
                location = location_element.text.strip() if location_element else "Не указано"

                if any(word in time.lower() for word in self.allowed_time):
                    ads.append(Advertisement(
                        title=title,
                        url=url,
                        price=price,
                        date=time,
                        location=location  # Make sure your Advertisement model has this field
                    ))
            except Exception as e:
                logger.error(f"Error parsing ad: {e}")
                continue

        return ads

    async def generate_url(self, brand: str, city: str, min_price: int, max_price: int, radius: int) -> str:
        location_id = await self.get_location_id_by_city_name(city)
        if not location_id:
            logger.warning(f"Не удалось найти город '{city}' через API.")
            return ""

        city_path = self.get_url_path_by_location_id(location_id)
        if not city_path:
            logger.warning(f"locationId {location_id} не найден в locations_dict.")
            return ""

        # Нормализация бренда - замена пробелов и специальных символов на дефисы
        normalized_brand = brand.lower().replace(' ', '_').replace('_', '-').replace('(', '').replace(')', '')

        base_url = f"https://www.avito.ru/{city_path}/avtomobili/s_probegom/{normalized_brand}"
        
        params = {
            'cd': 1,
            's': '104',
            'radius': radius,
            'pmax': max_price if max_price > 0 else None,
            'pmin': min_price if min_price > 0 else None,
        }
        params = {k: v for k, v in params.items() if v is not None}
        
        # Construct the URL with initial parameters
        url = f"{base_url}?"

        # Add parameters to the URL
        param_strings = [f"{k}={v}" for k, v in params.items()]
        url += '&'.join(param_strings)

        logger.info(f"Сформирован URL: {url}")
        return url