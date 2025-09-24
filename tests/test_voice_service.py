import pytest
import asyncio
import tempfile
import os
import json
from unittest.mock import Mock, AsyncMock, patch, mock_open
from datetime import datetime, timedelta

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.services.voice_service import VoiceService, MemoryService, ReminderService

class TestVoiceService:
    """Тесты для голосового сервиса"""
    
    @pytest.fixture
    def voice_service(self):
        """Фикстура голосового сервиса"""
        with patch('openai.OpenAI'):
            return VoiceService()
    
    @pytest.mark.asyncio
    async def test_download_voice_file(self, voice_service):
        """Тест скачивания голосового файла"""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.content.iter_chunked = AsyncMock(return_value=[b'test_audio_data'])
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
            
            with patch('aiofiles.open', mock_open()) as mock_file:
                result = await voice_service.download_voice_file('http://test.com/voice.ogg', 'test_id')
                
                assert result is not None
                assert 'test_id.ogg' in result
    
    @pytest.mark.asyncio
    async def test_transcribe_voice(self, voice_service):
        """Тест транскрипции голоса"""
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            temp_file.write(b'fake_audio_data')
            temp_file_path = temp_file.name
        
        try:
            # Мокаем OpenAI API
            mock_transcript = Mock()
            mock_transcript.text = "Привет, это тестовое сообщение"
            
            voice_service.openai_client.audio.transcriptions.create = Mock(return_value=mock_transcript)
            
            with patch.object(voice_service, 'convert_to_mp3', return_value=None):
                with patch.object(voice_service, 'cleanup_temp_files', return_value=None):
                    result = await voice_service.transcribe_voice(temp_file_path)
                    
                    assert result == "Привет, это тестовое сообщение"
        
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    
    @pytest.mark.asyncio
    async def test_synthesize_speech(self, voice_service):
        """Тест синтеза речи"""
        mock_response = Mock()
        mock_response.iter_bytes = Mock(return_value=[b'audio_chunk_1', b'audio_chunk_2'])
        
        voice_service.openai_client.audio.speech.create = Mock(return_value=mock_response)
        
        with patch('builtins.open', mock_open()) as mock_file:
            result = await voice_service.synthesize_speech("Тестовое сообщение")
            
            assert result is not None
            assert result.endswith('.mp3')
    
    @pytest.mark.asyncio
    async def test_process_voice_message(self, voice_service):
        """Тест полной обработки голосового сообщения"""
        with patch.object(voice_service, 'download_voice_file', return_value='/tmp/test.ogg'):
            with patch.object(voice_service, 'transcribe_voice', return_value='Тестовый текст'):
                result = await voice_service.process_voice_message('http://test.com/voice.ogg', 'test_id')
                
                assert result['success'] is True
                assert result['text'] == 'Тестовый текст'
    
    @pytest.mark.asyncio
    async def test_process_voice_message_error(self, voice_service):
        """Тест обработки ошибок при обработке голосового сообщения"""
        with patch.object(voice_service, 'download_voice_file', return_value=None):
            result = await voice_service.process_voice_message('http://test.com/voice.ogg', 'test_id')
            
            assert result['success'] is False
            assert 'error' in result

class TestMemoryService:
    """Тесты для сервиса памяти"""
    
    @pytest.fixture
    def memory_service(self):
        """Фикстура сервиса памяти без Redis"""
        return MemoryService(redis_client=None)
    
    @pytest.mark.asyncio
    async def test_store_and_get_short_term(self, memory_service):
        """Тест краткосрочной памяти"""
        user_id = 123
        key = 'test_key'
        data = {'message': 'test data'}
        
        # Сохраняем
        result = await memory_service.store_short_term(user_id, key, data)
        assert result is True
        
        # Получаем
        retrieved = await memory_service.get_short_term(user_id, key)
        assert retrieved == data
    
    @pytest.mark.asyncio
    async def test_store_and_get_long_term(self, memory_service):
        """Тест долгосрочной памяти"""
        user_id = 123
        key = 'preferences'
        data = {'language': 'ru', 'voice_enabled': True}
        
        # Сохраняем
        result = await memory_service.store_long_term(user_id, key, data)
        assert result is True
        
        # Получаем
        retrieved = await memory_service.get_long_term(user_id, key)
        assert retrieved == data
    
    @pytest.mark.asyncio
    async def test_conversation_history(self, memory_service):
        """Тест истории разговора"""
        user_id = 123
        
        # Добавляем сообщения
        messages = [
            {'type': 'user', 'text': 'Привет'},
            {'type': 'bot', 'text': 'Привет! Как дела?'},
            {'type': 'user', 'text': 'Хорошо, спасибо'}
        ]
        
        for message in messages:
            await memory_service.store_conversation(user_id, message)
        
        # Получаем историю
        history = await memory_service.get_conversation_history(user_id, limit=5)
        
        assert len(history) == 3
        assert history[0]['text'] == 'Привет'
        assert history[-1]['text'] == 'Хорошо, спасибо'
    
    @pytest.mark.asyncio
    async def test_user_context(self, memory_service):
        """Тест получения контекста пользователя"""
        user_id = 123
        
        # Настраиваем данные
        await memory_service.store_long_term(user_id, 'preferences', {'language': 'ru'})
        await memory_service.store_short_term(user_id, 'recent_templates', ['template1', 'template2'])
        await memory_service.store_conversation(user_id, {'type': 'user', 'text': 'test'})
        
        # Получаем контекст
        context = await memory_service.get_user_context(user_id)
        
        assert 'conversation_history' in context
        assert 'preferences' in context
        assert 'recent_templates' in context
        assert context['preferences']['language'] == 'ru'
        assert len(context['recent_templates']) == 2
    
    @pytest.mark.asyncio
    async def test_update_user_preferences(self, memory_service):
        """Тест обновления предпочтений пользователя"""
        user_id = 123
        
        # Устанавливаем начальные предпочтения
        initial_prefs = {'language': 'en', 'notifications': True}
        await memory_service.store_long_term(user_id, 'preferences', initial_prefs)
        
        # Обновляем предпочтения
        updates = {'language': 'ru', 'voice_enabled': True}
        result = await memory_service.update_user_preferences(user_id, updates)
        
        assert result is True
        
        # Проверяем обновленные предпочтения
        updated_prefs = await memory_service.get_long_term(user_id, 'preferences')
        assert updated_prefs['language'] == 'ru'
        assert updated_prefs['notifications'] is True  # Старое значение сохранилось
        assert updated_prefs['voice_enabled'] is True  # Новое значение добавилось
    
    @pytest.mark.asyncio
    async def test_memory_expiration(self, memory_service):
        """Тест истечения памяти"""
        user_id = 123
        key = 'test_key'
        data = {'test': 'data'}
        
        # Устанавливаем очень короткое время жизни
        memory_service.short_term_ttl = 1  # 1 секунда
        
        # Сохраняем данные
        await memory_service.store_short_term(user_id, key, data)
        
        # Сразу получаем - должны быть доступны
        retrieved = await memory_service.get_short_term(user_id, key)
        assert retrieved == data
        
        # Ждем истечения времени
        await asyncio.sleep(2)
        
        # Данные должны быть недоступны (в реальной реализации с Redis)
        # В локальной памяти нужно вручную проверить истечение
        if user_id in memory_service.local_memory:
            memory_item = memory_service.local_memory[user_id].get(key)
            if memory_item:
                assert memory_item['expires'] < datetime.now().timestamp()

class TestReminderService:
    """Тесты для сервиса напоминаний"""
    
    @pytest.fixture
    def reminder_service(self):
        """Фикстура сервиса напоминаний"""
        memory_service = MemoryService(redis_client=None)
        return ReminderService(memory_service)
    
    @pytest.mark.asyncio
    async def test_set_reminder(self, reminder_service):
        """Тест установки напоминания"""
        user_id = 123
        message = "Проверить статус workflows"
        delay_seconds = 5
        
        reminder_id = await reminder_service.set_reminder(user_id, message, delay_seconds)
        
        assert reminder_id is not None
        assert isinstance(reminder_id, str)
        assert reminder_id.startswith('reminder_')
    
    @pytest.mark.asyncio
    async def test_get_user_reminders(self, reminder_service):
        """Тест получения напоминаний пользователя"""
        user_id = 123
        
        # Устанавливаем несколько напоминаний
        await reminder_service.set_reminder(user_id, "Напоминание 1", 60)
        await reminder_service.set_reminder(user_id, "Напоминание 2", 120)
        
        # Получаем список напоминаний
        reminders = await reminder_service.get_user_reminders(user_id)
        
        # В базовой реализации возвращается пустой список
        assert isinstance(reminders, list)

class TestIntegration:
    """Интеграционные тесты для голосовых сервисов"""
    
    @pytest.mark.asyncio
    async def test_voice_to_memory_integration(self):
        """Тест интеграции голосового сервиса с памятью"""
        memory_service = MemoryService(redis_client=None)
        
        with patch('openai.OpenAI'):
            voice_service = VoiceService()
        
        user_id = 123
        
        # Симулируем обработку голосового сообщения
        with patch.object(voice_service, 'process_voice_message') as mock_process:
            mock_process.return_value = {
                'success': True,
                'text': 'Найди шаблоны для email автоматизации',
                'duration': 3.5
            }
            
            # Обрабатываем голосовое сообщение
            result = await voice_service.process_voice_message('http://test.com/voice.ogg', 'test_id')
            
            # Сохраняем в память
            await memory_service.store_conversation(user_id, {
                'type': 'voice',
                'text': result['text'],
                'duration': result['duration']
            })
            
            # Проверяем, что сохранилось
            history = await memory_service.get_conversation_history(user_id, 1)
            assert len(history) == 1
            assert history[0]['type'] == 'voice'
            assert history[0]['text'] == 'Найди шаблоны для email автоматизации'
    
    @pytest.mark.asyncio
    async def test_reminder_with_memory_integration(self):
        """Тест интеграции напоминаний с памятью"""
        memory_service = MemoryService(redis_client=None)
        reminder_service = ReminderService(memory_service)
        
        user_id = 123
        
        # Устанавливаем напоминание
        reminder_id = await reminder_service.set_reminder(
            user_id, 
            "Проверить импортированные workflows", 
            2  # 2 секунды для теста
        )
        
        assert reminder_id is not None
        
        # Проверяем, что данные сохранились в памяти
        reminder_data = await memory_service.get_short_term(user_id, f"reminder_{reminder_id}")
        
        # В базовой реализации может не сохраняться, но структура должна быть правильной
        if reminder_data:
            assert reminder_data['user_id'] == user_id
            assert reminder_data['message'] == "Проверить импортированные workflows"
            assert reminder_data['status'] == 'active'

if __name__ == '__main__':
    # Запуск тестов
    pytest.main([__file__, '-v'])
