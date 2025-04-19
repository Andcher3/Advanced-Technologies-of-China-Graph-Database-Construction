from tqdm import tqdm
from neo4j import GraphDatabase
import re

# 请根据你的实际情况修改下面的连接信息
uri = "neo4j://10.5.156.106:7687"  # Neo4j Bolt 协议地址
username = "neo4j"  # 数据库用户名
password = "123456788"

# 连接数据库
driver = GraphDatabase.driver(uri, auth=(username, password))

if __name__ == "__main__":
    from cleaner import cleaner_all
    from keyword_merger import keyword_merging
    from extractor import generate_neo4j_graph_queries

    all_data = cleaner_all("data/src_data")

    # --- 关键词合并 (使用更新后的 merger) ---
    print("运行关键词合并...")
    # 合并 Keywords
    merged_data = keyword_merging(all_data, key_names=['Keywords'], similarity_threshold=0.9)
    # 合并 Publishers 和 Places Published
    merged_data = keyword_merging(merged_data, key_names=['Author Address'], similarity_threshold=0.95)
    merged_data = keyword_merging(merged_data, key_names=['Place Published', 'Publisher'], similarity_threshold=0.9)
    print(f"数据准备完毕，共 {len(merged_data)} 条记录用于提取 Cypher 查询。")

    # --- Cypher 生成 (使用本文件中的 extractor) ---

    print("生成 Cypher 查询语句...")
    # 传入合并后的数据，配置表见Hype
    cypher_queries = generate_neo4j_graph_queries(merged_data)
    print(f"生成了 {len(cypher_queries)} 条唯一的 Cypher 查询语句。")  # 这行信息已移到函数内部打印

    with driver.session() as session:
        error_count = 0
        for query in tqdm(cypher_queries, desc="执行 Cypher 查询", unit="条"):
            try:
                # 每个查询默认在自己的事务中运行
                session.run(query)
            except Exception as e:
                # 打印出错的查询和错误信息
                print(f"\n执行查询时出错: {query}\n 错误: {e}")
                error_count += 1
    print(f"查询执行完毕，共遇到 {error_count} 个错误。")

    driver.close()

    # =========================注意事项==========================
    # 1.上传节点很慢，因此建议用QuantumInfo部分的数据（特别少好测试），现有的节点其实也没啥用，不需要的话可以删掉
    # 2.专利没有keywords所以没有keywords合并部分
    # 3.如果你的数据的格式是.net没法用cleaner里那个改文件名字的函数，
    #   那就把re.compile(r'^(.+?) \((\d+)\)\.txt$')改为re.compile(r'^(.+?) \((\d+)\)\.net$')
    #   用哪个函数之前把对应领域的数据的名字全选改为那个领域的名字，改完以后就可以用那个函数了
    # 4.当然完全也可以不改名字:) 上面那坨💩只是我的强迫症的杰作罢了
    # 5.我还没试把所有数据全部读取然后清洗...感觉会很夸张
    # 5. by 🐸
    # ==========================================================
