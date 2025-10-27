"""
Фоновый публикатор - автоматическая публикация постов по расписанию
"""
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from modules.post_manager import post_manager
from modules.account_manager import account_manager
from modules.scheduler import post_scheduler
from utils.logger import log_info, log_success, log_error, log_post_published, log_post_error
from utils.datetime_helper import parse_iso_datetime
from config import POST_STATUS

class BackgroundPublisher:
    """Фоновый публикатор постов"""
    
    def __init__(self):
        self.running = False
        self.thread = None
    
    def start(self):
        """Запускает фоновый публикатор"""
        if self.running:
            log_info("Фоновый публикатор уже запущен")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        log_success("Фоновый публикатор запущен")
    
    def stop(self):
        """Останавливает фоновый публикатор"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        log_info("Фоновый публикатор остановлен")
    
    def _run(self):
        """Основной цикл публикатора"""
        log_info("🚀 Фоновый публикатор начал работу")
        log_info("⏰ Проверка запланированных постов каждые 30 секунд")
        
        while self.running:
            try:
                self._check_and_publish()
            except Exception as e:
                log_error(f"❌ Ошибка в фоновом публикаторе: {e}")
            
            # Проверяем каждые 30 секунд для более точной публикации
            time.sleep(30)
    
    def _check_and_publish(self):
        """Проверяет и публикует посты, время которых пришло"""
        now = datetime.now()
        
        # Получаем все запланированные посты
        scheduled_posts = post_manager.get_scheduled_posts()
        
        if not scheduled_posts:
            return  # Нет запланированных постов
        
        posts_to_publish = []
        posts_to_move_to_drafts = []
        
        log_info(f"🔍 Проверка {len(scheduled_posts)} запланированных постов...")
        
        for post in scheduled_posts:
            try:
                post_id = post.get('id')
                if not post.get('scheduled_time'):
                    log_info(f"⚠️ Пост {post_id} не имеет времени планирования, пропускаем")
                    continue
                
                # Парсим время с поддержкой JavaScript формата (.000Z)
                scheduled_time = parse_iso_datetime(post['scheduled_time'])
                time_diff = (now - scheduled_time).total_seconds()
                minutes_diff = time_diff / 60
                
                log_info(f"📅 Пост {post_id}: запланирован на {scheduled_time.strftime('%H:%M:%S')}, разница: {minutes_diff:.1f} мин")
                
                # Если пост сильно просрочен (больше 1 часа) - возвращаем в черновики ОДИН РАЗ
                if time_diff > 3600:  # 1 час
                    # Проверяем, не был ли уже перемещен
                    if post_id not in posts_to_move_to_drafts:
                        posts_to_move_to_drafts.append(post_id)
                        log_info(f"⚠️ Пост {post_id} просрочен на {minutes_diff:.0f} минут. Будет перемещен в черновики.")
                    continue
                
                # Если время пришло или немного прошло (публикуем!)
                if -120 <= time_diff <= 600:  # от -2 минут до +10 минут
                    log_info(f"✅ Пост {post_id} готов к публикации (разница: {minutes_diff:.1f} мин)")
                    posts_to_publish.append((post, scheduled_time))
                elif time_diff < -120:
                    # Слишком рано
                    log_info(f"⏰ Пост {post_id} будет опубликован через {-minutes_diff:.0f} минут")
                else:
                    # Прошло больше 10 минут, но меньше часа - тоже публикуем
                    log_info(f"⚠️ Пост {post_id} опоздал на {minutes_diff:.0f} минут, но публикуем")
                    posts_to_publish.append((post, scheduled_time))
                    
            except Exception as e:
                log_error(f"❌ Ошибка обработки поста {post.get('id')}: {e}")
        
        # Перемещаем просроченные посты в черновики
        for post_id in posts_to_move_to_drafts:
            try:
                log_info(f"🔄 Перемещение поста {post_id} в черновики...")
                
                # Получаем пост
                post = post_manager.get_post(post_id)
                if not post:
                    continue
                
                # Удаляем из scheduled
                post_manager._delete_post_file(post_id, POST_STATUS['SCHEDULED'])
                
                # Создаем в drafts с новыми данными
                post['status'] = POST_STATUS['DRAFT']
                post['scheduled_time'] = None
                post['error'] = 'Пропущена запланированная публикация (сервер был выключен)'
                post_manager._save_post(post)
                
                # Удаляем из расписания
                post_scheduler.remove_from_schedule(post_id)
                
                log_success(f"✅ Пост {post_id} перемещен в черновики")
            except Exception as e:
                log_error(f"❌ Ошибка перемещения поста {post_id}: {e}")
        
        # Публикуем посты
        if posts_to_publish:
            log_info(f"📋 Публикуем {len(posts_to_publish)} постов...")
            
            for post, scheduled_time in posts_to_publish:
                try:
                    post_id = post['id']
                    time_str = scheduled_time.strftime('%H:%M:%S %d.%m.%Y')
                    log_info(f"🚀 Публикация поста {post_id} (запланировано на {time_str})")
                    
                    self._publish_post(post)
                    
                    # Небольшая пауза между публикациями
                    time.sleep(5)
                    
                except Exception as e:
                    log_error(f"❌ Ошибка публикации поста {post.get('id')}: {e}")
        else:
            if len(scheduled_posts) > 0:
                log_info(f"⏳ Нет постов готовых к публикации. Ожидаем...")
    
    def _publish_post(self, post: Dict):
        """Публикует пост"""
        post_id = post['id']
        account_id = post['account_id']
        
        try:
            # Получаем аккаунт и клиент
            account = account_manager.get_account(account_id)
            if not account:
                raise Exception(f"Аккаунт {account_id} не найден")
            
            username = account['username']
            log_info(f"📱 Публикация от имени @{username}")
            
            client = account_manager.get_client(account_id)
            if not client:
                # Пытаемся переподключиться
                log_info(f"🔄 Клиент не найден, попытка войти в аккаунт @{username}...")
                success = account_manager.login_account(account_id)
                if not success:
                    raise Exception(f"Не удалось войти в аккаунт @{username}")
                
                client = account_manager.get_client(account_id)
                if not client:
                    raise Exception(f"Клиент для аккаунта @{username} не инициализирован")
            
            # Проверяем лимиты Instagram
            log_info(f"✓ Проверка лимитов публикации...")
            self._check_instagram_limits(account_id)
            
            # Публикуем
            caption = post.get('text', '')
            media_files = post.get('media', [])
            
            if not media_files:
                raise Exception("Нет медиафайлов для публикации")
            
            log_info(f"📁 Подготовка медиафайлов: {media_files}")
            
            # Формируем полные пути
            from config import PHOTOS_DIR, VIDEOS_DIR
            
            media_paths = []
            for filename in media_files:
                # Пробуем найти в photos или videos
                photo_path = PHOTOS_DIR / filename
                video_path = VIDEOS_DIR / filename
                
                if photo_path.exists():
                    media_paths.append(str(photo_path))
                    log_info(f"✓ Найдено фото: {filename}")
                elif video_path.exists():
                    media_paths.append(str(video_path))
                    log_info(f"✓ Найдено видео: {filename}")
                else:
                    raise Exception(f"Медиафайл не найден: {filename}")
            
            # Публикуем в зависимости от типа
            log_info(f"🚀 Загрузка в Instagram...")
            
            # ВАЖНО: Проверяем реальный тип файла, а не только format
            if post.get('format') == 'video' and len(media_paths) == 1:
                file_extension = Path(media_paths[0]).suffix.lower()
                
                # Проверяем, действительно ли это видео файл
                if file_extension in ['.mp4', '.mov', '.avi']:
                    log_info(f"📹 Загрузка видео (расширение: {file_extension})...")
                    media = client.video_upload(media_paths[0], caption)
                else:
                    # Если формат video, но файл НЕ видео - публикуем как фото
                    log_info(f"⚠️ ВНИМАНИЕ: Формат поста 'video', но файл {file_extension} - публикуем как ФОТО")
                    log_info(f"📸 Загрузка фото...")
                    media = client.photo_upload(media_paths[0], caption)
            elif len(media_paths) == 1:
                log_info(f"📸 Загрузка фото...")
                media = client.photo_upload(media_paths[0], caption)
            else:
                log_info(f"📸 Загрузка альбома ({len(media_paths)} файлов)...")
                media = client.album_upload(media_paths, caption)
            
            log_info(f"✅ Медиа загружено в Instagram (ID: {media.pk})")
            
            # Обновляем статус поста
            post_manager.publish_post(post_id)
            
            # Обновляем расписание
            post_scheduler.mark_as_published(post_id)
            
            log_post_published(post_id, username)
            log_success(f"🎉 Пост успешно опубликован от @{username}!")
            
        except Exception as e:
            error_msg = str(e)
            
            # Если ошибка "Слишком рано" - откладываем публикацию
            if "Слишком рано" in error_msg or "wait" in error_msg.lower():
                log_info(f"⏰ Пост {post_id} отложен: {error_msg}")
                log_info(f"🔄 Попытка публикации будет повторена через 30 секунд...")
                # НЕ помечаем как error, оставляем в scheduled
                return
            
            # Для других ошибок - помечаем как error
            post_manager.mark_post_error(post_id, error_msg)
            log_post_error(post_id, error_msg)
            log_error(f"💥 Не удалось опубликовать пост {post_id}: {error_msg}")
    
    def _check_instagram_limits(self, account_id: str):
        """Проверяет лимиты Instagram"""
        from config import DEFAULT_SETTINGS
        
        # Получаем посты за сегодня
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        published_posts = post_manager.get_posts_by_account(
            account_id,
            POST_STATUS["PUBLISHED"]
        )
        
        today_posts = [
            p for p in published_posts
            if p.get('published_at') and 
            datetime.fromisoformat(p['published_at']) >= today_start
        ]
        
        if len(today_posts) >= DEFAULT_SETTINGS['max_posts_per_day']:
            raise Exception(f"Превышен лимит: максимум {DEFAULT_SETTINGS['max_posts_per_day']} постов в день")
        
        # Проверяем интервал между постами
        if today_posts:
            last_post = max(today_posts, key=lambda x: x.get('published_at', ''))
            last_time = datetime.fromisoformat(last_post['published_at'])
            time_diff = (datetime.now() - last_time).total_seconds() / 60
            
            min_interval = DEFAULT_SETTINGS['min_post_interval']
            if time_diff < min_interval:
                raise Exception(f"Слишком рано! Нужно подождать еще {min_interval - time_diff:.0f} минут")

# Глобальный экземпляр
background_publisher = BackgroundPublisher()
