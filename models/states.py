from aiogram.fsm.state import State, StatesGroup

class ParserState(StatesGroup):
    waiting_brand = State()
    waiting_region = State()
    waiting_radius = State()
    waiting_custom_region = State()
    choosing_city = State()
    waiting_min_price = State()
    waiting_max_price = State()
    viewing_results = State()
    export_searches = State()
    import_searches = State()
    waiting_for_city_selection = State()
    
class CompareState(StatesGroup):
    CHOOSE_BRAND = State()
    CHOOSE_MODEL = State()
    SHOW_RESULTS = State()
