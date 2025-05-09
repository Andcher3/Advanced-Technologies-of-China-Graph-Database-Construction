import re
from neo4j import GraphDatabase
from tqdm import tqdm

# 1. 读取日志
log_path = 'error_log.txt'
with open(log_path, 'r', encoding='utf-8') as f:
    log_text = f.read()

# 2. 提取失败的语句（包括末尾的分号）
failed_statements = re.findall(r'执行查询时出错:\s*(.+?;)', log_text)

# 去重，保留出现顺序
seen = set()
unique_statements = []
for stmt in failed_statements:
    if stmt not in seen:
        seen.add(stmt)
        unique_statements.append(stmt)

# 打印一下提取到的语句
print("共提取到 {} 条失败语句：".format(len(unique_statements)))
for s in unique_statements:
    print(s)

# 3. 连接 Neo4j 并重试执行
url = "bolt://10.15.248.213:7687"  # Neo4j Bolt 协议地址
username = "neo4j"  # 数据库用户名
password = "123456788"

# 连接数据库
driver = GraphDatabase.driver(url, auth=(username, password))
try:
    driver.verify_connectivity()
except Exception as e:
    print(f"Connection error:\n{e}")
    exit(1)
with driver.session() as session:
    error_count = 0
    for query in tqdm(unique_statements, desc="执行 Cypher 查询", unit="条"):
        try:
            # 每个查询默认在自己的事务中运行
            session.run(query)
        except Exception as e:
            # 打印出错的查询和错误信息
            print(f"\n执行查询时出错: {query}\n 错误: {e}")
            error_count += 1
print(f"查询执行完毕，共遇到 {error_count} 个错误。")
