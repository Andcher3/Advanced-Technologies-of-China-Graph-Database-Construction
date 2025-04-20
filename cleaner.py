import os
import re
from collections import defaultdict
from keyword_merger import keyword_merging
import json

def parse_entries(text: str) -> list:
    """
    将读取到的文本按照双换行符分割为每个参考文献条目，
    并利用正则表达式提取每行以 {字段} 开头的键值对。
    返回一个包含字典的列表，每个字典代表一篇论文的原始数据。
    """
    # 假设每个条目之间以空行（一个或多个换行）分隔
    blocks = re.split(r'\n\s*\n', text)
    records = []
    for block in blocks:
        if not block.strip():
            continue
        record = {}
        # 匹配形如： {Key}: Value 的格式
        matches = re.findall(r'\{([^}]+)\}:\s*(.*)', block)
        for field, value in matches:
            record[field.strip()] = value.strip()
        if record:
            records.append(record)
    return records


def delete_post_numbers(records: list) -> list:
    pattern = re.compile(r'(?:(?<=\D)|(?<=^))\s*\d{6}\s*(?=(?:\D)|$)')

    cleaned = []
    for s in records:
        # 第一步：移除数字及其左右空白，替换成单个空格
        temp = pattern.sub(' ', s)
        # 第二步：合并多余空格，去除首尾空格
        temp = re.sub(r'\s+', ' ', temp).strip()
        cleaned.append(temp)
    return cleaned


def format_data(record: dict) -> dict:
    """
    对单个论文条目的数据进行清洗。
      - 去除字段值两端多余的空格和末尾多余的分号；
      - 对作者、作者单位、关键词等字段按";"拆分成列表。
      - 对年份、卷号、期号等字段尝试转换为整数。
    返回清洗后的字典。
    """
    cleaned = {}

    for key, value in record.items():
        # 去除两端空格和末尾分号
        value = value.strip().strip(';')
        if key.lower() in ["author", "keywords", "tertiary author", "subsidiary author"]:
            # 按分号分隔，并剔除空内容
            cleaned[key] = [item.strip() for item in value.split(';') if item.strip()]
            # print(cleaned[key] if key == 'Keywords' else None)
        elif key.lower() == "author address":
            cleaned[key] = [item.strip() for item in value.split(';') if item.strip()]
            cleaned[key] = [item for part in cleaned[key] for item in part.split('.')]
            cleaned[key] = [item for part in cleaned[key] for item in part.split(',')]
            cleaned[key] = [item for part in cleaned[key] for item in part.split('/')]
            cleaned[key] = [item for part in cleaned[key] for item in part.split('·')]
            cleaned[key] = delete_post_numbers(cleaned[key])

        elif key.lower() in ["year", "volume", "issue"]:
            try:
                cleaned[key] = int(value)
            except ValueError:
                cleaned[key] = value  # 如果转换失败，保留原始字符串
        else:
            cleaned[key] = value
    return cleaned


def title_deduplication(cleaned_records, log=False):
    """
    去除具有重复标题的数据，只留下第一个
    """
    deduped_records = []
    seen_titles = set()
    for record in cleaned_records:
        title = record.get("Title", "")
        if title not in seen_titles:
            seen_titles.add(title)
            deduped_records.append(record)
        else:
            # print(title)
            pass
    if (log):
        print(f"去重前记录数：{len(cleaned_records)},去重后记录数：{len(deduped_records)}")

    return deduped_records


def data_cleaning(records: list) -> list:
    """
    针对构建“中国先进知识”知识图库时所需的进一步数据清洗操作，
    对各记录进行标准化调整：
      - 去除多余空白（将多个空格替换为一个空格）
      - 去重（去除具有同样标题的）
    返回进一步清洗后的记录列表。
    """
    cleaned_records = []
    for rec in records:
        new_rec = {}
        for k, v in rec.items():
            if isinstance(v, str):
                # 清理字符串值中的多余空格
                v = re.sub(r"\s+", " ", v).strip()
            elif isinstance(v, list):
                # 清理列表值中每个字符串元素的多余空格
                # 确保 item 是字符串再处理
                v = [re.sub(r"\s+", " ", item).strip() if isinstance(item, str) else item for item in v]
            new_rec[k] = v  # 将清理后的值（字符串或列表）赋给新记录
        cleaned_records.append(new_rec)

    # 去重：以 Title 属性为依据（仅保留第一次出现的记录）
    deduped_records = title_deduplication(cleaned_records)

    return deduped_records


def rename_files_by_samples(data_dir: str):
    """
    将指定目录下的所有符合形如aaa(1).txt、aaa(2).txt等格式的文件重命名为
    aaa0-x.txt、aaax+1-y.txt等格式，其中x和y代表该文件中样本的起始和结束索引。
    （用于整理数据，方便看到哪个文件里有多少条数据）
    """
    # 匹配形如 prefix(number).txt 的文件名
    file_pattern = re.compile(r'^(.+?) \((\d+)\)\.txt$')

    # 按前缀分组并记录序号和原文件名
    file_groups = defaultdict(list)
    for filename in os.listdir(data_dir):
        match = file_pattern.match(filename)
        if match:
            prefix = match.group(1)
            num = int(match.group(2))
            file_groups[prefix].append((num, filename))

    # 对每个前缀组内的文件按序号排序
    for prefix in file_groups:
        file_groups[prefix].sort(key=lambda x: x[0])

    # 处理每个组，生成新文件名并重命名
    for prefix in file_groups:
        current_start = 0  # 当前样本起始索引
        for num, filename in file_groups[prefix]:
            file_path = os.path.join(data_dir, filename)
            # 读取文件内容并解析样本数
            with open(file_path, 'r', encoding='utf-8') as file:
                text_content = file.read()
            raw_records = parse_entries(text_content)
            sample_count = len(raw_records)
            if sample_count == 0:
                print(f"跳过无样本文件: {filename}")
                continue
            # 计算结束索引并生成新文件名
            current_end = current_start + sample_count - 1
            new_filename = f"{prefix}{current_start}-{current_end}.txt"
            new_path = os.path.join(data_dir, new_filename)
            # 执行重命名
            os.rename(file_path, new_path)
            print(f"重命名文件: {filename} -> {new_filename}")
            # 更新起始索引
            current_start += sample_count


def cleaner(data_dir, log=False):
    """
    主要函数，从整个文件夹下的所有文件提取并整理数据，在其他代码里调用这个就行
    """

    area_data = []
    for data in os.listdir(data_dir):
        # 读取存有参考文献数据的文本文件（请确保文件编码正确，如 UTF-8）
        with open(os.path.join(data_dir, data), "r", encoding="utf-8") as file:
            text_content = file.read()

        # 1. 从文本中提取出各篇论文的原始数据记录
        raw_records = parse_entries(text_content)
        # print(f"{data}: {len(raw_records)} data has been found!")

        # 2. 针对每个记录执行初步数据清洗(格式化)
        cleaned_records = [format_data(record) for record in raw_records]

        area_data += cleaned_records

    # 3. 进一步执行数据清洗，标准化数据格式，准备构建知识图库
    fully_cleaned = data_cleaning(area_data)
    if log:
        print(f"{len(fully_cleaned)} data has been accepted in total!", end="\r")
    return fully_cleaned


def cleaner_all(main_dir='data/src_data'):
    """
    其实有一个bug是这个root_dir在第一次循环就已经覆盖掉了，实际上目录已经在第一个os.listdir硬编码进去了
    刚刚review发现的，改不改都行qwq ---HaMmer4.19

    Ohh shit I'll fix that ;) ---Andxher4.19.2
    """
    all_data = []
    for root_dir in os.listdir(main_dir):
        paper_dir = os.path.join(main_dir, root_dir, "论文")
        patent_dir = os.path.join(main_dir, root_dir, "专利")
        # data_dir = "data/src_data/Medicine/论文"
        cleaned_paper = cleaner(paper_dir)
        cleaned_patent = cleaner(patent_dir)
        all_data += cleaned_paper
        all_data += cleaned_patent

    print(f"{len(all_data)} data has been accepted in total!")

    return all_data


if __name__ == "__main__":
    data = cleaner_all()
    # with open("cleaned_data.json", "w", encoding="utf-8") as f:
    #     json.dump(data, f, ensure_ascii=False, indent=4)
    for sample in data:
        if sample["Reference Type"] == "Book":
            print(sample)
    # with open("address.json", "w", encoding="utf-8") as f:
    #     json.dump(list(sample["Author Address"] if "Author Address" in sample.keys() else None for sample in data), f, ensure_ascii=False, indent=4)
    # ========================= 检查各个类型的文献的属性==========================
    # paper_type = []
    # for data in all_data:
    #     if data['Reference Type'] not in paper_type:
    #         print(data.keys())
    #         paper_type.append(data['Reference Type'])
    # print(paper_type)

    # ========================= 检查Other Article类型的文献的属性=================
    # for data in all_data:
    #     if 'Tertiary Author' in data.keys():
    #         print("Author:", data['Author'])
    #         print('Tertiary Author:', data['Tertiary Author'])

