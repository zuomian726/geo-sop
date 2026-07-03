"""
添加最大并行平台数字段到任务表
"""
import sqlite3
import os

def migrate():
    """执行迁移"""
    db_path = os.path.join(os.path.dirname(__file__), '..', 'instance', 'ai_monitor.db')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查字段是否已存在
    cursor.execute("PRAGMA table_info(monitor_tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'max_parallel_platforms' not in columns:
        # 添加新字段，默认值为3
        cursor.execute('''
            ALTER TABLE monitor_tasks 
            ADD COLUMN max_parallel_platforms INTEGER DEFAULT 3
        ''')
        print("成功添加 max_parallel_platforms 字段到 monitor_tasks 表")
    else:
        print("max_parallel_platforms 字段已存在")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    migrate()
