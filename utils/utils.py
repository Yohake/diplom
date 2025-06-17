from transliterate import translit

def normalize_city_name(city: str) -> str:
    """Универсальная нормализация названия города"""
    special_cases = {
        'ё': 'yo',
        'я': 'ya',
        'ю': 'yu',
        'э': 'e',
        'й': 'y',
        'ы': 'y'
    }
    
    city = city.lower().strip()
    
    for ru, en in special_cases.items():
        city = city.replace(ru, en)
    
    try:
        transliterated = translit(city, 'ru', reversed=True)
    except:
        transliterated = city
    
    normalized = (
        transliterated
        .replace(' ', '_')
        .replace("'", '')
        .replace('"', '')
        .replace(',', '')
        .replace('-', '_')
    )
    
    return normalized.replace('__', '_').strip('_')

