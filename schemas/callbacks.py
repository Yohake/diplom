from aiogram.filters.callback_data import CallbackData

class SearchPaginationCallback(CallbackData, prefix="search_page"):
    page: int

class DeleteCallback(CallbackData, prefix="delete"):
    search_id: str

class ToggleCallback(CallbackData, prefix="toggle"):
    search_id: str

class ExportCallback(CallbackData, prefix="export"):
    action: str  # "export" или "import"
