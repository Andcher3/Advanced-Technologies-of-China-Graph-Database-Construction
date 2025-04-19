from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
import numpy as np

model = SentenceTransformer("shibing624/text2vec-base-chinese")


def keyword_merging(deduped_records: list, key_names: list, similarity_threshold: float = 0.9, only_merged_value=False) -> list:
    """
    对 deduped_records 中指定的一个或多个属性（key_names）的值进行同义词归并。
    使用预训练的中文句向量模型生成所有相关值的嵌入，然后使用层次聚类
    （基于余弦距离，距离阈值 = 1 - similarity_threshold）合并相似度高于阈值的词语/短语，
    最后更新每条记录中对应的属性值（如果是列表，则去重）。

    参数：
      deduped_records: 数据记录列表。
      key_names: 需要进行合并的属性名列表 (e.g., ['Keywords'] or ['Place Published', 'Publisher']).
      similarity_threshold: 合并阈值（基于余弦相似度，例如 0.9）。

    返回：
      更新后的 deduped_records 列表。
    """
    if not key_names:
        print("Warning: No key_names provided for merging.")
        return deduped_records

    # 1. 提取指定属性中的所有非空字符串值
    all_values = set()
    for record in deduped_records:
        for key_name in key_names:
            value = record.get(key_name)
            if isinstance(value, str) and value:
                all_values.add(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item:
                        all_values.add(item)

    all_values_list = list(all_values)
    if not all_values_list:
        print(f"No values found for keys {key_names} to merge.")
        return deduped_records # Nothing to merge

    print(f"Found {len(all_values_list)} unique values across keys {key_names}.")

    # 2. 计算每个值的嵌入向量
    print("Calculating embeddings...")
    embeddings = model.encode(all_values_list, show_progress_bar=True, batch_size=128) # Added batch_size
    embeddings = np.array(embeddings)

    # 3. 层次聚类
    print("Starting merging/clustering...")

    clustering_model = AgglomerativeClustering(n_clusters=None,
                                               linkage='average',
                                               distance_threshold=1 - similarity_threshold,
                                               metric='cosine') # Changed affinity to metric for newer sklearn versions
    clustering_model.fit(embeddings)
    labels = clustering_model.labels_

    # 4. 建立映射：选择每个组中字典序最小的词作为代表
    clusters = {}
    for i, label in enumerate(labels):
        clusters.setdefault(label, []).append(all_values_list[i])

    mapping = {}
    print(f"Merging finished. Found {len(clusters)} clusters for keys {key_names}.")
    merged_count = 0
    for group in clusters.values():
        if not group: continue # Should not happen, but safeguard
        # Choose representative (e.g., shortest, or alphabetically first)
        # Using alphabetically first here
        rep = min(group)
        if len(group) > 1:
            # print(f"Merging group: {group} -> '{rep}'") # Optional: Log merged groups
            merged_count += (len(group) -1)
        for val in group:
            mapping[val] = rep
    print(f"Total items merged into representatives: {merged_count}")

    # 5. 更新每条记录中的指定属性值
    for record in deduped_records:
        for key_name in key_names:
            if key_name in record:
                original_value = record[key_name]
                if isinstance(original_value, str):
                    # Map the string value if it's in the mapping
                    record[key_name] = mapping.get(original_value, original_value)
                elif isinstance(original_value, list):
                    # Map each item in the list and remove duplicates
                    new_list = [mapping.get(item, item) for item in original_value if isinstance(item, str)]
                    # Keep unique values while preserving order (if important) or just use set for simplicity
                    record[key_name] = list(dict.fromkeys(new_list)) # Preserves order
                    # record[key_name] = list(set(new_list)) # Simpler, order not guaranteed

        return deduped_records


if __name__ == '__main__':

    # NOTE:
    from cleaner import cleaner

    deduped_records = cleaner(data_dir='data/src_data/QuantumInfo/论文/')
    fully_cleaned = keyword_merging(deduped_records)
