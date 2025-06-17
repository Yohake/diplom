from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from models.states import ParserState
from config.settings import settings
from keyboards.builders import next_ad_keyboard
from services.search_service import save_search
import logging

logger = logging.getLogger(__name__)

router = Router()

@router.message(Command("results"))
async def show_results(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if 'results' not in data:
        await message.answer("Нет результатов для отображения.")
        return

    ads = data['results']
    platform = data['platform']
    params = data.get('params', {})  # Добавляем параметры поиска
    
    # Сохраняем результаты в базу данных
    search_id, is_new = save_search(
        user_id=message.from_user.id,
        platform=platform,
        params=params,
        last_result_ids=[ad.get('id', str(i)) for i, ad in enumerate(ads)],
        last_results=ads
    )
    
    if is_new:
        await message.answer(f"🔍 Поиск сохранен с ID: {search_id}")
    else:
        await message.answer(f"🔍 Существующий поиск обновлен: {search_id}")

    current_ad_index = data.get('current_ad_index', 0)

    if current_ad_index >= len(ads):
        await message.answer("Нет больше объявлений.")
        return

    ad = ads[current_ad_index]
    await show_advertisement(message, ad, platform, current_ad_index + 1)
    await state.update_data(current_ad_index=current_ad_index + 1)

# Остальной код остается без изменений
async def show_advertisement(
    message: types.Message | types.CallbackQuery, 
    ad: object, 
    platform: str, 
    next_index: int,
    edit: bool = False
):
    text = (
        f"🚗 <b>{ad.get('title', 'Без названия')}</b>\n"
        f"💰 {'Цена' if not edit else '<b>Цена:</b>'} {ad.get('price', 'Не указана')}\n"
        f"📍 {'Местоположение' if not edit else '<b>Местоположение:</b>'} {ad.get('address', 'Не указано')}\n"
        f"🔗 {'Ссылка' if not edit else '<b>Ссылка:</b>'} <a href='{ad.get('url', '#')}'>Перейти к объявлению</a>\n"
        f"📅 {'Дата' if not edit else '<b>Дата:</b>'} {ad.get('date', 'Не указана')}"
    )
    
    keyboard = next_ad_keyboard(next_index)
    
    if isinstance(message, types.CallbackQuery):
        try:
            await message.message.edit_text(
                text,
                parse_mode=settings.PARSE_MODE,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            await message.answer("Произошла ошибка при обновлении объявления")
    else:
        await message.answer(
            text,
            parse_mode=settings.PARSE_MODE,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

@router.message(Command("next"))
async def show_next_ad(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != ParserState.viewing_results:
        return
    
    data = await state.get_data()
    results = data.get('results', [])
    current_index = data.get('current_ad_index', 0)
    
    if current_index >= len(results):
        await message.answer("🏁 Это были все объявления!")
        return
    
    ad = results[current_index]
    await show_advertisement(message, ad, data['platform'], current_index + 1, edit=True)
    await state.update_data(current_ad_index=current_index + 1)

@router.callback_query(F.data.startswith("next_ad_"))
async def handle_next_ad_callback(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state != ParserState.viewing_results:
        return
    
    next_index = int(callback.data.split('_')[2])
    data = await state.get_data()
    results = data.get('results', [])
    
    if next_index >= len(results):
        await callback.answer("🏁 Это были все объявления!")
        return
    
    ad = results[next_index]
    await show_advertisement(callback, ad, data['platform'], next_index + 1, edit=True)
    await state.update_data(current_ad_index=next_index + 1)
    await callback.answer()