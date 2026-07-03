import sys
sys.path.insert(0, 'web_app')

from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    
    # 检查 rankings 字段是否存在
    columns = inspector.get_columns('collection_results')
    has_rankings = any(col['name'] == 'rankings' for col in columns)
    
    if has_rankings:
        print('rankings 字段已存在，无需迁移')
    else:
        print('正在添加 rankings 字段...')
        try:
            # 使用 text() 包装 SQL
            db.session.execute(text('ALTER TABLE collection_results ADD COLUMN rankings TEXT'))
            db.session.commit()
            print('OK: rankings 字段添加成功')
        except Exception as e:
            print('ERROR: 添加失败:', str(e))
            db.session.rollback()
    
    # 验证
    columns = inspector.get_columns('collection_results')
    has_rankings = any(col['name'] == 'rankings' for col in columns)
    print('\n验证: rankings 字段存在 =', has_rankings)
