import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import openai
from openai import OpenAI

logger = logging.getLogger(__name__)

class ThinkingType(Enum):
    """Типы мышления агента"""
    ANALYSIS = "analysis"
    PLANNING = "planning"
    REFLECTION = "reflection"
    DECISION = "decision"
    LEARNING = "learning"
    PROBLEM_SOLVING = "problem_solving"

class ThoughtLevel(Enum):
    """Уровни глубины мышления"""
    SURFACE = "surface"      # Поверхностные мысли
    DEEP = "deep"           # Глубокий анализ
    METACOGNITIVE = "meta"  # Мышление о мышлении

class ThinkingService:
    """Сервис для системы мышления агентов"""
    
    def __init__(self):
        self.openai_client = OpenAI()
        self.thinking_history = {}
        self.reflection_patterns = {}
        
    async def think(self, 
                   agent_name: str,
                   context: Dict[str, Any],
                   thinking_type: ThinkingType,
                   level: ThoughtLevel = ThoughtLevel.SURFACE) -> Dict[str, Any]:
        """Основной метод мышления"""
        try:
            thought_id = f"{agent_name}_{int(datetime.now().timestamp())}"
            
            # Генерируем мысль
            thought = await self._generate_thought(
                agent_name, context, thinking_type, level
            )
            
            # Сохраняем в историю
            await self._store_thought(agent_name, thought_id, thought)
            
            # Выполняем рефлексию если нужно
            if level in [ThoughtLevel.DEEP, ThoughtLevel.METACOGNITIVE]:
                reflection = await self._reflect_on_thought(agent_name, thought)
                thought['reflection'] = reflection
            
            return thought
            
        except Exception as e:
            logger.error(f"Error in thinking process: {e}")
            return {
                'type': thinking_type.value,
                'level': level.value,
                'content': f"Ошибка мышления: {str(e)}",
                'timestamp': datetime.now().isoformat(),
                'success': False
            }
    
    async def _generate_thought(self,
                               agent_name: str,
                               context: Dict[str, Any],
                               thinking_type: ThinkingType,
                               level: ThoughtLevel) -> Dict[str, Any]:
        """Генерирует мысль с помощью LLM"""
        
        system_prompts = {
            ThinkingType.ANALYSIS: self._get_analysis_prompt(level),
            ThinkingType.PLANNING: self._get_planning_prompt(level),
            ThinkingType.REFLECTION: self._get_reflection_prompt(level),
            ThinkingType.DECISION: self._get_decision_prompt(level),
            ThinkingType.LEARNING: self._get_learning_prompt(level),
            ThinkingType.PROBLEM_SOLVING: self._get_problem_solving_prompt(level)
        }
        
        system_prompt = system_prompts.get(thinking_type, "Проанализируй ситуацию.")
        
        # Формируем контекст для LLM
        context_text = self._format_context(context)
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Контекст: {context_text}"}
                ],
                temperature=0.7
            )
            
            thought_content = response.choices[0].message.content
            
            return {
                'agent': agent_name,
                'type': thinking_type.value,
                'level': level.value,
                'content': thought_content,
                'context': context,
                'timestamp': datetime.now().isoformat(),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Error generating thought: {e}")
            return {
                'agent': agent_name,
                'type': thinking_type.value,
                'level': level.value,
                'content': f"Не удалось сгенерировать мысль: {str(e)}",
                'timestamp': datetime.now().isoformat(),
                'success': False
            }
    
    def _get_analysis_prompt(self, level: ThoughtLevel) -> str:
        """Промпт для аналитического мышления"""
        base_prompt = """
        Ты - аналитический модуль агента n8n. Твоя задача - глубоко анализировать ситуацию.
        
        Анализируй:
        1. Текущую ситуацию
        2. Доступные данные
        3. Возможные проблемы
        4. Потенциальные решения
        
        Отвечай структурированно и логично.
        """
        
        if level == ThoughtLevel.DEEP:
            base_prompt += """
            
            Проведи ГЛУБОКИЙ анализ:
            - Рассмотри скрытые связи
            - Найди неочевидные паттерны
            - Предскажи возможные последствия
            - Оцени риски и возможности
            """
        elif level == ThoughtLevel.METACOGNITIVE:
            base_prompt += """
            
            Проведи МЕТАКОГНИТИВНЫЙ анализ:
            - Анализируй свой процесс анализа
            - Оцени качество своих рассуждений
            - Найди слабые места в логике
            - Предложи улучшения методологии
            """
        
        return base_prompt
    
    def _get_planning_prompt(self, level: ThoughtLevel) -> str:
        """Промпт для планирования"""
        return """
        Ты - модуль планирования агента n8n. Создавай детальные планы действий.
        
        Планируй:
        1. Последовательность действий
        2. Необходимые ресурсы
        3. Временные рамки
        4. Точки контроля
        5. План Б на случай проблем
        
        Будь конкретным и практичным.
        """
    
    def _get_reflection_prompt(self, level: ThoughtLevel) -> str:
        """Промпт для рефлексии"""
        return """
        Ты - модуль рефлексии агента n8n. Анализируй прошлые действия и решения.
        
        Рефлексируй:
        1. Что прошло хорошо?
        2. Что можно было сделать лучше?
        3. Какие уроки извлечь?
        4. Как применить опыт в будущем?
        
        Будь честным и конструктивным.
        """
    
    def _get_decision_prompt(self, level: ThoughtLevel) -> str:
        """Промпт для принятия решений"""
        return """
        Ты - модуль принятия решений агента n8n. Принимай обоснованные решения.
        
        Процесс принятия решения:
        1. Определи варианты
        2. Оцени плюсы и минусы каждого
        3. Учти ограничения и риски
        4. Выбери оптимальный вариант
        5. Обоснуй выбор
        
        Будь логичным и решительным.
        """
    
    def _get_learning_prompt(self, level: ThoughtLevel) -> str:
        """Промпт для обучения"""
        return """
        Ты - модуль обучения агента n8n. Извлекай знания из опыта.
        
        Обучение:
        1. Что нового узнал?
        2. Какие паттерны обнаружил?
        3. Как обновить знания?
        4. Что запомнить на будущее?
        
        Будь любознательным и систематичным.
        """
    
    def _get_problem_solving_prompt(self, level: ThoughtLevel) -> str:
        """Промпт для решения проблем"""
        return """
        Ты - модуль решения проблем агента n8n. Находи творческие решения.
        
        Решение проблем:
        1. Четко определи проблему
        2. Найди корень проблемы
        3. Сгенерируй варианты решений
        4. Оцени осуществимость каждого
        5. Выбери лучшее решение
        
        Будь креативным и практичным.
        """
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Форматирует контекст для LLM"""
        try:
            formatted_parts = []
            
            for key, value in context.items():
                if isinstance(value, (dict, list)):
                    formatted_parts.append(f"{key}: {json.dumps(value, ensure_ascii=False, indent=2)}")
                else:
                    formatted_parts.append(f"{key}: {value}")
            
            return "\n".join(formatted_parts)
            
        except Exception as e:
            logger.error(f"Error formatting context: {e}")
            return str(context)
    
    async def _store_thought(self, agent_name: str, thought_id: str, thought: Dict[str, Any]):
        """Сохраняет мысль в историю"""
        try:
            if agent_name not in self.thinking_history:
                self.thinking_history[agent_name] = []
            
            self.thinking_history[agent_name].append({
                'id': thought_id,
                'thought': thought
            })
            
            # Ограничиваем размер истории
            if len(self.thinking_history[agent_name]) > 100:
                self.thinking_history[agent_name] = self.thinking_history[agent_name][-100:]
                
        except Exception as e:
            logger.error(f"Error storing thought: {e}")
    
    async def _reflect_on_thought(self, agent_name: str, thought: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет рефлексию над мыслью"""
        try:
            reflection_prompt = f"""
            Проанализируй эту мысль агента {agent_name}:
            
            Тип мышления: {thought['type']}
            Уровень: {thought['level']}
            Содержание: {thought['content']}
            
            Рефлексия:
            1. Насколько качественна эта мысль?
            2. Что можно улучшить?
            3. Какие есть альтернативы?
            4. Как это поможет в будущем?
            
            Будь конструктивным и честным.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты - модуль рефлексии. Анализируй мысли других агентов."},
                    {"role": "user", "content": reflection_prompt}
                ],
                temperature=0.5
            )
            
            return {
                'content': response.choices[0].message.content,
                'timestamp': datetime.now().isoformat(),
                'quality_score': self._assess_thought_quality(thought)
            }
            
        except Exception as e:
            logger.error(f"Error in reflection: {e}")
            return {
                'content': f"Ошибка рефлексии: {str(e)}",
                'timestamp': datetime.now().isoformat(),
                'quality_score': 0.5
            }
    
    def _assess_thought_quality(self, thought: Dict[str, Any]) -> float:
        """Оценивает качество мысли"""
        try:
            score = 0.5  # Базовая оценка
            
            # Проверяем наличие ключевых элементов
            if thought.get('success', False):
                score += 0.2
            
            content = thought.get('content', '')
            if len(content) > 50:  # Достаточно детальная мысль
                score += 0.1
            
            if len(content) > 200:  # Очень детальная мысль
                score += 0.1
            
            # Проверяем структурированность
            if any(marker in content.lower() for marker in ['1.', '2.', '•', '-']):
                score += 0.1
            
            return min(score, 1.0)
            
        except Exception as e:
            logger.error(f"Error assessing thought quality: {e}")
            return 0.5
    
    async def get_thinking_summary(self, agent_name: str, limit: int = 10) -> Dict[str, Any]:
        """Получает сводку мышления агента"""
        try:
            history = self.thinking_history.get(agent_name, [])
            recent_thoughts = history[-limit:] if history else []
            
            if not recent_thoughts:
                return {
                    'agent': agent_name,
                    'total_thoughts': 0,
                    'recent_thoughts': [],
                    'thinking_patterns': {}
                }
            
            # Анализируем паттерны мышления
            thinking_types = {}
            quality_scores = []
            
            for item in recent_thoughts:
                thought = item['thought']
                thinking_type = thought.get('type', 'unknown')
                thinking_types[thinking_type] = thinking_types.get(thinking_type, 0) + 1
                
                if 'reflection' in thought:
                    quality_scores.append(thought['reflection'].get('quality_score', 0.5))
            
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.5
            
            return {
                'agent': agent_name,
                'total_thoughts': len(history),
                'recent_thoughts': recent_thoughts,
                'thinking_patterns': thinking_types,
                'average_quality': avg_quality,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting thinking summary: {e}")
            return {
                'agent': agent_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def collaborative_thinking(self, 
                                   agents: List[str],
                                   problem: str,
                                   context: Dict[str, Any]) -> Dict[str, Any]:
        """Коллективное мышление нескольких агентов"""
        try:
            collaborative_thoughts = {}
            
            # Каждый агент думает независимо
            for agent in agents:
                thought = await self.think(
                    agent, 
                    {**context, 'problem': problem},
                    ThinkingType.PROBLEM_SOLVING,
                    ThoughtLevel.DEEP
                )
                collaborative_thoughts[agent] = thought
            
            # Синтезируем коллективное решение
            synthesis = await self._synthesize_thoughts(collaborative_thoughts, problem)
            
            return {
                'problem': problem,
                'individual_thoughts': collaborative_thoughts,
                'synthesis': synthesis,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in collaborative thinking: {e}")
            return {
                'problem': problem,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def _synthesize_thoughts(self, thoughts: Dict[str, Any], problem: str) -> Dict[str, Any]:
        """Синтезирует мысли разных агентов"""
        try:
            synthesis_prompt = f"""
            Проблема: {problem}
            
            Мысли агентов:
            """
            
            for agent, thought in thoughts.items():
                synthesis_prompt += f"\n{agent}: {thought.get('content', 'Нет мысли')}\n"
            
            synthesis_prompt += """
            
            Синтезируй лучшее решение:
            1. Найди общие идеи
            2. Выдели уникальные предложения
            3. Объедини в комплексное решение
            4. Оцени качество синтеза
            
            Будь объективным и конструктивным.
            """
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты - модуль синтеза коллективного мышления."},
                    {"role": "user", "content": synthesis_prompt}
                ],
                temperature=0.6
            )
            
            return {
                'content': response.choices[0].message.content,
                'participating_agents': list(thoughts.keys()),
                'synthesis_quality': self._assess_synthesis_quality(thoughts),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error synthesizing thoughts: {e}")
            return {
                'content': f"Ошибка синтеза: {str(e)}",
                'timestamp': datetime.now().isoformat()
            }
    
    def _assess_synthesis_quality(self, thoughts: Dict[str, Any]) -> float:
        """Оценивает качество синтеза"""
        try:
            # Базовая оценка зависит от количества участвующих агентов
            base_score = min(len(thoughts) * 0.2, 0.8)
            
            # Проверяем успешность мыслей
            successful_thoughts = sum(1 for t in thoughts.values() if t.get('success', False))
            success_bonus = (successful_thoughts / len(thoughts)) * 0.2
            
            return min(base_score + success_bonus, 1.0)
            
        except Exception as e:
            logger.error(f"Error assessing synthesis quality: {e}")
            return 0.5


class ReflectionEngine:
    """Движок рефлексии для агентов"""
    
    def __init__(self, thinking_service: ThinkingService):
        self.thinking_service = thinking_service
        self.reflection_triggers = {}
    
    async def setup_reflection_trigger(self, 
                                     agent_name: str,
                                     trigger_condition: Callable,
                                     reflection_type: ThinkingType = ThinkingType.REFLECTION):
        """Настраивает триггер для автоматической рефлексии"""
        try:
            self.reflection_triggers[agent_name] = {
                'condition': trigger_condition,
                'type': reflection_type,
                'last_triggered': None
            }
            
            logger.info(f"Reflection trigger set for agent {agent_name}")
            
        except Exception as e:
            logger.error(f"Error setting reflection trigger: {e}")
    
    async def check_reflection_triggers(self, agent_name: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Проверяет триггеры рефлексии"""
        try:
            trigger = self.reflection_triggers.get(agent_name)
            if not trigger:
                return None
            
            # Проверяем условие триггера
            if trigger['condition'](context):
                reflection = await self.thinking_service.think(
                    agent_name,
                    context,
                    trigger['type'],
                    ThoughtLevel.METACOGNITIVE
                )
                
                trigger['last_triggered'] = datetime.now().isoformat()
                return reflection
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking reflection triggers: {e}")
            return None
