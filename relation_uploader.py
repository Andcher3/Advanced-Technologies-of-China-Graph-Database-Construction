authors = record.get("Author", [])
if isinstance(authors, str): authors = [authors]
for author_name in authors:
    if author_name: paper_author_rels.append({'start_id': paper_id, 'end_id': author_name.strip(), 'type': 'AUTHORED'})

tertiary_authors = record.get("Tertiary Author", [])
if isinstance(tertiary_authors, str): tertiary_authors = [tertiary_authors]
for author_name in tertiary_authors:
    if author_name: paper_tertiary_author_rels.append(
        {'start_id': paper_id, 'end_id': author_name.strip(), 'type': 'TERTIARY_AUTHORED'})


def write_relationship_csv(filename, rel_list, start_id_col, end_id_col, type_col_name="type:TYPE"):
    if not rel_list:
        print(f"关系列表为空，跳过写入 {filename}")
        return
    with open(os.path.join(output_dir, filename), 'w', newline='', encoding='utf-8') as f:
        # fieldnames = [':START_ID', ':END_ID', ':TYPE'] # 默认
        fieldnames = [start_id_col, end_id_col, type_col_name]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        # 写入修改后的表头，以符合 LOAD CSV 的要求
        header_map = {
            start_id_col: ':START_ID',
            end_id_col: ':END_ID',
            type_col_name: ':TYPE'
        }
        writer.writerow(header_map)

        # writer.writeheader() # 直接用原始列名写入数据
        for rel_data in tqdm(rel_list, desc=f"写入 {filename}"):
            # 构造符合 fieldnames 的行字典
            row_to_write = {
                start_id_col: rel_data['start_id'],
                end_id_col: rel_data['end_id'],
                type_col_name: rel_data['type']
            }
            writer.writerow(row_to_write)
    print(f"写入 {filename} 完成，共 {len(rel_list)} 条关系。")


write_relationship_csv("paper_authored_author.csv", paper_author_rels,
                       start_id_col=':START_ID(Author-ID)', end_id_col=':END_ID(Paper-ID)')  # 注意方向和ID组
# 修正：根据你的 NODE_LINK_CONFIG, (Author)-AUTHORED->(Paper)
# 所以 Start 是 Author, End 是 Paper

# 修正关系方向和ID组名
# (Author)-AUTHORED->(Paper)
write_relationship_csv("rels_author_authored_paper.csv", paper_author_rels,
                       start_id_col='author_name:START_ID(Author-ID)',  # 列名是 author_name，类型是 START_ID(Author-ID)
                       end_id_col='paper_title:END_ID(Paper-ID)',  # 列名是 paper_title，类型是 END_ID(Paper-ID)
                       type_col_name="relationship_type:TYPE")  # 列名是 relationship_type，类型是 TYPE
# 在写入时，rel_list 中的字典应该是 {'author_name': ..., 'paper_title': ..., 'relationship_type': 'AUTHORED'}

# 为了简化，我们让 rel_list 内部的 key 和 CSV 列名一致，除了特殊类型标记
# 重新准备 paper_author_rels 格式
rels_author_authored_paper_data = []
for rel in paper_author_rels:
    rels_author_authored_paper_data.append({
        'author_name': rel['end_id'],  # 因为原AUTHORED是 (Author)->(Paper)
        'paper_title': rel['start_id'],
        'relationship_type': 'AUTHORED'
    })
write_relationship_csv("rels_author_authored_paper.csv", rels_author_authored_paper_data,
                       'author_name:START_ID(Author-ID)', 'paper_title:END_ID(Paper-ID)', 'relationship_type:TYPE')

rels_author_tertiary_authored_paper_data = []
for rel in paper_tertiary_author_rels:
    rels_author_tertiary_authored_paper_data.append({
        'author_name': rel['end_id'],
        'paper_title': rel['start_id'],
        'relationship_type': 'TERTIARY_AUTHORED'
    })
write_relationship_csv("rels_author_tertiary_authored_paper.csv", rels_author_tertiary_authored_paper_data,
                       'author_name:START_ID(Author-ID)', 'paper_title:END_ID(Paper-ID)', 'relationship_type:TYPE')

# 文献与关键词 (Paper)-HAS_KEYWORD->(Keyword)
paper_keyword_rels = []
for record in tqdm(all_data, desc="收集文献-关键词关系"):
    paper_id = record.get("Title")
    if not paper_id: continue
    keywords = record.get("Keywords", [])
    if isinstance(keywords, str): keywords = [keywords]
    for keyword in keywords:
        if keyword:
            paper_keyword_rels.append({
                'paper_title': paper_id,
                'keyword_name': keyword.strip(),
                'relationship_type': 'HAS_KEYWORD'
            })
write_relationship_csv("rels_paper_haskeyword_keyword.csv", paper_keyword_rels,
                       'paper_title:START_ID(Paper-ID)', 'keyword_name:END_ID(Keyword-ID)', 'relationship_type:TYPE')

# TODO: 为 NODE_LINK_CONFIG 中的其他关系类型（PUBLISHED_BY, AUTHOR_ADDRESS）生成类似的CSV文件
# 例如：rels_paper_publishedby_organization.csv
#       rels_paper_authoraddress_authoraddress.csv (注意自己的命名一致性)

# --- 新增：近义词关系 ---
# 假设 refined_keyword_mapping 是从 recorrect_mapping.py 的 refine_mapping_with_deepseek 加载的
# refined_keyword_mapping = json.load(open("data/refined_keywords.json", 'r', encoding='utf-8'))
# refined_org_mapping = json.load(open("data/refined_organization.json", 'r', encoding='utf-8'))
# refined_addr_mapping = json.load(open("data/refined_address.json", 'r', encoding='utf-8'))

similar_keywords_rels = []
if 'refined_keyword_mapping' in locals() and refined_keyword_mapping:  # 检查变量是否存在且非空
    for original_word, representative_word in tqdm(refined_keyword_mapping.items(), desc="收集关键词相似关系"):
        if original_word != representative_word:  # 只为实际不同的词创建关系
            similar_keywords_rels.append({
                'original_keyword:START_ID(Keyword-ID)': original_word,  # 使用 Keyword-ID 组
                'representative_keyword:END_ID(Keyword-ID)': representative_word,
                'relationship_type:TYPE': 'ALIAS_OF'  # 或者 SIMILAR_TO
            })
    # 写入时，列名就是字典的key
    write_relationship_csv("rels_keyword_aliasof_keyword.csv", similar_keywords_rels,
                           'original_keyword:START_ID(Keyword-ID)',
                           'representative_keyword:END_ID(Keyword-ID)',
                           'relationship_type:TYPE')
else:
    print("警告：refined_keyword_mapping 未定义或为空，跳过关键词相似关系生成。")

# TODO: 为 Organization 和 AuthorAddress 也生成类似的 ALIAS_OF 关系CSV文件
# (rels_org_aliasof_org.csv, rels_addr_aliasof_addr.csv)

print("所有CSV文件已生成到目录:", output_dir)