"""
AI-планировщик контента через Gemini
"""
import json
import time
import re
from typing import Dict, List
import google.generativeai as genai
from utils.logger import log_info, log_error, log_success
from utils.rate_limiter import gemini_rate_limiter

class AIPlanner:
    """AI-планировщик для создания планов публикаций"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        if api_key:
            genai.configure(api_key=api_key)
    
    def create_plan(self, instruction: str, available_accounts: List[Dict]) -> Dict:
        """
        Создает план публикаций на основе текстовой инструкции
        
        Args:
            instruction: Инструкция пользователя
            available_accounts: Список доступных аккаунтов
        
        Returns:
            План публикаций в формате JSON
        """
        if not self.api_key:
            raise Exception("Gemini API не настроен")
        
        # Формируем список доступных аккаунтов
        accounts_list = "\n".join([
            f"- {acc['username']} (ID: {acc['id']})"
            for acc in available_accounts
        ])
        
        system_prompt = f"""Ты — планировщик контента для Instagram. 
Пользователь даёт тебе инструкции, а ты создаёшь структурированный план.

Доступные аккаунты (залогиненные):
{accounts_list}

Верни JSON в таком формате:
{{
  "accounts": [
    {{
      "account_id": "account_1",
      "username": "@sportblog_kz",
      "theme": "спорт",
      "language": "русский",
      "posts_per_day": 5,
      "format": "photo",
      "keywords": ["тренировки", "фитнес", "здоровье"]
    }}
  ],
  "total_posts": 15,
  "duration_days": 1
}}

Правила:
- Если аккаунт не указан в инструкции, не включай его
- posts_per_day не более 10 (лимит Instagram)
- format: "photo" или "video"
- language: язык контента (русский, казахский, английский и т.д.)
- theme: основная тематика аккаунта
- keywords: 5-10 ключевых слов для генерации контента
- Если в инструкции не указано количество постов, используй 5 постов в день
- Если не указан формат, используй "photo"

ИНСТРУКЦИЯ ПОЛЬЗОВАТЕЛЯ:
{instruction}

Верни ТОЛЬКО JSON, без дополнительного текста."""

        try:
            log_info("Отправка запроса в Gemini для создания плана...")
            
            # Вызываем Gemini с повтором при ошибке квоты
            response_text = self._call_gemini_with_retry(system_prompt)
            
            # Извлекаем JSON из ответа
            response_text = response_text.strip()
            
            # Убираем markdown форматирование если есть
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
            
            plan = json.loads(response_text)
            
            # Валидация плана
            validated_plan = self._validate_plan(plan, available_accounts)
            
            log_success(f"План создан: {validated_plan['total_posts']} постов для {len(validated_plan['accounts'])} аккаунтов")
            
            return validated_plan
            
        except Exception as e:
            log_error(f"Ошибка создания плана: {e}")
            raise
    
    def _call_gemini_with_retry(self, prompt: str, max_retries: int = 1000) -> str:
        """Вызывает Gemini с автоматическим повтором при ошибке квоты"""
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        for attempt in range(max_retries):
            try:
                # ВАЖНО: Ждем согласно rate limiter перед каждым запросом
                gemini_rate_limiter.wait_if_needed()
                
                log_info(f"🤖 Запрос к Gemini API для создания плана (попытка {attempt + 1}/{max_retries})...")
                response = model.generate_content(prompt)
                
                log_info(f"✅ План получен от Gemini API")
                return response.text.strip()
                
            except Exception as e:
                error_str = str(e)
                
                # Проверяем, является ли это ошибкой квоты (429)
                if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                    # Извлекаем время ожидания из ошибки
                    retry_seconds = self._extract_retry_delay(error_str)
                    
                    if attempt < max_retries - 1:
                        # Увеличиваем время ожидания с каждой попыткой (exponential backoff)
                        backoff_multiplier = 2 ** attempt  # 1x, 2x
                        wait_time = retry_seconds * backoff_multiplier + 5  # +5 секунд для безопасности
                        
                        log_info(f"⏳ Достигнут лимит Gemini API. Ожидание {wait_time} секунд перед повтором (попытка {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    else:
                        log_error(f"❌ Превышен лимит запросов Gemini API после {max_retries} попыток.")
                        raise Exception(f"Превышен лимит запросов Gemini API. Пожалуйста, подождите несколько минут (достигнут дневной лимит 50 запросов для бесплатного тарифа).")
                
                # Другие ошибки
                log_error(f"Ошибка генерации через Gemini: {e}")
                raise
        
        raise Exception("Не удалось создать план после нескольких попыток")
    
    def _extract_retry_delay(self, error_message: str) -> int:
        """Извлекает время ожидания из сообщения об ошибке"""
        # Ищем паттерн "retry in X.Xs" или "retry in Xs"
        match = re.search(r'retry in (\d+(?:\.\d+)?)', error_message, re.IGNORECASE)
        if match:
            seconds = float(match.group(1))
            return int(seconds) + 1  # Округляем вверх
        
        # По умолчанию ждем 30 секунд
        return 30
    
    def _validate_plan(self, plan: Dict, available_accounts: List[Dict]) -> Dict:
        """Валидирует план"""
        # Проверяем наличие ключей
        if 'accounts' not in plan:
            plan['accounts'] = []
        
        valid_accounts = []
        available_ids = {acc['id']: acc['username'] for acc in available_accounts}
        
        for acc_plan in plan['accounts']:
            # Проверяем существование аккаунта
            account_id = acc_plan.get('account_id')
            if account_id not in available_ids:
                log_error(f"Аккаунт {account_id} не найден среди доступных")
                continue
            
            # Проверяем posts_per_day
            posts_per_day = acc_plan.get('posts_per_day', 5)
            if posts_per_day > 10:
                log_info(f"posts_per_day {posts_per_day} превышает лимит, установлено 10")
                acc_plan['posts_per_day'] = 10
            
            # Проверяем format
            if acc_plan.get('format') not in ['photo', 'video']:
                acc_plan['format'] = 'photo'
            
            # Проверяем keywords
            if 'keywords' not in acc_plan or not acc_plan['keywords']:
                acc_plan['keywords'] = [acc_plan.get('theme', 'общее')]
            
            valid_accounts.append(acc_plan)
        
        plan['accounts'] = valid_accounts
        
        # Пересчитываем total_posts
        total = sum(acc.get('posts_per_day', 0) for acc in valid_accounts)
        plan['total_posts'] = total
        
        if 'duration_days' not in plan:
            plan['duration_days'] = 1
        
        return plan

# Глобальный экземпляр будет создан в app.py
ai_planner = None
