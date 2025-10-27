"""
Instagram Auto Post Tool V3 - Мультиаккаунтная система с AI-планированием
"""
from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_cors import CORS
import os
import secrets
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные окружения
load_dotenv()

# Импортируем модули
from config import *
from modules.account_manager import account_manager
from modules.post_manager import post_manager
from modules.scheduler import post_scheduler
from modules.ai_planner import AIPlanner
from modules.content_generator import ContentGenerator
from background_publisher import background_publisher
from utils.logger import log_info, log_success, log_error, get_logs

# Создаем Flask приложение
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# Инициализируем AI модули
gemini_api_key = os.getenv('GEMINI_API_KEY')
kling_api_key = os.getenv('KLING_API_KEY')

ai_planner = AIPlanner(gemini_api_key) if gemini_api_key else None
content_generator = ContentGenerator(gemini_api_key) if gemini_api_key else None

# Видео генератор
from modules.video_generator import VideoGenerator
video_generator = VideoGenerator(kling_api_key) if kling_api_key else None

# ==================== STARTUP ====================

def startup():
    """Выполняется при запуске приложения"""
    log_info("=" * 50)
    log_info("🚀 Запуск Instagram Auto Post Tool V3")
    log_info("=" * 50)
    
    # Автологин всех аккаунтов
    log_info("🔐 Автологин аккаунтов...")
    account_manager.auto_login_all()
    
    # Запускаем фоновый публикатор
    log_info("📅 Запуск фонового публикатора...")
    background_publisher.start()
    
    # Проверяем запланированные посты
    from modules.post_manager import post_manager
    scheduled_count = len(post_manager.get_scheduled_posts())
    if scheduled_count > 0:
        log_info(f"📋 Найдено {scheduled_count} запланированных постов")
    else:
        log_info("📋 Нет запланированных постов")
    
    log_success("✅ Приложение успешно запущено и готово к работе!")

# ==================== ACCOUNT MANAGEMENT ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Получить список всех аккаунтов"""
    accounts = account_manager.get_all_accounts()
    
    # Убираем зашифрованные пароли из ответа
    safe_accounts = []
    for acc in accounts:
        safe_acc = acc.copy()
        safe_acc.pop('password', None)
        safe_accounts.append(safe_acc)
    
    return jsonify({'success': True, 'accounts': safe_accounts})

@app.route('/api/accounts', methods=['POST'])
def create_account():
    """Создать новый аккаунт"""
    data = request.json
    
    username = data.get('username')
    password = data.get('password')
    
    # Дефолтные значения - настройки через AI-планировщик
    theme = data.get('theme', '')
    language = data.get('language', 'русский')
    posts_per_day = data.get('posts_per_day', 5)
    format = data.get('format', 'photo')
    
    if not username or not password:
        return jsonify({'success': False, 'error': 'Требуются username и password'}), 400
    
    try:
        account = account_manager.create_account(
            username=username,
            password=password,
            theme=theme,
            language=language,
            posts_per_day=posts_per_day,
            format=format
        )
        
        # Убираем пароль
        account_safe = account.copy()
        account_safe.pop('password', None)
        
        return jsonify({'success': True, 'account': account_safe})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/accounts/<account_id>/login', methods=['POST'])
def login_account(account_id):
    """Войти в аккаунт"""
    try:
        success = account_manager.login_account(account_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Успешный вход'})
        else:
            return jsonify({'success': False, 'error': 'Не удалось войти'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/accounts/<account_id>/logout', methods=['POST'])
def logout_account(account_id):
    """Выйти из аккаунта"""
    try:
        account_manager.logout_account(account_id)
        return jsonify({'success': True, 'message': 'Выход выполнен'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/accounts/<account_id>', methods=['DELETE'])
def delete_account(account_id):
    """Удалить аккаунт"""
    try:
        account_manager.delete_account(account_id)
        return jsonify({'success': True, 'message': 'Аккаунт удален'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== AI PLANNER ====================

@app.route('/api/ai/create-plan', methods=['POST'])
def create_plan():
    """Создать план публикаций через AI"""
    if not ai_planner:
        return jsonify({'success': False, 'error': 'Gemini API не настроен'}), 400
    
    data = request.json
    instruction = data.get('instruction', '')
    
    if not instruction:
        return jsonify({'success': False, 'error': 'Требуется инструкция'}), 400
    
    try:
        # Получаем активные аккаунты
        active_accounts = account_manager.get_active_accounts()
        
        if not active_accounts:
            return jsonify({'success': False, 'error': 'Нет активных аккаунтов'}), 400
        
        # Создаем план
        plan = ai_planner.create_plan(instruction, active_accounts)
        
        return jsonify({'success': True, 'plan': plan})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/ai/generate-posts', methods=['POST'])
def generate_posts():
    """Генерировать посты по плану"""
    if not content_generator:
        return jsonify({'success': False, 'error': 'Gemini API не настроен'}), 400
    
    data = request.json
    plan = data.get('plan')
    
    if not plan:
        return jsonify({'success': False, 'error': 'Требуется план'}), 400
    
    try:
        # Генерируем посты
        posts = content_generator.generate_posts_from_plan(plan)
        
        # Планируем время публикации для каждого аккаунта
        for account_plan in plan['accounts']:
            account_id = account_plan['account_id']
            posts_per_day = account_plan['posts_per_day']
            
            # Получаем посты этого аккаунта
            account_post_ids = [p['id'] for p in posts if p['account_id'] == account_id]
            
            # Планируем
            post_scheduler.schedule_posts_for_account(
                account_id,
                account_post_ids,
                posts_per_day
            )
        
        return jsonify({
            'success': True,
            'message': f'Создано и запланировано {len(posts)} постов',
            'posts_count': len(posts)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== POST MANAGEMENT ====================

@app.route('/api/posts', methods=['GET'])
def get_posts():
    """Получить все посты"""
    status = request.args.get('status')
    account_id = request.args.get('account_id')
    
    try:
        if account_id:
            posts = post_manager.get_posts_by_account(account_id, status)
        else:
            posts = post_manager.get_all_posts(status)
        
        return jsonify({'success': True, 'posts': posts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/posts/<post_id>', methods=['GET'])
def get_post(post_id):
    """Получить пост по ID"""
    try:
        post = post_manager.get_post(post_id)
        
        if not post:
            return jsonify({'success': False, 'error': 'Пост не найден'}), 404
        
        return jsonify({'success': True, 'post': post})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/posts/<post_id>', methods=['PUT'])
def update_post(post_id):
    """Обновить пост"""
    data = request.json
    
    try:
        post = post_manager.get_post(post_id)
        
        if not post:
            return jsonify({'success': False, 'error': 'Пост не найден'}), 404
        
        # Можно редактировать только черновики и запланированные посты
        if post['status'] not in [POST_STATUS['DRAFT'], POST_STATUS['SCHEDULED']]:
            return jsonify({'success': False, 'error': 'Можно редактировать только черновики и запланированные посты'}), 403
        
        # Обновляем
        updated_post = post_manager.update_post(post_id, data)
        
        # Если статус стал scheduled или время изменилось - обновляем scheduler
        if updated_post['status'] == POST_STATUS['SCHEDULED'] and updated_post.get('scheduled_time'):
            post_scheduler.schedule_post(
                post_id,
                updated_post['account_id'],
                updated_post['scheduled_time']
            )
            log_info(f"📅 Обновлено время публикации поста {post_id}: {updated_post['scheduled_time']}")
        elif updated_post['status'] == POST_STATUS['DRAFT']:
            # Если вернули в черновики - убираем из scheduler
            post_scheduler.remove_from_schedule(post_id)
        
        return jsonify({'success': True, 'post': updated_post})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/posts/<post_id>', methods=['DELETE'])
def delete_post(post_id):
    """Удалить пост"""
    try:
        post_manager.delete_post(post_id)
        post_scheduler.remove_from_schedule(post_id)
        
        return jsonify({'success': True, 'message': 'Пост удален'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/posts/<post_id>/publish-now', methods=['POST'])
def publish_now(post_id):
    """Опубликовать пост немедленно (работает для любого статуса: draft, scheduled)"""
    try:
        post = post_manager.get_post(post_id)
        
        if not post:
            return jsonify({'success': False, 'error': 'Пост не найден'}), 404
        
        # Проверяем что пост не опубликован уже
        if post['status'] == POST_STATUS['PUBLISHED']:
            return jsonify({'success': False, 'error': 'Пост уже опубликован'}), 400
        
        log_info(f"📤 Ручная публикация поста {post_id} (статус: {post['status']})")
        
        # Публикуем через фоновый публикатор
        background_publisher._publish_post(post)
        
        return jsonify({'success': True, 'message': 'Пост успешно опубликован!'})
    except Exception as e:
        log_error(f"❌ Ошибка ручной публикации поста {post_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/posts/<post_id>/regenerate-text', methods=['POST'])
def regenerate_text(post_id):
    """Перегенерировать текст поста"""
    if not content_generator:
        return jsonify({'success': False, 'error': 'Gemini API не настроен'}), 400
    
    data = request.json
    theme = data.get('theme', '')
    language = data.get('language', 'русский')
    keywords = data.get('keywords', [])
    
    try:
        new_text = content_generator.regenerate_text(post_id, theme, language, keywords)
        return jsonify({'success': True, 'text': new_text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/posts/<post_id>/regenerate-image', methods=['POST'])
def regenerate_image(post_id):
    """Перегенерировать изображение поста"""
    if not content_generator:
        return jsonify({'success': False, 'error': 'Gemini API не настроен'}), 400
    
    data = request.json
    prompt = data.get('prompt', '')
    
    try:
        new_image = content_generator.regenerate_image(post_id, prompt)
        return jsonify({'success': True, 'image': new_image})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== VIDEO GENERATION ====================

@app.route('/api/generate-video', methods=['POST'])
def generate_video():
    """Генерировать видео через Kling AI"""
    if not video_generator:
        return jsonify({'success': False, 'error': 'Kling AI API не настроен. Добавьте KLING_API_KEY в .env файл'}), 400
    
    data = request.json
    prompt = data.get('prompt', '')
    duration = data.get('duration', 5)
    aspect_ratio = data.get('aspect_ratio', '16:9')
    mode = data.get('mode', 'std')
    
    if not prompt:
        return jsonify({'success': False, 'error': 'Требуется промпт'}), 400
    
    try:
        result = video_generator.generate_video(
            prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            mode=mode
        )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/generate-video-from-image', methods=['POST'])
def generate_video_from_image():
    """Генерировать видео из изображения через Kling AI"""
    if not video_generator:
        return jsonify({'success': False, 'error': 'Kling AI API не настроен'}), 400
    
    data = request.json
    prompt = data.get('prompt', '')
    image_filename = data.get('image_filename', '')
    duration = data.get('duration', 5)
    mode = data.get('mode', 'std')
    
    if not prompt or not image_filename:
        return jsonify({'success': False, 'error': 'Требуется промпт и изображение'}), 400
    
    try:
        image_path = PHOTOS_DIR / image_filename
        
        if not image_path.exists():
            return jsonify({'success': False, 'error': 'Изображение не найдено'}), 404
        
        result = video_generator.generate_video_from_image(
            prompt=prompt,
            image_path=str(image_path),
            duration=duration,
            mode=mode
        )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/generate-video-prompt', methods=['POST'])
def generate_video_prompt():
    """Генерировать промпт для видео через Gemini"""
    if not gemini_api_key:
        return jsonify({'success': False, 'error': 'Gemini API не настроен'}), 400
    
    data = request.json
    topic = data.get('topic', '')
    
    if not topic:
        return jsonify({'success': False, 'error': 'Требуется тема'}), 400
    
    try:
        import google.generativeai as genai
        import time
        import re
        from utils.rate_limiter import gemini_rate_limiter
        
        genai.configure(api_key=gemini_api_key)
        
        prompt = f"""Ты - эксперт по созданию промптов для генерации видео. На основе следующей темы создай ДИНАМИЧЕСКИЙ промпт на английском языке для AI генератора видео.

ТЕМА: {topic}

ВАЖНО:
1. Сфокусируйся на ДВИЖЕНИИ и ДЕЙСТВИИ - опиши что происходит в кадре
2. Укажи движение камеры (camera pans, zooms, tracking shot, etc.) если уместно
3. Опиши динамическую сцену с действием, движением объектов, изменениями
4. НЕ включай текст в видео (no text overlay, no words)
5. Добавь детали: темп движения, освещение, настроение, стиль
6. Промпт должен быть 30-80 слов

ПРИМЕРЫ:
- Тема: "Закат на море" → "Cinematic sunset over ocean, waves gently rolling, camera slowly panning left, golden hour lighting, seagulls flying across frame, peaceful atmosphere, warm colors, smooth motion"
- Тема: "Городская жизнь" → "Busy city street time-lapse, people walking fast, cars moving, camera tracking forward, urban energy, evening lights turning on, dynamic movement, modern cityscape"

Верни ТОЛЬКО промпт на английском, без объяснений и комментариев."""
        
        # Вызов с повтором при ошибке квоты
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Используем rate limiter
                gemini_rate_limiter.wait_if_needed()
                
                log_info(f"🤖 Запрос к Gemini API для генерации видео-промпта (попытка {attempt + 1}/{max_retries})...")
                
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                response = model.generate_content(prompt)
                
                log_info(f"✅ Видео-промпт получен от Gemini API")
                
                return jsonify({
                    'success': True,
                    'prompt': response.text.strip()
                })
            except Exception as e:
                error_str = str(e)
                
                if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                    # Извлекаем время ожидания
                    match = re.search(r'retry in (\d+(?:\.\d+)?)', error_str, re.IGNORECASE)
                    retry_seconds = int(float(match.group(1))) + 1 if match else 30
                    
                    if attempt < max_retries - 1:
                        # Exponential backoff
                        backoff_multiplier = 2 ** attempt
                        wait_time = retry_seconds * backoff_multiplier + 5
                        
                        log_info(f"⏳ Достигнут лимит Gemini API. Ожидание {wait_time} секунд...")
                        time.sleep(wait_time)
                        continue
                    else:
                        log_error(f"❌ Превышен лимит запросов Gemini API после {max_retries} попыток.")
                        return jsonify({'success': False, 'error': 'Превышен лимит запросов Gemini API. Пожалуйста, подождите несколько минут (достигнут дневной лимит 50 запросов для бесплатного тарифа).'}), 429
                
                raise e
        
        return jsonify({'success': False, 'error': 'Не удалось сгенерировать промпт после нескольких попыток'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== MEDIA ====================

@app.route('/api/photos/<filename>')
def get_photo(filename):
    """Получить фото"""
    return send_from_directory(PHOTOS_DIR, filename)

@app.route('/api/videos/<filename>')
def get_video(filename):
    """Получить видео"""
    return send_from_directory(VIDEOS_DIR, filename)

@app.route('/api/media/photos', methods=['GET'])
def list_photos():
    """Получить список всех фото с метаданными"""
    try:
        files = []
        for file in PHOTOS_DIR.glob('*.jpg'):
            timestamp = file.stem
            files.append({
                'filename': file.name,
                'timestamp': timestamp,
                'size': file.stat().st_size
            })
        
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/media/videos', methods=['GET'])
def list_videos():
    """Получить список всех видео с метаданными"""
    try:
        files = []
        for file in VIDEOS_DIR.glob('*.mp4'):
            timestamp = file.stem
            files.append({
                'filename': file.name,
                'timestamp': timestamp,
                'size': file.stat().st_size
            })
        
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/media/photos/<filename>/metadata', methods=['GET'])
def get_photo_metadata(filename):
    """Получить метаданные фото"""
    try:
        import json
        metadata_file = PHOTOS_DIR / f"{Path(filename).stem}.json"
        
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return jsonify(metadata)
        else:
            return jsonify({'prompt': 'Метаданные не найдены'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/media/videos/<filename>/metadata', methods=['GET'])
def get_video_metadata(filename):
    """Получить метаданные видео"""
    try:
        import json
        metadata_file = VIDEOS_DIR / f"{Path(filename).stem}.json"
        
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return jsonify(metadata)
        else:
            return jsonify({'prompt': 'Метаданные не найдены'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ==================== LOGS ====================

@app.route('/api/logs', methods=['GET'])
def get_app_logs():
    """Получить логи приложения"""
    limit = request.args.get('limit', 100, type=int)
    
    try:
        logs = get_logs(limit)
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/publisher/status', methods=['GET'])
def get_publisher_status():
    """Получить статус фонового публикатора"""
    try:
        is_running = background_publisher.running
        scheduled_posts = post_manager.get_scheduled_posts()
        
        return jsonify({
            'success': True,
            'publisher_running': is_running,
            'scheduled_posts_count': len(scheduled_posts),
            'scheduled_posts': scheduled_posts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/gemini/stats', methods=['GET'])
def get_gemini_stats():
    """Получить статистику использования Gemini API"""
    try:
        from utils.rate_limiter import gemini_rate_limiter
        stats = gemini_rate_limiter.get_stats()
        
        return jsonify({
            'success': True,
            'stats': stats,
            'info': {
                'free_tier_limit': '50 запросов в день',
                'rate_limit': '2.5 секунды между запросами',
                'recommendation': 'Не генерируйте более 20-25 постов за раз'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ==================== FRONTEND ROUTES ====================

@app.route('/')
def index():
    """Главная страница - дашборд"""
    return render_template('dashboard.html')

@app.route('/accounts')
def accounts_page():
    """Страница управления аккаунтами"""
    return render_template('accounts.html')

@app.route('/create-plan')
def create_plan_page():
    """Страница AI-планировщика"""
    return render_template('create_plan.html')

@app.route('/posts')
def posts_page():
    """Страница постов"""
    return render_template('posts.html')

@app.route('/library')
def library_page():
    """Библиотека медиа"""
    return render_template('library.html')

@app.route('/settings')
def settings_page():
    """Настройки"""
    return render_template('settings.html')

@app.route('/logs')
def logs_page():
    """Логи"""
    return render_template('logs.html')

# ==================== MAIN ====================

if __name__ == '__main__':
    # Выполняем стартовые задачи
    startup()
    
    # Запускаем сервер
    app.run(debug=True, host='0.0.0.0', port=5000)
