from pydantic import BaseModel

class DromItem(BaseModel):
    title: str
    price: int
    year: int
    mileage: int
    engine_volume: float
    engine_power: int
    transmission: str
    body_type: str
    link: str
    city: str
