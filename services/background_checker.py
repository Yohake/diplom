import asyncio
from aiogram import Bot
from services.search_service import SearchService
from services.avito_parser import AvitoParser
from services.drom_parser import DromParser
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class BackgroundChecker:
    def __init__(self, bot: Bot, interval: int = 600):
        self.bot = bot
        self.interval = interval
        self.search_service = SearchService()
        self.avito_parser = AvitoParser()
        self.drom_parser = DromParser()

    async def start(self):
        while True:
            try:
                await self._check_all_searches()
            except Exception as e:
                logger.error(f"Ошибка в фоновой проверке: {e}")
            await asyncio.sleep(self.interval)

    async def _check_all_searches(self):
        searches = self.search_service._load_all()
        
        for user_id, user_searches in searches.items():
            for search in user_searches:
                if not search["notifications"]:
                    continue
                
                new_ads = await self._check_search(search)
                if new_ads:
                    await self._notify_user(user_id, new_ads, search)

    async def _check_search(self, search: Dict) -> List[Dict]:
        platform = search["platform"]
        params = search["params"]
        
        try:
            if platform == "avito":
                ads = await self.avito_parser.parse_ads(
                    brand=params.get("brand"),
                    city=params.get("city"),
                    radius_km=params.get("radius", 200),
                    min_price=params.get("min_price"),
                    max_price=params.get("max_price"),
                    min_year=params.get("min_year"),
                    max_year=params.get("max_year")
                )
            elif platform == "drom":
                ads = await self.drom_parser.parse_ads_drom(
                    brand=params.get("brand"),
                    city=params.get("city"),
                    radius_km=params.get("radius", 200),
                    min_price=params.get("min_price"),
                    max_price=params.get("max_price"),
                    min_year=params.get("min_year"),
                    max_year=params.get("max_year")
                )
            else:
                return []
            
            last_ids = {ad["id"] for ad in search["last_results"]}
            new_ads = [ad for ad in ads if ad["id"] not in last_ids]
            
            if new_ads:
                self.search_service.update_search_results(
                    search["id"],
                    ads[:50]  # Сохраняем только последние 50 объявлений
                )
            
            return new_ads
        except Exception as e:
            logger.error(f"Ошибка проверки поиска {search['id']}: {e}")
            return []

    async def _notify_user(self, user_id: str, ads: List[Dict], search: Dict):
        message = f"🔔 Новые объявления по вашему поиску:\n\n"
        for ad in ads[:5]:  # Ограничиваем 5 объявлениями в уведомлении
            message += (
                f"{ad['title']}\n"
                f"Цена: {ad['price']}\n"
                f"Год: {ad.get('year', '—')}\n"
                f"Ссылка: {ad['link']}\n\n"
            )
        
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
