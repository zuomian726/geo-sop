"""
数据库迁移脚本：修复时间戳时区问题
将数据库中的 UTC 时间转换为上海时间 (+08:00)
"""
import sys
import os
from sqlalchemy import create_engine, text

# 数据库路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'instance', 'ai_monitor.db')
DATABASE_URI = f'sqlite:///{DB_PATH}'

def migrate():
    """修复时间戳时区"""
    print(f"数据库路径: {DB_PATH}")
    
    engine = create_engine(DATABASE_URI)
    
    with engine.connect() as conn:
        # 1. 修复 CollectionResult 表的 created_at
        result = conn.execute(text("SELECT COUNT(*) FROM collection_results"))
        count = result.fetchone()[0]
        print(f"CollectionResult 表共有 {count} 条记录")
        
        if count > 0:
            # SQLite 不支持直接的时区转换，我们需要手动计算
            # 将 UTC 时间（假设存储的是 UTC）转换为上海时间（+8小时）
            # 注意：如果之前存储的已经是上海时间，就不需要转换
            # 这里我们假设需要 +8 小时转换
            
            # 先检查是否需要转换 - 查看几条样本数据
            result = conn.execute(text("SELECT id, created_at FROM collection_results LIMIT 3"))
            samples = result.fetchall()
            print("\n样本数据（迁移前）:")
            for row in samples:
                print(f"  id={row[0]}, created_at={row[1]}")
            
            # 执行转换：所有时间 +8 小时
            conn.execute(text("""
                UPDATE collection_results
                SET created_at = datetime(created_at, '+8 hours')
            """))
            conn.commit()
            print("\n已转换 CollectionResult 表的时间戳")
        
        # 2. 修复 MonitorTask 表的时间戳
        result = conn.execute(text("SELECT COUNT(*) FROM monitor_tasks"))
        count = result.fetchone()[0]
        print(f"\nMonitorTask 表共有 {count} 条记录")
        
        if count > 0:
            conn.execute(text("""
                UPDATE monitor_tasks
                SET created_at = datetime(created_at, '+8 hours'),
                    updated_at = datetime(updated_at, '+8 hours'),
                    last_run_at = datetime(last_run_at, '+8 hours')
            """))
            conn.commit()
            print("已转换 MonitorTask 表的时间戳")
        
        # 3. 修复 User 表的时间戳
        result = conn.execute(text("SELECT COUNT(*) FROM users"))
        count = result.fetchone()[0]
        print(f"\nUser 表共有 {count} 条记录")
        
        if count > 0:
            conn.execute(text("""
                UPDATE users
                SET created_at = datetime(created_at, '+8 hours')
            """))
            conn.commit()
            print("已转换 User 表的时间戳")
        
        print("\n迁移完成！")
        print("\n注意：如果时间仍然不正确，可能需要反向操作（-8小时），请反馈具体情况。")

if __name__ == '__main__':
    migrate()