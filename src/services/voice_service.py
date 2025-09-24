import os
import tempfile
import logging
import asyncio
from typing import Optional, Dict, Any
import aiohttp
import aiofiles
from pathlib import Path

import openai
from openai import OpenAI

logger = logging.getLogger(__name__)

class VoiceService:
    """Сервис для обработки голосовых сообщений"""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.temp_dir = Path(tempfile.gettempdir()) / "n8n_bot_voice"
        self.temp_dir.mkdir(exist_ok=True)
    
    async def download_voice_file(self, file_url: str, file_id: str) -> Optional[str]:
        """Скачивает голосовой файл с серверов Telegram"""
        try:
            file_path = self.temp_dir / f"{file_id}.ogg"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                        
                        logger.info(f"Voice file downloaded: {file_path}")
                        return str(file_path)
                    else:
                        logger.error(f"Failed to download voice file: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error downloading voice file: {e}")
            return None
    
    async def transcribe_voice(self, file_path: str) -> Optional[str]:
        """Транскрибирует голосовое сообщение в текст"""
        try:
            # Конвертируем OGG в MP3 для лучшей совместимости
            mp3_path = await self.convert_to_mp3(file_path)
            if not mp3_path:
                mp3_path = file_path
            
            # Используем OpenAI Whisper для транскрипции
            with open(mp3_path, 'rb') as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ru"  # Указываем русский язык
                )
            
            text = transcript.text.strip()
            logger.info(f"Voice transcribed: {text[:100]}...")
            
            # Очищаем временные файлы
            await self.cleanup_temp_files([file_path, mp3_path])
            
            return text
            
        except Exception as e:
            logger.error(f"Error transcribing voice: {e}")
            await self.cleanup_temp_files([file_path])
            return None
    
    async def convert_to_mp3(self, ogg_path: str) -> Optional[str]:
        """Конвертирует OGG файл в MP3 (если доступен ffmpeg)"""
        try:
            mp3_path = ogg_path.replace('.ogg', '.mp3')
            
            # Проверяем наличие ffmpeg
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if process.returncode != 0:
                logger.warning("ffmpeg not available, using original file")
                return None
            
            # Конвертируем файл
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', ogg_path, '-acodec', 'mp3', mp3_path, '-y',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"File converted to MP3: {mp3_path}")
                return mp3_path
            else:
                logger.error(f"ffmpeg conversion failed: {stderr.decode()}")
                return None
                
        except Exception as e:
            logger.error(f"Error converting to MP3: {e}")
            return None
    
    async def cleanup_temp_files(self, file_paths: list):
        """Очищает временные файлы"""
        for file_path in file_paths:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Temp file removed: {file_path}")
            except Exception as e:
                logger.error(f"Error removing temp file {file_path}: {e}")
    
    async def synthesize_speech(self, text: str, voice: str = "alloy") -> Optional[str]:
        """Синтезирует речь из текста"""
        try:
            # Ограничиваем длину текста
            if len(text) > 4000:
                text = text[:4000] + "..."
            
            output_path = self.temp_dir / f"response_{hash(text)}.mp3"
            
            response = self.openai_client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text
            )
            
            # Сохраняем аудио файл
            with open(output_path, 'wb') as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
            
            logger.info(f"Speech synthesized: {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            return None
    
    async def process_voice_message(self, file_url: str, file_id: str) -> Dict[str, Any]:
        """Полная обработка голосового сообщения"""
        try:
            # Скачиваем файл
            file_path = await self.download_voice_file(file_url, file_id)
            if not file_path:
                return {
                    'success': False,
                    'error': 'Failed to download voice file'
                }
            
            # Транскрибируем
            text = await self.transcribe_voice(file_path)
            if not text:
                return {
                    'success': False,
                    'error': 'Failed to transcribe voice'
                }
            
            return {
                'success': True,
                'text': text,
                'duration': None  # Можно добавить определение длительности
            }
            
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            return {
                'success': False,
                'error': str(e)
            }


class MemoryService:
    """Сервис для управления памятью бота"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.local_memory = {}
        
        # Настройки памяти
        self.short_term_ttl = 3600  # 1 час
        self.long_term_ttl = 86400 * 30  # 30 дней
        self.conversation_ttl = 86400 * 7  # 7 дней
    
    async def store_short_term(self, user_id: int, key: str, data: Any) -> bool:
        """Сохраняет данные в краткосрочную память"""
        try:
            memory_key = f"short_term:{user_id}:{key}"
            
            if self.redis_client:
                await self.redis_client.setex(
                    memory_key, 
                    self.short_term_ttl, 
                    json.dumps(data, ensure_ascii=False)
                )
            else:
                if user_id not in self.local_memory:
                    self.local_memory[user_id] = {}
                self.local_memory[user_id][key] = {
                    'data': data,
                    'expires': datetime.now().timestamp() + self.short_term_ttl
                }
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing short-term memory: {e}")
            return False
    
    async def get_short_term(self, user_id: int, key: str) -> Optional[Any]:
        """Получает данные из краткосрочной памяти"""
        try:
            memory_key = f"short_term:{user_id}:{key}"
            
            if self.redis_client:
                data = await self.redis_client.get(memory_key)
                return json.loads(data) if data else None
            else:
                user_memory = self.local_memory.get(user_id, {})
                memory_item = user_memory.get(key)
                
                if memory_item and memory_item['expires'] > datetime.now().timestamp():
                    return memory_item['data']
                elif memory_item:
                    # Удаляем просроченные данные
                    del user_memory[key]
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting short-term memory: {e}")
            return None
    
    async def store_long_term(self, user_id: int, key: str, data: Any) -> bool:
        """Сохраняет данные в долгосрочную память"""
        try:
            memory_key = f"long_term:{user_id}:{key}"
            
            if self.redis_client:
                await self.redis_client.setex(
                    memory_key, 
                    self.long_term_ttl, 
                    json.dumps(data, ensure_ascii=False)
                )
            else:
                if user_id not in self.local_memory:
                    self.local_memory[user_id] = {}
                self.local_memory[user_id][f"long_{key}"] = {
                    'data': data,
                    'expires': datetime.now().timestamp() + self.long_term_ttl
                }
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing long-term memory: {e}")
            return False
    
    async def get_long_term(self, user_id: int, key: str) -> Optional[Any]:
        """Получает данные из долгосрочной памяти"""
        try:
            memory_key = f"long_term:{user_id}:{key}"
            
            if self.redis_client:
                data = await self.redis_client.get(memory_key)
                return json.loads(data) if data else None
            else:
                user_memory = self.local_memory.get(user_id, {})
                memory_item = user_memory.get(f"long_{key}")
                
                if memory_item and memory_item['expires'] > datetime.now().timestamp():
                    return memory_item['data']
                elif memory_item:
                    del user_memory[f"long_{key}"]
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting long-term memory: {e}")
            return None
    
    async def store_conversation(self, user_id: int, message: Dict[str, Any]) -> bool:
        """Сохраняет сообщение в историю разговора"""
        try:
            conversation_key = f"conversation:{user_id}"
            
            # Получаем существующую историю
            conversation = await self.get_conversation_history(user_id) or []
            
            # Добавляем новое сообщение
            message['timestamp'] = datetime.now().isoformat()
            conversation.append(message)
            
            # Ограничиваем размер истории (последние 50 сообщений)
            if len(conversation) > 50:
                conversation = conversation[-50:]
            
            if self.redis_client:
                await self.redis_client.setex(
                    conversation_key, 
                    self.conversation_ttl, 
                    json.dumps(conversation, ensure_ascii=False)
                )
            else:
                if user_id not in self.local_memory:
                    self.local_memory[user_id] = {}
                self.local_memory[user_id]['conversation'] = {
                    'data': conversation,
                    'expires': datetime.now().timestamp() + self.conversation_ttl
                }
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing conversation: {e}")
            return False
    
    async def get_conversation_history(self, user_id: int, limit: int = 10) -> Optional[list]:
        """Получает историю разговора"""
        try:
            conversation_key = f"conversation:{user_id}"
            
            if self.redis_client:
                data = await self.redis_client.get(conversation_key)
                conversation = json.loads(data) if data else []
            else:
                user_memory = self.local_memory.get(user_id, {})
                memory_item = user_memory.get('conversation')
                
                if memory_item and memory_item['expires'] > datetime.now().timestamp():
                    conversation = memory_item['data']
                else:
                    conversation = []
            
            # Возвращаем последние N сообщений
            return conversation[-limit:] if conversation else []
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    async def get_user_context(self, user_id: int) -> Dict[str, Any]:
        """Получает полный контекст пользователя"""
        try:
            context = {
                'conversation_history': await self.get_conversation_history(user_id, 5),
                'preferences': await self.get_long_term(user_id, 'preferences') or {},
                'recent_templates': await self.get_short_term(user_id, 'recent_templates') or [],
                'active_workflows': await self.get_short_term(user_id, 'active_workflows') or [],
                'last_activity': await self.get_short_term(user_id, 'last_activity')
            }
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting user context: {e}")
            return {}
    
    async def update_user_preferences(self, user_id: int, preferences: Dict[str, Any]) -> bool:
        """Обновляет предпочтения пользователя"""
        try:
            current_prefs = await self.get_long_term(user_id, 'preferences') or {}
            current_prefs.update(preferences)
            
            return await self.store_long_term(user_id, 'preferences', current_prefs)
            
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            return False


class ReminderService:
    """Сервис для напоминаний и уведомлений"""
    
    def __init__(self, memory_service: MemoryService):
        self.memory_service = memory_service
        self.active_reminders = {}
    
    async def set_reminder(self, user_id: int, message: str, delay_seconds: int) -> str:
        """Устанавливает напоминание"""
        try:
            reminder_id = f"reminder_{user_id}_{int(datetime.now().timestamp())}"
            
            reminder_data = {
                'user_id': user_id,
                'message': message,
                'created_at': datetime.now().isoformat(),
                'trigger_at': (datetime.now() + timedelta(seconds=delay_seconds)).isoformat(),
                'status': 'active'
            }
            
            # Сохраняем в память
            await self.memory_service.store_short_term(user_id, f"reminder_{reminder_id}", reminder_data)
            
            # Планируем выполнение
            asyncio.create_task(self._execute_reminder(reminder_id, delay_seconds))
            
            logger.info(f"Reminder set for user {user_id}: {reminder_id}")
            return reminder_id
            
        except Exception as e:
            logger.error(f"Error setting reminder: {e}")
            return None
    
    async def _execute_reminder(self, reminder_id: str, delay_seconds: int):
        """Выполняет напоминание"""
        try:
            await asyncio.sleep(delay_seconds)
            
            # Здесь должна быть логика отправки напоминания через Telegram
            # Пока что просто логируем
            logger.info(f"Reminder triggered: {reminder_id}")
            
        except Exception as e:
            logger.error(f"Error executing reminder: {e}")
    
    async def get_user_reminders(self, user_id: int) -> list:
        """Получает активные напоминания пользователя"""
        try:
            # Здесь должна быть логика получения всех напоминаний пользователя
            # Пока что возвращаем пустой список
            return []
            
        except Exception as e:
            logger.error(f"Error getting user reminders: {e}")
            return []


# Импорты для типов
import json
from datetime import datetime, timedelta
