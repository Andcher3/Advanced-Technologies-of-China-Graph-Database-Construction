import os
from utlis import *
from Hype import *
from utlis import _escape_cypher_string


# --- 主要生成函数 ---

def generate_neo4j_graph_queries(records: list, link_config: list = NODE_LINK_CONFIG) -> list:
    """
    根据记录和关联配置生成 Neo4j Cypher 查询语句。

    1. 创建/合并 Paper/Patent 节点及其直接属性。
    2. 根据配置创建/合并关联节点（作者、关键词、机构等）。
    3. 根据配置创建/合并 Paper/Patent 与关联节点之间的关系。
    """
    all_queries = []
    processed_titles = set()  # 跟踪已处理的标题，以防输入列表未完全去重

    # 确定所有将被作为独立节点处理的键，以便在设置文献节点属性时忽略它们
    keys_handled_as_nodes = set()
    for cfg in link_config:
        keys = cfg['record_keys']
        if isinstance(keys, list):
            keys_handled_as_nodes.update(keys)  # 如果是列表，添加所有键
        else:
            keys_handled_as_nodes.add(keys)  # 如果是单个键，添加该键
    # 始终将 "Title" 视为特殊处理，因为它用于 MERGE，不通过 SET 设置
    keys_handled_as_nodes.add("Title")

    # 遍历所有记录
    for record in records:
        title = record.get("Title")
        # 跳过没有标题或标题已处理过的记录
        if not title or title in processed_titles:
            continue

        processed_titles.add(title)  # 记录已处理的标题
        title_safe = _escape_cypher_string(title)
        # 判断是 Paper 还是 Patent
        paper_node_type = record.get("Reference Type")
        # 定义用于匹配文献节点的 Cypher 片段
        paper_match_clause = f"(p:{paper_node_type} {{title: '{title_safe}'}})"

        # 1. 生成 Paper/Patent 节点的查询语句
        # 传入 keys_handled_as_nodes，这样这些键就不会被当作普通属性添加
        paper_queries = generate_paper_patent_node_queries(record, keys_handled_as_nodes)
        all_queries.extend(paper_queries)
        # 如果未能生成文献节点查询（理论上不应发生，因为有标题检查），则跳过后续处理
        if not paper_queries:
            continue

        # 2. 处理当前记录中配置的关联节点和关系
        for item_config in link_config:
            record_keys = item_config['record_keys']
            # 统一处理成列表，方便迭代
            if not isinstance(record_keys, list):
                record_keys = [record_keys]

            # 从记录中查找第一个非空的属性值
            value = None
            for r_key in record_keys:
                raw_value = record.get(r_key)
                # 检查是否为非空字符串或非空列表
                if (isinstance(raw_value, str) and raw_value) or \
                        (isinstance(raw_value, list) and raw_value):
                    value = raw_value
                    break  # 找到第一个就使用

            # 如果没有找到有效的属性值，则跳过此配置项
            if not value:
                continue

            node_label = item_config['node_label']
            node_id_prop = item_config['node_id_prop']
            rel_type = item_config['rel_type']
            rel_direction = item_config['rel_direction']

            # 处理列表值和单个字符串值
            values_to_process = []
            if isinstance(value, list):
                # 确保列表中的项是有效（非空）的字符串
                values_to_process.extend(item for item in value if isinstance(item, str) and item)
            elif isinstance(value, str):
                values_to_process.append(value)
            # 其他类型（如整数年份）不应在此处作为关联节点处理，会被忽略

            # 为每个有效值生成节点和关系的 MERGE 查询
            for val in values_to_process:
                safe_val = _escape_cypher_string(val)
                # 定义用于匹配新关联节点的 Cypher 片段
                new_node_match_clause = f"(n:{node_label} {{{node_id_prop}: '{safe_val}'}})"

                # MERGE 新的关联节点 (Author, Keyword, Organization 等)
                merge_node_query = f"MERGE {new_node_match_clause};"
                all_queries.append(merge_node_query)

                # MERGE 关系
                # 使用上面定义的匹配片段构建完整的 MATCH 子句
                if rel_direction == 'from_new':  # 例如：(Author)-[:AUTHORED]->(Paper)
                    merge_rel_query = f"MATCH {new_node_match_clause}, {paper_match_clause} MERGE (n)-[:{rel_type}]->(p);"
                else:  # 默认为 'to_new'，例如：(Paper)-[:HAS_KEYWORD]->(Keyword)
                    merge_rel_query = f"MATCH {new_node_match_clause}, {paper_match_clause} MERGE (p)-[:{rel_type}]->(n);"

                all_queries.append(merge_rel_query)

    # 对生成的查询列表进行去重（使用 dict.fromkeys 保留顺序）
    final_queries = list(dict.fromkeys(all_queries))
    print(f"总共生成 {len(records)} 条记录的 Cypher 查询，去重后得到 {len(final_queries)} 条唯一查询语句。")
    return final_queries


if __name__ == '__main__':
    # ============================TEST CODE===========================

    from cleaner import cleaner  # 导入原始 cleaner
    from keyword_merger import keyword_merging  # 导入更新后的 keyword_merger

    # --- 数据加载与清洗 (使用原始 cleaner) ---
    # data_dir = "data/src_data/QuantumInfo/论文" # 示例目录
    data_dir = "./data/src_data/Medicine/论文"
    print("运行原始 cleaner 清洗数据...")
    cleaned_data = cleaner(data_dir)  # 调用原始 cleaner 的逻辑

    # --- 关键词合并 (使用更新后的 merger) ---
    print("运行关键词合并...")
    # 合并 Keywords
    merged_data = keyword_merging(cleaned_data, key_names=['Keywords'], similarity_threshold=0.9)
    # 合并 Publishers 和 Places Published
    merged_data = keyword_merging(merged_data, key_names=['Author Address'], similarity_threshold=0.95)
    merged_data = keyword_merging(merged_data, key_names=['Place Published', 'Publisher'], similarity_threshold=0.9)
    print(f"数据准备完毕，共 {len(merged_data)} 条记录用于提取 Cypher 查询。")

    # --- Cypher 生成 (使用本文件中的 extractor) ---
    print("生成 Cypher 查询语句...")
    # 传入合并后的数据，可选择性传入配置 (默认为 NODE_LINK_CONFIG)
    cypher_queries = generate_neo4j_graph_queries(merged_data)
    print(f"生成了 {len(cypher_queries)} 条唯一的 Cypher 查询语句。")  # 这行信息已移到函数内部打印
