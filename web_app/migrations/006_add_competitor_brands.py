"""
数据库迁移脚本：添加 competitor_brands 字段
"""
import sys
import os
from sqlalchemy import create_engine, text

# 数据库路径 - 在 instance 目录下
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'instance', 'ai_monitor.db')
DATABASE_URI = f'sqlite:///{DB_PATH}'

def migrate():
    """添加 competitor_brands 字段"""
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"数据库路径: {DB_PATH}")
    
    # 直接创建引擎，不使用 Flask-SQLAlchemy
    engine = create_engine(DATABASE_URI)
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("PRAGMA table_info(monitor_tasks)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'competitor_brands' not in columns:
            # 使用 ALTER TABLE 添加字段 (SQLite)
            conn.execute(text("ALTER TABLE monitor_tasks ADD COLUMN competitor_brands TEXT"))
            conn.commit()
            print("已添加 competitor_brands 字段")
        else:
            print("competitor_brands 字段已存在")
        
        # 确保现有任务有正确的默认值（空数组的JSON）
        conn.execute(text("UPDATE monitor_tasks SET competitor_brands = '[]' WHERE competitor_brands IS NULL"))
        conn.commit()
        
        # 验证数据
        result = conn.execute(text("SELECT COUNT(*) FROM monitor_tasks"))
        count = result.fetchone()[0]
        print(f"共有 {count} 个任务")
        print("迁移完成！")

if __name__ == '__main__':
    migrate()