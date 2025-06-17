from aiogram.types import InlineKeyboardButton

# Основные кнопки меню
about_button = InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")
avito_button = InlineKeyboardButton(text="🛒 Поиск на Avito", callback_data="avito_search")
drom_button = InlineKeyboardButton(text="🚗 Поиск на Drom", callback_data="drom_search")
autoru_button = InlineKeyboardButton(text="🚘 Поиск на Auto.ru", callback_data="autoru_search")
author_button = InlineKeyboardButton(text="👨‍💻 Автор", callback_data="author")
back_button = InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")
start_search_button = InlineKeyboardButton(text="🔍 Начать поиск", callback_data="start_search")
back_to_platforms_button = InlineKeyboardButton(text="🔙 К выбору площадки", callback_data="back_to_platforms")


# Дополнительные кнопки
my_searches_button = InlineKeyboardButton(text="📑 Мои поиски", callback_data="my_searches")
manage_notifications_button = InlineKeyboardButton(text="🔔 Управление уведомлениями", callback_data="manage_notifications")
delete_all_searches_button = InlineKeyboardButton(text="❌ Удалить все поиски", callback_data="delete_all_searches")

# Кнопки для импорта и экспорта
export_button = InlineKeyboardButton(text="📤 Экспорт", callback_data="export")
import_button = InlineKeyboardButton(text="📥 Импорт", callback_data="import")

# Новые кнопки для управления поисками
view_search_button = InlineKeyboardButton(text="🔍 Просмотреть", callback_data="view_search")
toggle_notify_button = InlineKeyboardButton(text="🔔 Уведомления", callback_data="toggle_notify")
export_search_button = InlineKeyboardButton(text="📤 Экспорт", callback_data="export_search")
delete_search_button = InlineKeyboardButton(text="🗑️ Удалить", callback_data="delete_search")
compare_search_button = InlineKeyboardButton(text="🔄 Сравнить", callback_data="compare_by_model")
select_compare_button = InlineKeyboardButton(text="Выбрать для сравнения", callback_data="select_compare")
export_json_button = InlineKeyboardButton(text="JSON", callback_data="export_json")
export_csv_button = InlineKeyboardButton(text="CSV", callback_data="export_csv")
export_excel_button = InlineKeyboardButton(text="Excel", callback_data="export_excel")

no_action_button = InlineKeyboardButton(text="·", callback_data="no_action")

# Функции для создания динамических кнопок
def brand_button(brand: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=brand,
        callback_data=f"brand_{brand}"
    )

def region_button(region: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=region,
        callback_data=f"region_{region}"
    )

def city_button(city: str, city_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=city,
        callback_data=f"city_{city_id}"
    )

def radius_button(text: str, radius: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=f"radius_{radius}"
    )

def navigation_button(text: str, page: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=f"page_{page}"
    )

def next_ad_button(index: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="➡️ Следующее объявление",
        callback_data=f"next_ad_{index}"
    )

def search_action_button(search_id: str, action: str) -> InlineKeyboardButton:
    """Создает кнопку действия для конкретного поиска"""
    actions = {
        "view": ("🔍 Просмотреть", "view_search"),
        "toggle": ("🔔 Уведомления", "toggle_notify"),
        "export": ("📤 Экспорт", "export_search"),
        "delete": ("🗑️ Удалить", "delete_search"),
        "compare": ("🔄 Сравнить", "compare_by_model")
    }
    text, prefix = actions[action]
    return InlineKeyboardButton(
        text=text,
        callback_data=f"{prefix}:{search_id}"
    )