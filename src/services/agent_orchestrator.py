import asyncio
import logging
import json
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import uuid

from src.services.thinking_service import ThinkingService, ThinkingType, ThoughtLevel, ReflectionEngine
from src.services.voice_service import MemoryService
from src.services.template_service import TemplateService, UserWorkflowService
from src.services.n8n_api import N8nApiClient, N8nMonitor

logger = logging.getLogger(__name__)

class AgentRole(Enum):
    """Роли агентов в системе"""
    COORDINATOR = "coordinator"        # Координатор
    TEMPLATE_SPECIALIST = "template"   # Специалист по шаблонам
    SERVER_MANAGER = "server"          # Менеджер сервера
    RESEARCHER = "researcher"          # Исследователь
    ANALYST = "analyst"               # Аналитик
    MONITOR = "monitor"               # Монитор системы
    ASSISTANT = "assistant"           # Помощник пользователя

class TaskPriority(Enum):
    """Приоритеты задач"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4

class TaskStatus(Enum):
    """Статусы задач"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Agent:
    """Базовый класс агента"""
    
    def __init__(self, 
                 name: str, 
                 role: AgentRole, 
                 thinking_service: ThinkingService,
                 memory_service: MemoryService):
        self.name = name
        self.role = role
        self.thinking_service = thinking_service
        self.memory_service = memory_service
        self.capabilities = set()
        self.current_task = None
        self.performance_metrics = {
            'tasks_completed': 0,
            'tasks_failed': 0,
            'average_response_time': 0.0,
            'last_activity': None
        }
        self.is_busy = False
        self.created_at = datetime.now()
    
    async def think(self, context: Dict[str, Any], thinking_type: ThinkingType) -> Dict[str, Any]:
        """Заставляет агента думать"""
        return await self.thinking_service.think(
            self.name, context, thinking_type, ThoughtLevel.DEEP
        )
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет задачу (должен быть переопределен в наследниках)"""
        raise NotImplementedError("Subclasses must implement execute_task")
    
    async def reflect_on_performance(self) -> Dict[str, Any]:
        """Рефлексия над собственной производительностью"""
        context = {
            'performance_metrics': self.performance_metrics,
            'recent_tasks': await self.get_recent_tasks(),
            'capabilities': list(self.capabilities)
        }
        
        return await self.thinking_service.think(
            self.name, context, ThinkingType.REFLECTION, ThoughtLevel.METACOGNITIVE
        )
    
    async def get_recent_tasks(self) -> List[Dict[str, Any]]:
        """Получает последние задачи агента"""
        return await self.memory_service.get_short_term(
            hash(self.name), 'recent_tasks'
        ) or []
    
    def update_performance(self, task_result: Dict[str, Any]):
        """Обновляет метрики производительности"""
        if task_result.get('success', False):
            self.performance_metrics['tasks_completed'] += 1
        else:
            self.performance_metrics['tasks_failed'] += 1
        
        self.performance_metrics['last_activity'] = datetime.now().isoformat()
    
    def get_status(self) -> Dict[str, Any]:
        """Возвращает статус агента"""
        return {
            'name': self.name,
            'role': self.role.value,
            'is_busy': self.is_busy,
            'current_task': self.current_task,
            'capabilities': list(self.capabilities),
            'performance': self.performance_metrics,
            'uptime': (datetime.now() - self.created_at).total_seconds()
        }

class TemplateAgent(Agent):
    """Агент для работы с шаблонами"""
    
    def __init__(self, thinking_service: ThinkingService, memory_service: MemoryService):
        super().__init__("TemplateAgent", AgentRole.TEMPLATE_SPECIALIST, thinking_service, memory_service)
        self.template_service = TemplateService()
        self.capabilities = {
            'search_templates', 'analyze_templates', 'categorize_templates',
            'recommend_templates', 'validate_templates'
        }
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет задачи по работе с шаблонами"""
        try:
            self.is_busy = True
            self.current_task = task
            
            task_type = task.get('type')
            task_data = task.get('data', {})
            
            # Думаем о задаче
            thinking_context = {
                'task_type': task_type,
                'task_data': task_data,
                'agent_capabilities': list(self.capabilities)
            }
            
            thought = await self.think(thinking_context, ThinkingType.ANALYSIS)
            
            result = None
            
            if task_type == 'search_templates':
                result = await self._search_templates(task_data)
            elif task_type == 'analyze_template':
                result = await self._analyze_template(task_data)
            elif task_type == 'recommend_templates':
                result = await self._recommend_templates(task_data)
            elif task_type == 'categorize_templates':
                result = await self._categorize_templates(task_data)
            else:
                result = {
                    'success': False,
                    'error': f'Unknown task type: {task_type}'
                }
            
            # Добавляем мысли к результату
            result['agent_thoughts'] = thought
            
            self.update_performance(result)
            return result
            
        except Exception as e:
            logger.error(f"TemplateAgent task execution error: {e}")
            result = {'success': False, 'error': str(e)}
            self.update_performance(result)
            return result
        finally:
            self.is_busy = False
            self.current_task = None
    
    async def _search_templates(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Поиск шаблонов"""
        query = data.get('query', '')
        category = data.get('category', '')
        limit = data.get('limit', 10)
        
        templates = await self.template_service.search_templates(
            query=query, category=category, limit=limit
        )
        
        return {
            'success': True,
            'templates': templates,
            'count': len(templates),
            'search_params': {'query': query, 'category': category}
        }
    
    async def _analyze_template(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Анализ шаблона"""
        template_id = data.get('template_id')
        
        if not template_id:
            return {'success': False, 'error': 'Template ID required'}
        
        template = await self.template_service.get_template_by_id(template_id)
        
        if not template:
            return {'success': False, 'error': 'Template not found'}
        
        # Анализируем шаблон
        analysis = {
            'complexity_score': self._calculate_complexity(template),
            'node_count': len(template.get('json_content', {}).get('nodes', [])),
            'category_relevance': self._assess_category_relevance(template),
            'potential_issues': self._identify_potential_issues(template)
        }
        
        return {
            'success': True,
            'template': template,
            'analysis': analysis
        }
    
    async def _recommend_templates(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Рекомендация шаблонов"""
        user_preferences = data.get('preferences', {})
        user_history = data.get('history', [])
        
        # Получаем популярные шаблоны
        popular = await self.template_service.get_popular_templates(20)
        
        # Фильтруем по предпочтениям
        recommendations = []
        for template in popular:
            score = self._calculate_recommendation_score(template, user_preferences, user_history)
            if score > 0.5:
                recommendations.append({
                    'template': template,
                    'score': score,
                    'reason': self._get_recommendation_reason(template, user_preferences)
                })
        
        # Сортируем по скору
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        
        return {
            'success': True,
            'recommendations': recommendations[:10],
            'total_analyzed': len(popular)
        }
    
    async def _categorize_templates(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Категоризация шаблонов"""
        stats = await self.template_service.get_categories_with_stats()
        
        return {
            'success': True,
            'categories': stats['categories'],
            'total_templates': stats['total_templates'],
            'total_categories': stats['total_categories']
        }
    
    def _calculate_complexity(self, template: Dict[str, Any]) -> float:
        """Вычисляет сложность шаблона"""
        try:
            json_content = template.get('json_content', {})
            nodes = json_content.get('nodes', [])
            connections = json_content.get('connections', {})
            
            # Базовая сложность по количеству узлов
            node_complexity = len(nodes) * 0.1
            
            # Сложность по связям
            connection_complexity = len(connections) * 0.2
            
            # Сложность по типам узлов
            node_types = set(node.get('type', '') for node in nodes)
            type_complexity = len(node_types) * 0.15
            
            total_complexity = min(node_complexity + connection_complexity + type_complexity, 1.0)
            return round(total_complexity, 2)
            
        except Exception as e:
            logger.error(f"Error calculating complexity: {e}")
            return 0.5
    
    def _assess_category_relevance(self, template: Dict[str, Any]) -> float:
        """Оценивает релевантность категории"""
        # Простая оценка на основе соответствия названия и описания категории
        category = template.get('category', '').lower()
        name = template.get('name', '').lower()
        description = template.get('description', '').lower()
        
        relevance = 0.5  # Базовая релевантность
        
        if category in name:
            relevance += 0.2
        if category in description:
            relevance += 0.1
        
        return min(relevance, 1.0)
    
    def _identify_potential_issues(self, template: Dict[str, Any]) -> List[str]:
        """Выявляет потенциальные проблемы в шаблоне"""
        issues = []
        
        json_content = template.get('json_content', {})
        nodes = json_content.get('nodes', [])
        
        if len(nodes) == 0:
            issues.append("Шаблон не содержит узлов")
        
        if len(nodes) > 50:
            issues.append("Очень сложный шаблон (>50 узлов)")
        
        # Проверяем наличие учетных данных
        credential_nodes = [node for node in nodes if 'credentials' in str(node)]
        if credential_nodes:
            issues.append("Требует настройки учетных данных")
        
        return issues
    
    def _calculate_recommendation_score(self, template: Dict[str, Any], 
                                      preferences: Dict[str, Any], 
                                      history: List[Dict[str, Any]]) -> float:
        """Вычисляет скор рекомендации"""
        score = 0.5  # Базовый скор
        
        # Скор по категории
        preferred_categories = preferences.get('categories', [])
        if template.get('category') in preferred_categories:
            score += 0.3
        
        # Скор по сложности
        preferred_complexity = preferences.get('complexity', 'medium')
        template_complexity = template.get('complexity', 'unknown')
        if template_complexity == preferred_complexity:
            score += 0.2
        
        # Скор по популярности
        download_count = template.get('download_count', 0)
        if download_count > 100:
            score += 0.1
        
        return min(score, 1.0)
    
    def _get_recommendation_reason(self, template: Dict[str, Any], 
                                 preferences: Dict[str, Any]) -> str:
        """Возвращает причину рекомендации"""
        reasons = []
        
        if template.get('category') in preferences.get('categories', []):
            reasons.append(f"соответствует предпочитаемой категории {template.get('category')}")
        
        if template.get('download_count', 0) > 100:
            reasons.append("популярный шаблон")
        
        if template.get('rating', 0) > 4.0:
            reasons.append("высокий рейтинг")
        
        return ", ".join(reasons) if reasons else "общая рекомендация"

class ServerAgent(Agent):
    """Агент для управления сервером n8n"""
    
    def __init__(self, thinking_service: ThinkingService, memory_service: MemoryService):
        super().__init__("ServerAgent", AgentRole.SERVER_MANAGER, thinking_service, memory_service)
        self.workflow_service = UserWorkflowService()
        self.capabilities = {
            'import_templates', 'export_workflows', 'activate_workflows',
            'deactivate_workflows', 'monitor_executions', 'manage_credentials'
        }
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет задачи по управлению сервером"""
        try:
            self.is_busy = True
            self.current_task = task
            
            task_type = task.get('type')
            task_data = task.get('data', {})
            user_id = task_data.get('user_id')
            
            # Думаем о задаче
            thinking_context = {
                'task_type': task_type,
                'user_id': user_id,
                'server_capabilities': list(self.capabilities)
            }
            
            thought = await self.think(thinking_context, ThinkingType.PLANNING)
            
            result = None
            
            if task_type == 'import_template':
                result = await self._import_template(task_data)
            elif task_type == 'export_workflow':
                result = await self._export_workflow(task_data)
            elif task_type == 'activate_workflow':
                result = await self._activate_workflow(task_data)
            elif task_type == 'deactivate_workflow':
                result = await self._deactivate_workflow(task_data)
            elif task_type == 'get_workflows':
                result = await self._get_workflows(task_data)
            elif task_type == 'monitor_system':
                result = await self._monitor_system(task_data)
            else:
                result = {
                    'success': False,
                    'error': f'Unknown task type: {task_type}'
                }
            
            result['agent_thoughts'] = thought
            self.update_performance(result)
            return result
            
        except Exception as e:
            logger.error(f"ServerAgent task execution error: {e}")
            result = {'success': False, 'error': str(e)}
            self.update_performance(result)
            return result
        finally:
            self.is_busy = False
            self.current_task = None
    
    async def _import_template(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Импорт шаблона"""
        user_id = data.get('user_id')
        template_id = data.get('template_id')
        
        return await self.workflow_service.import_template_to_n8n(user_id, template_id)
    
    async def _export_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Экспорт workflow"""
        user_id = data.get('user_id')
        workflow_id = data.get('workflow_id')
        
        return await self.workflow_service.export_workflow(user_id, workflow_id)
    
    async def _activate_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Активация workflow"""
        user_id = data.get('user_id')
        workflow_id = data.get('workflow_id')
        
        return await self.workflow_service.activate_workflow(user_id, workflow_id)
    
    async def _deactivate_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Деактивация workflow"""
        user_id = data.get('user_id')
        workflow_id = data.get('workflow_id')
        
        return await self.workflow_service.deactivate_workflow(user_id, workflow_id)
    
    async def _get_workflows(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Получение списка workflows"""
        user_id = data.get('user_id')
        
        workflows = await self.workflow_service.get_user_workflows(user_id)
        
        return {
            'success': True,
            'workflows': workflows,
            'count': len(workflows)
        }
    
    async def _monitor_system(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Мониторинг системы"""
        user_id = data.get('user_id')
        
        # Получаем клиент n8n для пользователя
        api_client = await self.workflow_service.get_user_n8n_client(user_id)
        
        if not api_client:
            return {
                'success': False,
                'error': 'n8n API not configured'
            }
        
        async with api_client:
            monitor = N8nMonitor(api_client)
            status = await monitor.get_system_status()
            
            return {
                'success': True,
                'system_status': status
            }

class AgentOrchestrator:
    """Оркестратор агентов"""
    
    def __init__(self):
        self.thinking_service = ThinkingService()
        self.memory_service = MemoryService()
        self.reflection_engine = ReflectionEngine(self.thinking_service)
        
        # Инициализация агентов
        self.agents = {
            'template': TemplateAgent(self.thinking_service, self.memory_service),
            'server': ServerAgent(self.thinking_service, self.memory_service),
            'coordinator': CoordinatorAgent(self.thinking_service, self.memory_service),
            'monitor': MonitorAgent(self.thinking_service, self.memory_service)
        }
        
        # Очередь задач
        self.task_queue = asyncio.Queue()
        self.active_tasks = {}
        self.completed_tasks = []
        
        # Метрики системы
        self.system_metrics = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'average_response_time': 0.0,
            'system_uptime': datetime.now()
        }
        
        # Запускаем фоновые процессы
        self.running = False
    
    async def start(self):
        """Запуск оркестратора"""
        self.running = True
        
        # Запускаем обработчик задач
        asyncio.create_task(self._task_processor())
        
        # Запускаем мониторинг агентов
        asyncio.create_task(self._agent_monitor())
        
        # Запускаем систему рефлексии
        asyncio.create_task(self._reflection_loop())
        
        logger.info("Agent Orchestrator started")
    
    async def stop(self):
        """Остановка оркестратора"""
        self.running = False
        logger.info("Agent Orchestrator stopped")
    
    async def submit_task(self, 
                         task_type: str,
                         data: Dict[str, Any],
                         priority: TaskPriority = TaskPriority.MEDIUM,
                         required_agent: Optional[str] = None) -> str:
        """Отправляет задачу в очередь"""
        
        task_id = str(uuid.uuid4())
        
        task = {
            'id': task_id,
            'type': task_type,
            'data': data,
            'priority': priority,
            'required_agent': required_agent,
            'created_at': datetime.now().isoformat(),
            'status': TaskStatus.PENDING
        }
        
        await self.task_queue.put(task)
        self.system_metrics['total_tasks'] += 1
        
        logger.info(f"Task submitted: {task_id} ({task_type})")
        return task_id
    
    async def get_task_result(self, task_id: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Получает результат задачи"""
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            # Проверяем завершенные задачи
            for task in self.completed_tasks:
                if task['id'] == task_id:
                    return task
            
            # Проверяем активные задачи
            if task_id in self.active_tasks:
                task = self.active_tasks[task_id]
                if task['status'] in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    return task
            
            await asyncio.sleep(0.1)
        
        return None
    
    async def _task_processor(self):
        """Обработчик задач"""
        while self.running:
            try:
                # Получаем задачу из очереди
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                
                # Выбираем подходящего агента
                agent = await self._select_agent(task)
                
                if not agent:
                    task['status'] = TaskStatus.FAILED
                    task['error'] = 'No suitable agent found'
                    self.completed_tasks.append(task)
                    continue
                
                # Выполняем задачу
                task['status'] = TaskStatus.IN_PROGRESS
                task['assigned_agent'] = agent.name
                task['started_at'] = datetime.now().isoformat()
                self.active_tasks[task['id']] = task
                
                # Запускаем выполнение в отдельной корутине
                asyncio.create_task(self._execute_task(agent, task))
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in task processor: {e}")
    
    async def _execute_task(self, agent: Agent, task: Dict[str, Any]):
        """Выполняет задачу агентом"""
        try:
            start_time = datetime.now()
            
            # Выполняем задачу
            result = await agent.execute_task(task)
            
            # Обновляем задачу
            task['result'] = result
            task['completed_at'] = datetime.now().isoformat()
            task['execution_time'] = (datetime.now() - start_time).total_seconds()
            
            if result.get('success', False):
                task['status'] = TaskStatus.COMPLETED
                self.system_metrics['completed_tasks'] += 1
            else:
                task['status'] = TaskStatus.FAILED
                self.system_metrics['failed_tasks'] += 1
            
            # Перемещаем в завершенные
            if task['id'] in self.active_tasks:
                del self.active_tasks[task['id']]
            
            self.completed_tasks.append(task)
            
            # Ограничиваем размер истории
            if len(self.completed_tasks) > 1000:
                self.completed_tasks = self.completed_tasks[-1000:]
            
            logger.info(f"Task completed: {task['id']} by {agent.name}")
            
        except Exception as e:
            logger.error(f"Error executing task {task['id']}: {e}")
            task['status'] = TaskStatus.FAILED
            task['error'] = str(e)
            task['completed_at'] = datetime.now().isoformat()
            
            if task['id'] in self.active_tasks:
                del self.active_tasks[task['id']]
            
            self.completed_tasks.append(task)
            self.system_metrics['failed_tasks'] += 1
    
    async def _select_agent(self, task: Dict[str, Any]) -> Optional[Agent]:
        """Выбирает подходящего агента для задачи"""
        
        # Если указан конкретный агент
        if task.get('required_agent'):
            return self.agents.get(task['required_agent'])
        
        # Выбираем по типу задачи
        task_type = task['type']
        
        if task_type in ['search_templates', 'analyze_template', 'recommend_templates', 'categorize_templates']:
            return self.agents['template']
        elif task_type in ['import_template', 'export_workflow', 'activate_workflow', 'deactivate_workflow', 'get_workflows', 'monitor_system']:
            return self.agents['server']
        elif task_type in ['coordinate_agents', 'plan_execution']:
            return self.agents['coordinator']
        elif task_type in ['system_health', 'performance_analysis']:
            return self.agents['monitor']
        
        # Выбираем наименее загруженного агента
        available_agents = [agent for agent in self.agents.values() if not agent.is_busy]
        
        if not available_agents:
            return None
        
        # Выбираем агента с лучшей производительностью
        best_agent = max(available_agents, key=lambda a: a.performance_metrics['tasks_completed'])
        return best_agent
    
    async def _agent_monitor(self):
        """Мониторинг агентов"""
        while self.running:
            try:
                for agent in self.agents.values():
                    # Проверяем здоровье агента
                    if agent.performance_metrics['last_activity']:
                        last_activity = datetime.fromisoformat(agent.performance_metrics['last_activity'])
                        if (datetime.now() - last_activity).total_seconds() > 3600:  # 1 час
                            logger.warning(f"Agent {agent.name} has been inactive for over 1 hour")
                
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
            except Exception as e:
                logger.error(f"Error in agent monitor: {e}")
    
    async def _reflection_loop(self):
        """Цикл рефлексии системы"""
        while self.running:
            try:
                # Рефлексия каждые 10 минут
                await asyncio.sleep(600)
                
                # Коллективная рефлексия агентов
                agent_names = list(self.agents.keys())
                system_context = {
                    'system_metrics': self.system_metrics,
                    'active_tasks': len(self.active_tasks),
                    'completed_tasks': len(self.completed_tasks)
                }
                
                collaborative_reflection = await self.thinking_service.collaborative_thinking(
                    agent_names,
                    "Как улучшить производительность системы?",
                    system_context
                )
                
                logger.info(f"System reflection completed: {collaborative_reflection.get('synthesis', {}).get('content', 'No insights')[:100]}...")
                
            except Exception as e:
                logger.error(f"Error in reflection loop: {e}")
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Получает статус системы"""
        agent_statuses = {name: agent.get_status() for name, agent in self.agents.items()}
        
        return {
            'system_metrics': self.system_metrics,
            'agents': agent_statuses,
            'active_tasks': len(self.active_tasks),
            'queue_size': self.task_queue.qsize(),
            'uptime': (datetime.now() - self.system_metrics['system_uptime']).total_seconds(),
            'timestamp': datetime.now().isoformat()
        }
    
    async def get_agent_thoughts(self, agent_name: str, limit: int = 5) -> Dict[str, Any]:
        """Получает мысли агента"""
        if agent_name not in self.agents:
            return {'error': 'Agent not found'}
        
        return await self.thinking_service.get_thinking_summary(agent_name, limit)

class CoordinatorAgent(Agent):
    """Агент-координатор"""
    
    def __init__(self, thinking_service: ThinkingService, memory_service: MemoryService):
        super().__init__("CoordinatorAgent", AgentRole.COORDINATOR, thinking_service, memory_service)
        self.capabilities = {
            'coordinate_agents', 'plan_execution', 'resolve_conflicts',
            'optimize_workflow', 'delegate_tasks'
        }
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет координационные задачи"""
        # Базовая реализация
        return {
            'success': True,
            'message': 'Coordination task completed',
            'coordinator_action': task.get('type', 'unknown')
        }

class MonitorAgent(Agent):
    """Агент мониторинга"""
    
    def __init__(self, thinking_service: ThinkingService, memory_service: MemoryService):
        super().__init__("MonitorAgent", AgentRole.MONITOR, thinking_service, memory_service)
        self.capabilities = {
            'system_health', 'performance_analysis', 'error_detection',
            'resource_monitoring', 'alert_management'
        }
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет задачи мониторинга"""
        # Базовая реализация
        return {
            'success': True,
            'message': 'Monitoring task completed',
            'monitoring_data': {
                'timestamp': datetime.now().isoformat(),
                'status': 'healthy'
            }
        }
