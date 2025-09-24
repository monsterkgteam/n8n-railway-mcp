from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Template(db.Model):
    """Модель для хранения шаблонов n8n"""
    __tablename__ = 'templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text)
    category = db.Column(db.String(100), nullable=False, index=True)
    complexity = db.Column(db.String(50))  # Free/Paid, Beginner/Intermediate/Advanced
    json_content = db.Column(db.Text)  # JSON содержимое шаблона
    download_url = db.Column(db.String(500))
    author = db.Column(db.String(100))
    tags = db.Column(db.Text)  # JSON массив тегов
    nodes_used = db.Column(db.Text)  # JSON массив используемых нодов
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    download_count = db.Column(db.Integer, default=0)
    rating = db.Column(db.Float, default=0.0)
    
    def __repr__(self):
        return f'<Template {self.name}>'
    
    def to_dict(self):
        """Преобразует объект в словарь"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'complexity': self.complexity,
            'author': self.author,
            'tags': json.loads(self.tags) if self.tags else [],
            'nodes_used': json.loads(self.nodes_used) if self.nodes_used else [],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'download_count': self.download_count,
            'rating': self.rating
        }
    
    @classmethod
    def search_by_category(cls, category):
        """Поиск шаблонов по категории"""
        return cls.query.filter_by(category=category, is_active=True).all()
    
    @classmethod
    def search_by_keywords(cls, keywords):
        """Поиск шаблонов по ключевым словам"""
        query = cls.query.filter(cls.is_active == True)
        
        for keyword in keywords:
            query = query.filter(
                db.or_(
                    cls.name.contains(keyword),
                    cls.description.contains(keyword),
                    cls.tags.contains(keyword)
                )
            )
        
        return query.all()
    
    @classmethod
    def get_popular_templates(cls, limit=10):
        """Получить популярные шаблоны"""
        return cls.query.filter_by(is_active=True)\
                       .order_by(cls.download_count.desc())\
                       .limit(limit).all()
    
    @classmethod
    def get_categories_stats(cls):
        """Получить статистику по категориям"""
        return db.session.query(
            cls.category,
            db.func.count(cls.id).label('count')
        ).filter_by(is_active=True)\
         .group_by(cls.category)\
         .all()


class UserWorkflow(db.Model):
    """Модель для отслеживания workflows пользователей"""
    __tablename__ = 'user_workflows'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False, index=True)  # Telegram user ID
    workflow_id = db.Column(db.String(100), nullable=False)  # n8n workflow ID
    template_id = db.Column(db.Integer, db.ForeignKey('templates.id'))
    workflow_name = db.Column(db.String(255))
    status = db.Column(db.String(50), default='inactive')  # active, inactive, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_execution = db.Column(db.DateTime)
    execution_count = db.Column(db.Integer, default=0)
    error_count = db.Column(db.Integer, default=0)
    
    # Связь с шаблоном
    template = db.relationship('Template', backref='user_workflows')
    
    def __repr__(self):
        return f'<UserWorkflow {self.workflow_name} for user {self.user_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'workflow_name': self.workflow_name,
            'status': self.status,
            'template_name': self.template.name if self.template else None,
            'created_at': self.created_at.isoformat(),
            'last_execution': self.last_execution.isoformat() if self.last_execution else None,
            'execution_count': self.execution_count,
            'error_count': self.error_count
        }


class UserSession(db.Model):
    """Модель для хранения сессий пользователей"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False, index=True)
    session_data = db.Column(db.Text)  # JSON данные сессии
    n8n_api_key = db.Column(db.String(500))  # Зашифрованный API ключ
    n8n_base_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<UserSession for user {self.user_id}>'
    
    def get_session_data(self):
        """Получить данные сессии"""
        return json.loads(self.session_data) if self.session_data else {}
    
    def set_session_data(self, data):
        """Установить данные сессии"""
        self.session_data = json.dumps(data)
        self.updated_at = datetime.utcnow()


class ExecutionLog(db.Model):
    """Модель для логирования выполнений"""
    __tablename__ = 'execution_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False, index=True)
    workflow_id = db.Column(db.String(100))
    execution_id = db.Column(db.String(100))
    status = db.Column(db.String(50))  # success, error, running
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    duration = db.Column(db.Float)  # в секундах
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ExecutionLog {self.execution_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'execution_id': self.execution_id,
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat()
        }
