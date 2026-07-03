"""
添加舆情配置字段到任务表
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
    
    if 'sentiment_config_id' not in columns:
        # 添加新字段
        cursor.execute('''
            ALTER TABLE monitor_tasks 
            ADD COLUMN sentiment_config_id INTEGER 
            REFERENCES sentiment_configs(id)
        ''')
        print("成功添加 sentiment_config_id 字段到 monitor_tasks 表")
    else:
        print("sentiment_config_id 字段已存在")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    migrate()
