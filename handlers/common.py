import json
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import logging
from aiogram import Router, types, F, Bot
from models.states import CompareState
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config.settings import settings
from aiogram.filters import StateFilter
from services.search_service import clean_price
from aiogram.types import CallbackQuery, Message
from keyboards.builders import (
    main_menu_keyboard, about_keyboard, back_to_menu,
    platform_choice_keyboard, export_import_keyboard,
    back_to_menu_keyboard, create_search_keyboard,
    build_comparison_keyboard, build_export_options_keyboard,
    build_results_keyboard, build_main_searches_keyboard,
    build_search_details_keyboard, back_button,
    get_brands_keyboard, models_keyboard, platforms_keyboard
)
from schemas.callbacks import (
    SearchPaginationCallback,
    DeleteCallback,
    ToggleCallback,
    ExportCallback
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from services.search_service import (
    get_user_searches, 
    delete_search_by_id as remove_search_by_id,
    toggle_notifications, 
    load_searches,
    import_user_searches,
    cleanup_old_searches, 
    get_search_info,
    delete_search_by_id,
    get_search_results,
    get_ads_by_model,
    get_unique_brands_and_models,
    compare_prices_by_model
)

from services.export_service import export_user_searches  
from models.states import ParserState

import aiofiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

router = Router()

def save_chat_id(chat_id: int):
    storage_path = Path("storage")
    storage_path.mkdir(exist_ok=True)

    chat_ids_file = storage_path / "chat_ids.json"

    try:
        if chat_ids_file.exists():
            with open(chat_ids_file, 'r') as f:
                chat_ids = json.load(f)
        else:
            chat_ids = []
    except (json.JSONDecodeError, Exception):
        chat_ids = []

    if chat_id not in chat_ids:
        chat_ids.append(chat_id)
        with open(chat_ids_file, 'w') as f:
            json.dump(chat_ids, f, indent=4)

@router.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    searches = load_searches()
    total_users = len(searches)
    active_searches = sum(len(platform_searches) for user in searches.values() for platform_searches in user.values())
    inactive_searches = cleanup_old_searches(days=30)  # Автоматически чистим старые поиски

    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"🔍 Активных поисков: {active_searches}\n"
        f"🗑️ Удалено неактивных: {inactive_searches}\n"
        f"⏳ Последняя проверка: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

@router.message(Command("admin_broadcast"))
async def admin_broadcast(message: types.Message, bot: Bot):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    if not message.reply_to_message:
        await message.answer("Ответьте этим командой на сообщение для рассылки")
        return

    searches = load_searches()
    users = list(searches.keys())
    success = 0
    failed = 0

    await message.answer(f"Начинаю рассылку для {len(users)} пользователей...")

    for user_id in users:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.message_id
            )
            success += 1
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка рассылки для {user_id}: {e}")
        await asyncio.sleep(0.1)

    await message.answer(
        f"✅ Рассылка завершена\n"
        f"Успешно: {success}\n"
        f"Не удалось: {failed}"
    )

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    save_chat_id(message.chat.id)
    await message.answer(
        "🚗 <b>AutoParserBot - поиск автообъявлений</b>\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode=settings.PARSE_MODE
    )

# Обработчик кнопки "Назад" в результатах
@router.callback_query(F.data.startswith("prev_result:"))
async def prev_result_handler(callback: types.CallbackQuery):
    try:
        _, search_id, index = callback.data.split(":")
        index = int(index)
        results = get_search_results(callback.from_user.id, search_id)
        
        if index >= 0 and index < len(results):
            await show_advertisement(callback, results[index], search_id, index, len(results))
        else:
            await callback.answer("Это первое объявление", show_alert=True)
    except Exception as e:
        logger.error(f"Error in prev_result_handler: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

# Обработчик кнопки "Вперед" в результатах
@router.callback_query(F.data.startswith("next_result:"))
async def next_result_handler(callback: types.CallbackQuery):
    try:
        _, search_id, index = callback.data.split(":")
        index = int(index)
        results = get_search_results(callback.from_user.id, search_id)
        
        if index < len(results):
            await show_advertisement(callback, results[index], search_id, index, len(results))
        else:
            await callback.answer("Это последнее объявление", show_alert=True)
    except Exception as e:
        logger.error(f"Error in next_result_handler: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "my_searches")
async def my_searches_callback(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        keyboard = build_main_searches_keyboard(user_id)  # Убедитесь, что эта функция правильно возвращает клавиатуру
        
        # Отправляем сообщение с клавиатурой
        await callback.message.edit_text(
            "🔍 <b>Мои сохранённые поиски</b>\n\n"
            "Выберите поиск для просмотра или управления:",
            reply_markup=keyboard,
            parse_mode=settings.PARSE_MODE  # Проверьте, что settings.PARSE_MODE корректно задан
        )
        
        await callback.answer()  # Отправка ответа для предотвращения загрузки сообщения
    except Exception as e:
        logger.error(f"Error in my_searches_callback: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("view_search:"))
async def view_search_handler(callback: types.CallbackQuery):
    search_id = callback.data.split(":")[1]
    keyboard = build_search_details_keyboard(search_id)

    search = get_search_info(callback.from_user.id, search_id)
    if not search:
        await callback.answer("Поиск не найден", show_alert=True)
        return

    params = search['params']
    platform = params.get('platform', 'Не указано')  # Добавлена проверка
    await callback.message.edit_text(
        f"🏷️ <b>Платформа:</b> {platform}\n"
        f"🏎️ <b>Марка:</b> {params.get('brand', 'Не указано')}\n"
        f"📍 <b>Регион:</b> {params.get('region', 'Не указано')}\n"
        f"💰 <b>Цена:</b> {params.get('min_price', 'Не указана')} - {params.get('max_price', 'Не указана')}\n"
        f"🔔 <b>Уведомления:</b> {'Вкл' if search['notifications'] else 'Выкл'}\n"
        f"📅 <b>Создан:</b> {datetime.fromisoformat(search['created_at']).strftime('%d.%m.%Y')}",
        reply_markup=keyboard,
        parse_mode=settings.PARSE_MODE
    )
    await callback.answer()

@router.callback_query(F.data.startswith("show_results:"))
async def show_results_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        search_id = callback.data.split(":")[1]
        results = get_search_results(callback.from_user.id, search_id)
        
        if not results:
            await callback.answer("Нет результатов для отображения", show_alert=True)
            return
        
        # Показываем первое объявление
        await show_advertisement(callback, results[0], search_id, 0, len(results))
        
    except Exception as e:
        logger.error(f"Error in show_results_handler: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

# Обработчик кнопки "Экспорт"
@router.callback_query(F.data.startswith("export_search:"))
async def export_search_handler(callback: types.CallbackQuery):
    search_id = callback.data.split(":")[1]
    keyboard = build_export_options_keyboard(search_id)
    
    await callback.message.edit_text(
        "📤 Выберите формат экспорта:",
        reply_markup=keyboard
    )
    await callback.answer()

# Обработчик кнопки "Удалить"
@router.callback_query(F.data.startswith("delete_search:"))
async def delete_search_handler(callback: types.CallbackQuery):
    try:
        search_id = callback.data.split(":")[1]
        if delete_search_by_id(callback.from_user.id, search_id):
            await callback.answer("Поиск успешно удалён", show_alert=False)
            # Возвращаемся к списку поисков
            await my_searches_callback(callback)
        else:
            await callback.answer("Не удалось удалить поиск", show_alert=True)
    except Exception as e:
        logger.error(f"Error in delete_search_handler: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

# Вспомогательная функция для показа объявлений
async def show_advertisement(
    callback: types.CallbackQuery,
    ad: dict,
    search_id: str,
    current_index: int,
    total_results: int
):
    keyboard = build_results_keyboard(search_id, current_index, total_results)
    
    text = (
        f"🚗 <b>{ad.get('title', 'Без названия')}</b>\n"
        f"💰 Цена: {ad.get('price', 'Не указана')}\n"
        f"📍 Адрес: {ad.get('address', 'Не указан')}\n"
        f"📅 Дата: {ad.get('date', 'Не указана')}\n"
        f"🔗 <a href='{ad.get('url', '#')}'>Ссылка на объявление</a>"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(SearchPaginationCallback.filter())
async def paginate_searches_callback(callback: types.CallbackQuery, callback_data: SearchPaginationCallback):
    user_id = str(callback.from_user.id)
    data = get_user_searches(user_id)

    all_searches = []
    for platform, searches in data.items():
        for search in searches:
            all_searches.append((platform, search))

    if not all_searches:
        await callback.answer("У вас нет активных поисков.", show_alert=True)
        return

    page = callback_data.page
    page = max(0, min(page, len(all_searches) - 1))  # ограничиваем страницу

    platform, search = all_searches[page]
    params = search['params']
    last_check = search.get('last_check', 'Никогда')

    keyboard = create_search_keyboard(search, current_page=page, total_pages=len(all_searches))

    text = (
        f"📑 <b>Ваши сохранённые поиски:</b>\n\n"
        f"<b>{platform.upper()}</b>\n"
        f"🚗 Марка: {params['brand']}\n"
        f"📍 Регион: {params['region']}\n"
        f"💰 Цена: {params['min_price']} - {params['max_price']}\n"
        f"⏳ Последняя проверка: {last_check}"
    )

    # Редактируем сообщение с новым поиском
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(DeleteCallback.filter())
async def delete_search_handler(
    callback: types.CallbackQuery,
    callback_data: DeleteCallback
):
    try:
        user_id = str(callback.from_user.id)
        search_id = callback_data.search_id

        # Удаляем поиск из базы данных
        remove_search_by_id(user_id, search_id)

        # Успешное уведомление
        await callback.answer("Поиск успешно удалён!", show_alert=False)

        # Обновляем список поисков (если он сейчас отображается)
        await my_searches_callback(callback)

    except Exception as e:
        logger.error(f"Ошибка при удалении поиска: {str(e)}", exc_info=True)
        await callback.answer(
            "⚠️ Произошла ошибка при удалении поиска",
            show_alert=True
        )
        
@router.callback_query(F.data == "manage_notifications")
async def manage_notifications_handler(callback: types.CallbackQuery):
    try:
        # Get user_id from callback
        user_id = str(callback.from_user.id)
        
        # Get all searches for this user
        user_searches = get_user_searches(user_id)
        
        if not user_searches:
            await callback.answer("У вас нет активных поисков.", show_alert=True)
            return

        # Create a keyboard to show all searches with toggle buttons
        builder = InlineKeyboardBuilder()
        
        for platform, searches in user_searches.items():
            for search in searches:
                search_id = search['id']
                status = "🔔" if search.get('notifications', True) else "🔕"
                builder.add(InlineKeyboardButton(
                    text=f"{status} {platform}: {search['params']['brand']}",
                    callback_data=f"toggle_{search_id}"
                ))
        
        builder.adjust(1)
        # Add back button using your existing keyboard builder function
        builder.row(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_menu"
        ))
        
        await callback.message.edit_text(
            "🔔 <b>Управление уведомлениями</b>\n\n"
            "Выберите поиск для переключения уведомлений:",
            reply_markup=builder.as_markup(),
            parse_mode=settings.PARSE_MODE
        )
        
    except Exception as e:
        logger.error(f"Error in manage_notifications: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error in manage_notifications: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("toggle_"))
async def handle_toggle_notification(callback: types.CallbackQuery):
    try:
        search_id = callback.data.split("_")[1]
        user_id = callback.from_user.id
        
        # Use the existing toggle_notifications function
        new_status = toggle_notifications(user_id, search_id)
        
        await callback.answer(
            f"Уведомления {'включены' if new_status else 'отключены'}",
            show_alert=False
        )
        
        # Refresh the management interface
        await manage_notifications_handler(callback)
        
    except Exception as e:
        logger.error(f"Error toggling notification: {e}")
        await callback.answer("Ошибка при переключении уведомления", show_alert=True)

# Обработчик для переключения состояния уведомлений
@router.callback_query(ToggleCallback.filter())
async def toggle_notification_handler(
    callback: types.CallbackQuery,
    callback_data: ToggleCallback
):
    try:
        user_id = callback.from_user.id  # Get user_id from callback
        search_id = callback_data.search_id  # Get search_id from callback_data

        # Переключаем статус уведомлений и получаем новый статус
        new_status = toggle_notifications(user_id, search_id)

        # Обновляем текст кнопки в клавиатуре
        keyboard = callback.message.reply_markup
        for row in keyboard.inline_keyboard:
            for button in row:
                if button.callback_data == callback.data:
                    button.text = "🔕 Отключить" if new_status else "🔔 Включить"

        # Обновляем сообщение
        await callback.message.edit_reply_markup(reply_markup=keyboard)

        # Краткое уведомление для пользователя
        notification_text = (
            "🔔 Уведомления включены"
            if new_status
            else "🔕 Уведомления отключены"
        )
        await callback.answer(notification_text, show_alert=False)

    except Exception as e:
        logger.error(f"Error toggling notifications: {str(e)}", exc_info=True)
        await callback.answer(
            "⚠️ Произошла ошибка при изменении настроек уведомлений",
            show_alert=True
        )

@router.callback_query(ExportCallback.filter())
async def handle_export_import(callback: types.CallbackQuery, callback_data: ExportCallback, state: FSMContext):
    action = callback_data.action

    if action == "export":
        await state.set_state(ParserState.export_searches)
        await callback.message.answer("Отправьте мне название файла для экспорта (без расширения):")
    elif action == "import":
        await state.set_state(ParserState.import_searches)
        await callback.message.answer("Отправьте мне файл с сохранёнными поисками:")

@router.message(F.text, StateFilter(ParserState.export_searches))
async def process_export_searches(message: types.Message, state: FSMContext):
    filename = message.text.strip()
    if not filename:
        await message.answer("Название файла не может быть пустым")
        return

    try:
        file_path = export_user_searches(message.from_user.id, filename)
        await message.answer_document(
            document=types.FSInputFile(file_path),
            caption="Ваши поиски успешно экспортированы"
        )

    except Exception as e:
        await message.answer(f"Ошибка при экспорте: {str(e)}")

    await state.clear()

@router.callback_query(F.data.startswith("export_json:"))
async def export_json_handler(callback: types.CallbackQuery):
    try:
        search_id = callback.data.split(":")[1]
        user_id = callback.from_user.id
        file_path = export_user_searches(user_id, f"search_{search_id}", format="json")
        
        await callback.message.answer_document(
            document=types.FSInputFile(file_path),
            caption="Ваши поиски экспортированы в JSON"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in export_json_handler: {e}")
        await callback.answer("Ошибка при экспорте в JSON", show_alert=True)

@router.callback_query(F.data.startswith("export_csv:"))
async def export_csv_handler(callback: types.CallbackQuery):
    try:
        search_id = callback.data.split(":")[1]
        user_id = callback.from_user.id
        file_path = export_user_searches(user_id, f"search_{search_id}", format="csv")
        
        await callback.message.answer_document(
            document=types.FSInputFile(file_path),
            caption="Ваши поиски экспортированы в CSV"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in export_csv_handler: {e}")
        await callback.answer("Ошибка при экспорте в CSV", show_alert=True)

@router.callback_query(F.data.startswith("export_excel:"))
async def export_excel_handler(callback: types.CallbackQuery):
    try:
        search_id = callback.data.split(":")[1]
        user_id = callback.from_user.id
        file_path = export_user_searches(user_id, f"search_{search_id}", format="xlsx", search_id=search_id)

        await callback.message.answer_document(
            document=types.FSInputFile(file_path),
            caption="Ваши поиски экспортированы в Excel (XLSX)"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in export_excel_handler: {e}")
        await callback.answer("Ошибка при экспорте в Excel", show_alert=True)


@router.message(F.document, StateFilter(ParserState.import_searches))
async def process_import_searches(message: types.Message, state: FSMContext, bot: Bot):
    try:
        file = await bot.download(
            message.document,
            destination=f"storage/temp_{message.from_user.id}.json"
        )

        async with aiofiles.open(file, mode='r') as f:
            content = await f.read()
            searches = json.loads(content)

        import_user_searches(message.from_user.id, searches)
        await message.answer("Ваши поиски успешно импортированы!")
    except Exception as e:
        await message.answer(f"Ошибка при импорте: {str(e)}")
    finally:
        file.unlink(missing_ok=True)
        await state.clear()

# @router.callback_query(F.data == "about")
#async def about_bot(callback: types.CallbackQuery):
#        await callback.message.edit_text("🔔 Уведомления включены." if result else "🔕 Уведомления отключены.")

@router.callback_query(F.data == "about")
async def about_bot(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ <b>О боте:</b>\n\n"
        "Этот бот помогает искать свежие объявления о продаже автомобилей на Avito, Drom и Auto.ru.\n\n"
        "Возможности:\n"
        "- Поиск по марке автомобиля\n"
        "- Фильтрация по цене и региону\n"
        "- Показ только свежих объявлений (до 24 часов)\n"
        "- Удобный просмотр результатов\n\n"
        "Для начала поиска нажмите кнопку 'Назад' и выберите площадку.",
        reply_markup=about_keyboard(),
        parse_mode=settings.PARSE_MODE
    )

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()  # Очищаем состояние
    await callback.message.edit_text(
        "🚗 <b>AutoParserBot - поиск автообъявлений</b>\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode=settings.PARSE_MODE
    )
    await callback.answer()


@router.callback_query(F.data == "author")
async def about_author(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👨‍💻 <b>Автор проекта:</b>\n\n"
        "Если у вас есть вопросы или предложения по улучшению бота, "
        "пишите мне: <a href='https://t.me/yohake'>автор</a>\n\n"
        "Бот разработан с использованием:\n"
        "- Python 3.11\n"
        "- Aiogram 3.x\n"
        "- aiohttp\n"
        "- BeautifulSoup",
        reply_markup=back_to_menu_keyboard(),
        parse_mode=settings.PARSE_MODE,
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "avito_search")
async def start_avito_search(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🛒 <b>Вы выбрали поиск на Avito</b>\n\n"
        "Нажмите кнопку <b>🔍 Начать поиск</b>, чтобы перейти к выбору параметров.\n"
        "Или вернитесь к выбору площадки, если передумали.",
        reply_markup=platform_choice_keyboard("avito"),
        parse_mode=settings.PARSE_MODE
    )

@router.callback_query(F.data == "drom_search")
async def start_drom_search(callback: types.CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} начал поиск на Drom")
    try:
        await callback.message.edit_text(
            "🚗 <b>Вы выбрали поиск на Drom</b>\n\n"
            "Нажмите кнопку <b>🔍 Начать поиск</b>, чтобы перейти к выбору параметров.\n"
            "Или вернитесь к выбору площадки, если передумали.\n\n",
            reply_markup=platform_choice_keyboard("drom"),
            parse_mode=settings.PARSE_MODE
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса на поиск на Drom: {e}")
        await callback.answer("Произошла ошибка. Попробуйте позже.")

@router.callback_query(F.data == "autoru_search")
async def start_autoru_search(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🚘 <b>Вы выбрали поиск на Auto.ru</b>\n\n"
        "Нажмите кнопку <b>🔍 Начать поиск</b>, чтобы перейти к выбору параметров.\n"
        "Или вернитесь к выбору площадки, если передумали.\n\n",
        reply_markup=platform_choice_keyboard("autoru"),
        parse_mode=settings.PARSE_MODE
    )

@router.callback_query(F.data == "back_to_platforms")
async def back_to_platforms(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🚗 <b>AutoParserBot - поиск автообъявлений</b>\n"
        "Выберите площадку для поиска:",
        reply_markup=main_menu_keyboard(),
        parse_mode=settings.PARSE_MODE
    )


@router.callback_query(F.data.startswith("compare_by_model:"))
async def start_compare_by_model(callback: CallbackQuery, state: FSMContext):
    """Запуск процесса сравнения по модели"""
    try:
        search_id = callback.data.split(":")[1]
        user_id = callback.from_user.id
        
        # Получаем информацию о поиске
        search = get_search_info(user_id, search_id)
        if not search:
            await callback.answer("Поиск не найден", show_alert=True)
            return
            
        # Извлекаем марку из параметров поиска
        brand = search['params'].get('brand')
        if not brand:
            await callback.answer("Марка не указана в поиске", show_alert=True)
            return
            
        # Получаем все марки и модели пользователя
        brands_models = get_unique_brands_and_models(user_id)
        
        if not brands_models:
            await callback.message.edit_text(
                "❌ У вас нет сохраненных объявлений для сравнения",
                reply_markup=back_to_menu_keyboard()
            )
            return
            
        # Проверяем, есть ли модели для выбранной марки
        if brand not in brands_models or not brands_models[brand]:
            await callback.answer(f"Нет моделей для марки {brand}", show_alert=True)
            return
            
        await state.update_data({
            'brands_models': brands_models,
            'selected_brand': brand,
            'search_id': search_id
        })
        
        await callback.message.edit_text(
            f"\U0001F4CB Выберите модель марки {brand}:",
            reply_markup=models_keyboard(brands_models[brand])
        )
        await state.set_state(CompareState.CHOOSE_MODEL)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in start_compare_by_model: {e}", exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("select_brand:"), CompareState.CHOOSE_BRAND)
async def select_brand(callback: CallbackQuery, state: FSMContext):
    """Обработка выбранной марки"""
    brand = callback.data.split(":")[1]
    data = await state.get_data()
    models = data['brands_models'].get(brand, [])
    
    if not models:
        await callback.answer("Нет моделей для этой марки")
        return
    
    builder = InlineKeyboardBuilder()
    for model in sorted(models):
        builder.add(InlineKeyboardButton(
            text=model,
            callback_data=f"select_model:{model}"
        ))
    builder.button(text="⬅️ Назад в меню", callback_data="back_to_menu")  
    builder.adjust(2)
    
    await callback.message.edit_text(
        f"🚗 Выберите модель для марки {brand}:",
        reply_markup=builder.as_markup()
    )
    await state.update_data(selected_brand=brand)
    await state.set_state(CompareState.CHOOSE_MODEL)

@router.callback_query(F.data.startswith("select_model:"), CompareState.CHOOSE_MODEL)
async def select_model(callback: CallbackQuery, state: FSMContext):
    """Обработка выбранной модели с красивым табличным выводом"""
    try:
        model = callback.data.split(":")[1]
        data = await state.get_data()
        brand = data['selected_brand']
        
        comparison = compare_prices_by_model(
            user_id=callback.from_user.id,
            brand=brand,
            model=model
        )
        
        if not comparison or not comparison.get('platforms'):
            await callback.message.edit_text(
                f"❌ Нет данных для сравнения по модели {brand} {model}",
                reply_markup=back_to_menu_keyboard()
            )
            return
        
        price_diff = comparison['max_price'] - comparison['min_price']

        # Вычисляем процентное изменение, если минимальная цена больше 0
        price_diff_percent = (price_diff / comparison['min_price']) * 100 if comparison['min_price'] > 0 else 0

        # Форматируем таблицу
        table = [
            ["Платформа", "Мин. цена", "Средняя", "Макс. цена", "Кол-во"],
            ["-----------", "-----------", "---------", "------------", "--------"]
        ]

        for platform in comparison['platforms']:
            table.append([
                platform['platform'].upper(),
                f"{int(platform['min_price']):,} ₽",
                f"{int(platform['avg_price']):,} ₽",
                f"{int(platform['max_price']):,} ₽",
                str(platform['count'])
            ])

        # Вычисляем максимальную ширину для каждого столбца
        col_widths = [max(len(str(cell)) for cell in col) for col in zip(*table)]

        # Формируем текст таблицы с выравниванием
        formatted_table = "\n".join(
            " | ".join(f"{str(cell):<{col_widths[i]}}" for i, cell in enumerate(row))
            for row in table
        )

        # Теперь formatted_table можно вставить в сообщение
        message_text = (
            f"🚗 <b>Сравнение цен для {brand.capitalize()} {model.capitalize()}</b>\n\n"
            f"<pre>{formatted_table}</pre>\n\n"
            f"📊 <b>Общая статистика:</b>\n"
            f"• Разброс цен: {int(comparison['min_price']):,} - {int(comparison['max_price']):,} ₽\n"
            f"• Разница: {int(price_diff):,} ₽ ({price_diff_percent:.1f}%)\n"
            f"• Всего объявлений: {comparison['total_ads']}"
        )

        # Создаем клавиатуру с кнопками для каждой платформы
        builder = InlineKeyboardBuilder()
        for platform in comparison['platforms']:
            builder.add(InlineKeyboardButton(
                text=f"🔍 {platform['platform'].upper()}",
                callback_data=f"show_ads:{brand}:{model}:{platform['platform']}"
            ))
        
        builder.add(InlineKeyboardButton(
            text="⬅️ Назад к моделям",
            callback_data=f"compare_by_model:{data.get('search_id', '')}"
        ))
        builder.adjust(1)
        
        await callback.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode=settings.PARSE_MODE
        )
        await state.set_state(CompareState.SHOW_RESULTS)
        
    except Exception as e:
        logger.error(f"Error in select_model: {e}", exc_info=True)
        await callback.message.edit_text(
            "❌ Произошла ошибка при сравнении цен",
            reply_markup=back_to_menu_keyboard()
        )

@router.callback_query(F.data.startswith("show_ads:"), CompareState.SHOW_RESULTS)
async def show_platform_ads(callback: CallbackQuery, state: FSMContext):
    """Красивый вывод объявлений с гиперссылками"""
    _, brand, model, platform = callback.data.split(":", 3)
    user_id = callback.from_user.id
    
    ads = get_ads_by_model(user_id, brand, model, platform)
    
    if not ads:
        await callback.answer("Нет объявлений для этой платформы")
        return
    
    message_text = f"🚘 <b>{brand.capitalize()} {model.capitalize()} на {platform.upper()}</b>\n\n"
    
    for idx, ad in enumerate(ads[:5], 1):
        price = f"{int(clean_price(ad.get('price', '0'))):,} ₽" if ad.get('price') else "Цена не указана"
        year = ad.get('year', 'г.в. не указан')
        url = ad.get('url', '#')
        
        message_text += (
            f"{idx}. <b>{price}</b> - {year}\n"
            f"<a href='{url}'>🔗 Ссылка на объявление</a>\n\n"
        )
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="⬅️ Назад к сравнению",
        callback_data=f"select_model:{model}"
    ))
    await state.set_state(CompareState.CHOOSE_MODEL)

    
    await callback.message.edit_text(
        message_text,
        reply_markup=builder.as_markup(),
        parse_mode=settings.PARSE_MODE,
        disable_web_page_preview=True
    )

@router.callback_query(F.data.startswith("compare:"))
async def compare_search_handler(callback: types.CallbackQuery):
    try:
        search_id = callback.data.split(":")[1]
        user_id = callback.from_user.id

        # Получаем результаты для сравнения (примерная логика)
        comparison = compare_prices_by_model(user_id, search_id)
        if not comparison:
            await callback.answer("Нет данных для сравнения.", show_alert=True)
            return

        # Формируем текст сравнения (пример)
        text = "🔎 Сравнение цен:\n\n"
        for item in comparison:
            text += (
                f"Платформа: {item['platform']}\n"
                f"Средняя цена: {item['avg_price']}\n"
                f"Объявлений: {item['count']}\n\n"
            )

        await callback.message.edit_text(
            text,
            reply_markup=back_to_menu_keyboard(),
            parse_mode=settings.PARSE_MODE
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in compare_search_handler: {e}")
        await callback.answer("Ошибка при сравнении", show_alert=True)

@router.callback_query(F.data.startswith("brands_page:"))
async def handle_brands_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    brands = data.get("brands", [])
    
    # Вычисляем общее количество страниц
    brands_per_page = 10  # Например, 10 брендов на страницу
    total_pages = (len(brands) + brands_per_page - 1) // brands_per_page
    
    # Получаем бренды для текущей страницы
    start = page * brands_per_page
    end = start + brands_per_page
    current_brands = brands[start:end]
    
    await callback.message.edit_reply_markup(
        reply_markup=get_brands_keyboard(current_brands, page, total_pages)
    )
    await callback.answer()