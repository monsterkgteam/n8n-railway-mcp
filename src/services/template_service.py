import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import aiohttp
import os

from src.models.template import db, Template, UserWorkflow, UserSession, ExecutionLog
from src.services.n8n_api import N8nApiClient, N8nTemplateManager, N8nMonitor

logger = logging.getLogger(__name__)

class TemplateService:
    """Сервис для управления шаблонами n8n"""
    
    def __init__(self):
        self.templates_cache = {}
        self.last_cache_update = None
    
    async def search_templates(self, query: str = None, category: str = None, 
                             complexity: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Поиск шаблонов по различным критериям"""
        try:
            templates_query = Template.query.filter_by(is_active=True)
            
            if category:
                templates_query = templates_query.filter_by(category=category)
            
            if complexity:
                templates_query = templates_query.filter(Template.complexity.contains(complexity))
            
            if query:
                search_filter = db.or_(
                    Template.name.contains(query),
                    Template.description.contains(query),
                    Template.tags.contains(query)
                )
                templates_query = templates_query.filter(search_filter)
            
            templates = templates_query.order_by(Template.download_count.desc()).limit(limit).all()
            
            return [template.to_dict() for template in templates]
            
        except Exception as e:
            logger.error(f"Error searching templates: {e}")
            return []
    
    async def get_template_by_id(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Получает шаблон по ID"""
        try:
            template = Template.query.get(template_id)
            if template and template.is_active:
                # Увеличиваем счетчик просмотров
                template.download_count += 1
                db.session.commit()
                
                result = template.to_dict()
                if template.json_content:
                    result['json_content'] = json.loads(template.json_content)
                
                return result
            return None
            
        except Exception as e:
            logger.error(f"Error getting template by ID: {e}")
            return None
    
    async def get_popular_templates(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает популярные шаблоны"""
        try:
            templates = Template.get_popular_templates(limit)
            return [template.to_dict() for template in templates]
            
        except Exception as e:
            logger.error(f"Error getting popular templates: {e}")
            return []
    
    async def get_categories_with_stats(self) -> Dict[str, Any]:
        """Получает категории с статистикой"""
        try:
            stats = Template.get_categories_stats()
            categories = {}
            
            for category, count in stats:
                categories[category] = {
                    'count': count,
                    'percentage': 0  # Будет вычислено позже
                }
            
            total = sum(cat['count'] for cat in categories.values())
            for category in categories:
                categories[category]['percentage'] = round(
                    categories[category]['count'] / total * 100, 1
                ) if total > 0 else 0
            
            return {
                'categories': categories,
                'total_templates': total,
                'total_categories': len(categories)
            }
            
        except Exception as e:
            logger.error(f"Error getting categories stats: {e}")
            return {'categories': {}, 'total_templates': 0, 'total_categories': 0}
    
    async def import_template_to_database(self, template_data: Dict[str, Any]) -> bool:
        """Импортирует шаблон в базу данных"""
        try:
            # Проверяем, существует ли уже такой шаблон
            existing = Template.query.filter_by(name=template_data['name']).first()
            if existing:
                logger.info(f"Template '{template_data['name']}' already exists")
                return False
            
            template = Template(
                name=template_data.get('name', 'Unknown Template'),
                description=template_data.get('description', ''),
                category=template_data.get('category', 'Other'),
                complexity=template_data.get('complexity', 'Unknown'),
                json_content=json.dumps(template_data.get('json_content', {})),
                download_url=template_data.get('download_url', ''),
                author=template_data.get('author', ''),
                tags=json.dumps(template_data.get('tags', [])),
                nodes_used=json.dumps(template_data.get('nodes_used', [])),
                rating=template_data.get('rating', 0.0)
            )
            
            db.session.add(template)
            db.session.commit()
            
            logger.info(f"Template '{template_data['name']}' imported to database")
            return True
            
        except Exception as e:
            logger.error(f"Error importing template to database: {e}")
            db.session.rollback()
            return False


class UserWorkflowService:
    """Сервис для управления workflows пользователей"""
    
    def __init__(self):
        pass
    
    async def get_user_n8n_client(self, user_id: int) -> Optional[N8nApiClient]:
        """Получает n8n API клиент для пользователя"""
        try:
            session = UserSession.query.filter_by(user_id=user_id, is_active=True).first()
            if not session or not session.n8n_api_key or not session.n8n_base_url:
                return None
            
            return N8nApiClient(session.n8n_base_url, session.n8n_api_key)
            
        except Exception as e:
            logger.error(f"Error getting user n8n client: {e}")
            return None
    
    async def import_template_to_n8n(self, user_id: int, template_id: int) -> Dict[str, Any]:
        """Импортирует шаблон на сервер n8n пользователя"""
        try:
            # Получаем шаблон
            template = Template.query.get(template_id)
            if not template:
                return {'success': False, 'error': 'Template not found'}
            
            # Получаем n8n клиент пользователя
            api_client = await self.get_user_n8n_client(user_id)
            if not api_client:
                return {
                    'success': False, 
                    'error': 'n8n API not configured. Use /set_api_key command'
                }
            
            async with api_client:
                # Создаем менеджер шаблонов
                template_manager = N8nTemplateManager(api_client)
                
                # Импортируем шаблон
                template_json = json.loads(template.json_content) if template.json_content else {}
                result = await template_manager.import_template(template_json, template.name)
                
                if result['success']:
                    # Сохраняем информацию о workflow пользователя
                    user_workflow = UserWorkflow(
                        user_id=user_id,
                        workflow_id=result['workflow_id'],
                        template_id=template_id,
                        workflow_name=template.name,
                        status='inactive'
                    )
                    
                    db.session.add(user_workflow)
                    db.session.commit()
                    
                    # Увеличиваем счетчик загрузок
                    template.download_count += 1
                    db.session.commit()
                
                return result
                
        except Exception as e:
            logger.error(f"Error importing template to n8n: {e}")
            return {'success': False, 'error': str(e)}
    
    async def activate_workflow(self, user_id: int, workflow_id: str) -> Dict[str, Any]:
        """Активирует workflow пользователя"""
        try:
            api_client = await self.get_user_n8n_client(user_id)
            if not api_client:
                return {'success': False, 'error': 'n8n API not configured'}
            
            async with api_client:
                result = await api_client.activate_workflow(workflow_id)
                
                # Обновляем статус в базе данных
                user_workflow = UserWorkflow.query.filter_by(
                    user_id=user_id, 
                    workflow_id=workflow_id
                ).first()
                
                if user_workflow:
                    user_workflow.status = 'active'
                    db.session.commit()
                
                return {
                    'success': True,
                    'message': f'Workflow {workflow_id} activated successfully',
                    'data': result
                }
                
        except Exception as e:
            logger.error(f"Error activating workflow: {e}")
            return {'success': False, 'error': str(e)}
    
    async def deactivate_workflow(self, user_id: int, workflow_id: str) -> Dict[str, Any]:
        """Деактивирует workflow пользователя"""
        try:
            api_client = await self.get_user_n8n_client(user_id)
            if not api_client:
                return {'success': False, 'error': 'n8n API not configured'}
            
            async with api_client:
                result = await api_client.deactivate_workflow(workflow_id)
                
                # Обновляем статус в базе данных
                user_workflow = UserWorkflow.query.filter_by(
                    user_id=user_id, 
                    workflow_id=workflow_id
                ).first()
                
                if user_workflow:
                    user_workflow.status = 'inactive'
                    db.session.commit()
                
                return {
                    'success': True,
                    'message': f'Workflow {workflow_id} deactivated successfully',
                    'data': result
                }
                
        except Exception as e:
            logger.error(f"Error deactivating workflow: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_user_workflows(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает список workflows пользователя"""
        try:
            workflows = UserWorkflow.query.filter_by(user_id=user_id).all()
            return [workflow.to_dict() for workflow in workflows]
            
        except Exception as e:
            logger.error(f"Error getting user workflows: {e}")
            return []
    
    async def export_workflow(self, user_id: int, workflow_id: str) -> Dict[str, Any]:
        """Экспортирует workflow пользователя"""
        try:
            api_client = await self.get_user_n8n_client(user_id)
            if not api_client:
                return {'success': False, 'error': 'n8n API not configured'}
            
            async with api_client:
                template_manager = N8nTemplateManager(api_client)
                return await template_manager.export_workflow(workflow_id)
                
        except Exception as e:
            logger.error(f"Error exporting workflow: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_workflow_analytics(self, user_id: int, workflow_id: str, days: int = 7) -> Dict[str, Any]:
        """Получает аналитику workflow"""
        try:
            api_client = await self.get_user_n8n_client(user_id)
            if not api_client:
                return {'success': False, 'error': 'n8n API not configured'}
            
            async with api_client:
                monitor = N8nMonitor(api_client)
                analytics = await monitor.get_workflow_analytics(workflow_id, days)
                
                return {
                    'success': True,
                    'data': analytics
                }
                
        except Exception as e:
            logger.error(f"Error getting workflow analytics: {e}")
            return {'success': False, 'error': str(e)}


class UserSessionService:
    """Сервис для управления сессиями пользователей"""
    
    def __init__(self):
        pass
    
    async def set_user_n8n_config(self, user_id: int, api_key: str, base_url: str) -> bool:
        """Устанавливает конфигурацию n8n для пользователя"""
        try:
            session = UserSession.query.filter_by(user_id=user_id, is_active=True).first()
            
            if not session:
                session = UserSession(user_id=user_id)
                db.session.add(session)
            
            # TODO: Добавить шифрование API ключа
            session.n8n_api_key = api_key
            session.n8n_base_url = base_url.rstrip('/')
            session.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Проверяем подключение
            api_client = N8nApiClient(base_url, api_key)
            async with api_client:
                health = await api_client.health_check()
                if health['status'] == 'healthy':
                    logger.info(f"n8n API configured successfully for user {user_id}")
                    return True
                else:
                    logger.error(f"n8n API health check failed for user {user_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error setting user n8n config: {e}")
            db.session.rollback()
            return False
    
    async def get_user_session_data(self, user_id: int) -> Dict[str, Any]:
        """Получает данные сессии пользователя"""
        try:
            session = UserSession.query.filter_by(user_id=user_id, is_active=True).first()
            
            if not session:
                return {}
            
            return {
                'has_n8n_config': bool(session.n8n_api_key and session.n8n_base_url),
                'session_data': session.get_session_data(),
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting user session data: {e}")
            return {}
    
    async def update_user_session_data(self, user_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет данные сессии пользователя"""
        try:
            session = UserSession.query.filter_by(user_id=user_id, is_active=True).first()
            
            if not session:
                session = UserSession(user_id=user_id)
                db.session.add(session)
            
            session.set_session_data(data)
            db.session.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating user session data: {e}")
            db.session.rollback()
            return False


class ExecutionLogService:
    """Сервис для логирования выполнений"""
    
    def __init__(self):
        pass
    
    async def log_execution(self, user_id: int, workflow_id: str, execution_data: Dict[str, Any]) -> bool:
        """Логирует выполнение workflow"""
        try:
            execution_log = ExecutionLog(
                user_id=user_id,
                workflow_id=workflow_id,
                execution_id=execution_data.get('execution_id'),
                status=execution_data.get('status'),
                start_time=execution_data.get('start_time'),
                end_time=execution_data.get('end_time'),
                duration=execution_data.get('duration'),
                error_message=execution_data.get('error_message')
            )
            
            db.session.add(execution_log)
            db.session.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Error logging execution: {e}")
            db.session.rollback()
            return False
    
    async def get_user_execution_logs(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получает логи выполнений пользователя"""
        try:
            logs = ExecutionLog.query.filter_by(user_id=user_id)\
                                   .order_by(ExecutionLog.created_at.desc())\
                                   .limit(limit).all()
            
            return [log.to_dict() for log in logs]
            
        except Exception as e:
            logger.error(f"Error getting user execution logs: {e}")
            return []
    
    async def get_execution_statistics(self, user_id: int, days: int = 7) -> Dict[str, Any]:
        """Получает статистику выполнений пользователя"""
        try:
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            logs = ExecutionLog.query.filter(
                ExecutionLog.user_id == user_id,
                ExecutionLog.created_at >= cutoff_date
            ).all()
            
            total_executions = len(logs)
            successful = len([log for log in logs if log.status == 'success'])
            failed = len([log for log in logs if log.status == 'error'])
            
            # Вычисляем среднее время выполнения
            durations = [log.duration for log in logs if log.duration]
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            return {
                'period_days': days,
                'total_executions': total_executions,
                'successful_executions': successful,
                'failed_executions': failed,
                'success_rate': successful / total_executions * 100 if total_executions > 0 else 0,
                'average_duration_seconds': avg_duration,
                'executions_per_day': total_executions / days
            }
            
        except Exception as e:
            logger.error(f"Error getting execution statistics: {e}")
            return {}
