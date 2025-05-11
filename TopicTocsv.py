import json
import csv
import re
from tqdm import tqdm

# === 输入和输出文件路径 ===
# !! 修改为你 classified_chinese_references.json 文件的实际路径 !!
input_json_path = r"D:\my_projects\Advanced-Technologies-of-China-Graph-Database-Construction\HaMmerData\classified_chinese_references.json"
output_csv_path = "paper_topic_relations_for_neo4j.csv" # CSV 文件将保存在脚本同目录下

# === 文献类型到 Neo4j 标签的映射 ===
# !! 你需要根据你的实际 "Reference Type" 值来完善这个映射 !!
# 键是 JSON 文件中 "Reference Type" 字段的值，值是对应的 Neo4j 节点标签。
reference_type_to_label_map = {
    "Journal Article": "Journal_Article",
    "Journal_Article": "Journal_Article", # 确保你的JSON中的类型字符串和这里一致
    "Book": "Book",
    "Conference Proceedings": "Conference_Proceedings", # 假设你的JSON里是这个字符串
    "Newspaper Article": "Newspaper_Article",
    "Thesis": "Thesis",
    # "Other Article": "Other_Article", # 如果有 "Other Article" 类型
    # ... 添加其他你实际使用的类型映射
}
# 如果JSON中的 "Reference Type" 无法在此映射中找到，可以设置一个默认标签，或者跳过该记录
default_label_if_unmapped = "Other_Article" # 或者设置为 None 如果你想跳过未映射的类型

# === 开始转换 ===
records_for_csv = []
skipped_records_count = 0

print(f"正在从 '{input_json_path}' 加载数据...")
with open(input_json_path, "r", encoding="utf-8") as f:
    paper_data = json.load(f)

print(f"数据加载完毕，共 {len(paper_data)} 条记录。开始转换为 CSV 格式...")
for record in tqdm(paper_data, desc="处理记录并准备CSV数据"):
    paper_title = record.get("Title")
    # 假设你的JSON记录中仍然保留了原始的 "Reference Type" 字段
    json_reference_type = record.get("Reference Type")
    classification = record.get("classification", {})
    topic_name_raw = classification.get("topic_name")

    if not (paper_title and json_reference_type and topic_name_raw):
        # print(f"记录信息不完整，已跳过：Title={paper_title}, RefType={json_reference_type}, TopicRaw={topic_name_raw}")
        skipped_records_count +=1
        continue

    # 1. 获取论文的 Neo4j 标签
    paper_label = reference_type_to_label_map.get(json_reference_type)
    if not paper_label:
        if default_label_if_unmapped:
            paper_label = default_label_if_unmapped
            # print(f"警告：文献 '{paper_title}' 的类型 '{json_reference_type}' 未在映射中找到，使用默认标签 '{paper_label}'。")
        else:
            # print(f"警告：文献 '{paper_title}' 的类型 '{json_reference_type}' 未在映射中找到，且无默认标签，已跳过。")
            skipped_records_count +=1
            continue
    
    # 2. 清理主题名称 (去掉括号及其内容)
    topic_name_cleaned = re.sub(r"\s*\(.*?\)", "", topic_name_raw).strip()

    if topic_name_cleaned: # 确保清理后主题名称不为空
        records_for_csv.append({
            "paperTitle": paper_title,
            "paperLabel": paper_label, # 这是论文节点的 Neo4j 标签
            "topicName": topic_name_cleaned
        })
    else:
        # print(f"记录 '{paper_title}' 的主题名称处理后为空，已跳过。原始主题: '{topic_name_raw}'")
        skipped_records_count +=1

# 3. 写入 CSV 文件
if records_for_csv:
    print(f"准备写入 {len(records_for_csv)} 条有效记录到 CSV 文件...")
    with open(output_csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["paperTitle", "paperLabel", "topicName"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records_for_csv)
    print(f"CSV 文件 '{output_csv_path}' 已成功创建。")
else:
    print("没有有效数据可写入 CSV 文件。")

if skipped_records_count > 0:
    print(f"处理过程中共跳过了 {skipped_records_count} 条记录（因信息不完整、类型未映射或主题名处理后为空）。")

print("CSV 文件准备完成！")