# --- 合并后词汇映射表 ---
MERGED_SAVED_PATH = {
    "Keywords": "data/merged_keywords.json",
    'Author Address': "data/merged_address.json",
    'Publisher': "data/merged_publisher.json"
}

# --- 关联节点的配置 ---

# 定义记录中的特定属性如何映射到关联的节点和关系
# 'record_keys': 输入记录字典中的键名（或键名列表）。如果是列表，则使用找到的第一个非空值。
# 'node_label': 新节点的标签。
# 'node_id_prop': 用于 MERGE 操作以确保新节点唯一性的属性名。
# 'rel_type': 关系类型。
# 'rel_direction': 关系方向，'from_new' 表示 (新节点)-[关系]->(文献)，'to_new' 表示 (文献)-[关系]->(新节点)。
NODE_LINK_CONFIG = [
    {
        'record_keys': 'Author',  # 记录中的作者字段
        'node_label': 'Author',  # 创建/合并 Author 节点
        'node_id_prop': 'name',  # Author 节点用 name 属性唯一标识
        'rel_type': 'AUTHORED',  # 关系类型为 AUTHORED (创作了)
        'rel_direction': 'from_new'  # 方向： (Author)-[:AUTHORED]->(Paper/Patent)
    },
    {
        'record_keys': 'Tertiary Author',  # 记录中的第三作者字段
        'node_label': 'Author',  # 复用 Author 节点标签
        'node_id_prop': 'name',  # 同样用 name 属性唯一标识
        'rel_type': 'TERTIARY_AUTHORED',  # 关系类型为 TERTIARY_AUTHORED (作为第三作者创作了)
        'rel_direction': 'from_new'  # 方向： (Author)-[:TERTIARY_AUTHORED]->(Paper/Patent)
    },
    {
        'record_keys': 'Keywords',  # 记录中的关键词字段
        'node_label': 'Keyword',  # 创建/合并 Keyword 节点
        'node_id_prop': 'name',  # Keyword 节点用 name 属性唯一标识
        'rel_type': 'HAS_KEYWORD',  # 关系类型为 HAS_KEYWORD (拥有关键词)
        'rel_direction': 'to_new'  # 方向： (Paper/Patent)-[:HAS_KEYWORD]->(Keyword)
    },
    {
        'record_keys': ['Publisher', 'Place Published'],  # 处理合并后的字段（优先使用 Publisher）
        'node_label': 'Organization',  # 创建/合并 Organization 节点
        'node_id_prop': 'name',  # Organization 节点用 name 属性唯一标识
        'rel_type': 'PUBLISHED_BY',  # 关系类型为 PUBLISHED_BY (由...出版/发表)
        'rel_direction': 'to_new'  # 方向： (Paper/Patent)-[:PUBLISHED_BY]->(Organization)
    },
    # --- 在这里添加更多属性到节点的映射配置 ---
    # 示例：如果你想把 'Journal' 也作为一个节点：
    # {
    #     'record_keys': 'Journal',
    #     'node_label': 'Journal',
    #     'node_id_prop': 'name',
    #     'rel_type': 'PUBLISHED_IN',      # 关系类型：发表于
    #     'rel_direction': 'to_new'         # 方向：(Paper)-[:PUBLISHED_IN]->(Journal)
    # },
]
