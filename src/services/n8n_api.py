import aiohttp
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class N8nApiClient:
    """Клиент для работы с n8n API"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-N8N-API-KEY': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        self.session = None
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Выполняет HTTP запрос к n8n API"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if not self.session:
                self.session = aiohttp.ClientSession(headers=self.headers)
            
            async with self.session.request(method, url, json=data) as response:
                response_text = await response.text()
                
                if response.status >= 400:
                    logger.error(f"n8n API error {response.status}: {response_text}")
                    raise N8nApiError(f"HTTP {response.status}: {response_text}")
                
                if response_text:
                    return json.loads(response_text)
                return {}
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            raise N8nApiError(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise N8nApiError(f"Invalid JSON response: {str(e)}")
    
    # Workflow Management
    async def get_workflows(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """Получает список всех workflows"""
        endpoint = "/workflows"
        if active_only:
            endpoint += "?active=true"
        
        response = await self._make_request("GET", endpoint)
        return response.get('data', [])
    
    async def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Получает конкретный workflow по ID"""
        endpoint = f"/workflows/{workflow_id}"
        return await self._make_request("GET", endpoint)
    
    async def create_workflow(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Создает новый workflow"""
        endpoint = "/workflows"
        return await self._make_request("POST", endpoint, workflow_data)
    
    async def update_workflow(self, workflow_id: str, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет существующий workflow"""
        endpoint = f"/workflows/{workflow_id}"
        return await self._make_request("PUT", endpoint, workflow_data)
    
    async def delete_workflow(self, workflow_id: str) -> bool:
        """Удаляет workflow"""
        endpoint = f"/workflows/{workflow_id}"
        await self._make_request("DELETE", endpoint)
        return True
    
    async def activate_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Активирует workflow"""
        endpoint = f"/workflows/{workflow_id}/activate"
        return await self._make_request("POST", endpoint)
    
    async def deactivate_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Деактивирует workflow"""
        endpoint = f"/workflows/{workflow_id}/deactivate"
        return await self._make_request("POST", endpoint)
    
    # Execution Management
    async def get_executions(self, workflow_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Получает список выполнений"""
        endpoint = f"/executions?limit={limit}"
        if workflow_id:
            endpoint += f"&workflowId={workflow_id}"
        
        response = await self._make_request("GET", endpoint)
        return response.get('data', [])
    
    async def get_execution(self, execution_id: str) -> Dict[str, Any]:
        """Получает конкретное выполнение"""
        endpoint = f"/executions/{execution_id}"
        return await self._make_request("GET", endpoint)
    
    async def retry_execution(self, execution_id: str) -> Dict[str, Any]:
        """Повторяет выполнение"""
        endpoint = f"/executions/{execution_id}/retry"
        return await self._make_request("POST", endpoint)
    
    async def delete_execution(self, execution_id: str) -> bool:
        """Удаляет выполнение"""
        endpoint = f"/executions/{execution_id}"
        await self._make_request("DELETE", endpoint)
        return True
    
    # Credential Management
    async def get_credentials(self) -> List[Dict[str, Any]]:
        """Получает список учетных данных"""
        endpoint = "/credentials"
        response = await self._make_request("GET", endpoint)
        return response.get('data', [])
    
    async def create_credential(self, credential_data: Dict[str, Any]) -> Dict[str, Any]:
        """Создает новые учетные данные"""
        endpoint = "/credentials"
        return await self._make_request("POST", endpoint, credential_data)
    
    async def update_credential(self, credential_id: str, credential_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет учетные данные"""
        endpoint = f"/credentials/{credential_id}"
        return await self._make_request("PUT", endpoint, credential_data)
    
    async def delete_credential(self, credential_id: str) -> bool:
        """Удаляет учетные данные"""
        endpoint = f"/credentials/{credential_id}"
        await self._make_request("DELETE", endpoint)
        return True
    
    # Tags Management
    async def get_workflow_tags(self, workflow_id: str) -> List[str]:
        """Получает теги workflow"""
        endpoint = f"/workflows/{workflow_id}/tags"
        response = await self._make_request("GET", endpoint)
        return response.get('tags', [])
    
    async def update_workflow_tags(self, workflow_id: str, tags: List[str]) -> Dict[str, Any]:
        """Обновляет теги workflow"""
        endpoint = f"/workflows/{workflow_id}/tags"
        return await self._make_request("PUT", endpoint, {'tags': tags})
    
    # Health Check
    async def health_check(self) -> Dict[str, Any]:
        """Проверяет состояние n8n сервера"""
        try:
            endpoint = "/workflows"  # Простой endpoint для проверки
            await self._make_request("GET", endpoint)
            return {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'api_accessible': True
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now().isoformat(),
                'api_accessible': False,
                'error': str(e)
            }


class N8nTemplateManager:
    """Менеджер для работы с шаблонами n8n"""
    
    def __init__(self, api_client: N8nApiClient):
        self.api_client = api_client
    
    async def import_template(self, template_json: Dict[str, Any], template_name: str = None) -> Dict[str, Any]:
        """Импортирует шаблон в n8n"""
        try:
            # Подготавливаем данные для импорта
            workflow_data = {
                'name': template_name or template_json.get('name', 'Imported Template'),
                'nodes': template_json.get('nodes', []),
                'connections': template_json.get('connections', {}),
                'settings': template_json.get('settings', {}),
                'staticData': template_json.get('staticData', {}),
                'tags': template_json.get('tags', []),
                'active': False  # Импортируем как неактивный
            }
            
            # Создаем workflow
            result = await self.api_client.create_workflow(workflow_data)
            
            logger.info(f"Template '{template_name}' imported successfully with ID: {result.get('id')}")
            
            return {
                'success': True,
                'workflow_id': result.get('id'),
                'name': result.get('name'),
                'message': f"Шаблон '{template_name}' успешно импортирован"
            }
            
        except Exception as e:
            logger.error(f"Error importing template: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f"Ошибка импорта шаблона: {str(e)}"
            }
    
    async def export_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Экспортирует workflow в формате JSON"""
        try:
            workflow = await self.api_client.get_workflow(workflow_id)
            
            # Подготавливаем данные для экспорта
            export_data = {
                'name': workflow.get('name'),
                'nodes': workflow.get('nodes', []),
                'connections': workflow.get('connections', {}),
                'settings': workflow.get('settings', {}),
                'staticData': workflow.get('staticData', {}),
                'tags': workflow.get('tags', []),
                'meta': {
                    'exported_at': datetime.now().isoformat(),
                    'n8n_version': workflow.get('versionId'),
                    'workflow_id': workflow_id
                }
            }
            
            return {
                'success': True,
                'data': export_data,
                'filename': f"{workflow.get('name', 'workflow')}_{workflow_id}.json"
            }
            
        except Exception as e:
            logger.error(f"Error exporting workflow: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f"Ошибка экспорта workflow: {str(e)}"
            }
    
    async def duplicate_workflow(self, workflow_id: str, new_name: str = None) -> Dict[str, Any]:
        """Дублирует существующий workflow"""
        try:
            # Экспортируем workflow
            export_result = await self.export_workflow(workflow_id)
            if not export_result['success']:
                return export_result
            
            # Импортируем как новый workflow
            template_data = export_result['data']
            if new_name:
                template_data['name'] = new_name
            else:
                template_data['name'] = f"Copy of {template_data['name']}"
            
            return await self.import_template(template_data, template_data['name'])
            
        except Exception as e:
            logger.error(f"Error duplicating workflow: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f"Ошибка дублирования workflow: {str(e)}"
            }


class N8nMonitor:
    """Монитор для отслеживания состояния n8n"""
    
    def __init__(self, api_client: N8nApiClient):
        self.api_client = api_client
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Получает общий статус системы"""
        try:
            # Проверяем доступность API
            health = await self.api_client.health_check()
            
            # Получаем статистику
            workflows = await self.api_client.get_workflows()
            active_workflows = [w for w in workflows if w.get('active', False)]
            
            # Получаем последние выполнения
            recent_executions = await self.api_client.get_executions(limit=10)
            
            # Анализируем выполнения
            successful_executions = [e for e in recent_executions if e.get('finished', False) and not e.get('stoppedAt')]
            failed_executions = [e for e in recent_executions if e.get('stoppedAt')]
            
            return {
                'api_status': health['status'],
                'total_workflows': len(workflows),
                'active_workflows': len(active_workflows),
                'recent_executions': len(recent_executions),
                'successful_executions': len(successful_executions),
                'failed_executions': len(failed_executions),
                'success_rate': len(successful_executions) / len(recent_executions) * 100 if recent_executions else 0,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                'api_status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_workflow_analytics(self, workflow_id: str, days: int = 7) -> Dict[str, Any]:
        """Получает аналитику по конкретному workflow"""
        try:
            # Получаем выполнения workflow
            executions = await self.api_client.get_executions(workflow_id=workflow_id, limit=100)
            
            # Фильтруем по дням
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            
            recent_executions = []
            for execution in executions:
                if execution.get('startedAt'):
                    start_time = datetime.fromisoformat(execution['startedAt'].replace('Z', '+00:00'))
                    if start_time >= cutoff_date:
                        recent_executions.append(execution)
            
            # Анализируем данные
            total_executions = len(recent_executions)
            successful = len([e for e in recent_executions if e.get('finished', False) and not e.get('stoppedAt')])
            failed = len([e for e in recent_executions if e.get('stoppedAt')])
            
            # Вычисляем среднее время выполнения
            durations = []
            for execution in recent_executions:
                if execution.get('startedAt') and execution.get('stoppedAt'):
                    start = datetime.fromisoformat(execution['startedAt'].replace('Z', '+00:00'))
                    end = datetime.fromisoformat(execution['stoppedAt'].replace('Z', '+00:00'))
                    durations.append((end - start).total_seconds())
            
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            return {
                'workflow_id': workflow_id,
                'period_days': days,
                'total_executions': total_executions,
                'successful_executions': successful,
                'failed_executions': failed,
                'success_rate': successful / total_executions * 100 if total_executions > 0 else 0,
                'average_duration_seconds': avg_duration,
                'executions_per_day': total_executions / days,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting workflow analytics: {e}")
            return {
                'workflow_id': workflow_id,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


class N8nApiError(Exception):
    """Исключение для ошибок n8n API"""
    pass


# Пример использования
async def example_usage():
    """Пример использования n8n API клиента"""
    api_client = N8nApiClient(
        base_url="https://your-instance.app.n8n.cloud/api/v1",
        api_key="your-api-key"
    )
    
    async with api_client:
        # Проверяем состояние
        health = await api_client.health_check()
        print(f"API Status: {health['status']}")
        
        # Получаем список workflows
        workflows = await api_client.get_workflows()
        print(f"Total workflows: {len(workflows)}")
        
        # Создаем менеджер шаблонов
        template_manager = N8nTemplateManager(api_client)
        
        # Создаем монитор
        monitor = N8nMonitor(api_client)
        status = await monitor.get_system_status()
        print(f"System status: {status}")


if __name__ == "__main__":
    asyncio.run(example_usage())
