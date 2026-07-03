import sys
sys.path.insert(0, 'web_app')

from app import app
from models import db, CollectionResult

with app.app_context():
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    
    # 检查 collection_results 表
    print('=== collection_results 表结构 ===')
    try:
        columns = inspector.get_columns('collection_results')
        for col in columns:
            print(f"  {col['name']}: {col['type']}")
    except Exception as e:
        print(f"  错误: {e}")
    
    # 检查 rankings 字段是否存在
    has_rankings = False
    try:
        columns = inspector.get_columns('collection_results')
        has_rankings = any(col['name'] == 'rankings' for col in columns)
    except:
        pass
    print(f"\nrankings 字段存在: {has_rankings}")
    
    # 检查 GeoManuscript 表
    print('\n=== GeoManuscript 表结构 ===')
    try:
        columns = inspector.get_columns('geo_manuscripts')
        for col in columns:
            print(f"  {col['name']}: {col['type']}")
    except Exception as e:
        print(f"  错误: {e}")
