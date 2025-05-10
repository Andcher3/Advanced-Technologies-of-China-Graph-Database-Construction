import json
import os
from typing import Optional

from openai import OpenAI
from tqdm import tqdm
import time
from collections import defaultdict

# --- DeepSeek API 客户端初始化 ---
# 请确保 API Key 和 Base URL 是正确的，并且你有足够的配额
DEEPSEEK_API_KEY = "sk-5d02bdfb0c9a4c67a4ea6bf27ecb0792"  # 你的 API Key
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"  # 或者 "deepseek-chat" 如果你觉得它更适合处理结构化文本

client = None


def initialize_deepseek_client():
    global client
    if client is None:
        try:
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            # 可以尝试发送一个简单的测试请求来验证连接和认证
            client.models.list()
            print("DeepSeek API 客户端初始化成功。")
        except Exception as e:
            print(f"DeepSeek API 客户端初始化失败: {e}")
            client = None
    return client


def _parse_deepseek_response(response_text: str, original_cluster_keys: list) -> dict:
    """
    解析 DeepSeek API 返回的文本，将其转换为映射字典。
    确保原始簇中的每个键都有一个映射。
    """
    lines = response_text.strip().split('\n')
    parsed_mapping = {}
    seen_keys = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            # 尝试匹配 "原始词": "代表词" 或 '原始词': '代表词' (处理引号)
            # 更鲁棒的解析可能需要正则表达式，但这里先用简单分割
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip().strip('"').strip("'")
                value = parts[1].strip().strip('"').strip("'")
                if key:  # 确保 key 不是空的
                    parsed_mapping[key] = value
                    seen_keys.add(key)
            else:
                print(f"警告：无法解析API响应行: '{line}'")
        except Exception as e:
            print(f"警告：解析API响应行 '{line}' 时出错: {e}")

    # 确保原始簇中的所有 key 都在新的映射中，如果API遗漏了，则让其映射到自身
    for key in original_cluster_keys:
        if key not in parsed_mapping:
            print(f"警告：API响应中缺少对原始词 '{key}' 的映射，将使其映射到自身。")
            parsed_mapping[key] = key

    return parsed_mapping


def call_deepseek_api_for_correction(cluster_string: str, max_retries: int = 3, retry_delay: int = 5) -> Optional[str]:
    """
    调用 DeepSeek API 进行簇校正。
    """
    if client is None:
        print("错误：DeepSeek API 客户端未初始化。")
        return None

    system_prompt = """你是一个实体合并助手。你的任务是判断给定的一组词语是否应该合并为同一个概念，并给出最合适的代表词。

请根据以下规则进行判断和输出：
1. 若簇中词语指向同一机构或地点，且当前代表词是合适的，请直接输出原始内容，格式与输入相同。
2. 若簇中词语指向同一机构或地点，但当前的代表词不够好（例如，不是最常用或最规范的），请选择一个更合适的代表词，并输出更新后的簇，所有原始词都映射到新的代表词，格式与输入相同。
3. 若簇中某些词语不应与其他词语合并，或整个簇的合并都不合理，请将它们拆分开。对于每个独立的子概念，选择一个代表词，并输出所有原始词到其对应正确代表词的映射。确保原始簇中的每一个词都有一个映射，即使它自己成为代表词。输出格式仍然是每行一个 "原始词": "代表词"。

请严格按照上述格式输出，不要包含任何额外的解释或说明文字。

如输入是：
"大连理工大学": "大连理工大学",
"DUT": "大连理工大学",
"大工": "大连理工大学",
输出应该是（假设合并合理）：
"大连理工大学": "大连理工大学",
"DUT": "大连理工大学",
"大工": "大连理工大学",

如输入是：
"四川大学": "四川大学",
"川大": "四川大学",
"四川科技大学": "四川大学",
输出应该是（假设需要拆分）：
"四川大学": "四川大学",
"川大": "四川大学",
"四川科技大学": "四川科技大学",
"""
    user_content = f"请校正以下词语簇：\n{cluster_string}"

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    # 将簇内容直接嵌入系统提示，或作为用户消息的一部分
                    {"role": "user", "content": user_content} # 或者这样传递
                ],
                stream=False,
                max_tokens=1024  # 根据簇大小调整，确保能容纳所有输出
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"调用 DeepSeek API 失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"将在 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                print("达到最大重试次数，放弃此簇。")
                return None  # 返回 None 表示API调用失败


def refine_mapping_with_deepseek(original_mapping_path: str, refined_mapping_path: str,
                                 min_cluster_size_for_api: int = 2):
    """
    加载原始映射表，对其中大小 >= min_cluster_size_for_api 的簇调用 DeepSeek API 进行校正，
    并保存精炼后的映射表。
    参数:
      original_mapping_path: 原始映射表 (JSON) 的路径。
      refined_mapping_path: 保存精炼后映射表 (JSON) 的路径。
      min_cluster_size_for_api: 簇中至少有多少个不同的原始词才调用 API（默认 2，代表词本身不算）。
    """
    if initialize_deepseek_client() is None:
        print("无法进行映射精炼，因为 DeepSeek API 客户端初始化失败。")
        return

    try:
        with open(original_mapping_path, 'r', encoding='utf-8') as f:
            original_mapping = json.load(f)
        print(f"成功加载 {len(original_mapping)} 条原始映射。")
    except Exception as e:
        print(f"加载原始映射文件失败: {e}")
        return

    # 1. 将原始映射转换为按代表词组织的簇
    clusters_to_refine = defaultdict(dict)
    for original_word, rep_word in original_mapping.items():
        clusters_to_refine[rep_word][original_word] = rep_word

    refined_mapping = {}
    processed_original_words = set()
    print(f"共找到 {len(clusters_to_refine)} 个簇。")

    # 2. 筛选出需要调用 API 的簇，并统计跳过的小簇数量
    cluster_items = list(clusters_to_refine.items())
    large_clusters = []
    skip_count = 0
    for rep, cluster_map in cluster_items:
        distinct_keys = set(cluster_map.keys())
        if len(distinct_keys) >= min_cluster_size_for_api:
            large_clusters.append((rep, cluster_map))
        else:
            skip_count += 1

    # 3. 遍历并校正满足条件的大簇
    for rep, cluster_map in tqdm(large_clusters, desc="通过 DeepSeek API 校正簇"):
        distinct_keys = set(cluster_map.keys())
        # 构造发送给 API 的簇字符串
        cluster_lines = [f'"{orig}": "{cluster_map[orig]}"' for orig in cluster_map]
        cluster_str = "\n".join(cluster_lines)

        print(f"\n正在处理代表词 '{rep}' 的簇 (包含 {len(distinct_keys)} 个唯一原始词):")
        api_response = call_deepseek_api_for_correction(cluster_str)
        if api_response:
            corrected = _parse_deepseek_response(api_response, list(cluster_map.keys()))
            for original_word, new_rep in corrected.items():
                refined_mapping[original_word] = new_rep
                processed_original_words.add(original_word)
        else:
            print("API 调用失败，簇保持原映射。")
            for original, rep_word in cluster_map.items():
                if original not in processed_original_words:
                    refined_mapping[original] = rep_word
                    processed_original_words.add(original)


    # 统计并报告跳过的小簇数量
    print(f"\n跳过了 {skip_count} 个簇 (原始词数量 < {min_cluster_size_for_api})。")

    # 4. 添加未经过 API 处理的映射（单个元素簇或漏掉的映射）
    unprocessed_count = 0
    for original_word, rep_word in original_mapping.items():
        if original_word not in processed_original_words:
            refined_mapping[original_word] = rep_word
            processed_original_words.add(original_word)
            unprocessed_count += 1
    print(f"添加了 {unprocessed_count} 条未经过API处理的映射。")

    # 5. 保存精炼后的映射表
    try:
        os.makedirs(os.path.dirname(refined_mapping_path), exist_ok=True)
        with open(refined_mapping_path, 'w', encoding='utf-8') as f:
            json.dump(refined_mapping, f, ensure_ascii=False, indent=4)
        print(f"精炼后的映射已成功保存到 {refined_mapping_path}。")
    except Exception as e:
        print(f"保存精炼后映射文件失败: {e}")



if __name__ == '__main__':

    # --- 指定路径并调用精炼函数 ---
    # 确保这个原始映射文件存在，并且包含一些可以被API校正的簇
    from Hype import MERGED_SAVED_PATH

    original_map_path = MERGED_SAVED_PATH['Publisher']
    refined_map_path = "data/refined_publisher.json"  # 精炼后映射的保存路径

    # 创建一个假的原始映射文件用于测试
    if not os.path.exists(original_map_path):
        print(f"没有找到路径{original_map_path}")
        exit(0)

    refine_mapping_with_deepseek(original_map_path, refined_map_path, min_cluster_size_for_api=2)
