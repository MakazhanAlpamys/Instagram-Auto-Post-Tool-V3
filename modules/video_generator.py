"""
Генератор видео через Kling AI (Segmind API)
"""
import requests
import json
from datetime import datetime
from pathlib import Path

from config import VIDEOS_DIR
from utils.logger import log_info, log_error, log_success

class VideoGenerator:
    """Генератор видео через Kling AI"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Используем новый Kling 2.0 endpoint
        self.api_url = "https://api.segmind.com/v1/kling-2"
    
    def generate_video(self, prompt: str, duration: int = 5, 
                      aspect_ratio: str = "16:9", mode: str = "std") -> dict:
        """
        Генерирует видео через Kling AI
        
        Args:
            prompt: Текстовый промпт для генерации видео
            duration: Длительность видео (5 или 10 секунд)
            aspect_ratio: Соотношение сторон ("16:9", "9:16", "1:1")
            mode: Режим генерации ("std" или "pro")
        
        Returns:
            dict с информацией о сгенерированном видео
        """
        if not self.api_key:
            raise Exception("Kling AI API ключ не настроен. Добавьте KLING_API_KEY в .env файл")
        
        # Валидация параметров
        if duration not in [5, 10]:
            duration = 5
        
        if aspect_ratio not in ["16:9", "9:16", "1:1"]:
            aspect_ratio = "16:9"
        
        if mode not in ["std", "pro"]:
            mode = "std"
        
        try:
            log_info(f"🎬 Генерация видео через Kling 2.0: '{prompt[:50]}...'")
            log_info(f"⚙️ Параметры: duration={duration}s")
            
            # Формируем payload для Kling 2.0 (согласно документации)
            payload = {
                "prompt": prompt,
                "duration": duration  # 5 или 10 секунд
            }
            
            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            log_info(f"📤 Отправка запроса на {self.api_url}...")
            
            # Отправляем запрос
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=180  # Kling AI может генерировать до 3 минут
            )
            
            log_info(f"📥 Получен ответ: статус {response.status_code}")
            
            if response.status_code == 200:
                # Проверяем тип контента
                content_type = response.headers.get('Content-Type', '')
                
                # Если вернули JSON с URL
                if 'application/json' in content_type:
                    try:
                        result_json = response.json()
                        log_info(f"📋 Получен JSON ответ: {result_json}")
                        
                        # Если есть URL видео, скачиваем его
                        if 'video_url' in result_json or 'url' in result_json:
                            video_url = result_json.get('video_url') or result_json.get('url')
                            log_info(f"🔗 Скачивание видео с URL: {video_url}")
                            
                            video_response = requests.get(video_url, timeout=60)
                            if video_response.status_code != 200:
                                raise Exception(f"Не удалось скачать видео: HTTP {video_response.status_code}")
                            
                            video_content = video_response.content
                        else:
                            raise Exception(f"В ответе нет URL видео. Ответ: {result_json}")
                    except json.JSONDecodeError:
                        raise Exception(f"Не удалось распарсить JSON ответ: {response.text[:200]}")
                else:
                    # Прямой бинарный контент видео
                    video_content = response.content
                
                # Проверяем что получили видео
                if len(video_content) < 1000:  # Минимальный размер видео
                    raise Exception(f"Полученный файл слишком мал ({len(video_content)} байт). Возможно, это не видео.")
                
                # Сохраняем видео
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"{timestamp}.mp4"
                filepath = VIDEOS_DIR / filename
                
                with open(filepath, 'wb') as f:
                    f.write(video_content)
                
                # Сохраняем метаданные
                metadata = {
                    'prompt': prompt,
                    'duration': duration,
                    'aspect_ratio': aspect_ratio,
                    'mode': mode,
                    'timestamp': timestamp,
                    'model': 'kling-ai',
                    'file_size': len(video_content)
                }
                
                metadata_file = VIDEOS_DIR / f"{timestamp}.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                log_success(f"✅ Видео сгенерировано: {filename} ({len(video_content) / 1024:.1f} KB)")
                
                return {
                    'success': True,
                    'filename': filename,
                    'url': f'/api/videos/{filename}',
                    'metadata': metadata
                }
            else:
                error_message = f"HTTP {response.status_code}"
                try:
                    error_json = response.json()
                    error_message = error_json.get('error', error_json.get('message', str(error_json)))
                except:
                    error_message = response.text[:500] if response.text else error_message
                
                log_error(f"❌ Ошибка Kling AI API: {error_message}")
                raise Exception(f"Ошибка Kling AI API: {error_message}")
                
        except requests.exceptions.Timeout:
            log_error("⏱️ Таймаут генерации видео")
            raise Exception("Таймаут генерации видео. Попробуйте еще раз или уменьшите длительность.")
        except Exception as e:
            log_error(f"❌ Ошибка генерации видео: {e}")
            raise
    
    def generate_video_from_image(self, prompt: str, image_path: str, 
                                  duration: int = 5, mode: str = "std") -> dict:
        """
        Генерирует видео из изображения (image-to-video)
        
        Args:
            prompt: Текстовый промпт
            image_path: Путь к изображению
            duration: Длительность (5 или 10 секунд)
            mode: Режим генерации
        
        Returns:
            dict с информацией о сгенерированном видео
        """
        if not self.api_key:
            raise Exception("Kling AI API ключ не настроен")
        
        try:
            log_info(f"🎬 Генерация видео из изображения через Kling 2.0: '{prompt[:50]}...'")
            log_info(f"🖼️ Исходное изображение: {image_path}")
            
            # Читаем изображение и конвертируем в base64
            import base64
            with open(image_path, 'rb') as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Формируем payload для Kling 2.0 (с изображением)
            duration = duration if duration in [5, 10] else 5
            
            payload = {
                "prompt": prompt,
                "duration": duration,
                "start_image": f"data:image/jpeg;base64,{image_base64}"
            }
            
            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            log_info(f"📤 Отправка запроса image-to-video на {self.api_url}...")
            
            # Используем тот же endpoint Kling 2.0
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=180
            )
            
            log_info(f"📥 Получен ответ: статус {response.status_code}")
            
            if response.status_code == 200:
                # Проверяем тип контента
                content_type = response.headers.get('Content-Type', '')
                
                # Если вернули JSON с URL
                if 'application/json' in content_type:
                    try:
                        result_json = response.json()
                        log_info(f"📋 Получен JSON ответ: {result_json}")
                        
                        # Если есть URL видео, скачиваем его
                        if 'video_url' in result_json or 'url' in result_json:
                            video_url = result_json.get('video_url') or result_json.get('url')
                            log_info(f"🔗 Скачивание видео с URL: {video_url}")
                            
                            video_response = requests.get(video_url, timeout=60)
                            if video_response.status_code != 200:
                                raise Exception(f"Не удалось скачать видео: HTTP {video_response.status_code}")
                            
                            video_content = video_response.content
                        else:
                            raise Exception(f"В ответе нет URL видео. Ответ: {result_json}")
                    except json.JSONDecodeError:
                        raise Exception(f"Не удалось распарсить JSON ответ: {response.text[:200]}")
                else:
                    # Прямой бинарный контент видео
                    video_content = response.content
                
                # Проверяем что получили видео
                if len(video_content) < 1000:
                    raise Exception(f"Полученный файл слишком мал ({len(video_content)} байт)")
                
                # Сохраняем видео
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = f"{timestamp}.mp4"
                filepath = VIDEOS_DIR / filename
                
                with open(filepath, 'wb') as f:
                    f.write(video_content)
                
                # Сохраняем метаданные
                metadata = {
                    'prompt': prompt,
                    'source_image': str(image_path),
                    'duration': duration,
                    'mode': mode,
                    'timestamp': timestamp,
                    'model': 'kling-ai-image-to-video',
                    'file_size': len(video_content)
                }
                
                metadata_file = VIDEOS_DIR / f"{timestamp}.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                log_success(f"✅ Видео из изображения сгенерировано: {filename} ({len(video_content) / 1024:.1f} KB)")
                
                return {
                    'success': True,
                    'filename': filename,
                    'url': f'/api/videos/{filename}',
                    'metadata': metadata
                }
            else:
                error_message = f"HTTP {response.status_code}"
                try:
                    error_json = response.json()
                    error_message = error_json.get('error', error_json.get('message', str(error_json)))
                except:
                    error_message = response.text[:500] if response.text else error_message
                
                log_error(f"❌ Ошибка Kling AI API: {error_message}")
                raise Exception(f"Ошибка Kling AI API: {error_message}")
                
        except Exception as e:
            log_error(f"❌ Ошибка генерации видео из изображения: {e}")
            raise

# Глобальный экземпляр будет создан в app.py
video_generator = None
