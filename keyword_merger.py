from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering, DBSCAN
import numpy as np
import json  # for saving/loading
import os
from tqdm import tqdm

model = SentenceTransformer("shibing624/text2vec-base-chinese")


def keyword_merging_deprecated(deduped_records: list, key_names: list, similarity_threshold: float = 0.9,
                               only_merged_value=False) -> list:
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
        return deduped_records  # Nothing to merge

    print(f"Found {len(all_values_list)} unique values across keys {key_names}.")

    # 2. 计算每个值的嵌入向量
    print("Calculating embeddings...")
    embeddings = model.encode(all_values_list, show_progress_bar=True, batch_size=128)  # Added batch_size
    embeddings = np.array(embeddings)

    # 3. 层次聚类
    print("Starting merging/clustering...")

    clustering_model = AgglomerativeClustering(n_clusters=None,
                                               linkage='average',
                                               distance_threshold=1 - similarity_threshold,
                                               metric='cosine')  # Changed affinity to metric for newer sklearn versions
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
        if not group: continue  # Should not happen, but safeguard
        # Choose representative (e.g., shortest, or alphabetically first)
        # Using alphabetically first here
        rep = min(group)
        if len(group) > 1:
            # print(f"Merging group: {group} -> '{rep}'") # Optional: Log merged groups
            merged_count += (len(group) - 1)
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
                    record[key_name] = list(dict.fromkeys(new_list))  # Preserves order
                    # record[key_name] = list(set(new_list)) # Simpler, order not guaranteed

        return deduped_records


def keyword_merging(
        deduped_records: list,
        key_names: list,
        similarity_threshold: float = 0.9,
        mapping_file_path: str = None,  # 新增：用于加载/保存映射文件的路径
        force_recompute: bool = False  # 新增：是否强制重新计算，即使存在映射文件
) -> list:
    """
    对 deduped_records 中指定的一个或多个属性（key_names）的值进行同义词归并。
    使用预训练模型生成嵌入，然后使用层次聚类合并相似词语。
    可以加载已有的词语映射文件以跳过计算，也可以将计算结果保存。

    参数：
      deduped_records: 数据记录列表。
      key_names: 需要进行合并的属性名列表 (例如 ['Keywords'] 或 ['Place Published', 'Publisher'])。
      similarity_threshold: 合并阈值（基于余弦相似度，例如 0.9）。
      mapping_file_path: (可选) 用于加载或保存词语映射（JSON 文件）的路径。
                         如果文件存在且 `force_recompute` 为 False，则加载映射；
                         如果计算了新映射且此路径被指定，则保存映射。
      force_recompute: (可选) 如果为 True，即使 `mapping_file_path` 文件存在，也强制重新计算映射。

    返回：
      更新后的 deduped_records 列表。
    """
    if not key_names:
        print("警告：未提供用于合并的 key_names。")
        return deduped_records

    mapping = None  # 初始化映射字典

    # 1. 尝试加载已有的映射文件 (除非强制重新计算)
    if mapping_file_path and not force_recompute:
        try:
            if os.path.exists(mapping_file_path):
                with open(mapping_file_path, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                print(f"成功从 {mapping_file_path} 加载了词语映射。")
            else:
                print(f"映射文件 {mapping_file_path} 不存在，将计算新映射。")
        except (json.JSONDecodeError, IOError) as e:
            print(f"加载或读取映射文件 {mapping_file_path} 时出错: {e}。将重新计算映射。")
            mapping = None  # 确保加载失败时 mapping 为 None

    # 2. 如果没有加载映射，则进行计算
    if mapping is None:
        print(f"开始为属性 {key_names} 计算词语映射...")
        # 2.1 提取指定属性中的所有非空字符串值
        print("步骤 1/4: 提取唯一值...")
        all_values = set()
        # 使用 tqdm 显示记录迭代进度
        for record in tqdm(deduped_records, desc="提取属性值"):
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
            print(f"未找到属性 {key_names} 中的有效值进行合并。")
            # 即使没有值，也创建一个空映射，以便后续步骤统一处理
            mapping = {}
            # 如果指定了路径，可以选择保存空映射
            if mapping_file_path:
                print(f"由于未找到值，将在 {mapping_file_path} 保存空映射。")
                try:
                    with open(mapping_file_path, 'w', encoding='utf-8') as f:
                        json.dump({}, f, ensure_ascii=False, indent=4)
                except IOError as e:
                    print(f"保存空映射文件时出错: {e}")

        else:  # 只有在有值的情况下才进行计算
            print(f"步骤 1/4: 完成。找到 {len(all_values_list)} 个唯一值。")

            # 2.2 计算每个值的嵌入向量 (模型自带进度条)
            print("步骤 2/4: 计算嵌入向量...")
            # SentenceTransformer 的 encode 方法有 show_progress_bar 参数
            embeddings = model.encode(all_values_list, show_progress_bar=True, batch_size=64)  # 调小 batch_size 观察进度
            embeddings = np.array(embeddings)
            print("步骤 2/4: 完成。")

            # 2.3 层次聚类
            print("步骤 3/4: 执行DBSCAN...")
            # min_samples: 形成核心点的最小样本数。对于同义词，2 可能比较合适（自己+另一个）
            # 或者设为 1，允许单个词构成一个簇（如果它与其他词都不够近）
            min_samples = 2

            # 注意：metric='cosine' 在 DBSCAN 中意味着使用余弦距离 (1 - cosine_similarity)
            dbscan = DBSCAN(eps=1-similarity_threshold, min_samples=min_samples, metric='cosine', n_jobs=-1)  # 使用所有 CPU 核心

            # 拟合过程可能仍然需要一些时间，但内存占用通常较低
            labels = dbscan.fit_predict(embeddings)  # 或者 embeddings，如果没降维
            n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)  # -1 标签表示噪声点
            n_noise_ = list(labels).count(-1)
            print(f'步骤 3/4: 完成。估计的簇数量: {n_clusters_}')
            print(f'估计的噪声点数量: {n_noise_}，它们不会被合并')

            # 2.4 建立映射：选择每个簇中字典序最小的词作为代表
            print("步骤 4/4: 生成代表词映射...")

            # 注意：DBSCAN 可能将某些词标记为噪声 (-1)，这些词不会被合并到任何簇中
            # 在建立映射时，需要处理这些噪声点（通常让它们自成一派，即映射到自身）
            clusters = {}
            noise_points = []
            for i, label in enumerate(labels):
                if label == -1:
                    noise_points.append(all_values_list[i])
                    continue  # 跳过噪声点，后面单独处理
                clusters.setdefault(label, []).append(all_values_list[i])

            mapping = {} # 这是最终的映射
            merged_count = 0

            # 使用 tqdm 显示簇处理进度
            for group in tqdm(clusters.values(), desc="生成映射"):
                if not group: continue
                rep = min(group)  # 选择字典序最小的作为代表
                if len(group) > 1:
                    # print(f"合并组: {group} -> '{rep}'") # 可选：打印合并的组
                    merged_count += (len(group) - 1)
                for val in group:
                    mapping[val] = rep
            print(f"步骤 4/4: 完成。共形成 {len(clusters)} 个簇，{merged_count} 个词语被合并。")

            # 处理噪声点，让它们映射到自身
            for noise_word in noise_points:
                mapping[noise_word] = noise_word

            # 2.5 (可选) 保存计算出的映射
            if mapping_file_path:
                print(f"尝试将计算出的映射保存到 {mapping_file_path} ...")
                try:
                    # 创建目录（如果不存在）
                    os.makedirs(os.path.dirname(mapping_file_path), exist_ok=True)
                    with open(mapping_file_path, 'w', encoding='utf-8') as f:
                        # 使用 indent 使 JSON 文件更易读
                        json.dump(mapping, f, ensure_ascii=False, indent=4)
                    print(f"映射已成功保存到 {mapping_file_path}")
                except IOError as e:
                    print(f"保存映射文件到 {mapping_file_path} 时出错: {e}")
                except Exception as e:
                    print(f"保存映射时发生未知错误: {e}")

    # 3. 应用映射更新记录中的属性值
    print(f"开始将映射应用到 {len(deduped_records)} 条记录...")
    # 使用 tqdm 显示记录更新进度
    for record in tqdm(deduped_records, desc=f"更新记录属性 {key_names}"):
        for key_name in key_names:
            if key_name in record:
                original_value = record[key_name]
                if isinstance(original_value, str):
                    # 对字符串值，直接使用映射替换（如果存在）
                    record[key_name] = mapping.get(original_value, original_value)
                elif isinstance(original_value, list):
                    # 对列表值，映射列表中的每个字符串项，然后去重
                    new_list = [mapping.get(item, item) for item in original_value if isinstance(item, str)]
                    # 使用 dict.fromkeys 去重，同时保持大致顺序
                    record[key_name] = list(dict.fromkeys(new_list))

    print("记录更新完成。")
    return deduped_records


if __name__ == '__main__':

    from cleaner import cleaner, cleaner_all
    save_path = "data/merged_keywords.json"
    deduped_records = cleaner_all(root_dir='data/src_data/')
    fully_cleaned = keyword_merging(deduped_records, ["Keywords"], 0.95,
                                    mapping_file_path=save_path, force_recompute=True)
