import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.services.agent_orchestrator import (
    AgentOrchestrator, TemplateAgent, ServerAgent, 
    TaskPriority, TaskStatus, AgentRole
)
from src.services.thinking_service import ThinkingService, ThinkingType
from src.services.voice_service import MemoryService

class TestAgentOrchestrator:
    """Тесты для оркестратора агентов"""
    
    @pytest.fixture
    async def orchestrator(self):
        """Фикстура оркестратора"""
        orchestrator = AgentOrchestrator()
        await orchestrator.start()
        yield orchestrator
        await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self):
        """Тест инициализации оркестратора"""
        orchestrator = AgentOrchestrator()
        
        assert len(orchestrator.agents) > 0
        assert 'template' in orchestrator.agents
        assert 'server' in orchestrator.agents
        assert orchestrator.task_queue is not None
        assert orchestrator.system_metrics is not None
    
    @pytest.mark.asyncio
    async def test_task_submission(self, orchestrator):
        """Тест отправки задачи"""
        task_id = await orchestrator.submit_task(
            task_type='search_templates',
            data={'query': 'test', 'user_id': 123},
            priority=TaskPriority.HIGH
        )
        
        assert task_id is not None
        assert isinstance(task_id, str)
        assert orchestrator.system_metrics['total_tasks'] > 0
    
    @pytest.mark.asyncio
    async def test_task_execution(self, orchestrator):
        """Тест выполнения задачи"""
        # Мокаем template service
        with patch('src.services.template_service.TemplateService') as mock_service:
            mock_service.return_value.search_templates = AsyncMock(return_value=[
                {'id': 1, 'name': 'Test Template', 'category': 'AI'}
            ])
            
            task_id = await orchestrator.submit_task(
                task_type='search_templates',
                data={'query': 'AI', 'user_id': 123}
            )
            
            # Ждем выполнения
            result = await orchestrator.get_task_result(task_id, timeout=10.0)
            
            assert result is not None
            assert result['status'] in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]
    
    @pytest.mark.asyncio
    async def test_agent_selection(self, orchestrator):
        """Тест выбора агента"""
        # Тест выбора template агента
        task = {
            'type': 'search_templates',
            'data': {'query': 'test'}
        }
        
        agent = await orchestrator._select_agent(task)
        assert agent is not None
        assert agent.role == AgentRole.TEMPLATE_SPECIALIST
        
        # Тест выбора server агента
        task = {
            'type': 'import_template',
            'data': {'template_id': 1, 'user_id': 123}
        }
        
        agent = await orchestrator._select_agent(task)
        assert agent is not None
        assert agent.role == AgentRole.SERVER_MANAGER
    
    @pytest.mark.asyncio
    async def test_system_status(self, orchestrator):
        """Тест получения статуса системы"""
        status = await orchestrator.get_system_status()
        
        assert 'system_metrics' in status
        assert 'agents' in status
        assert 'active_tasks' in status
        assert 'uptime' in status
        assert isinstance(status['uptime'], float)

class TestTemplateAgent:
    """Тесты для агента шаблонов"""
    
    @pytest.fixture
    def template_agent(self):
        """Фикстура агента шаблонов"""
        thinking_service = Mock(spec=ThinkingService)
        thinking_service.think = AsyncMock(return_value={
            'success': True,
            'content': 'Test thinking',
            'type': 'analysis'
        })
        
        memory_service = Mock(spec=MemoryService)
        
        return TemplateAgent(thinking_service, memory_service)
    
    @pytest.mark.asyncio
    async def test_search_templates_task(self, template_agent):
        """Тест задачи поиска шаблонов"""
        with patch.object(template_agent.template_service, 'search_templates') as mock_search:
            mock_search.return_value = [
                {'id': 1, 'name': 'Test Template', 'category': 'AI'}
            ]
            
            task = {
                'type': 'search_templates',
                'data': {'query': 'AI', 'category': 'AI', 'limit': 10}
            }
            
            result = await template_agent.execute_task(task)
            
            assert result['success'] is True
            assert 'templates' in result
            assert len(result['templates']) == 1
            assert 'agent_thoughts' in result
    
    @pytest.mark.asyncio
    async def test_analyze_template_task(self, template_agent):
        """Тест задачи анализа шаблона"""
        with patch.object(template_agent.template_service, 'get_template_by_id') as mock_get:
            mock_get.return_value = {
                'id': 1,
                'name': 'Test Template',
                'json_content': {'nodes': [{'type': 'webhook'}]},
                'category': 'AI'
            }
            
            task = {
                'type': 'analyze_template',
                'data': {'template_id': 1}
            }
            
            result = await template_agent.execute_task(task)
            
            assert result['success'] is True
            assert 'template' in result
            assert 'analysis' in result
            assert 'complexity_score' in result['analysis']
    
    @pytest.mark.asyncio
    async def test_complexity_calculation(self, template_agent):
        """Тест вычисления сложности шаблона"""
        template = {
            'json_content': {
                'nodes': [
                    {'type': 'webhook'},
                    {'type': 'function'},
                    {'type': 'http'}
                ],
                'connections': {
                    'webhook': {'main': [['function']]},
                    'function': {'main': [['http']]}
                }
            }
        }
        
        complexity = template_agent._calculate_complexity(template)
        
        assert isinstance(complexity, float)
        assert 0.0 <= complexity <= 1.0
    
    @pytest.mark.asyncio
    async def test_recommendation_scoring(self, template_agent):
        """Тест скоринга рекомендаций"""
        template = {
            'category': 'AI',
            'complexity': 'medium',
            'download_count': 150,
            'rating': 4.5
        }
        
        preferences = {
            'categories': ['AI', 'Marketing'],
            'complexity': 'medium'
        }
        
        history = []
        
        score = template_agent._calculate_recommendation_score(template, preferences, history)
        
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Должен быть высокий скор из-за соответствия предпочтениям

class TestServerAgent:
    """Тесты для серверного агента"""
    
    @pytest.fixture
    def server_agent(self):
        """Фикстура серверного агента"""
        thinking_service = Mock(spec=ThinkingService)
        thinking_service.think = AsyncMock(return_value={
            'success': True,
            'content': 'Test server thinking',
            'type': 'planning'
        })
        
        memory_service = Mock(spec=MemoryService)
        
        return ServerAgent(thinking_service, memory_service)
    
    @pytest.mark.asyncio
    async def test_import_template_task(self, server_agent):
        """Тест задачи импорта шаблона"""
        with patch.object(server_agent.workflow_service, 'import_template_to_n8n') as mock_import:
            mock_import.return_value = {
                'success': True,
                'workflow_id': 'test-workflow-123',
                'message': 'Template imported successfully'
            }
            
            task = {
                'type': 'import_template',
                'data': {'user_id': 123, 'template_id': 1}
            }
            
            result = await server_agent.execute_task(task)
            
            assert result['success'] is True
            assert 'workflow_id' in result
            assert 'agent_thoughts' in result
    
    @pytest.mark.asyncio
    async def test_get_workflows_task(self, server_agent):
        """Тест задачи получения workflows"""
        with patch.object(server_agent.workflow_service, 'get_user_workflows') as mock_get:
            mock_get.return_value = [
                {'workflow_id': '123', 'workflow_name': 'Test Workflow', 'status': 'active'}
            ]
            
            task = {
                'type': 'get_workflows',
                'data': {'user_id': 123}
            }
            
            result = await server_agent.execute_task(task)
            
            assert result['success'] is True
            assert 'workflows' in result
            assert 'count' in result
            assert result['count'] == 1

class TestIntegration:
    """Интеграционные тесты"""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Тест полного рабочего процесса"""
        orchestrator = AgentOrchestrator()
        await orchestrator.start()
        
        try:
            # Мокаем сервисы
            with patch('src.services.template_service.TemplateService') as mock_template_service:
                mock_template_service.return_value.search_templates = AsyncMock(return_value=[
                    {'id': 1, 'name': 'AI Email Automation', 'category': 'AI'}
                ])
                
                with patch('src.services.template_service.UserWorkflowService') as mock_workflow_service:
                    mock_workflow_service.return_value.import_template_to_n8n = AsyncMock(return_value={
                        'success': True,
                        'workflow_id': 'imported-123'
                    })
                    
                    # 1. Поиск шаблона
                    search_task_id = await orchestrator.submit_task(
                        task_type='search_templates',
                        data={'query': 'AI email', 'user_id': 123}
                    )
                    
                    search_result = await orchestrator.get_task_result(search_task_id, timeout=10.0)
                    assert search_result is not None
                    assert search_result['status'] == TaskStatus.COMPLETED.value
                    
                    # 2. Импорт шаблона
                    import_task_id = await orchestrator.submit_task(
                        task_type='import_template',
                        data={'template_id': 1, 'user_id': 123}
                    )
                    
                    import_result = await orchestrator.get_task_result(import_task_id, timeout=10.0)
                    assert import_result is not None
                    assert import_result['status'] == TaskStatus.COMPLETED.value
        
        finally:
            await orchestrator.stop()
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Тест обработки ошибок"""
        orchestrator = AgentOrchestrator()
        await orchestrator.start()
        
        try:
            # Отправляем задачу с неизвестным типом
            task_id = await orchestrator.submit_task(
                task_type='unknown_task_type',
                data={'test': 'data'}
            )
            
            result = await orchestrator.get_task_result(task_id, timeout=10.0)
            
            # Должна быть ошибка
            assert result is not None
            assert result['status'] == TaskStatus.FAILED.value
            assert 'error' in result
        
        finally:
            await orchestrator.stop()

if __name__ == '__main__':
    # Запуск тестов
    pytest.main([__file__, '-v'])
