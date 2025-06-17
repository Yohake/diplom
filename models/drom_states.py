from aiogram.fsm.state import State, StatesGroup

class SearchState(StatesGroup):
    brand = State()
    region = State()
    radius = State()
    min_price = State()
    max_price = State()
    confirm = State()
    set_interval = State()
