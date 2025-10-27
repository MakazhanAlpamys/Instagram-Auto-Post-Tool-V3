"""
Глобальные настройки приложения
"""
from pathlib import Path

# Базовые пути
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
ACCOUNTS_DIR = DATA_DIR / 'accounts'
POSTS_DIR = DATA_DIR / 'posts'
MEDIA_DIR = DATA_DIR / 'media'
PHOTOS_DIR = MEDIA_DIR / 'photos'
VIDEOS_DIR = MEDIA_DIR / 'videos'
LOGS_DIR = DATA_DIR / 'logs'

# Подпапки для постов
DRAFTS_DIR = POSTS_DIR / 'drafts'
SCHEDULED_DIR = POSTS_DIR / 'scheduled'
PUBLISHED_DIR = POSTS_DIR / 'published'

# Файлы
SCHEDULER_FILE = DATA_DIR / 'scheduler.json'
APP_LOG_FILE = LOGS_DIR / 'app.log'

# Создаем все необходимые директории
DIRECTORIES = [
    DATA_DIR, ACCOUNTS_DIR, POSTS_DIR, MEDIA_DIR,
    PHOTOS_DIR, VIDEOS_DIR, LOGS_DIR,
    DRAFTS_DIR, SCHEDULED_DIR, PUBLISHED_DIR
]

for directory in DIRECTORIES:
    directory.mkdir(parents=True, exist_ok=True)

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    "auto_prompt": True,  # Всегда включен
    "media_per_post": 1,  # Только 1 фото/видео
    "default_model": "flux",  # flux, flux-realism, flux-anime, flux-3d
    "default_size": "square",  # square, portrait, landscape, story
    "min_post_interval": 30,  # Минимум 30 минут между постами
    "max_posts_per_day": 10,  # Максимум 10 постов в день
    "batch_size": 2,  # Генерировать по 2 поста за раз (оптимизация для Gemini API)
    "default_posts_per_day": 3,  # По умолчанию 3 поста в день (оптимизация для Gemini API)
}

# Размеры изображений
IMAGE_SIZES = {
    "square": {"width": 1080, "height": 1080},
    "portrait": {"width": 1080, "height": 1350},
    "landscape": {"width": 1080, "height": 608},
    "story": {"width": 1080, "height": 1920}
}

# Модели Pollinations
AVAILABLE_MODELS = [
    "flux",
    "flux-realism",
    "flux-anime",
    "flux-3d"
]

# Статусы аккаунтов
ACCOUNT_STATUS = {
    "ACTIVE": "active",
    "INACTIVE": "inactive",
    "ERROR": "error",
    "LOGGING_IN": "logging_in"
}

# Статусы постов
POST_STATUS = {
    "DRAFT": "draft",
    "SCHEDULED": "scheduled",
    "PUBLISHED": "published",
    "ERROR": "error"
}

# Форматы постов
POST_FORMATS = ["photo", "video"]

# Языки
AVAILABLE_LANGUAGES = [
    "русский",
    "казахский",
    "английский",
    "китайский",
    "немецкий",
    "французский",
    "испанский"
]

# Часы постинга (с 08:00 до 23:00)
POSTING_START_HOUR = 8
POSTING_END_HOUR = 23
