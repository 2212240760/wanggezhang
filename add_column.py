import sqlite3

# 数据库文件路径
db_path = "data/grid_assessment.db"

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 执行 ALTER TABLE 语句添加 total_score 列
    cursor.execute("ALTER TABLE assessments ADD COLUMN total_score REAL")
    conn.commit()
    print("total_score 列添加成功")
except sqlite3.OperationalError as e:
    print(f"添加列时出错: {e}")
finally:
    conn.close()
