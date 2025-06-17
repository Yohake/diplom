from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.buttons import (
    about_button, avito_button, drom_button, autoru_button, author_button,
    back_button, brand_button, region_button, city_button, 
    radius_button, navigation_button, next_ad_button, search_action_button,
    export_csv_button, export_json_button, select_compare_button,
    start_search_button, back_to_platforms_button, my_searches_button,
    manage_notifications_button, export_button, import_button
)
from schemas.callbacks import (
    SearchPaginationCallback,
    DeleteCallback,
    ToggleCallback,
    ExportCallback
)
from services.search_service import get_user_searches
from typing import List 
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(about_button)
    builder.row(avito_button, drom_button, autoru_button)
    builder.row(author_button)
    builder.row(my_searches_button, manage_notifications_button)
    return builder.as_markup()

def export_import_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(export_button, import_button)
    builder.row(back_button)
    return builder.as_markup()

def about_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(back_button)
    return builder.as_markup()

def back_to_menu():
    builder = InlineKeyboardBuilder()
    builder.add(back_button)
    return builder.as_markup()

def platform_choice_keyboard(platform: str):
    try:
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(
            text="🔍 Начать поиск", 
            callback_data=f"start_{platform}_search"
        ))
        builder.add(back_to_platforms_button)
        builder.adjust(1)
        return builder.as_markup()
    
    except Exception as e:
        logger.error(f"Ошибка в функции platform_choice_keyboard: {e}")
        return None  

def back_to_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_menu")  
    return builder.as_markup()

def get_brands_keyboard(brands: list, page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура для выбора марки автомобиля с пагинацией"""
    builder = InlineKeyboardBuilder()
    
    # Сортируем бренды и создаем кнопки
    for brand in sorted(brands):
        builder.add(InlineKeyboardButton(
            text=brand, 
            callback_data=f"brand_{brand.lower().replace(' ', '_')}"
        ))
    
    # Кнопки пагинации (если нужно)
    if total_pages > 1:
        if page > 0:
            builder.add(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"page_{page-1}"
            ))
        
        builder.add(InlineKeyboardButton(
            text=f"{page+1}/{total_pages}",
            callback_data="no_action"
        ))
        
        if page < total_pages - 1:
            builder.add(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"page_{page+1}"
            ))
    
    builder.add(back_button)
    builder.adjust(2, repeat=True)
    return builder.as_markup()

def regions_keyboard():
    builder = InlineKeyboardBuilder()
    regions = ["Москва", "Санкт-Петербург", "Казань", "Другой"]
    for region in regions:
        builder.add(region_button(region))
    builder.add(back_button)
    builder.adjust(2)
    return builder.as_markup()

def radius_keyboard():
    builder = InlineKeyboardBuilder()
    radii = [("Только город", 0), ("+50 км", 50), ("+100 км", 100), ("+200 км", 200)]
    for text, radius in radii:
        builder.add(radius_button(text, radius))
    builder.add(back_button)
    builder.adjust(2)
    return builder.as_markup()

def next_ad_keyboard(index: int):
    builder = InlineKeyboardBuilder()
    builder.add(next_ad_button(index))
    builder.add(back_button)
    return builder.as_markup()

def cities_keyboard(cities: list, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    start = page * per_page
    end = start + per_page
    builder = InlineKeyboardBuilder()
    
    for city in cities[start:end]:
        builder.add(city_button(city["name"], city['id']))
    
    builder.adjust(2)
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cities_page_{page - 1}"))
    if end < len(cities):
        nav_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"cities_page_{page + 1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(back_button)
    
    return builder.as_markup()

def create_search_keyboard(search, current_page, total_pages):
    builder = InlineKeyboardBuilder()
    
    # Кнопки управления поиском
    builder.row(
        InlineKeyboardButton(
            text="❌ Удалить",
            callback_data=DeleteCallback(search_id=search['id']).pack()
        ),
        InlineKeyboardButton(
            text="🔕 Отключить" if search['notifications'] else "🔔 Включить",
            callback_data=ToggleCallback(search_id=search['id']).pack()
        )
    )
    
    # Кнопки пагинации
    if current_page > 0:
        builder.add(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=SearchPaginationCallback(page=current_page - 1).pack()
            )
        )
    if current_page < total_pages - 0:
        builder.add(
            InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=SearchPaginationCallback(page=current_page + 1).pack()
            )
        )
    
    # Кнопки экспорта/импорта
    builder.row(
        InlineKeyboardButton(text="📤 Экспорт", callback_data=ExportCallback(action="export").pack()),
        InlineKeyboardButton(text="📥 Импорт", callback_data=ExportCallback(action="import").pack())
    )
    
    return builder.as_markup()


def searches_list_keyboard(searches: dict) -> InlineKeyboardMarkup:
    """Клавиатура со списком всех поисков пользователя"""
    builder = InlineKeyboardBuilder()
    
    for platform, platform_searches in searches.items():
        for search in platform_searches:
            params = search.get('params', {})
            brand = params.get('brand', '—')
            region = params.get('region', '—')
            text = f"{brand} ({region})"

            builder.add(InlineKeyboardButton(
                text=text,
                callback_data=f"view_search:{search['id']}"
            ))
    
    builder.row(export_button, import_button)
    builder.row(back_button)
    builder.adjust(1)
    return builder.as_markup()

def search_actions_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с действиями для конкретного поиска"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        search_action_button(search_id, "view"),
        search_action_button(search_id, "toggle")
    )
    builder.row(
        search_action_button(search_id, "export"),
        search_action_button(search_id, "compare_prices_by_model")
    )
    builder.row(
        search_action_button(search_id, "delete"),
        back_to_menu_keyboard()
    )
    
    builder.adjust(2)
    return builder.as_markup()

def build_results_keyboard(
    search_id: str, 
    current_index: int, 
    total_results: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Кнопки навигации
    nav_buttons = []
    if current_index > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"prev_result:{search_id}:{current_index-1}"
        ))
    
    nav_buttons.append(InlineKeyboardButton(
        text=f"{current_index+1}/{total_results}",
        callback_data="no_action"
    ))
    
    if current_index < total_results - 1:
        nav_buttons.append(InlineKeyboardButton(
            text="➡️ Вперед",
            callback_data=f"next_result:{search_id}:{current_index+1}"
        ))
    
    builder.row(*nav_buttons)

    # Кнопка "🔙 Назад"
    builder.row(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="my_searches"
    ))

    return builder.as_markup()


def build_comparison_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для сравнения поисков"""
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(
        text="Выбрать для сравнения",
        callback_data=f"select_compare:{search_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="Вернуться к моим поискам",  # Изменили текст кнопки
        callback_data=f"my_searches:{search_id}"  # Обновили callback_data
    ))
    
    return builder.as_markup()


def build_export_options_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с вариантами экспорта"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="JSON", callback_data=f"export_json:{search_id}"),
        InlineKeyboardButton(text="CSV", callback_data=f"export_csv:{search_id}"),
        InlineKeyboardButton(text="Excel", callback_data=f"export_excel:{search_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="my_searches")
    )
    
    return builder.as_markup()

def compare_selection_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора второго поиска для сравнения"""
    builder = InlineKeyboardBuilder()
    
    builder.add(select_compare_button)
    builder.add(back_button)
    
    return builder.as_markup()

def export_options_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами экспорта"""
    builder = InlineKeyboardBuilder()
    
    builder.row(export_json_button, export_csv_button)
    builder.row(back_button)
    
    return builder.as_markup()

def build_main_searches_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Основная клавиатура для раздела 'Мои поиски'"""
    searches = get_user_searches(user_id)
    builder = InlineKeyboardBuilder()
    
    if not searches:
        builder.add(back_button)
        return builder.as_markup()
    
    # Кнопки для каждого поиска
    for platform, platform_searches in searches.items():
        for search in platform_searches:
            params = search.get('params', {})
            brand = params.get('brand', '—')
            region = params.get('region', '—')
            text = f"{brand} ({region})"

            builder.add(InlineKeyboardButton(
                text=text,
                callback_data=f"view_search:{search['id']}"
            ))

    # Дополнительные кнопки
    builder.row(back_button)
    
    builder.adjust(1)
    return builder.as_markup()

def build_search_details_keyboard(search_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с действиями для конкретного поиска"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔍 Показать", callback_data=f"show_results:{search_id}"),
        InlineKeyboardButton(text="🔔 Уведомления", callback_data=f"toggle_notify:{search_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📤 Экспорт", callback_data=f"export_search:{search_id}"),
        InlineKeyboardButton(text="🔄 Сравнить", callback_data=f"compare_by_model:{search_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_search:{search_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="my_searches")
    )
    
    builder.adjust(2)
    return builder.as_markup()

def compare_by_model_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для запуска сравнения по модели.
    """
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🔄 Сравнить по модели", callback_data="compare_by_model"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")
    )
    builder.adjust(1)
    return builder.as_markup()


def models_keyboard(models: List[str]) -> InlineKeyboardMarkup:
    """Создает клавиатуру с моделями автомобилей"""
    builder = InlineKeyboardBuilder()
    
    for model in sorted(models):
        builder.add(InlineKeyboardButton(
            text=model,
            callback_data=f"select_model:{model}"
        ))
    
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    builder.adjust(2)
    return builder.as_markup()


def platforms_keyboard(platforms: list, brand: str, model: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора платформы (для показа объявлений по платформе).
    """
    builder = InlineKeyboardBuilder()
    for platform in platforms:
        builder.add(InlineKeyboardButton(
            text=f"🔍 {platform}",
            callback_data=f"show_ads:{brand}:{model}:{platform}"
        ))
    builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="compare_by_model"))
    builder.adjust(2)
    return builder.as_markup()
