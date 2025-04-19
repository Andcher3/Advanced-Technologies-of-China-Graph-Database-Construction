# --- START OF FILE extractor.py ---
import re


# --- 辅助函数 (Helper Functions) ---

def _escape_cypher_string(value: str) -> str:
    """对字符串进行转义，以便在 Cypher 查询中安全使用。"""
    if not isinstance(value, str):
        value = str(value)  # 将非字符串转为字符串
    # 转义单引号和反斜杠
    return value.replace('\\', '\\\\').replace("'", "\\'")


def _normalize_prop_key(key: str) -> str:
    """标准化属性键名（小写，下划线替换空格和连字符，处理斜杠等特殊字符）。"""
    prop_key = key.lower().replace(" ", "_").replace("-", "_")
    # 如果键名包含特殊字符（如此处的 /）或不符合标准变量命名规则，则使用反引号包裹
    if "/" in prop_key or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', prop_key):
        prop_key = f"`{prop_key}`"
    return prop_key


def _format_cypher_properties(props_dict: dict) -> str:
    """将属性字典格式化为用于 SET 或 CREATE 的 Cypher Map 字符串。"""
    props = []
    for key, value in props_dict.items():
        prop_key = _normalize_prop_key(key)
        if isinstance(value, (int, float, bool)):
            # 直接处理数字和布尔值
            props.append(f"{prop_key}: {value}")
        elif isinstance(value, list):
            # 格式化列表：对每个非 None 的字符串项进行转义
            list_items = [_escape_cypher_string(item) for item in value if item is not None]
            # 确保列表项被引号包裹
            list_str = "[" + ", ".join(f"'{item}'" for item in list_items) + "]"
            props.append(f"{prop_key}: {list_str}")
        elif isinstance(value, str):
            # 对字符串进行转义和加引号
            safe_val = _escape_cypher_string(value)
            props.append(f"{prop_key}: '{safe_val}'")
        # 忽略 None 或其他不支持的类型
    return f"{{{', '.join(props)}}}"


# --- 核心节点生成函数 ---

def generate_paper_patent_node_queries(record: dict, keys_to_ignore: set) -> list:
    """
    为 Paper 或 Patent 节点生成 MERGE/SET 查询，忽略指定的键。
    返回包含 MERGE 查询和可能的 SET 查询的列表。
    如果找不到标题，则返回空列表。
    """
    queries = []
    title = record.get("Title")
    if not title:
        return []  # 跳过没有标题的记录

    title_safe = _escape_cypher_string(title)
    # 根据 'Reference Type' 判断节点类型是 Paper 还是 Patent
    node_type = record.get("Reference Type").replace(" ", "_")

    # 构建节点属性字典，排除那些将作为独立节点处理的键或显式忽略的键
    node_props = {}
    for key, value in record.items():
        # 仅当键不在忽略列表中且值非空时才添加为属性
        if key not in keys_to_ignore and value not in [None, "", []]:
            node_props[key] = value

    # 确保 title 始终包含在内，用于后续匹配
    node_props['title'] = title  # 这里使用原始 title，格式化函数会处理转义

    # 仅基于 title 进行 MERGE 操作，确保节点唯一性
    merge_query = f"MERGE (p:{node_type} {{title: '{title_safe}'}})"
    queries.append(merge_query)

    # 使用 SET 添加或更新其他属性
    # 从待 SET 的属性中过滤掉 title 本身（因为它已在 MERGE 中使用）
    set_props = {k: v for k, v in node_props.items() if k != 'title'}
    if set_props:
        props_cypher_str = _format_cypher_properties(set_props)
        # 使用 SET p += props 来合并属性，这会添加新属性并更新现有属性
        set_query = f"MATCH (p:{node_type} {{title: '{title_safe}'}}) SET p += {props_cypher_str};"
        queries.append(set_query)

    return queries


if __name__ == '__main__':
    pass

# --- END OF FILE extractor.py ---
