from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from services.avito_parser import AvitoParser
from services.drom_parser import DromParser
from services.autoru_parser import AutoRuParser
from services.search_service import save_search
from datetime import datetime
from keyboards.builders import (
    get_brands_keyboard,
    regions_keyboard,
    radius_keyboard,
    cities_keyboard,
    back_to_platforms_button,
    back_to_menu_keyboard
)
from config.settings import settings
from storage.cities import locations_dict
from transliterate import translit
from models.states import ParserState
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()


def get_city_name(city_path: str) -> str:
    return city_path.replace('_', ' ').title()


def normalize_city_name(city: str) -> str:
    try:
        transliterated = translit(city.lower(), 'ru', reversed=True)
        normalized = ''.join(c if c.isalpha() or c == ' ' else '' for c in transliterated)
        return normalized.replace(' ', '_')
    except:
        return city.lower().replace(' ', '_')

def load_cities_data(file_path: str) -> dict:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных из {file_path}: {e}")
        return {}

@router.callback_query(F.data.startswith("start_avito_search"))
async def start_avito_search_process(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ParserState.waiting_brand)
    parser = AvitoParser()
    html = await parser.fetch_html("https://www.avito.ru/moskva/avtomobili")
    brands = await parser.parse_brands(html)

    total_pages = (len(brands) + 3) // 4

    await state.update_data(brands=brands, current_page=0, platform="avito")
    await callback.message.edit_text(
        "🔍 <b>Выберите марку автомобиля:</b>",
        reply_markup=get_brands_keyboard(brands[:4], 0, total_pages),
        parse_mode=settings.PARSE_MODE
    )


@router.callback_query(F.data.startswith("start_drom_search"))
async def start_drom_search_process(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ParserState.waiting_brand)
    parser = DromParser()

    # Теперь не нужно fetch_html
    brands = await parser.parse_brands_drom()  # <-- без html

    logger.info(f"Марки, полученные из Drom: {brands}")
    
    total_pages = (len(brands) + 3) // 4

    await state.update_data(brands=brands, current_page=0, platform="drom")
    
    if brands:
        await callback.message.edit_text(
            "🔍 <b>Выберите марку автомобиля:</b>",
            reply_markup=get_brands_keyboard(brands[:4], 0, total_pages),
            parse_mode=settings.PARSE_MODE
        )
    else:
        await callback.message.edit_text(
            "🚫 <b>Не удалось получить марки автомобилей.</b>",
            reply_markup=back_to_menu_keyboard(),
            parse_mode=settings.PARSE_MODE
        )

@router.callback_query(F.data.startswith("start_autoru_search"))
async def start_autoru_search_process(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ParserState.waiting_brand)
    parser = AutoRuParser()
    brands = await parser.parse_brands()
    logger.info(f"Марки, полученные из Auto.ru: {brands}")
    
    total_pages = (len(brands) + 3) // 4

    await state.update_data(brands=brands, current_page=0, platform="autoru")

    if brands:
        await callback.message.edit_text(
            "🔍 <b>Выберите марку автомобиля:</b>",
            reply_markup=get_brands_keyboard(brands[:4], 0, total_pages),
            parse_mode=settings.PARSE_MODE
        )
    else:
        await callback.message.edit_text(
            "🚫 <b>Не удалось получить марки автомобилей.</b>",
            reply_markup=back_to_menu_keyboard(),
            parse_mode=settings.PARSE_MODE
        )

@router.callback_query(F.data.startswith("page_"))
async def change_page(callback: types.CallbackQuery, state: FSMContext):
    if await state.get_state() != ParserState.waiting_brand:
        return

    page = int(callback.data.split('_')[1])
    data = await state.get_data()
    brands = data['brands']

    current_brands = brands[page * 4: (page + 1) * 4]
    
    total_pages = (len(brands) + 3) // 4
    await callback.message.edit_text(
        "🔍 <b>Выберите марку автомобиля:</b>",
        reply_markup=get_brands_keyboard(current_brands, page, total_pages),
        parse_mode=settings.PARSE_MODE
    )


@router.callback_query(F.data.startswith("brand_"))
async def select_region(callback: types.CallbackQuery, state: FSMContext):
    if await state.get_state() != ParserState.waiting_brand:
        return

    brand = callback.data.split('_')[1]
    await state.update_data(brand=brand)
    await callback.message.edit_text(
        "📍 <b>Выберите регион:</b>",
        reply_markup=regions_keyboard(),
        parse_mode=settings.PARSE_MODE
    )
    await state.set_state(ParserState.waiting_region)


@router.callback_query(F.data.startswith("region_"))
async def handle_region_selection(callback: types.CallbackQuery, state: FSMContext):
    if await state.get_state() != ParserState.waiting_region:
        return

    region_name = callback.data.split('_')[1]
    await state.update_data(region_name=region_name)

    if region_name == "Другой":
        await callback.message.edit_text("✏️ Введите название города (например: Киров):")
        await state.set_state(ParserState.waiting_custom_region)
        return

    await callback.message.edit_text(
        "🔎 <b>Выберите радиус поиска:</b>",
        reply_markup=radius_keyboard(),
        parse_mode=settings.PARSE_MODE
    )
    await state.set_state(ParserState.waiting_radius)


@router.message(F.text, StateFilter(ParserState.waiting_custom_region))
async def process_custom_region(message: types.Message, state: FSMContext):
    russian_city = message.text.strip()
    data = await state.get_data()
    platform = data.get('platform')

    if platform in ["avito", "autoru"]:
        normalized_city = normalize_city_name(russian_city)

        logger.info(f"Пользователь ввёл город: {russian_city} -> нормализовано: {normalized_city}")

        matched_cities = []
        for city_path, city_id in locations_dict.items():
            if normalized_city in city_path.lower():
                matched_cities.append({
                    "id": city_id,
                    "name": get_city_name(city_path),
                    "path": city_path
                })

        if not matched_cities:
            logger.warning(f"Город не найден: {russian_city}")
            await message.answer(f"Город '{russian_city}' не найден. Попробуйте ввести другое название:")
            return

        if len(matched_cities) == 1:
            city = matched_cities[0]
            logger.info(f"Город определён однозначно: {city['name']} -> {city['path']}")
            await state.update_data(region_name=city['name'], city_id=city['id'], city_path=city['path'])
            await message.answer(
                f"📍 Выбран город: {city['name']}\n"
                "🔎 <b>Выберите радиус поиска:</b>",
                reply_markup=radius_keyboard(),
                parse_mode=settings.PARSE_MODE
            )
            await state.set_state(ParserState.waiting_radius)
        else:
            logger.info(
                f"Найдено несколько совпадений для города {russian_city}: {[c['name'] for c in matched_cities]}")
            await state.update_data(matched_cities=matched_cities)
            await message.answer(
                f"🔎 Найдено несколько городов с названием «{russian_city}». Пожалуйста, выберите нужный:",
                reply_markup=cities_keyboard(matched_cities, page=0),
                parse_mode=settings.PARSE_MODE
            )
            await state.set_state(ParserState.choosing_city)

    elif platform == "drom":
        parser = DromParser()
        matches = await parser.find_all_matching_cities(russian_city)

        if not matches:
            await message.answer("❌ Такой город не найден. Попробуйте снова.")
            return

        if len(matches) == 1:
            match = matches[0]
            await state.update_data(region_name=match['city'], city_link=match['link'])
            await message.answer(
                f"📍 Выбран город: {match['city']} ({match['region']})\n"
                "🔎 <b>Выберите радиус поиска:</b>",
                reply_markup=radius_keyboard(),
                parse_mode=settings.PARSE_MODE
            )
            await state.set_state(ParserState.waiting_radius)
        else:
            buttons = [
                types.InlineKeyboardButton(
                    text=f"{m['city']} ({m['region']})",
                    callback_data=f"drom_city_{i}"
                )
                for i, m in enumerate(matches)
            ]
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])
            await state.update_data(drom_city_matches=matches)
            await message.answer(
                f"🔎 Найдено несколько городов с названием «{russian_city}». Выберите нужный:",
                reply_markup=keyboard,
                parse_mode=settings.PARSE_MODE
            )
            await state.set_state(ParserState.choosing_city)

@router.callback_query(F.data.startswith("drom_city_"))
async def handle_drom_city_selection(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[-1])
    data = await state.get_data()
    matches = data.get("drom_city_matches", [])

    if index >= len(matches):
        await callback.answer("Некорректный выбор.")
        return

    match = matches[index]
    await state.update_data(region_name=match['city'], city_link=match['link'])
    await callback.message.edit_text(
        f"📍 Выбран город: {match['city']} ({match['region']})\n"
        "🔎 <b>Выберите радиус поиска:</b>",
        reply_markup=radius_keyboard(),
        parse_mode=settings.PARSE_MODE
    )
    await state.set_state(ParserState.waiting_radius)


@router.callback_query(F.data.startswith("cities_page_"))
async def paginate_cities(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    data = await state.get_data()
    matched_cities = data.get("matched_cities", [])

    if not matched_cities:
        await callback.answer("Ошибка: нет доступных городов.")
        return

    await callback.message.edit_text(
        "📍 <b>Выберите нужный город:</b>",
        reply_markup=cities_keyboard(matched_cities, page=page),
        parse_mode=settings.PARSE_MODE
    )


@router.callback_query(F.data.startswith("city_"))
async def handle_city_selection(callback: types.CallbackQuery, state: FSMContext):
    if await state.get_state() != ParserState.choosing_city:
        return

    city_id = int(callback.data.split('_')[1])
    data = await state.get_data()
    platform = data.get('platform')

    if platform in ["avito", "autoru"]:
        selected_city = None
        for city_path, c_id in locations_dict.items():
            if c_id == city_id:
                selected_city = {
                    "id": c_id,
                    "name": get_city_name(city_path),
                    "path": city_path
                }
                break

        if selected_city:
            logger.info(f"Пользователь выбрал город: {selected_city['name']} -> {selected_city['path']}")
            await state.update_data(region_name=selected_city['name'], city_id=city_id,
                                     city_path=selected_city['path'])
            await callback.message.edit_text(
                f"📍 Выбран город: {selected_city['name']}\n"
                "🔎 <b>Выберите радиус поиска:</b>",
                reply_markup=radius_keyboard(),
                parse_mode=settings.PARSE_MODE
            )
            await state.set_state(ParserState.waiting_radius)
        else:
            logger.warning(f"Ошибка при выборе города. city_id: {city_id}")
            await callback.answer("Ошибка выбора города. Попробуйте еще раз.")
    elif platform == "drom":
        pass


@router.callback_query(F.data.startswith("radius_"))
async def ask_min_price(callback: types.CallbackQuery, state: FSMContext):
    if await state.get_state() != ParserState.waiting_radius:
        return

    radius = int(callback.data.split('_')[1])
    data = await state.get_data()
    platform = data.get('platform')

    if platform == "drom":
        await state.update_data(distance=radius)
    elif platform in ["avito", "autoru"]:
        await state.update_data(radius=radius)
    
    logger.info(f"Установлен радиус: {radius}, платформа: {platform}, данные в state: {await state.get_data()}")
    await callback.message.edit_text("💰 Введите минимальную цену:")
    await state.set_state(ParserState.waiting_min_price)


@router.message(F.text, StateFilter(ParserState.waiting_min_price))
async def process_min_price(message: types.Message, state: FSMContext):
    try:
        min_price = int(message.text.strip())
        if min_price < 0:
            raise ValueError
        await state.update_data(min_price=min_price)
        await message.answer("💰 Введите максимальную цену:")
        await state.set_state(ParserState.waiting_max_price)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для минимальной цены (например: 100000)")


@router.message(F.text, StateFilter(ParserState.waiting_max_price))
async def process_max_price(message: types.Message, state: FSMContext):
    try:
        max_price = int(message.text.strip())
        
        if max_price < 0:
            raise ValueError

        await state.update_data(max_price=max_price)
        data = await state.get_data()

        logger.info(f"Данные в state перед вызовом parse_ads: {data}")

        await message.answer("🔍 Поиск объявлений начат. Пожалуйста, подождите...")

        platform = data['platform']
        if platform == "avito":
            await parse_ads_avito(message, state, data)
        elif platform == "drom":
            await parse_ads_drom(message, state, data)
        elif platform == "autoru":
            await parse_ads_autoru(message, state, data)
        else:
            await message.answer("Ошибка: Неизвестная платформа.")

    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для максимальной цены (например: 500000)")

async def parse_ads_autoru(message: types.Message, state: FSMContext, data: dict):
    parser = AutoRuParser()
    ads = await parser.parse_ads(
        brand=data['brand'],
        city=data['region_name'],
        radius=data['radius'],
        min_price=data['min_price'],
        max_price=data['max_price']
    )
    await process_ads_results(message, state, ads)


async def parse_ads_avito(message: types.Message, state: FSMContext, data: dict):
    parser = AvitoParser()
    ads = await parser.parse_ads(
        brand=data['brand'],
        city=data['region_name'],
        radius_km=data['radius'],
        min_price=data['min_price'],
        max_price=data['max_price']
    )
    await process_ads_results(message, state, ads)


async def parse_ads_drom(message: types.Message, state: FSMContext, data: dict):
    parser = DromParser()
    ads = await parser.parse_ads(
        brand=data['brand'],
        city=data['region_name'],
        distance=data['distance'],
        min_price=data['min_price'],
        max_price=data['max_price'],
        city_link=data.get('city_link')
    )
    
    # Преобразуем объявления в словари, если они еще не словари
    ads_data = []
    for ad in ads:
        if isinstance(ad, dict):
            ads_data.append(ad)
        else:
            ads_data.append({
                'id': getattr(ad, 'id', None),
                'title': getattr(ad, 'title', 'Без названия'),
                'price': getattr(ad, 'price', 'Не указана'),
                'address': getattr(ad, 'address', 'Не указано'),
                'url': getattr(ad, 'url', '#'),
                'date': getattr(ad, 'date', 'Не указана')
            })
    
    await process_ads_results(message, state, ads_data)

async def process_ads_results(message: types.Message, state: FSMContext, ads: list):
    if not ads:
        await message.answer("😔 Свежих объявлений нет. Попробуйте изменить параметры поиска.")
        return

    # Преобразуем объявления в словари, если они еще не словари
    ads_data = []
    for ad in ads:
        if isinstance(ad, dict):
            ads_data.append(ad)
        else:
            ads_data.append({
                'id': getattr(ad, 'id', None),
                'title': getattr(ad, 'title', 'Без названия'),
                'price': getattr(ad, 'price', 'Не указана'),
                'brand': getattr(ad, 'brand', 'Не указана'),  # Добавлено
                'model': getattr(ad, 'model', 'Не указана'),  # Добавлено
                'address': getattr(ad, 'address', 'Не указано'),
                'url': getattr(ad, 'url', '#'),
                'date': getattr(ad, 'date', 'Не указана')
            })

    data = await state.get_data()
    search_params = {
        "brand": data['brand'],
        "region": data['region_name'],
        "radius": data.get('radius', 0),
        "min_price": data['min_price'],
        "max_price": data['max_price'],
        "platform": data['platform']
    }

    save_search(
        user_id=message.from_user.id,
        platform=data['platform'],
        params=search_params,
        last_result_ids=[ad.get('id') for ad in ads_data] if ads_data else [],
        last_results=ads_data,
        notifications=True
    )

    await state.update_data(results=ads_data, current_ad_index=0)
    await state.set_state(ParserState.viewing_results)

    await message.answer(
        "✅ Найдено объявлений: {}. Для просмотра нажмите /results".format(len(ads_data)),
        parse_mode=settings.PARSE_MODE
    )
