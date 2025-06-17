from pydantic import BaseModel

class Advertisement(BaseModel):
    title: str
    url: str
    price: str
    date: str

