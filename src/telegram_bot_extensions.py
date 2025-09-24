import os
import tempfile
import json
import logging
from typing import Dict, Any, Optional
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

logger = logging.getLogger(__name__)

class TelegramBotExtensions:
    """Расширения для Telegram бота"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
    
    async def format_agent_result(self, result: Dict[str, Any], intent: str) -> Any:
        """Форматирует результат работы агента для пользователя"""
        try:
            task_result = result.get('result', {})
            agent_thoughts = task_result.get('agent_thoughts', {})
            
            # Показываем мысли агента если они есть
            thinking_text = ""
            if agent_thoughts.get('success', False):
                thinking_text = f"\n\n🧠 **Мысли агента:** {agent_thoughts.get('content', '')[:200]}..."
            
            if intent == 'search_template':
                return await self._format_search_result(task_result, thinking_text)
            elif intent == 'get_categories':
                return await self._format_categories_result(task_result, thinking_text)
            elif intent == 'import_template':
                return await self._format_import_result(task_result, thinking_text)
            elif intent == 'export_template':
                return await self._format_export_result(task_result, thinking_text)
            elif intent in ['activate_workflow', 'deactivate_workflow']:
                return await self._format_workflow_action_result(task_result, intent, thinking_text)
            elif intent == 'list_workflows':
                return await self._format_workflows_list_result(task_result, thinking_text)
            else:
                return f"✅ Задача выполнена успешно{thinking_text}"
                
        except Exception as e:
            logger.error(f"Error formatting agent result: {e}")
            return f"Результат получен, но произошла ошибка форматирования: {str(e)}"
    
    async def _format_search_result(self, result: Dict[str, Any], thinking_text: str) -> str:
        """Форматирует результат поиска шаблонов"""
        templates = result.get('templates', [])
        
        if not templates:
            return f"🔍 **Поиск шаблонов**\n\nПо вашему запросу ничего не найдено.{thinking_text}"
        
        message = f"🔍 **Найдено шаблонов: {len(templates)}**\n\n"
        
        for i, template in enumerate(templates[:5], 1):
            message += f"{i}. **{template['name']}**\n"
            message += f"   📂 {template['category']} | 🏷️ {template.get('complexity', 'Unknown')}\n"
            message += f"   📝 {template['description'][:100]}...\n"
            message += f"   📥 Загрузок: {template.get('download_count', 0)}\n\n"
        
        message += "Для импорта напишите: 'Импортируй шаблон [название]'"
        message += thinking_text
        
        return message
    
    async def _format_categories_result(self, result: Dict[str, Any], thinking_text: str) -> str:
        """Форматирует результат категорий"""
        categories = result.get('categories', {})
        
        if not categories:
            return f"📂 **Категории шаблонов**\n\nДанные о категориях недоступны.{thinking_text}"
        
        message = "📂 **Категории шаблонов:**\n\n"
        
        # Сортируем по количеству
        sorted_categories = sorted(categories.items(), key=lambda x: x[1].get('count', 0), reverse=True)
        
        for category, data in sorted_categories[:10]:
            count = data.get('count', 0)
            message += f"• **{category}**: {count} шаблонов\n"
        
        total = result.get('total_templates', 0)
        message += f"\n📊 Всего: {total} шаблонов"
        message += thinking_text
        
        return message
    
    async def _format_import_result(self, result: Dict[str, Any], thinking_text: str) -> str:
        """Форматирует результат импорта"""
        if result.get('success', False):
            workflow_id = result.get('workflow_id', 'Unknown')
            message = f"✅ **Шаблон импортирован!**\n\n"
            message += f"🆔 Workflow ID: `{workflow_id}`\n"
            message += f"▶️ Для активации: 'Активируй workflow {workflow_id}'"
            message += thinking_text
            return message
        else:
            error = result.get('error', 'Неизвестная ошибка')
            return f"❌ **Ошибка импорта:**\n{error}{thinking_text}"
    
    async def _format_export_result(self, result: Dict[str, Any], thinking_text: str) -> Any:
        """Форматирует результат экспорта"""
        if result.get('success', False):
            filename = result.get('filename', 'workflow.json')
            data = result.get('data', {})
            
            # Возвращаем файл
            return {
                'message': f"📤 **Workflow экспортирован!**\n\nФайл: {filename}{thinking_text}",
                'file_data': data,
                'filename': filename
            }
        else:
            error = result.get('error', 'Неизвестная ошибка')
            return f"❌ **Ошибка экспорта:**\n{error}{thinking_text}"
    
    async def _format_workflow_action_result(self, result: Dict[str, Any], intent: str, thinking_text: str) -> str:
        """Форматирует результат действий с workflow"""
        if result.get('success', False):
            action = "активирован" if intent == 'activate_workflow' else "деактивирован"
            emoji = "▶️" if intent == 'activate_workflow' else "⏸️"
            
            message = f"{emoji} **Workflow {action}!**\n\n"
            message += f"📊 Статус обновлен"
            message += thinking_text
            return message
        else:
            error = result.get('error', 'Неизвестная ошибка')
            return f"❌ **Ошибка:**\n{error}{thinking_text}"
    
    async def _format_workflows_list_result(self, result: Dict[str, Any], thinking_text: str) -> str:
        """Форматирует список workflows"""
        workflows = result.get('workflows', [])
        
        if not workflows:
            return f"📋 **Ваши workflows**\n\nУ вас пока нет импортированных workflows.{thinking_text}"
        
        message = f"📋 **Ваши workflows ({len(workflows)}):**\n\n"
        
        for workflow in workflows[:10]:
            status_emoji = "▶️" if workflow.get('status') == 'active' else "⏸️"
            message += f"{status_emoji} **{workflow.get('workflow_name', 'Unknown')}**\n"
            message += f"   🆔 `{workflow.get('workflow_id', 'Unknown')}`\n"
            message += f"   📊 {workflow.get('status', 'unknown')}\n\n"
        
        message += thinking_text
        return message
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик голосовых сообщений"""
        try:
            user_id = update.effective_user.id
            voice = update.message.voice
            
            # Показываем что обрабатываем голосовое сообщение
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            thinking_msg = await update.message.reply_text("🎤 *Обрабатываю голосовое сообщение...*", parse_mode='Markdown')
            
            # Получаем файл
            file = await context.bot.get_file(voice.file_id)
            file_url = file.file_path
            
            # Обрабатываем голосовое сообщение
            await thinking_msg.edit_text("🎤 *Распознаю речь...*", parse_mode='Markdown')
            voice_result = await self.bot.voice_service.process_voice_message(file_url, voice.file_id)
            
            if not voice_result['success']:
                await thinking_msg.edit_text(f"❌ Ошибка обработки голосового сообщения: {voice_result['error']}")
                return
            
            # Получили текст из голосового сообщения
            text = voice_result['text']
            await thinking_msg.edit_text(f"🎤 *Распознано:* {text[:100]}...\n\n🤔 *Обрабатываю запрос...*", parse_mode='Markdown')
            
            # Сохраняем в память
            await self.bot.memory_service.store_conversation(user_id, {
                'type': 'voice',
                'text': text,
                'duration': voice_result.get('duration')
            })
            
            # Обрабатываем как обычное текстовое сообщение
            nlu_result = await self.bot.process_natural_language(text, user_id)
            response = await self.bot.orchestrate_agents(
                nlu_result['intent'], 
                nlu_result['entities'], 
                user_id
            )
            
            # Удаляем сообщение о мышлении
            await thinking_msg.delete()
            
            # Отправляем ответ
            if isinstance(response, dict) and 'file_data' in response:
                # Отправляем файл
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(response['file_data'], f, indent=2, ensure_ascii=False)
                    f.flush()
                    
                    with open(f.name, 'rb') as file:
                        await update.message.reply_document(
                            document=InputFile(file, filename=response.get('filename', 'template.json')),
                            caption=response.get('message', 'Файл шаблона'),
                            parse_mode='Markdown'
                        )
                    
                    os.unlink(f.name)
            else:
                # Отправляем текстовый ответ
                await update.message.reply_text(response, parse_mode='Markdown')
                
                # Опционально синтезируем голосовой ответ
                if len(response) < 500:  # Только для коротких ответов
                    voice_file = await self.bot.voice_service.synthesize_speech(response)
                    if voice_file:
                        with open(voice_file, 'rb') as audio:
                            await update.message.reply_voice(
                                voice=InputFile(audio, filename="response.mp3"),
                                caption="🔊 Голосовой ответ"
                            )
                        os.unlink(voice_file)
            
        except Exception as e:
            logger.error(f"Error handling voice message: {e}")
            await update.message.reply_text(f"❌ Ошибка обработки голосового сообщения: {str(e)}")
    
    async def show_agent_thinking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает мысли агентов"""
        try:
            # Получаем статус системы агентов
            system_status = await self.bot.orchestrator.get_system_status()
            
            message = "🧠 **Состояние агентов:**\n\n"
            
            for agent_name, agent_status in system_status['agents'].items():
                status_emoji = "🟢" if not agent_status['is_busy'] else "🔴"
                message += f"{status_emoji} **{agent_name}**\n"
                message += f"   📊 Задач выполнено: {agent_status['performance']['tasks_completed']}\n"
                message += f"   ❌ Ошибок: {agent_status['performance']['tasks_failed']}\n"
                
                if agent_status['current_task']:
                    message += f"   🔄 Текущая задача: {agent_status['current_task'].get('type', 'Unknown')}\n"
                
                message += "\n"
            
            message += f"📈 **Система:**\n"
            message += f"• Активных задач: {system_status['active_tasks']}\n"
            message += f"• В очереди: {system_status['queue_size']}\n"
            message += f"• Время работы: {system_status['uptime']:.0f}с\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing agent thinking: {e}")
            await update.message.reply_text(f"❌ Ошибка получения состояния агентов: {str(e)}")
    
    async def handle_reminder_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды напоминания"""
        try:
            if len(context.args) < 2:
                await update.message.reply_text(
                    "⏰ **Напоминания**\n\n"
                    "Использование: `/remind [время в минутах] [сообщение]`\n\n"
                    "Пример: `/remind 30 Проверить статус workflows`",
                    parse_mode='Markdown'
                )
                return
            
            try:
                delay_minutes = int(context.args[0])
                message = ' '.join(context.args[1:])
            except ValueError:
                await update.message.reply_text("❌ Время должно быть числом (в минутах)")
                return
            
            user_id = update.effective_user.id
            delay_seconds = delay_minutes * 60
            
            reminder_id = await self.bot.reminder_service.set_reminder(
                user_id, message, delay_seconds
            )
            
            if reminder_id:
                await update.message.reply_text(
                    f"⏰ **Напоминание установлено!**\n\n"
                    f"📝 Сообщение: {message}\n"
                    f"⏱️ Через: {delay_minutes} минут\n"
                    f"🆔 ID: `{reminder_id}`",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Ошибка установки напоминания")
                
        except Exception as e:
            logger.error(f"Error handling reminder command: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def handle_thinking_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды просмотра мыслей агентов"""
        try:
            agent_name = context.args[0] if context.args else None
            
            if not agent_name:
                await self.show_agent_thinking(update, context)
                return
            
            # Получаем мысли конкретного агента
            thoughts = await self.bot.orchestrator.get_agent_thoughts(agent_name, 3)
            
            if 'error' in thoughts:
                await update.message.reply_text(f"❌ {thoughts['error']}")
                return
            
            message = f"🧠 **Мысли агента {agent_name}:**\n\n"
            
            recent_thoughts = thoughts.get('recent_thoughts', [])
            if not recent_thoughts:
                message += "Пока нет записанных мыслей."
            else:
                for i, thought_item in enumerate(recent_thoughts[-3:], 1):
                    thought = thought_item['thought']
                    message += f"{i}. **{thought.get('type', 'Unknown')}** ({thought.get('level', 'surface')})\n"
                    message += f"   💭 {thought.get('content', 'Нет содержания')[:150]}...\n"
                    message += f"   🕐 {thought.get('timestamp', 'Unknown')[:19]}\n\n"
            
            # Статистика мышления
            patterns = thoughts.get('thinking_patterns', {})
            if patterns:
                message += "📊 **Паттерны мышления:**\n"
                for pattern, count in patterns.items():
                    message += f"• {pattern}: {count}\n"
            
            avg_quality = thoughts.get('average_quality', 0)
            message += f"\n⭐ Средняя оценка качества: {avg_quality:.2f}"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error handling thinking command: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def start_orchestrator(self):
        """Запускает оркестратор агентов"""
        try:
            await self.bot.orchestrator.start()
            logger.info("Agent orchestrator started successfully")
        except Exception as e:
            logger.error(f"Error starting orchestrator: {e}")
    
    async def stop_orchestrator(self):
        """Останавливает оркестратор агентов"""
        try:
            await self.bot.orchestrator.stop()
            logger.info("Agent orchestrator stopped")
        except Exception as e:
            logger.error(f"Error stopping orchestrator: {e}")
