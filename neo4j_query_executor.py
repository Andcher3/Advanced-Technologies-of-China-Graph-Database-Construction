import json
import os
from typing import List, Tuple, Optional, Any, Dict

from neo4j.graph import Node, Relationship, Path
from neo4j import GraphDatabase,  Record

# --- Neo4j 连接信息 (需要根据你的实际情况修改) ---
# 建议从配置文件或环境变量读取
NEO4J_URI = "bolt://10.9.116.110:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456788"

# 全局 Driver 实例
neo4j_driver: Optional[GraphDatabase.driver] = None


def get_neo4j_driver():
    """获取或初始化 Neo4j Driver 实例"""
    global neo4j_driver
    if neo4j_driver is None:
        try:
            # 可以根据需要调整连接池大小等参数
            neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            # 验证连接
            neo4j_driver.verify_connectivity()
            print("Neo4j Driver 初始化成功。")
        except Exception as e:
            print(f"Neo4j Driver 初始化或连接失败: {e}")
            neo4j_driver = None
    return neo4j_driver


def close_neo4j_driver():
    """关闭 Neo4j Driver 连接"""
    global neo4j_driver
    if neo4j_driver:
        neo4j_driver.close()
        neo4j_driver = None
        print("Neo4j Driver 已关闭。")


# --- 结果格式化函数 ---
def _format_neo4j_value_for_llm(value: Any) -> str:
    """
    将 Neo4j 返回的不同类型的值格式化为适合大模型阅读的字符串表示。
    尝试识别常见的节点ID属性（如 name, title, paper_id）。
    """
    if isinstance(value, Node):
        labels = ":".join(list(value.labels))
        properties_str_parts = []
        # 尝试获取主要的标识属性
        if 'name' in value:
            properties_str_parts.append(f"name: '{value['name']}'")
        if 'title' in value:
            properties_str_parts.append(f"title: '{value['title']}'")
        if 'paper_id' in value:  # 假设你的 paper_id 属性
            properties_str_parts.append(f"paper_id: '{value['paper_id']}'")
        # 可以添加更多常见的标识属性

        # 如果没有找到标识属性，或者想包含更多属性，可以遍历所有属性
        for prop_key, prop_value in value.items():
            if prop_key not in ['name', 'title', 'paper_id']:  # 避免重复添加
                # 递归格式化属性值，注意避免无限递归复杂对象
                properties_str_parts.append(f"{prop_key}: '{prop_value}'")  # 简化处理，直接转字符串可能不够

        properties_str = ", ".join(properties_str_parts)
        return f"({labels} {{{properties_str}}})" if properties_str else f"({labels})"

    elif isinstance(value, Relationship):
        # 只显示关系类型
        return f"-[:{value.type}]-"
        # 如果需要包含关系属性，会更复杂
        # return f"-[:{value.type} {{...}}]-"

    elif isinstance(value, Path):
        path_parts = []
        for i, item in enumerate(value):
            if i % 2 == 0:  # 节点
                path_parts.append(_format_neo4j_value_for_llm(item))
            else:  # 关系
                # 路径中的关系是带有方向的，但这里的格式化简化为无方向
                path_parts.append(_format_neo4j_value_for_llm(item))
        return "->".join(path_parts)  # 简化表示，不严格区分关系方向

    elif isinstance(value, list):
        # 格式化列表中的每个元素
        formatted_items = [_format_neo4j_value_for_llm(item) for item in value]
        return "[" + ", ".join(formatted_items) + "]"

    elif isinstance(value, dict):
        # 格式化字典中的键值对
        formatted_items = [f"{k}: {_format_neo4j_value_for_llm(v)}" for k, v in value.items()]
        return "{" + ", ".join(formatted_items) + "}"

    else:
        # 格式化基本数据类型
        return str(value)


def format_neo4j_results_for_llm(result_records: List[Record], returned_keys: List[str]) -> str:
    """
    将 Neo4j 查询返回的 Record 列表格式化为适合大模型阅读的字符串。
    """
    if not result_records:
        return "查询没有返回任何结果。"

    formatted_output_lines = ["查询结果如下："]

    for i, record in enumerate(result_records):
        formatted_output_lines.append(f"--- 记录 {i + 1} ---")
        record_str_parts = []
        # 遍历查询返回的每一列
        for key in returned_keys:
            value = record[key]
            formatted_value = _format_neo4j_value_for_llm(value)
            record_str_parts.append(f"{key}: {formatted_value}")
        formatted_output_lines.append(", ".join(record_str_parts))

    return "\n".join(formatted_output_lines)


# --- Cypher 查询执行函数 ---
def execute_cypher_query(query_string: str) -> Tuple[Optional[List[Record]], Optional[str]]:
    """
    执行给定的 Cypher 查询字符串，返回查询结果（Record 列表）或错误信息。

    参数:
      query_string: 要执行的 Cypher 查询字符串。

    返回:
      一个元组 (results, error_message)。
      如果执行成功，results 是 Record 对象的列表，error_message 为 None。
      如果执行失败，results 为 None，error_message 为错误字符串。
    """
    driver = get_neo4j_driver()
    if driver is None:
        return None, "Neo4j Driver 未成功初始化，无法连接数据库。"

    try:
        with driver.session() as session:
            # 执行查询
            result = session.run(query_string, suppress=["Neo.ClientNotification.Statement.UnknownRelationshipTypeWarning"])
            # 获取所有返回的记录
            records = list(result)
            # 返回 Record 对象列表和 None 作为错误信息
            return records, None

    except Exception as e:
        # 捕获查询执行过程中的任何异常
        error_message = str(e)
        print(f"Cypher 查询执行失败: {error_message}\n查询: {query_string}")
        return None, error_message


# --- 与大模型交互的集成示例 (概念性代码) ---

# 假设你已经有了大模型的客户端初始化代码
from openai import OpenAI
DEEPSEEK_API_KEY = "sk-5d02bdfb0c9a4c67a4ea6bf27ecb0792"  # 你的 API Key
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"  # 或者 "deepseek-chat" 如果你觉得它更适合处理结构化文本
llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# 假设你的图谱 Schema 可以用文本描述（需要根据你的实际 Schema 编写）
# 可以是节点标签、属性、关系类型及其方向的列表或结构化描述
GRAPH_SCHEMA_DESCRIPTION = """
你的知识图谱包含以下节点和关系：
节点标签:
- Journal_Article {"title", ":ID", ":LABEL", "abstract", "database_provider", "isbn/issn", "journal", "notes", "pages", "reference_type", "url"
         "doi", "volume", "year", "issue"}
- Conference_Proceedings {"title", ":ID", ":LABEL", "abstract", "database_provider", "doi", "pages", "reference_type", "url", "year", "secondary_title", 
         "subsidiary_author", "tertiary_title"}   
- Patent {"title", ":ID", ":LABEL", "abstract", "notes", "reference_type", "subsidiary_author", "date", "srcdatabase", "subject"}
- Newspaper_Article {"title", ":ID", ":LABEL", "database_provider", "doi", "notes", "pages", "reference_type", "url", "secondary_title", "date"}
- Thesis {"title", ":ID", ":LABEL", "abstract", "database_provider", "doi", "reference_type", "url", "year", "type_of_work"}
- Other_Article {"title", ":ID", ":LABEL", "abstract", "notes", "reference_type", "date"}
- Book {"title", ":ID", ":LABEL", "abstract", "database_provider", "isbn/issn", "pages", "reference_type", "date", "edition"}
- Author {"name", ":ID", ":LABEL"}
- Keyword {"name", ":ID", ":LABEL"}
- Organization {"name", ":ID", ":LABEL"}
- Author_Address {"name", ":ID", ":LABEL"}
- Topic {"name",, ":ID", ":LABEL"} 

关系类型:
- (Author)-[:AUTHORED]->(Paper/Patent)
- (Author)-[:TERTIARY_AUTHORED]->(Paper/Patent)
- (Paper/Patent)-[:HAS_KEYWORD]->(Keyword)
- (Paper/Patent)-[:PUBLISHED_BY]->(Organization)
- (Paper/Patent)-[:HAS_AUTHOR_ADDRESS]->(AuthorAddress)
- (Keyword)-[:ALIAS_OF]->(Keyword)
- (Organization)-[:ALIAS_OF]->(Organization)
- (AuthorAddress)-[:ALIAS_OF]->(AuthorAddress)
- (Paper/Patent)-[:HAS_TOPIC]->(Topic)

查询时请使用节点属性进行匹配，例如 `title`, `name`, `paper_id`
"""


def query_knowledge_graph_with_llm(user_question: str, llm_client: Any) -> str:
    """
    使用大模型回答关于知识图谱的问题。
    这是一个简化的两阶段过程：用户问题 -> LLM生成Cypher -> 执行Cypher -> LLM根据结果生成答案。
    实际问答系统会更复杂，包含多轮交互、意图识别、实体链接、回退机制等。
    """
    # 阶段 1: LLM 将用户问题转换为 Cypher 查询
    print(f"用户问题: {user_question}")
    print("阶段 1: 请求 LLM 生成 Cypher 查询...")

    cypher_generation_prompt = f"""
    你的知识图谱Schema如下：
    {GRAPH_SCHEMA_DESCRIPTION}
    
    重要说明：
    - **别名关系**: `(Keyword)-[:ALIAS_OF]->(Keyword)`, `(Organization)-[:ALIAS_OF]->(Organization)`, `(AuthorAddress)-[:ALIAS_OF]->(AuthorAddress)`. 并非所有 Keyword/Organization/AuthorAddress 节点都有别名关系。
    - **部分节点属性可能缺失**: 例如，某些文献可能没有 year, abstract, url, doi 等属性。
    
    生成Cypher查询的规则：
    1.  **处理可选关系 (如别名关系):** 当你需要查询一个节点及其别名或相关联的可选节点时，请使用 `OPTIONAL MATCH`。例如，要查找一个Keyword及其别名，使用 `MATCH (k:Keyword {{name: "某个词"}}) OPTIONAL MATCH (k)-[:ALIAS_OF]->(alias)`。之后在 WHERE 子句中可以使用 `WHERE relatedNode = k OR relatedNode = alias` 来匹配原始节点或其别名。
    2.  **处理可选属性:** 在 WHERE 子句中直接比较属性值 (例如 `p.year = 2022`) 会自动排除缺失该属性的节点。如果你只想查找**拥有**某个特定属性的节点，可以使用 `WHERE node.property IS NOT NULL`。
    3.  **确保数据类型匹配:** 在比较属性值时，请根据Schema使用正确的数据类型，例如年份是整数，使用 `p.year = 2022` 而不是 `"2022"`。
    4.  **使用节点属性匹配:** 在 MATCH 或 MERGE 时，使用 `name`, `title`, `paper_id` 等属性来精确匹配节点。
    5.  **限制结果数量:** 通常在 RETURN 语句后加上 `LIMIT 10`，除非用户明确要求返回所有结果。
    
    请严格按照上述Schema和规则生成Cypher查询语句，只输出查询本身，不要包含任何额外文字或解释。
    用户的输入可能会带有错别字，请谨慎的判别是否有错别字并替换为正确的短语。
    
    示例1 (处理关键词别名和年份过滤):
    用户问题: 2022年关于肺癌的论文有哪些？
    Cypher 查询:
    MATCH (k:Keyword {{name: "肺癌"}})
    OPTIONAL MATCH (k)-[:ALIAS_OF]->(alias) // 使用 OPTIONAL MATCH 处理可选的别名关系
    MATCH (p)-[:HAS_KEYWORD]->(relatedKeyword) // 匹配与关键词相关的论文
    WHERE (relatedKeyword = k OR relatedKeyword = alias) // 相关的关键词是原始关键词或其别名
      AND (p:Paper OR p:Patent) // 确保是文献节点 (根据你的实际主要文献标签调整)
      AND p.year = 2022 // 过滤年份，直接比较数值类型
    RETURN p.title, p.year LIMIT 10
    
    示例2 (查找所有有摘要的专利):
    用户问题: 查找所有有摘要的专利。
    Cypher 查询:
    MATCH (p:Patent)
    WHERE p.abstract IS NOT NULL // 只匹配有摘要属性的专利
    RETURN p.title, p.abstract LIMIT 10
    
    示例3 (查找某个作者在特定年份发表的论文):
    用户问题: 张三在2023年发表了哪些论文？
    Cypher 查询:
    MATCH (a:Author {{name: "张三"}})-[:AUTHORED]->(p:Paper) // 假设AUTHORED关系只连接Paper
    WHERE p.year = 2023
    RETURN p.title, p.year LIMIT 10
    
    
    用户问题: {user_question}
    Cypher 查询:
    """

    messages_for_cypher = [
        {"role": "system", "content": cypher_generation_prompt},
        {"role": "user", "content": user_question}  # 也可以把问题放在用户消息里
    ]

    try:
        # 调用大模型 API
        response_cypher = llm_client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages_for_cypher,
            temperature=0,  # 生成 Cypher 需要确定性
            max_tokens=500  # 根据预期 Cypher 长度调整
        )
        generated_cypher = response_cypher.choices[0].message.content.strip()
        print(f"LLM 生成的 Cypher 查询:\n{generated_cypher}")

    except Exception as e:
        print(f"LLM 生成 Cypher 查询失败: {e}")
        return f"抱歉，无法将您的问题转换为图谱查询 ({e})"

    # 阶段 2: 执行 Cypher 查询
    print("阶段 2: 执行 Cypher 查询...")
    query_results, execution_error = execute_cypher_query(generated_cypher)

    # 阶段 3: LLM 根据查询结果生成最终答案
    if execution_error:
        # 如果执行失败，将错误信息反馈给用户（或者尝试让LLM修正查询）
        print(f"查询执行错误: {execution_error}")
        return f"抱歉，执行图谱查询时出错: {execution_error}"
    else:
        print(f"查询执行成功，返回 {len(query_results)} 条记录。")
        # 将查询结果格式化为文本
        formatted_results_text = format_neo4j_results_for_llm(query_results,
                                                              query_results[0].keys() if query_results else [])

        # 如果结果为空，直接返回提示
        if "查询没有返回任何结果" in formatted_results_text:
            return "抱歉，未能找到相关信息。"

        print("阶段 3: 请求 LLM 根据结果生成自然语言答案...")

        answer_generation_prompt = f"""
        你是一个知识图谱问答助手。根据提供的查询结果，用自然语言简洁地回答用户的问题。
        只使用提供的查询结果中的信息。如果结果无法回答问题，请说明。

        用户问题: {user_question}

        查询结果：
        {formatted_results_text}

        根据以上信息，用自然语言回答用户的问题：
        """

        messages_for_answer = [
            {"role": "system", "content": answer_generation_prompt},
            {"role": "user", "content": f"回答用户问题：'{user_question}'"}  # 再次强调问题
        ]

        try:
            # 调用大模型 API 生成答案
            response_answer = llm_client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages_for_answer,
                temperature=0.5,  # 生成答案可以稍微灵活
                max_tokens=500  # 根据预期答案长度调整
            )
            final_answer = response_answer.choices[0].message.content.strip()
            print(f"LLM 生成的最终答案:\n{final_answer}")
            return final_answer

        except Exception as e:
            print(f"LLM 生成最终答案失败: {e}")
            return f"抱歉，处理查询结果时遇到问题 ({e})"


# --- 主函数示例 (需要实际运行环境和 API Key) ---
if __name__ == "__main__":
    # 初始化 Neo4j Driver
    neo4j_driver = get_neo4j_driver()
    if neo4j_driver is None:
        exit(1)  # 如果驱动初始化失败则退出

    # 导入大模型客户端 (需要安装 openai 库并配置 API Key)
    try:
        from openai import OpenAI

        # 请确保在这里设置你的 DeepSeek 或其他 API Key
        # 建议使用环境变量或配置文件
        DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-5d02bdfb0c9a4c67a4ea6bf27ecb0792")
        if not DEEPSEEK_API_KEY:
            print("错误：请设置 DEEPSEEK_API_KEY 环境变量或在代码中提供。")
            exit(1)

        llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        # 可以再次验证 LLM API 连接
        # llm_client.models.list()
        print("大模型客户端初始化成功。")

    except ImportError:
        print("错误：请安装 openai 库 (`pip install openai`) 以使用大模型API。")
        exit(1)
    except Exception as e:
        print(f"大模型客户端初始化失败: {e}")
        exit(1)

    # --- 示例问答流程 ---
    print("\n--- 开始示例问答 ---")

    # 确保你的数据库中有能匹配的节点和关系，以及对应的摘要等属性
    # 这里的示例问题需要LLM能够理解并转换为Cypher
    example_question = "2022年带有唐尿病关键词的论文有哪些？"
    # 假设 LLM 可能会生成类似这样的 Cypher:
    # MATCH (p:Paper)-[:HAS_KEYWORD]->(k:Keyword) WHERE k.name = '人工智能' RETURN p.title LIMIT 10

    # 如果你有 Topic 节点
    # example_question = "关于量子计算的主题有哪些论文？"
    # 假设 LLM 可能会生成类似这样的 Cypher:
    # MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic {name: '量子计算'}) RETURN p.title LIMIT 10

    # 询问特定文献内容
    # example_question = "介绍一下标题为'一种新的量子密钥分发协议'的论文内容。"
    # 假设 LLM 可能生成 Cypher 来获取摘要:
    # MATCH (p:Paper {title: '一种新的量子密钥分发协议'}) RETURN p.abstract LIMIT 1

    final_answer = query_knowledge_graph_with_llm(example_question, llm_client)
    print(f"\n问答系统最终回答:\n{final_answer}")

    print("\n--- 示例问答结束 ---")

    # 关闭 Neo4j Driver
    close_neo4j_driver()
