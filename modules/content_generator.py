"""
Генератор контента (текст и изображения)
"""
import time
import re
import requests
import urllib.parse
from datetime import datetime
from typing import Dict, List
import google.generativeai as genai

from config import PHOTOS_DIR, VIDEOS_DIR, DEFAULT_SETTINGS, IMAGE_SIZES
from utils.logger import log_info, log_error, log_success
from utils.rate_limiter import gemini_rate_limiter
from modules.post_manager import post_manager

class ContentGenerator:
    """Генератор текстового и визуального контента"""
    
    def __init__(self, gemini_api_key: str):
        self.gemini_api_key = gemini_api_key
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        self.batch_size = DEFAULT_SETTINGS['batch_size']
    
    def generate_posts_from_plan(self, plan: Dict, progress_callback=None) -> List[Dict]:
        """
        Генерирует все посты согласно плану
        
        Args:
            plan: План публикаций
            progress_callback: Функция для отслеживания прогресса
        
        Returns:
            Список созданных постов
        """
        all_posts = []
        total_posts = plan['total_posts']
        current_post = 0
        
        log_info(f"Начало генерации {total_posts} постов...")
        
        for account_plan in plan['accounts']:
            account_id = account_plan['account_id']
            posts_count = account_plan['posts_per_day']
            
            log_info(f"Генерация {posts_count} постов для аккаунта {account_plan['username']}")
            
            # Генерируем посты пакетами
            for i in range(0, posts_count, self.batch_size):
                batch_count = min(self.batch_size, posts_count - i)
                
                for j in range(batch_count):
                    try:
                        post = self._generate_single_post(account_plan)
                        all_posts.append(post)
                        current_post += 1
                        
                        if progress_callback:
                            progress_callback(current_post, total_posts, account_plan['username'])
                        
                        log_info(f"✅ Сгенерировано {current_post}/{total_posts} постов")
                        
                        # Пауза между генерациями постов (каждый пост = 2 запроса к Gemini)
                        if current_post < total_posts:
                            log_info(f"⏸️ Пауза 3 секунды перед следующим постом...")
                            time.sleep(3)
                        
                    except Exception as e:
                        log_error(f"❌ Ошибка генерации поста: {e}")
                        current_post += 1
                        # Увеличенная пауза при ошибке
                        time.sleep(5)
                
                # Пауза между батчами
                if i + batch_count < posts_count:
                    log_info(f"⏸️ Пауза между батчами...")
                    time.sleep(5)
        
        log_success(f"Генерация завершена: создано {len(all_posts)} постов")
        return all_posts
    
    def _generate_single_post(self, account_plan: Dict) -> Dict:
        """Генерирует один пост"""
        post_format = account_plan.get('format', 'photo')
        
        # 1. Генерируем текст поста
        log_info(f"📝 Генерация текста для формата: {post_format}")
        text = self._generate_post_text(
            theme=account_plan['theme'],
            language=account_plan['language'],
            keywords=account_plan['keywords']
        )
        
        # 2. Генерируем медиа в зависимости от формата
        if post_format == 'video':
            # Генерация видео
            log_info(f"🎬 Генерация ВИДЕО для поста...")
            media_path = self._generate_video_for_post(text, account_plan['theme'])
        else:
            # Генерация изображения (по умолчанию)
            log_info(f"📸 Генерация ФОТО для поста...")
            image_prompt = self._generate_image_prompt(text)
            media_path = self._generate_image(image_prompt)
        
        # 3. Создаем пост
        post = post_manager.create_post(
            account_id=account_plan['account_id'],
            text=text,
            media=[media_path],
            post_format=post_format
        )
        
        log_success(f"✅ Пост создан: формат={post_format}, медиа={media_path}")
        
        return post
    
    def _generate_video_for_post(self, post_text: str, theme: str) -> str:
        """Генерирует видео для поста"""
        # Проверяем наличие video_generator
        from app import video_generator
        
        if not video_generator:
            log_error("❌ Video generator не настроен (отсутствует KLING_API_KEY в .env).")
            log_info("📸 Генерируем фото вместо видео...")
            # Fallback на фото
            image_prompt = self._generate_image_prompt(post_text)
            return self._generate_image(image_prompt)
        
        # Генерируем промпт для видео
        log_info("🎬 Генерация промпта для видео через Gemini...")
        video_prompt = self._generate_video_prompt(post_text, theme)
        
        log_info(f"🎬 Промпт для видео: {video_prompt[:100]}...")
        
        # Генерируем видео через Kling AI
        try:
            log_info("🎬 Отправка запроса в Kling 2.0 для генерации видео...")
            result = video_generator.generate_video(
                prompt=video_prompt,
                duration=5
            )
            
            if result['success']:
                log_success(f"✅ Видео успешно сгенерировано: {result['filename']}")
                return result['filename']
            else:
                raise Exception(result.get('error', 'Неизвестная ошибка'))
                
        except Exception as e:
            error_msg = str(e)
            log_error(f"❌ Ошибка генерации видео через Kling AI: {error_msg}")
            
            # Проверяем типичные ошибки
            if "404" in error_msg or "not found" in error_msg.lower():
                log_error("💡 Подсказка: Kling AI endpoint недоступен. Возможно:")
                log_error("   1. API ключ неверный или истёк")
                log_error("   2. Требуется платная подписка Segmind")
                log_error("   3. Модель временно недоступна")
            elif "401" in error_msg or "403" in error_msg:
                log_error("💡 Подсказка: Проблема с аутентификацией. Проверьте KLING_API_KEY в .env")
            
            log_info("📸 Fallback: генерируем фото вместо видео...")
            # Fallback на фото
            image_prompt = self._generate_image_prompt(post_text)
            return self._generate_image(image_prompt)
    
    def _generate_video_prompt(self, post_text: str, theme: str) -> str:
        """Генерирует промпт для видео на основе текста поста"""
        if not self.gemini_api_key:
            # Базовый промпт без AI
            return f"Cinematic video about {theme}, smooth camera movement, professional lighting, dynamic action"
        
        prompt = f"""На основе этого Instagram поста создай ДИНАМИЧЕСКИЙ промпт для генерации ВИДЕО на английском языке:

Пост: {post_text}
Тема: {theme}

Промпт должен быть:
- На английском языке
- Описывать ДВИЖЕНИЕ и ДЕЙСТВИЕ (camera pans, zooms, objects moving)
- Без текста в видео (no text overlay, no words)
- 30-60 слов
- Фокус на визуальных элементах в движении
- Кинематографический стиль

Верни только промпт для видео, без объяснений."""
        
        try:
            return self._call_gemini_with_retry(prompt)
        except Exception as e:
            log_error(f"Ошибка генерации видео-промпта: {e}")
            # Возвращаем базовый промпт
            return f"Cinematic video about {theme}, smooth camera movement, professional lighting, dynamic action, 5 seconds"
    
    def _generate_post_text(self, theme: str, language: str, keywords: List[str]) -> str:
        """Генерирует текст поста через Gemini с обработкой квот"""
        if not self.gemini_api_key:
            raise Exception("Gemini API не настроен")
        
        keywords_str = ", ".join(keywords)
        
        prompt = f"""Создай Instagram пост на тему: {theme}
Язык: {language}
Ключевые слова: {keywords_str}

Требования:
- Длина: 100-150 слов
- Эмодзи: 3-5 штук (используй умеренно)
- Хештеги: 5-10 релевантных (добавь в конце через пустую строку)
- Стиль: {language} язык, вовлекающий и живой
- Призыв к действию в конце (не клише!)
- НЕ используй markdown разметку (**, ##, _, ~~)
- Пиши естественно, как для реальной аудитории

Верни только текст поста, без дополнительных комментариев."""
        
        return self._call_gemini_with_retry(prompt)
    
    def _call_gemini_with_retry(self, prompt: str, max_retries: int = 1000, wait_on_limit: bool = True) -> str:
        """
        Вызывает Gemini с автоматическим повтором при ошибке квоты
        
        Args:
            prompt: Промпт для Gemini
            max_retries: Максимальное количество попыток
            wait_on_limit: Если True, ждет указанное в ошибке время (может быть долго)
        """
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        for attempt in range(max_retries):
            try:
                # ВАЖНО: Ждем согласно rate limiter перед каждым запросом
                gemini_rate_limiter.wait_if_needed()
                
                log_info(f"🤖 Запрос к Gemini API (попытка {attempt + 1}/{max_retries})...")
                response = model.generate_content(prompt)
                
                log_info(f"✅ Ответ получен от Gemini API")
                return response.text.strip()
                
            except Exception as e:
                error_str = str(e)
                
                # Проверяем, является ли это ошибкой квоты (429)
                if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                    # Извлекаем время ожидания из ошибки
                    retry_seconds = self._extract_retry_delay(error_str)
                    
                    if attempt < max_retries - 1:
                        # Если wait_on_limit=True и время ожидания большое - ждем
                        if wait_on_limit and retry_seconds > 60:
                            # Длительное ожидание
                            wait_minutes = retry_seconds / 60
                            log_info(f"⏳ Достигнут дневной лимит Gemini API.")
                            log_info(f"⏰ Ожидание {wait_minutes:.1f} минут до сброса лимита...")
                            log_info(f"💡 Совет: Не закрывайте приложение, оно автоматически продолжит работу")
                            
                            # Разбиваем ожидание на части по 60 секунд для промежуточных логов
                            elapsed = 0
                            while elapsed < retry_seconds:
                                chunk = min(60, retry_seconds - elapsed)
                                time.sleep(chunk)
                                elapsed += chunk
                                remaining = (retry_seconds - elapsed) / 60
                                if remaining > 1:
                                    log_info(f"⏰ Осталось ждать: {remaining:.1f} минут...")
                            
                            log_info(f"✅ Ожидание завершено, повторяем запрос...")
                            continue
                        else:
                            # Короткое ожидание с exponential backoff
                            backoff_multiplier = 2 ** attempt  # 1x, 2x, 4x
                            wait_time = min(retry_seconds * backoff_multiplier + 5, 120)  # Максимум 2 минуты
                            
                            log_info(f"⏳ Достигнут лимит Gemini API. Ожидание {wait_time} секунд перед повтором (попытка {attempt + 1}/{max_retries})...")
                            time.sleep(wait_time)
                            continue
                    else:
                        log_error(f"❌ Превышен лимит запросов Gemini API после {max_retries} попыток.")
                        raise Exception(f"Превышен лимит запросов Gemini API. Достигнут дневной лимит 50 запросов для бесплатного тарифа. Подождите до завтра.")
                
                # Другие ошибки
                log_error(f"Ошибка генерации через Gemini: {e}")
                raise
        
        raise Exception("Не удалось сгенерировать контент после нескольких попыток")
    
    def _extract_retry_delay(self, error_message: str) -> int:
        """Извлекает время ожидания из сообщения об ошибке"""
        # Ищем паттерн "retry in X.Xs" или "retry in Xs"
        match = re.search(r'retry in (\d+(?:\.\d+)?)', error_message, re.IGNORECASE)
        if match:
            seconds = float(match.group(1))
            return int(seconds) + 1  # Округляем вверх
        
        # По умолчанию ждем 30 секунд
        return 30
    
    def _generate_image_prompt(self, post_text: str) -> str:
        """Генерирует промпт для изображения на основе текста поста"""
        if not self.gemini_api_key:
            raise Exception("Gemini API не настроен")
        
        prompt = f"""На основе этого Instagram поста создай короткий промпт для генерации изображения:

Пост: {post_text}

Промпт должен быть:
- На английском языке
- Описательным и визуальным
- Без текста/слов на изображении (no text overlay, no words)
- 15-30 слов
- Фокус на визуальных элементах, которые отражают тему поста
- Профессиональный стиль фотографии

Верни только промпт, без объяснений."""
        
        try:
            return self._call_gemini_with_retry(prompt)
        except Exception as e:
            log_error(f"Ошибка генерации промпта для изображения: {e}")
            # Возвращаем базовый промпт
            return "Professional Instagram photo, high quality, vibrant colors"
    
    def _generate_image(self, prompt: str) -> str:
        """Генерирует изображение через Pollinations AI"""
        size = DEFAULT_SETTINGS['default_size']
        model = DEFAULT_SETTINGS['default_model']
        
        width = IMAGE_SIZES[size]['width']
        height = IMAGE_SIZES[size]['height']
        
        try:
            # Pollinations API
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
            params = {
                'width': width,
                'height': height,
                'model': model,
                'nologo': 'true'
            }
            
            response = requests.get(url, params=params, timeout=60)
            
            if response.status_code == 200:
                # Сохраняем изображение
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"{timestamp}.jpg"
                filepath = PHOTOS_DIR / filename
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                # Сохраняем метаданные
                import json
                metadata = {
                    'prompt': prompt,
                    'width': width,
                    'height': height,
                    'model': model,
                    'timestamp': timestamp
                }
                
                metadata_file = PHOTOS_DIR / f"{timestamp}.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                return filename
            else:
                raise Exception(f"Ошибка генерации изображения: {response.status_code}")
                
        except Exception as e:
            log_error(f"Ошибка генерации изображения: {e}")
            raise
    
    def regenerate_text(self, post_id: str, theme: str, language: str, keywords: List[str]) -> str:
        """Перегенерирует текст для существующего поста"""
        new_text = self._generate_post_text(theme, language, keywords)
        
        post_manager.update_post(post_id, {'text': new_text})
        log_info(f"Текст поста {post_id} перегенерирован")
        
        return new_text
    
    def regenerate_image(self, post_id: str, new_prompt: str) -> str:
        """Перегенерирует изображение для существующего поста"""
        new_image = self._generate_image(new_prompt)
        
        post_manager.update_post(post_id, {'media': [new_image]})
        log_info(f"Изображение поста {post_id} перегенерировано")
        
        return new_image

# Глобальный экземпляр будет создан в app.py
content_generator = None
