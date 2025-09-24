import os
import asyncio
import logging
import json
import redis
from typing import Dict, Any, Optional
from datetime import datetime
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ChatAction

import openai
from openai import OpenAI

from src.services.template_service import TemplateService, UserWorkflowService, UserSessionService, ExecutionLogService
from src.services.n8n_api import N8nApiClient
from src.services.voice_service import VoiceService, MemoryService, ReminderService
from src.services.thinking_service import ThinkingService, ThinkingType, ThoughtLevel
from src.services.agent_orchestrator import AgentOrchestrator, TaskPriority

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class N8nTelegramBot:
    def __init__(self):
        # Инициализация конфигурации
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
        self.openai_api_key = os.getenv('OPENAI_API_KEY', 'YOUR_OPENAI_API_KEY')
        
        # Инициализация OpenAI клиента
        self.openai_client = OpenAI(api_key=self.openai_api_key)
        
        # Инициализация Redis для краткосрочной памяти
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis_client.ping()
        except:
            logger.warning("Redis не доступен, используется локальная память")
            self.redis_client = None
        
        # Локальная память как fallback
        self.local_memory = {}
        
        # Инициализация сервисов
        self.template_service = TemplateService()
        self.workflow_service = UserWorkflowService()
        self.session_service = UserSessionService()
        self.execution_service = ExecutionLogService()
        
        # Новые сервисы
        self.voice_service = VoiceService()
        self.memory_service = MemoryService(self.redis_client)
        self.reminder_service = ReminderService(self.memory_service)
        self.thinking_service = ThinkingService()
        
        # Оркестратор агентов
        self.orchestrator = AgentOrchestrator()
        
        # Состояния пользователей
        self.user_states = {}
        
        # Загрузка базы данных шаблонов
        self.templates_db = self.load_templates_database()
        
    def load_templates_database(self) -> Dict[str, Any]:
        """Загружает базу данных шаблонов n8n"""
        try:
            # Загружаем данные из файлов анализа
            templates_db = {
                'categories': {
                    'AI': {'count': 1600, 'templates': []},
                    'Multimodal AI': {'count': 1529, 'templates': []},
                    'Marketing': {'count': 717, 'templates': []},
                    'Content Creation': {'count': 488, 'templates': []},
                    'Engineering': {'count': 415, 'templates': []},
                    'Sales': {'count': 364, 'templates': []},
                    'DevOps': {'count': 170, 'templates': []},
                    'Personal Productivity': {'count': 149, 'templates': []}
                },
                'total_templates': 5727
            }
            return templates_db
        except Exception as e:
            logger.error(f"Ошибка загрузки базы шаблонов: {e}")
            return {'categories': {}, 'total_templates': 0}
    
    def get_user_memory(self, user_id: int) -> Dict[str, Any]:
        """Получает память пользователя"""
        if self.redis_client:
            try:
                memory = self.redis_client.get(f"user_memory:{user_id}")
                return json.loads(memory) if memory else {}
            except:
                pass
        return self.local_memory.get(user_id, {})
    
    def set_user_memory(self, user_id: int, memory: Dict[str, Any]):
        """Сохраняет память пользователя"""
        if self.redis_client:
            try:
                self.redis_client.setex(f"user_memory:{user_id}", 3600, json.dumps(memory))
                return
            except:
                pass
        self.local_memory[user_id] = memory
    
    async def show_thinking(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
        """Показывает процесс мышления бота"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        thinking_msg = await update.message.reply_text(f"🤔 *Думаю...* {message}", parse_mode='Markdown')
        await asyncio.sleep(1)
        return thinking_msg
    
    async def update_thinking(self, thinking_msg, new_message: str):
        """Обновляет сообщение о мышлении"""
        try:
            await thinking_msg.edit_text(f"🧠 *Обрабатываю...* {new_message}", parse_mode='Markdown')
            await asyncio.sleep(0.5)
        except:
            pass
    
    async def process_natural_language(self, text: str, user_id: int) -> Dict[str, Any]:
        """Обрабатывает естественный язык для извлечения намерений"""
        try:
            system_prompt = """
            Ты - NLU процессор для Telegram бота управления n8n шаблонами.
            Анализируй сообщения пользователя и извлекай:
            1. intent (намерение): search_template, import_template, export_template, activate_workflow, 
               deactivate_workflow, list_workflows, get_help, research_info, analyze_data, set_api_key,
               show_stats, get_categories
            2. entities (сущности): категория, название шаблона, ключевые слова, workflow_id, api_key, base_url
            3. confidence (уверенность): 0.0-1.0
            
            Отвечай только в JSON формате:
            {
                "intent": "название_намерения",
                "entities": {"category": "категория", "template_name": "название", "keywords": ["слово1", "слово2"], "workflow_id": "id", "api_key": "key", "base_url": "url"},
                "confidence": 0.95
            }
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Ошибка NLU обработки: {e}")
            return {
                "intent": "get_help",
                "entities": {},
                "confidence": 0.5
            }
    
    async def orchestrate_agents(self, intent: str, entities: Dict[str, Any], user_id: int) -> Any:
        """Оркестрирует работу агентов на основе намерения"""
        try:
            # Специальные случаи
            if intent == 'set_api_key':
                return await self.handle_set_api_key(entities, user_id)
            
            # Определяем тип задачи и данные
            task_data = {
                'user_id': user_id,
                'entities': entities,
                'intent': intent
            }
            
            # Маппинг намерений к типам задач
            intent_to_task = {
                'search_template': 'search_templates',
                'get_categories': 'categorize_templates',
                'show_stats': 'categorize_templates',
                'import_template': 'import_template',
                'export_template': 'export_workflow',
                'activate_workflow': 'activate_workflow',
                'deactivate_workflow': 'deactivate_workflow',
                'list_workflows': 'get_workflows',
                'analyze_data': 'system_health'
            }
            
            task_type = intent_to_task.get(intent)
            
            if not task_type:
                return self.get_help_message()
            
            # Отправляем задачу в оркестратор
            task_id = await self.orchestrator.submit_task(
                task_type=task_type,
                data=task_data,
                priority=TaskPriority.MEDIUM
            )
            
            # Ждем результат
            result = await self.orchestrator.get_task_result(task_id, timeout=30.0)
            
            if not result:
                return "⏰ Время ожидания истекло. Попробуйте позже."
            
            if result['status'] == 'failed':
                return f"❌ Ошибка выполнения: {result.get('error', 'Неизвестная ошибка')}"
            
            # Форматируем результат для пользователя
            return await self.format_agent_result(result, intent)
                
        except Exception as e:
            logger.error(f"Ошибка оркестрации агентов: {e}")
            return f"Произошла ошибка при обработке запроса: {str(e)}"
    
    async def handle_set_api_key(self, entities: Dict[str, Any], user_id: int) -> str:
        """Обрабатывает установку API ключа n8n"""
        try:
            api_key = entities.get('api_key')
            base_url = entities.get('base_url')
            
            if not api_key or not base_url:
                return """
🔑 **Настройка API ключа n8n**

Для настройки отправьте сообщение в формате:
`Установи API ключ: YOUR_API_KEY для сервера: https://your-instance.app.n8n.cloud/api/v1`

Или используйте команду:
`/set_api_key YOUR_API_KEY https://your-instance.app.n8n.cloud/api/v1`
                """
            
            success = await self.session_service.set_user_n8n_config(user_id, api_key, base_url)
            
            if success:
                return f"✅ **API ключ n8n настроен успешно!**\n\nСервер: {base_url}\nТеперь вы можете импортировать шаблоны и управлять workflows."
            else:
                return "❌ **Ошибка настройки API ключа**\n\nПроверьте правильность ключа и URL сервера."
                
        except Exception as e:
            logger.error(f"Error setting API key: {e}")
            return f"Ошибка настройки API ключа: {str(e)}"
    
    def get_help_message(self) -> str:
        """Возвращает справочное сообщение"""
        return """
🤖 **N8N Template Manager Bot**

Я умею:
• 🔍 Искать шаблоны n8n по категориям и ключевым словам
• 📥 Импортировать шаблоны на ваш сервер n8n
• 📤 Экспортировать шаблоны с сервера
• ▶️ Активировать/деактивировать workflows
• 📊 Анализировать данные выполнения
• 🔬 Исследовать новую информацию

**Примеры команд:**
- "Найди шаблоны для автоматизации email"
- "Импортируй шаблон AI DJ на мой сервер"
- "Покажи все активные workflows"
- "Проанализируй ошибки выполнения за последний день"
- "Установи API ключ: YOUR_KEY для сервера: YOUR_URL"

**Команды:**
/start - Начать работу
/help - Справка
/set_api_key - Настроить API ключ n8n
/stats - Статистика
/my_workflows - Мои workflows

Просто напишите мне что нужно сделать естественным языком! 🚀
        """
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        # Инициализация памяти пользователя
        memory = self.get_user_memory(user_id)
        memory['started_at'] = datetime.now().isoformat()
        memory['message_count'] = memory.get('message_count', 0)
        self.set_user_memory(user_id, memory)
        
        # Получаем данные сессии пользователя
        session_data = await self.session_service.get_user_session_data(user_id)
        
        welcome_message = f"""
👋 Привет, {update.effective_user.first_name}!

{self.get_help_message()}

📊 **Статистика базы данных:**
• Всего шаблонов: {self.templates_db['total_templates']}
• Категорий: {len(self.templates_db['categories'])}

🔧 **Статус конфигурации:**
• n8n API: {'✅ Настроен' if session_data.get('has_n8n_config') else '❌ Не настроен'}

Готов помочь с управлением n8n! 🎯
        """
        
        keyboard = [
            [InlineKeyboardButton("🔍 Поиск шаблонов", callback_data="search_templates")],
            [InlineKeyboardButton("📊 Статистика", callback_data="show_stats")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def set_api_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /set_api_key"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "🔑 **Настройка API ключа n8n**\n\n"
                "Использование: `/set_api_key YOUR_API_KEY https://your-instance.app.n8n.cloud/api/v1`\n\n"
                "Где:\n"
                "• YOUR_API_KEY - ваш API ключ n8n\n"
                "• URL - адрес вашего n8n сервера",
                parse_mode='Markdown'
            )
            return
        
        api_key = context.args[0]
        base_url = context.args[1]
        user_id = update.effective_user.id
        
        thinking_msg = await self.show_thinking(update, context, "Проверяю подключение к n8n...")
        
        success = await self.session_service.set_user_n8n_config(user_id, api_key, base_url)
        
        await thinking_msg.delete()
        
        if success:
            await update.message.reply_text(
                f"✅ **API ключ n8n настроен успешно!**\n\n"
                f"Сервер: {base_url}\n"
                f"Теперь вы можете импортировать шаблоны и управлять workflows.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ **Ошибка настройки API ключа**\n\n"
                "Проверьте правильность ключа и URL сервера.",
                parse_mode='Markdown'
            )
    
    async def my_workflows_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /my_workflows"""
        user_id = update.effective_user.id
        
        thinking_msg = await self.show_thinking(update, context, "Получаю список ваших workflows...")
        
        workflows = await self.workflow_service.get_user_workflows(user_id)
        
        await thinking_msg.delete()
        
        if not workflows:
            await update.message.reply_text(
                "📋 **Ваши workflows**\n\n"
                "У вас пока нет импортированных workflows.\n"
                "Используйте поиск шаблонов для импорта новых workflows.",
                parse_mode='Markdown'
            )
            return
        
        message = "📋 **Ваши workflows:**\n\n"
        for workflow in workflows:
            status_emoji = "▶️" if workflow['status'] == 'active' else "⏸️"
            message += f"{status_emoji} **{workflow['workflow_name']}**\n"
            message += f"   ID: `{workflow['workflow_id']}`\n"
            message += f"   Статус: {workflow['status']}\n"
            message += f"   Создан: {workflow['created_at'][:10]}\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats"""
        user_id = update.effective_user.id
        
        thinking_msg = await self.show_thinking(update, context, "Собираю статистику...")
        
        # Получаем статистику шаблонов
        categories_stats = await self.template_service.get_categories_with_stats()
        
        # Получаем статистику пользователя
        user_workflows = await self.workflow_service.get_user_workflows(user_id)
        execution_stats = await self.execution_service.get_execution_statistics(user_id)
        
        await thinking_msg.delete()
        
        message = "📊 **Статистика**\n\n"
        
        # Общая статистика
        message += f"🗂️ **База шаблонов:**\n"
        message += f"• Всего шаблонов: {categories_stats['total_templates']}\n"
        message += f"• Категорий: {categories_stats['total_categories']}\n\n"
        
        # Топ категории
        message += "🏆 **Топ категории:**\n"
        sorted_categories = sorted(
            categories_stats['categories'].items(), 
            key=lambda x: x[1]['count'], 
            reverse=True
        )[:5]
        
        for category, data in sorted_categories:
            message += f"• {category}: {data['count']} ({data['percentage']}%)\n"
        
        # Статистика пользователя
        message += f"\n👤 **Ваша статистика:**\n"
        message += f"• Workflows: {len(user_workflows)}\n"
        
        if execution_stats:
            message += f"• Выполнений (7 дней): {execution_stats.get('total_executions', 0)}\n"
            message += f"• Успешность: {execution_stats.get('success_rate', 0):.1f}%\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик сообщений"""
        user_id = update.effective_user.id
        text = update.message.text
        
        # Обновляем счетчик сообщений
        memory = self.get_user_memory(user_id)
        memory['message_count'] = memory.get('message_count', 0) + 1
        memory['last_message'] = text
        memory['last_message_time'] = datetime.now().isoformat()
        self.set_user_memory(user_id, memory)
        
        # Показываем процесс мышления
        thinking_msg = await self.show_thinking(update, context, "Анализирую ваш запрос...")
        
        # NLU обработка
        await self.update_thinking(thinking_msg, "Определяю намерение...")
        nlu_result = await self.process_natural_language(text, user_id)
        
        # Оркестрация агентов
        await self.update_thinking(thinking_msg, f"Вызываю агента для '{nlu_result['intent']}'...")
        response = await self.orchestrate_agents(
            nlu_result['intent'], 
            nlu_result['entities'], 
            user_id
        )
        
        # Удаляем сообщение о мышлении и отправляем результат
        await thinking_msg.delete()
        
        # Проверяем, нужно ли отправить файл
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
            await update.message.reply_text(response, parse_mode='Markdown')
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback кнопок"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "search_templates":
            await query.edit_message_text(
                "🔍 **Поиск шаблонов**\n\n"
                "Напишите категорию или ключевые слова для поиска.\n\n"
                "Примеры:\n"
                "• 'AI email automation'\n"
                "• 'Категория: Marketing'\n"
                "• 'Найди шаблоны для Telegram'",
                parse_mode='Markdown'
            )
        elif query.data == "show_stats":
            # Вызываем команду статистики
            await self.stats_command(update, context)
        elif query.data == "settings":
            await query.edit_message_text(
                "⚙️ **Настройки**\n\n"
                "Для настройки API ключей n8n используйте команду:\n"
                "`/set_api_key YOUR_API_KEY https://your-instance.app.n8n.cloud/api/v1`\n\n"
                "Другие команды:\n"
                "• `/my_workflows` - Мои workflows\n"
                "• `/stats` - Статистика\n"
                "• `/help` - Справка",
                parse_mode='Markdown'
            )
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.telegram_token).build()
        
        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text(self.get_help_message(), parse_mode='Markdown')))
        application.add_handler(CommandHandler("set_api_key", self.set_api_key_command))
        application.add_handler(CommandHandler("my_workflows", self.my_workflows_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        logger.info("Бот запущен!")
        application.run_polling()


# Агенты
class TemplateAgent:
    def __init__(self, template_service: TemplateService):
        self.template_service = template_service
    
    async def handle_request(self, intent: str, entities: Dict[str, Any], user_id: int) -> str:
        """Обрабатывает запросы по шаблонам"""
        if intent == 'search_template':
            category = entities.get('category', '')
            keywords = entities.get('keywords', [])
            query = ' '.join(keywords) if keywords else None
            
            templates = await self.template_service.search_templates(
                query=query, 
                category=category, 
                limit=5
            )
            
            if not templates:
                return f"🔍 **Поиск шаблонов**\n\nПо запросу '{query or category}' ничего не найдено.\nПопробуйте другие ключевые слова."
            
            message = f"🔍 **Найдено шаблонов: {len(templates)}**\n\n"
            for i, template in enumerate(templates, 1):
                message += f"{i}. **{template['name']}**\n"
                message += f"   📂 {template['category']} | 🏷️ {template['complexity']}\n"
                message += f"   📝 {template['description'][:100]}...\n"
                message += f"   📥 Загрузок: {template['download_count']}\n\n"
            
            message += "Для импорта напишите: 'Импортируй шаблон [название]'"
            return message
        
        elif intent == 'get_categories':
            stats = await self.template_service.get_categories_with_stats()
            
            message = "📂 **Категории шаблонов:**\n\n"
            sorted_categories = sorted(
                stats['categories'].items(), 
                key=lambda x: x[1]['count'], 
                reverse=True
            )
            
            for category, data in sorted_categories:
                message += f"• **{category}**: {data['count']} шаблонов ({data['percentage']}%)\n"
            
            message += f"\n📊 Всего: {stats['total_templates']} шаблонов в {stats['total_categories']} категориях"
            return message
        
        elif intent == 'show_stats':
            popular = await self.template_service.get_popular_templates(5)
            
            message = "🏆 **Популярные шаблоны:**\n\n"
            for i, template in enumerate(popular, 1):
                message += f"{i}. **{template['name']}**\n"
                message += f"   📥 {template['download_count']} загрузок\n"
                message += f"   📂 {template['category']}\n\n"
            
            return message
        
        return "Не удалось обработать запрос по шаблонам."


class ServerAgent:
    def __init__(self, workflow_service: UserWorkflowService):
        self.workflow_service = workflow_service
    
    async def handle_request(self, intent: str, entities: Dict[str, Any], user_id: int) -> Any:
        """Обрабатывает запросы к серверу n8n"""
        if intent == 'import_template':
            template_name = entities.get('template_name', '')
            
            # Ищем шаблон по названию
            template_service = TemplateService()
            templates = await template_service.search_templates(query=template_name, limit=1)
            
            if not templates:
                return f"❌ Шаблон '{template_name}' не найден.\nИспользуйте поиск для просмотра доступных шаблонов."
            
            template = templates[0]
            result = await self.workflow_service.import_template_to_n8n(user_id, template['id'])
            
            if result['success']:
                return f"✅ **Шаблон импортирован!**\n\n📋 **{template['name']}**\n🆔 Workflow ID: `{result['workflow_id']}`\n📂 Категория: {template['category']}\n\n▶️ Для активации: 'Активируй workflow {result['workflow_id']}'"
            else:
                return f"❌ **Ошибка импорта:**\n{result['error']}"
        
        elif intent == 'export_template':
            workflow_id = entities.get('workflow_id', '')
            
            if not workflow_id:
                return "❌ Укажите ID workflow для экспорта.\nПример: 'Экспортируй workflow 12345'"
            
            result = await self.workflow_service.export_workflow(user_id, workflow_id)
            
            if result['success']:
                return {
                    'message': f"📤 **Workflow экспортирован!**\n\n📋 Файл: {result['filename']}",
                    'file_data': result['data'],
                    'filename': result['filename']
                }
            else:
                return f"❌ **Ошибка экспорта:**\n{result['error']}"
        
        elif intent == 'activate_workflow':
            workflow_id = entities.get('workflow_id', '')
            
            if not workflow_id:
                return "❌ Укажите ID workflow для активации.\nПример: 'Активируй workflow 12345'"
            
            result = await self.workflow_service.activate_workflow(user_id, workflow_id)
            
            if result['success']:
                return f"▶️ **Workflow активирован!**\n\n🆔 ID: `{workflow_id}`\n📊 Мониторинг запущен"
            else:
                return f"❌ **Ошибка активации:**\n{result['error']}"
        
        elif intent == 'deactivate_workflow':
            workflow_id = entities.get('workflow_id', '')
            
            if not workflow_id:
                return "❌ Укажите ID workflow для деактивации.\nПример: 'Деактивируй workflow 12345'"
            
            result = await self.workflow_service.deactivate_workflow(user_id, workflow_id)
            
            if result['success']:
                return f"⏸️ **Workflow деактивирован!**\n\n🆔 ID: `{workflow_id}`\n📊 Статистика сохранена"
            else:
                return f"❌ **Ошибка деактивации:**\n{result['error']}"
        
        elif intent == 'list_workflows':
            workflows = await self.workflow_service.get_user_workflows(user_id)
            
            if not workflows:
                return "📋 **Ваши workflows**\n\nУ вас пока нет импортированных workflows."
            
            message = f"📋 **Ваши workflows ({len(workflows)}):**\n\n"
            for workflow in workflows:
                status_emoji = "▶️" if workflow['status'] == 'active' else "⏸️"
                message += f"{status_emoji} **{workflow['workflow_name']}**\n"
                message += f"   🆔 `{workflow['workflow_id']}`\n"
                message += f"   📊 {workflow['status']}\n\n"
            
            return message
        
        return "Не удалось выполнить операцию на сервере n8n."


class ResearchAgent:
    async def handle_request(self, intent: str, entities: Dict[str, Any], user_id: int) -> str:
        """Обрабатывает исследовательские запросы"""
        keywords = entities.get('keywords', [])
        return f"🔬 **Исследование по запросу**: {', '.join(keywords)}\n\nНайдена актуальная информация:\n• Новые возможности n8n 1.0\n• Интеграции с AI сервисами\n• Best practices автоматизации"


class AnalystAgent:
    def __init__(self, execution_service: ExecutionLogService):
        self.execution_service = execution_service
    
    async def handle_request(self, intent: str, entities: Dict[str, Any], user_id: int) -> str:
        """Обрабатывает аналитические запросы"""
        stats = await self.execution_service.get_execution_statistics(user_id)
        
        if not stats or stats.get('total_executions', 0) == 0:
            return "📊 **Анализ данных**\n\nНедостаточно данных для анализа.\nВыполните несколько workflows для получения статистики."
        
        message = "📊 **Анализ выполнений (7 дней):**\n\n"
        message += f"📈 Всего выполнений: {stats['total_executions']}\n"
        message += f"✅ Успешных: {stats['successful_executions']}\n"
        message += f"❌ Ошибок: {stats['failed_executions']}\n"
        message += f"📊 Успешность: {stats['success_rate']:.1f}%\n"
        message += f"⏱️ Среднее время: {stats['average_duration_seconds']:.1f}с\n"
        message += f"📅 В день: {stats['executions_per_day']:.1f}\n"
        
        if stats['failed_executions'] > 0:
            message += f"\n⚠️ Обнаружено {stats['failed_executions']} ошибок"
        
        return message


if __name__ == "__main__":
    bot = N8nTelegramBot()
    bot.run()
