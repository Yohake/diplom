import json
from pathlib import Path
from datetime import datetime, timedelta
import uuid
from typing import Dict, List, Optional, Tuple
import logging
import statistics
import json
import re
from collections import defaultdict
from typing import Dict, Any
from collections import defaultdict
import csv
from pathlib import Path
from openpyxl import Workbook
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Константы
STORAGE_PATH = Path("storage/searches.json")
MAX_RESULTS_PER_SEARCH = 200  # Максимальное количество сохраняемых результатов
MAX_SEARCH_AGE_DAYS = 30      # Максимальный возраст поиска в днях
MAX_SEARCHES_PER_USER = 20    # Максимальное количество поисков на пользователя

lock = Lock()  # Для потокобезопасности при записи

def load_searches() -> Dict[str, Dict[str, List[dict]]]:
    """Загружает все поиски пользователей с обработкой ошибок"""
    try:
        if not STORAGE_PATH.exists():
            return {}

        with open(STORAGE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        logger.error(f"Error loading searches: {e}")
        return {}

def save_searches(searches: Dict[str, Dict[str, List[dict]]]):
    """Сохраняет поисковые данные с обработкой ошибок"""
    try:
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Пытаюсь сохранить в {STORAGE_PATH.absolute()}")
        with open(STORAGE_PATH, 'w', encoding='utf-8') as f:
            json.dump(searches, f, indent=4, ensure_ascii=False)
        logger.info("Данные успешно сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}", exc_info=True)
        raise  # Добавьте это для отладки
    print("Перед сохранением:", json.dumps(searches, indent=2, ensure_ascii=False))
    print("Сохраняется в файл:", STORAGE_PATH.resolve())



def get_user_searches(user_id: int) -> Dict[str, List[dict]]:
    """Получает все поиски пользователя"""
    searches = load_searches()
    return searches.get(str(user_id), {})

def save_search(
    user_id: int,
    platform: str,
    params: dict,
    last_result_ids: List[str],
    last_results: List[dict],
    notifications: bool = True
) -> Tuple[str, bool]:
    """
    Сохраняет новый поиск с результатами
    Возвращает (search_id, is_new_search)
    """
    with lock:
        searches = load_searches()
        user_id_str = str(user_id)
        user_searches = searches.setdefault(user_id_str, {})
        platform_searches = user_searches.setdefault(platform, [])
        
        # Проверяем, не превышен ли лимит поисков
        total_searches = sum(len(s) for s in user_searches.values())
        if total_searches >= MAX_SEARCHES_PER_USER:
            return "", False
        
        now_iso = datetime.utcnow().isoformat()
        
        # Преобразуем результаты в новый формат (словарь с ID в качестве ключей)
        results_dict = {}
        for ad in last_results:
            ad_id = ad.get('id') or str(uuid.uuid4())
            brand = ad.get('brand')
            model = ad.get('model')
            if not brand or brand == "Не указана" or not model or model == "Не указана":
                # Попробовать извлечь из title
                brand_from_title, model_from_title = extract_brand_model(ad.get('title', ''))
                if not brand or brand == "Не указана":
                    brand = brand_from_title
                if not model or model == "Не указана":
                    model = model_from_title
            results_dict[ad_id] = {
                'title': ad.get('title', 'Без названия'),
                'price': ad.get('price', 'Не указана'),
                'brand': brand,
                'model': model,
                'address': ad.get('address', 'Не указано'),
                'url': ad.get('url', '#'),
                'date': ad.get('date', 'Не указана')
            }
        
        # Ищем существующий поиск с такими же параметрами
        for search in platform_searches:
            if search['params'] == params:
                # Обновляем существующий поиск
                search['last_result_ids'] = list(results_dict.keys())[:MAX_RESULTS_PER_SEARCH]
                search['last_results'] = results_dict
                search['last_check'] = now_iso
                search['updated_at'] = now_iso
                save_searches(searches)
                logger.info(f"Updated existing search {search['id']} for user {user_id}")
                return search['id'], False
        
        # Создаем новый поиск
        search_id = str(uuid.uuid4())
        new_search = {
            'id': search_id,
            'params': params,
            'last_result_ids': list(results_dict.keys())[:MAX_RESULTS_PER_SEARCH],
            'last_results': results_dict,
            'notifications': notifications,
            'created_at': now_iso,
            'updated_at': now_iso,
            'last_check': now_iso
        }
        
        platform_searches.append(new_search)
        save_searches(searches)
        logger.info(f"Saved new search {search_id} for user {user_id} on {platform}")
        return search_id, True
    
def remove_search_by_id(user_id: int, search_id: str) -> bool:
    """Удаляет поиск по ID"""
    with lock:
        searches = load_searches()
        user_searches = searches.get(str(user_id), {})
        
        removed = False
        for platform, platform_searches in user_searches.items():
            for i, search in enumerate(platform_searches):
                if search['id'] == search_id:
                    platform_searches.pop(i)
                    removed = True
                    break
            if removed:
                if not platform_searches:
                    user_searches.pop(platform)
                break

        if removed and not user_searches:
            searches.pop(str(user_id))

        if removed:
            save_searches(searches)
            logger.info(f"Removed search {search_id} for user {user_id}")
        else:
            logger.warning(f"Search {search_id} not found for user {user_id}")

        return removed

def toggle_notifications(user_id: int, search_id: str) -> Optional[bool]:
    """Переключает уведомления для поиска"""
    with lock:
        searches = load_searches()
        user_searches = searches.get(str(user_id), {})
        
        for platform_searches in user_searches.values():
            for search in platform_searches:
                if search['id'] == search_id:
                    search['notifications'] = not search.get('notifications', True)
                    search['updated_at'] = datetime.utcnow().isoformat()
                    save_searches(searches)
                    new_status = search['notifications']
                    logger.info(f"Toggled notifications for search {search_id} to {new_status}")
                    return new_status
        
        logger.warning(f"Search {search_id} not found for user {user_id}")
        return None

def cleanup_old_searches(days: int = MAX_SEARCH_AGE_DAYS) -> int:
    """Очищает старые поиски (старше указанного количества дней)"""
    with lock:
        searches = load_searches()
        removed_count = 0
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        for user_id in list(searches.keys()):
            user_searches = searches[user_id]
            for platform in list(user_searches.keys()):
                platform_searches = user_searches[platform]
                new_list = []
                for search in platform_searches:
                    try:
                        updated_at = datetime.fromisoformat(search.get('updated_at', search['created_at']))
                    except Exception:
                        removed_count += 1
                        continue

                    if updated_at >= cutoff_date:
                        new_list.append(search)
                    else:
                        removed_count += 1

                if new_list:
                    user_searches[platform] = new_list
                else:
                    user_searches.pop(platform)

            if not user_searches:
                searches.pop(user_id)

        save_searches(searches)
        logger.info(f"Cleaned up {removed_count} old searches")
        return removed_count

def import_user_searches(user_id: int, searches_data: dict) -> int:
    """Импортирует поиски для пользователя"""
    with lock:
        current_searches = load_searches()
        user_searches = current_searches.setdefault(str(user_id), {})
        imported_count = 0

        for platform, searches in searches_data.items():
            existing_ids = {s['id'] for s in user_searches.get(platform, [])}
            
            for search in searches:
                if search['id'] not in existing_ids:
                    # Проверяем лимит поисков
                    total_searches = sum(len(s) for s in user_searches.values())
                    if total_searches >= MAX_SEARCHES_PER_USER:
                        break
                        
                    user_searches.setdefault(platform, []).append(search)
                    imported_count += 1

        save_searches(current_searches)
        logger.info(f"Imported {imported_count} searches for user {user_id}")
        return imported_count

def get_search_results(user_id: int, search_id: str) -> List[dict]:
    """Получает сохраненные результаты поиска"""
    searches = load_searches()
    user_searches = searches.get(str(user_id), {})
    
    for platform_searches in user_searches.values():
        for search in platform_searches:
            if search['id'] == search_id:
                # Преобразуем словарь обратно в список для совместимости
                results_dict = search.get('last_results', {})
                return [
                    {'id': ad_id, **ad_data} 
                    for ad_id, ad_data in results_dict.items()
                ]
    
    return []

def compare_platforms_prices(user_id: int, platform1: str, platform2: str) -> Dict[str, List[dict]]:
    """
    Сравнивает цены на автомобили между двумя платформами по названию и модели.
    Возвращает словарь с:
    - common: автомобили, найденные на обеих платформах с разницей цен
    - only_first: автомобили, найденные только на первой платформе
    - only_second: автомобили, найденные только на второй платформе
    """
    comparison = {
        "common": [],
        "only_first": [],
        "only_second": []
    }
    
    searches = load_searches()
    user_searches = searches.get(str(user_id), {})
    
    # Получаем все результаты для указанных платформ
    platform1_results = []
    platform2_results = []
    
    if platform1 in user_searches:
        for search in user_searches[platform1]:
            platform1_results.extend(search.get('last_results', []))
    
    if platform2 in user_searches:
        for search in user_searches[platform2]:
            platform2_results.extend(search.get('last_results', []))
    
    # Создаем нормализованные ключи для сравнения (марка + модель)
    def create_key(ad):
        brand = ad.get('brand', '').lower().strip()
        model = ad.get('model', '').lower().strip()
        return f"{brand}_{model}"
    
    # Группируем объявления по ключам
    platform1_ads = {}
    for ad in platform1_results:
        key = create_key(ad)
        if key not in platform1_ads:
            platform1_ads[key] = []
        platform1_ads[key].append(ad)
    
    platform2_ads = {}
    for ad in platform2_results:
        key = create_key(ad)
        if key not in platform2_ads:
            platform2_ads[key] = []
        platform2_ads[key].append(ad)
    
    # Находим общие ключи
    common_keys = set(platform1_ads.keys()) & set(platform2_ads.keys())
    only_first_keys = set(platform1_ads.keys()) - common_keys
    only_second_keys = set(platform2_ads.keys()) - common_keys
    
    # Заполняем результаты сравнения
    
    # 1. Автомобили только на первой платформе
    for key in only_first_keys:
        for ad in platform1_ads[key]:
            comparison["only_first"].append({
                "ad": ad,
                "platform": platform1
            })
    
    # 2. Автомобили только на второй платформе
    for key in only_second_keys:
        for ad in platform2_ads[key]:
            comparison["only_second"].append({
                "ad": ad,
                "platform": platform2
            })
    
    # 3. Автомобили на обеих платформах (сравниваем цены)
    for key in common_keys:
        # Берем минимальные цены с каждой платформы для сравнения
        min_price1 = min(ad.get('price', 0) for ad in platform1_ads[key])
        min_price2 = min(ad.get('price', 0) for ad in platform2_ads[key])
        
        # Пример объявления с каждой платформы
        example_ad1 = platform1_ads[key][0]
        example_ad2 = platform2_ads[key][0]
        
        price_diff = min_price1 - min_price2
        price_diff_percent = (abs(price_diff) / max(min_price1, min_price2)) * 100 if max(min_price1, min_price2) > 0 else 0
        
        comparison["common"].append({
            "brand": example_ad1.get('brand'),
            "model": example_ad1.get('model'),
            "platform1_price": min_price1,
            "platform2_price": min_price2,
            "price_difference": price_diff,
            "price_difference_percent": price_diff_percent,
            "platform1_ad": example_ad1,
            "platform2_ad": example_ad2,
            "platform1_count": len(platform1_ads[key]),
            "platform2_count": len(platform2_ads[key])
        })
    
    # Сортируем результаты
    comparison["common"].sort(key=lambda x: abs(x["price_difference"]), reverse=True)
    comparison["only_first"].sort(key=lambda x: x["ad"].get('price', 0))
    comparison["only_second"].sort(key=lambda x: x["ad"].get('price', 0))
    
    return comparison

def clean_price(price_str: str) -> float:
    """Преобразует строку цены в число"""
    if not price_str:
        return 0
    
    # Удаляем все символы, кроме цифр и точки/запятой
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    
    # Заменяем запятые на точки для десятичных разделителей
    cleaned = cleaned.replace(',', '.')
    
    try:
        # Если есть точка - считаем это десятичной дробью
        if '.' in cleaned:
            return float(cleaned)
        # Иначе - целое число
        return float(cleaned)
    except ValueError:
        return 0

def build_platforms_comparison_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора платформ для сравнения"""
    searches = get_user_searches(user_id)
    platforms = list(searches.keys())
    
    if len(platforms) < 2:
        return None
    
    builder = InlineKeyboardBuilder()
    
    # Создаем все возможные пары платформ
    for i in range(len(platforms)):
        for j in range(i + 1, len(platforms)):
            platform1 = platforms[i]
            platform2 = platforms[j]
            text = f"{platform1.upper()} ↔ {platform2.upper()}"
            callback_data = f"compare_platforms:{platform1}:{platform2}"
            builder.add(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    builder.add(InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    builder.adjust(1)
    return builder.as_markup()

def build_search_actions_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с действиями для поиска"""
    builder = InlineKeyboardBuilder()
    
    buttons = [
        ("🔍 Просмотреть", f"view_search:{search_id}"),
        ("🔔 Уведомления", f"toggle_notify:{search_id}"),
        ("📤 Экспорт", f"export_search:{search_id}"),
        ("🗑️ Удалить", f"delete_search:{search_id}"),
        ("🔄 Сравнить", f"compare_search:{search_id}")
    ]
    
    for text, data in buttons:
        builder.add(InlineKeyboardButton(text=text, callback_data=data))
    
    builder.adjust(2)
    return builder.as_markup()

def delete_search_by_id(user_id: int, search_id: str) -> bool:
    """Удаляет поиск по ID и возвращает True если удаление прошло успешно"""
    with lock:
        searches = load_searches()
        user_id_str = str(user_id)
        
        if user_id_str not in searches:
            return False
            
        deleted = False
        for platform in list(searches[user_id_str].keys()):
            platform_searches = searches[user_id_str][platform]
            # Ищем и удаляем поиск
            searches[user_id_str][platform] = [
                s for s in platform_searches 
                if s['id'] != search_id
            ]
            
            # Если удалили что-то, отмечаем
            if len(searches[user_id_str][platform]) != len(platform_searches):
                deleted = True
                
            # Удаляем пустые платформы
            if not searches[user_id_str][platform]:
                del searches[user_id_str][platform]
        
        # Удаляем пустых пользователей
        if not searches[user_id_str]:
            del searches[user_id_str]
        
        if deleted:
            save_searches(searches)
            logger.info(f"Deleted search {search_id} for user {user_id}")
        else:
            logger.warning(f"Search {search_id} not found for user {user_id}")
            
        return deleted

def build_comparison_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора второго поиска для сравнения"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="Выбрать другой поиск",
        callback_data=f"select_to_compare:{search_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="Отмена",
        callback_data="cancel"
    ))
    return builder.as_markup()

def build_results_navigation_keyboard(
    current_index: int,
    total_results: int,
    search_id: str
) -> InlineKeyboardMarkup:
    """Создает клавиатуру для навигации по результатам"""
    builder = InlineKeyboardBuilder()
    
    if current_index > 0:
        builder.add(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"prev_result:{search_id}:{current_index}"
        ))
    
    builder.add(InlineKeyboardButton(
        text=f"{current_index + 1}/{total_results}",
        callback_data="noop"
    ))
    
    if current_index < total_results - 1:
        builder.add(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"next_result:{search_id}:{current_index}"
        ))
    
    builder.adjust(3)
    return builder.as_markup()

def get_search_info(user_id: int, search_id: str) -> Optional[dict]:
    """Получает информацию о поиске"""
    searches = load_searches()
    user_searches = searches.get(str(user_id), {})
    
    for platform_searches in user_searches.values():
        for search in platform_searches:
            if search['id'] == search_id:
                return search
    
    return None

def compare_search_results(search1: dict, search2: dict) -> dict:
    """Сравнивает результаты двух поисков"""
    results1 = {ad['id']: ad for ad in search1.get('last_results', [])}
    results2 = {ad['id']: ad for ad in search2.get('last_results', [])}
    
    common_ids = set(results1.keys()) & set(results2.keys())
    only_first_ids = set(results1.keys()) - common_ids
    only_second_ids = set(results2.keys()) - common_ids
    
    return {
        'common': [results1[id] for id in common_ids],
        'only_first': [results1[id] for id in only_first_ids],
        'only_second': [results2[id] for id in only_second_ids]
    }

def compare_prices_by_model(user_id: int, brand: str, model: str) -> Dict[str, Any]:
    """
    Сравнивает цены указанной модели автомобиля на всех платформах
    """
    searches = load_searches()
    user_searches = searches.get(str(user_id), {})
    
    # Нормализуем входные данные для сравнения
    brand_lower = brand.strip().lower()
    model_lower = model.strip().lower()
    
    result = {
        'brand': brand,
        'model': model,
        'platforms': [],
        'min_price': float('inf'),
        'max_price': 0.0,
        'total_ads': 0
    }
    
    # Собираем объявления по платформам
    platform_ads = defaultdict(list)
    
    for platform, searches_list in user_searches.items():
        if not isinstance(searches_list, list):
            continue
            
        for search in searches_list:
            # Получаем объявления - учитываем, что они могут быть в словаре
            ads_dict = search.get('last_results', {})
            ads = list(ads_dict.values()) if isinstance(ads_dict, dict) else []
            
            for ad in ads:
                if not isinstance(ad, dict):
                    continue
                    
                ad_brand = ad.get('brand', '').strip().lower()
                ad_model = ad.get('model', '').strip().lower()
                
                # Более гибкое сравнение (частичное совпадение)
                if (brand_lower in ad_brand and 
                    model_lower in ad_model):
                    
                    try:
                        price = float(clean_price(ad.get('price', '0')))
                        if price > 0:
                            platform_ads[platform].append({
                                'price': price,
                                'url': ad.get('url', ''),
                                'title': ad.get('title', ''),
                                'date': ad.get('date', ''),
                                'location': ad.get('location', '')
                            })
                    except (ValueError, TypeError):
                        continue
    
    # Анализируем данные по платформам
    for platform, ads in platform_ads.items():
        if not ads:
            continue
            
        prices = [ad['price'] for ad in ads]
        platform_stats = {
            'platform': platform,
            'min_price': min(prices),
            'max_price': max(prices),
            'avg_price': sum(prices) / len(prices),
            'median_price': sorted(prices)[len(prices) // 2],
            'count': len(ads),
            'ads': ads[:5]  # Сохраняем 5 объявлений для примера
        }
        
        result['platforms'].append(platform_stats)
        result['min_price'] = min(result['min_price'], platform_stats['min_price'])
        result['max_price'] = max(result['max_price'], platform_stats['max_price'])
        result['total_ads'] += platform_stats['count']
    
    # Сортируем платформы по минимальной цене
    result['platforms'].sort(key=lambda x: x['min_price'])
    
    return result

def get_unique_brands_and_models(user_id: int) -> Dict[str, List[str]]:
    searches = load_searches()
    user_data = searches.get(str(user_id), {})
    
    brands_models = defaultdict(list)
    
    for platform_searches in user_data.values():
        for search in platform_searches:
            if not isinstance(search.get('last_results'), dict):
                continue
                
            for ad_data in search['last_results'].values():
                if not isinstance(ad_data, dict):
                    continue
                    
                # Нормализуем регистр бренда
                brand = ad_data.get('brand', '').strip().lower()
                model = ad_data.get('model', '').strip()
                
                if brand and model and model not in brands_models[brand]:
                    brands_models[brand].append(model)
    
    return dict(brands_models)


def get_ads_by_model(user_id: int, brand: str, model: str, platform: str) -> List[dict]:
    """Возвращает объявления по конкретной модели и платформе"""
    searches = load_searches()
    user_searches = searches.get(str(user_id), {}).get(platform, [])
    
    ads = []
    
    for search in user_searches:
        results = search.get('last_results', {})
        if isinstance(results, dict):
            ads_list = list(results.values())
        else:
            ads_list = results
            
        for ad in ads_list:
            if not isinstance(ad, dict):
                continue
                
            # Получаем или извлекаем марку и модель
            ad_brand = ad.get('brand', '').strip().lower()
            ad_model = ad.get('model', '').strip().lower()
            
            if not ad_brand or not ad_model:
                title = ad.get('title', '').lower()
                parts = title.split()
                if len(parts) >= 2:
                    if not ad_brand:
                        ad_brand = parts[0]
                    if not ad_model:
                        ad_model = parts[1]
            
            if (ad_brand == brand.lower() and 
                ad_model == model.lower()):
                
                cleaned_ad = ad.copy()
                cleaned_ad['price_num'] = clean_price(ad.get('price', '0'))
                ads.append(cleaned_ad)
    
    ads.sort(key=lambda x: x['price_num'])
    return ads

def extract_brand_model(title: str) -> tuple:
    match = re.match(r"^([A-Za-zА-Яа-яЁё0-9]+)\s+([A-Za-zА-Яа-яЁё0-9]+)", title)
    if match:
        brand = match.group(1)
        model = match.group(2)
        return brand, model
    return "Не указана", "Не указана"
