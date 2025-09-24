from flask import Blueprint, request, jsonify
from src.models.template import db, Template, UserWorkflow, UserSession, ExecutionLog
import json

template_bp = Blueprint('template', __name__)

@template_bp.route('/templates', methods=['GET'])
def get_templates():
    """Получить список шаблонов с фильтрацией"""
    try:
        category = request.args.get('category')
        keywords = request.args.get('keywords', '').split(',') if request.args.get('keywords') else []
        limit = int(request.args.get('limit', 20))
        offset = int(request.args.get('offset', 0))
        
        query = Template.query.filter_by(is_active=True)
        
        if category:
            query = query.filter_by(category=category)
        
        if keywords:
            for keyword in keywords:
                if keyword.strip():
                    query = query.filter(
                        db.or_(
                            Template.name.contains(keyword.strip()),
                            Template.description.contains(keyword.strip()),
                            Template.tags.contains(keyword.strip())
                        )
                    )
        
        total = query.count()
        templates = query.offset(offset).limit(limit).all()
        
        return jsonify({
            'success': True,
            'data': [template.to_dict() for template in templates],
            'total': total,
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/templates/<int:template_id>', methods=['GET'])
def get_template(template_id):
    """Получить конкретный шаблон"""
    try:
        template = Template.query.get_or_404(template_id)
        
        # Увеличиваем счетчик просмотров
        template.download_count += 1
        db.session.commit()
        
        result = template.to_dict()
        if template.json_content:
            result['json_content'] = json.loads(template.json_content)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/templates/categories', methods=['GET'])
def get_categories():
    """Получить статистику по категориям"""
    try:
        stats = Template.get_categories_stats()
        categories = {}
        
        for category, count in stats:
            categories[category] = {
                'count': count,
                'templates': []
            }
        
        return jsonify({
            'success': True,
            'data': categories,
            'total_categories': len(categories)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/templates/popular', methods=['GET'])
def get_popular_templates():
    """Получить популярные шаблоны"""
    try:
        limit = int(request.args.get('limit', 10))
        templates = Template.get_popular_templates(limit)
        
        return jsonify({
            'success': True,
            'data': [template.to_dict() for template in templates]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/templates/search', methods=['POST'])
def search_templates():
    """Расширенный поиск шаблонов"""
    try:
        data = request.get_json()
        query_text = data.get('query', '')
        category = data.get('category')
        complexity = data.get('complexity')
        tags = data.get('tags', [])
        
        query = Template.query.filter_by(is_active=True)
        
        if query_text:
            query = query.filter(
                db.or_(
                    Template.name.contains(query_text),
                    Template.description.contains(query_text)
                )
            )
        
        if category:
            query = query.filter_by(category=category)
        
        if complexity:
            query = query.filter(Template.complexity.contains(complexity))
        
        if tags:
            for tag in tags:
                query = query.filter(Template.tags.contains(tag))
        
        templates = query.all()
        
        return jsonify({
            'success': True,
            'data': [template.to_dict() for template in templates],
            'total': len(templates)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/user/<int:user_id>/workflows', methods=['GET'])
def get_user_workflows(user_id):
    """Получить workflows пользователя"""
    try:
        workflows = UserWorkflow.query.filter_by(user_id=user_id).all()
        
        return jsonify({
            'success': True,
            'data': [workflow.to_dict() for workflow in workflows]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/user/<int:user_id>/workflows', methods=['POST'])
def create_user_workflow(user_id):
    """Создать workflow для пользователя"""
    try:
        data = request.get_json()
        
        workflow = UserWorkflow(
            user_id=user_id,
            workflow_id=data.get('workflow_id'),
            template_id=data.get('template_id'),
            workflow_name=data.get('workflow_name'),
            status=data.get('status', 'inactive')
        )
        
        db.session.add(workflow)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': workflow.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/user/<int:user_id>/session', methods=['GET'])
def get_user_session(user_id):
    """Получить сессию пользователя"""
    try:
        session = UserSession.query.filter_by(user_id=user_id, is_active=True).first()
        
        if not session:
            return jsonify({
                'success': True,
                'data': None
            })
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': session.user_id,
                'session_data': session.get_session_data(),
                'has_n8n_config': bool(session.n8n_api_key and session.n8n_base_url),
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/user/<int:user_id>/session', methods=['POST'])
def update_user_session(user_id):
    """Обновить сессию пользователя"""
    try:
        data = request.get_json()
        
        session = UserSession.query.filter_by(user_id=user_id, is_active=True).first()
        
        if not session:
            session = UserSession(user_id=user_id)
            db.session.add(session)
        
        if 'session_data' in data:
            session.set_session_data(data['session_data'])
        
        if 'n8n_api_key' in data:
            session.n8n_api_key = data['n8n_api_key']  # TODO: Добавить шифрование
        
        if 'n8n_base_url' in data:
            session.n8n_base_url = data['n8n_base_url']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': session.user_id,
                'updated_at': session.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/executions', methods=['GET'])
def get_executions():
    """Получить логи выполнений"""
    try:
        user_id = request.args.get('user_id', type=int)
        workflow_id = request.args.get('workflow_id')
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        
        query = ExecutionLog.query
        
        if user_id:
            query = query.filter_by(user_id=user_id)
        
        if workflow_id:
            query = query.filter_by(workflow_id=workflow_id)
        
        if status:
            query = query.filter_by(status=status)
        
        executions = query.order_by(ExecutionLog.created_at.desc()).limit(limit).all()
        
        return jsonify({
            'success': True,
            'data': [execution.to_dict() for execution in executions]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@template_bp.route('/executions', methods=['POST'])
def log_execution():
    """Записать лог выполнения"""
    try:
        data = request.get_json()
        
        execution = ExecutionLog(
            user_id=data.get('user_id'),
            workflow_id=data.get('workflow_id'),
            execution_id=data.get('execution_id'),
            status=data.get('status'),
            start_time=data.get('start_time'),
            end_time=data.get('end_time'),
            duration=data.get('duration'),
            error_message=data.get('error_message')
        )
        
        db.session.add(execution)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': execution.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
