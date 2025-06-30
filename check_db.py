import sqlite3

# 数据库文件路径
db_path = "data/grid_assessment.db"

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查询 assessments 表的数据
cursor.execute("SELECT * FROM assessments")
rows = cursor.fetchall()

if rows:
    print("assessments 表中有数据：")
    for row in rows:
        print(row)
else:
    print("assessments 表中没有数据。")

# 关闭连接
conn.close()
