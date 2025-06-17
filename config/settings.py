from aiogram.enums import ParseMode

class Settings:
    BOT_TOKEN = "7896860406:AAFlP6kux2NRzDmNmZ93FugEAB9xFpokpNU"
    ADMIN_IDS: list[int] = [5906501667]
    PARSE_MODE = ParseMode.HTML
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        # ... остальные user agents
    ]
    

settings = Settings()
