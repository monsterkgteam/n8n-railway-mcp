import os
import sys
import threading
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, jsonify
from src.models.user import db as user_db
from src.models.template import db as template_db, Template, UserWorkflow, UserSession, ExecutionLog
from src.routes.user import user_bp
from src.routes.template import template_bp
from src.telegram_bot import N8nTelegramBot

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'asdf#FGSgvasgf$5$WGT')

# Регистрация blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(template_bp, url_prefix='/api')

# Конфигурация базы данных
database_path = os.path.join(os.path.dirname(__file__), 'database', 'app.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{database_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация баз данных
user_db.init_app(app)
template_db.init_app(app)

# Создание таблиц
with app.app_context():
    user_db.create_all()
    template_db.create_all()
    logger.info("База данных инициализирована")

# Глобальная переменная для бота
telegram_bot = None

def start_telegram_bot():
    """Запуск Telegram бота в отдельном потоке"""
    global telegram_bot
    try:
        telegram_bot = N8nTelegramBot()
        logger.info("Запуск Telegram бота...")
        telegram_bot.run()
    except Exception as e:
        logger.error(f"Ошибка запуска Telegram бота: {e}")

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """Обслуживание статических файлов"""
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка состояния сервиса"""
    return jsonify({
        'status': 'healthy',
        'telegram_bot': 'running' if telegram_bot else 'not_started',
        'database': 'connected'
    })

@app.route('/api/bot/status', methods=['GET'])
def bot_status():
    """Статус Telegram бота"""
    global telegram_bot
    
    if not telegram_bot:
        return jsonify({
            'status': 'not_running',
            'message': 'Telegram bot is not started'
        })
    
    # Получаем статистику из базы данных
    with app.app_context():
        total_templates = Template.query.filter_by(is_active=True).count()
        total_users = UserSession.query.filter_by(is_active=True).count()
        total_workflows = UserWorkflow.query.count()
        
    return jsonify({
        'status': 'running',
        'statistics': {
            'total_templates': total_templates,
            'total_users': total_users,
            'total_workflows': total_workflows
        }
    })

@app.route('/api/templates/import', methods=['POST'])
def import_templates():
    """Импорт шаблонов в базу данных"""
    try:
        # Здесь можно добавить логику импорта шаблонов из файлов анализа
        # Пока что возвращаем заглушку
        return jsonify({
            'success': True,
            'message': 'Templates import functionality will be implemented'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    """Обработчик 404 ошибки"""
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Обработчик 500 ошибки"""
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Проверяем наличие необходимых переменных окружения
    required_env_vars = ['TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Отсутствуют переменные окружения: {', '.join(missing_vars)}")
        logger.info("Создайте файл .env на основе .env.example")
    else:
        # Запускаем Telegram бота в отдельном потоке
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
        logger.info("Telegram бот запущен в отдельном потоке")
    
    # Запускаем Flask приложение
    logger.info("Запуск Flask приложения...")
    app.run(host='0.0.0.0', port=5000, debug=False)  # debug=False для production
