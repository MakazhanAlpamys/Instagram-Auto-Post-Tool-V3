"""
Утилиты для работы с датой и временем
"""
from datetime import datetime
import re

def parse_iso_datetime(iso_string: str) -> datetime:
    """
    Парсит ISO datetime строку, включая формат JavaScript с .000Z
    и формат из HTML datetime-local input
    
    Args:
        iso_string: ISO строка (например, '2025-10-25T11:58:00.000Z', '2025-10-25T18:00', '2025-10-25T16:54:09.397434')
    
    Returns:
        datetime объект (локальное время)
    """
    if not iso_string:
        raise ValueError("ISO string is empty")
    
    # Убираем 'Z' в конце если есть
    if iso_string.endswith('Z'):
        iso_string = iso_string[:-1]
    
    # Убираем миллисекунды если формат .000
    iso_string = re.sub(r'\.\d{3}$', '', iso_string)
    
    # Пробуем разные форматы
    formats_to_try = [
        None,  # Пробуем fromisoformat
        '%Y-%m-%dT%H:%M',  # Формат из datetime-local input (БЕЗ секунд!)
        '%Y-%m-%dT%H:%M:%S',  # С секундами
        '%Y-%m-%dT%H:%M:%S.%f'  # С микросекундами
    ]
    
    for fmt in formats_to_try:
        try:
            if fmt is None:
                return datetime.fromisoformat(iso_string)
            else:
                return datetime.strptime(iso_string, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Не удалось распарсить время: {iso_string}")

