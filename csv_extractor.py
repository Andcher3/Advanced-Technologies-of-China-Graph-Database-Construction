# --- START OF FILE csv_generator.py ---
import csv
import os
from collections import defaultdict
import json
from typing import List, Dict, Any, Set, Tuple

# 导入必要的配置和辅助函数 (假设它们在 Hype.py 和 utils.py 中)
from Hype import NODE_LINK_CONFIG  # 假设 NODE_LINK_CONFIG 在 Hype.py 中定义

from utils import _sanitize_label, _format_list_property  # 仅用于示例，实际CSV生成通常不需要转义


# --- 生成节点 CSVs 的函数 ---

def generate_node_csvs(records: List[Dict[str, Any]], output_dir: str,
                       link_config: List[Dict[str, Any]] = NODE_LINK_CONFIG):
    """
    Generates CSV files for all node types based on records and link_config.

    Args:
        records: List of cleaned record dictionaries (before keyword replacement).
        output_dir: Directory to save the CSV files.
        link_config: Configuration list defining linked nodes.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Data structures to collect unique nodes
    document_nodes: Dict[str, Dict[str, Any]] = {}  # {title: {properties}}
    linked_nodes: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)  # {node_label: {id_value: {properties}}}

    # 1. Collect Document Nodes (Paper/Patent)
    # These are unique by title
    for record in records:
        title = record.get("Title")
        if not title:
            continue

        # Sanitize label based on Reference Type
        original_ref_type = record.get("Reference Type", "UnknownDocument")
        node_label = _sanitize_label(original_ref_type)

        # Select key properties for the document node CSV
        # Add more properties here as needed, ensure they exist in your records
        props = {
            ':ID': title,  # Use title as internal ID for CSV linking
            ':LABEL': node_label,
            'title': title,
            'year': record.get("Year"),
            'abstract': record.get("Abstract"),
            'journal': record.get("Journal"),
            'volume': record.get("Volume"),
            'issue': record.get("Issue"),
            'pages': record.get("Pages"),
            'doi': record.get("DOI"),
            'url': record.get("URL"),
            'isbn_issn': record.get("ISBN/ISSN"),  # Standardize key name
            # Add other direct properties here if needed
        }
        document_nodes[title] = props

    print(f"Collected {len(document_nodes)} unique document nodes.")

    # 2. Collect Linked Nodes (Author, Keyword, Organization, Author_Address etc.)
    # These are unique by their ID property (name) and label
    for record in records:
        for cfg in link_config:
            record_keys = cfg['record_keys']
            if not isinstance(record_keys, list):
                record_keys = [record_keys]

            node_label = cfg['node_label']
            node_id_prop = cfg['node_id_prop']  # e.g., 'name'

            # Extract values from specified keys
            values = []
            for r_key in record_keys:
                raw_value = record.get(r_key)
                if isinstance(raw_value, str) and raw_value:
                    values.append(raw_value)
                elif isinstance(raw_value, list):
                    values.extend([item for item in raw_value if isinstance(item, str) and item])

            # Process unique values for this config and record
            for value in set(values):  # Use set to get unique values from the list/string
                # Use the value itself as the node ID and name property
                node_id = value

                # Add to collection, properties might just be ID and name for simplicity
                # We store {id_value: {properties}} under the node_label
                if node_id not in linked_nodes[node_label]:
                    linked_nodes[node_label][node_id] = {
                        ':ID': node_id,  # Use value as internal ID for CSV linking
                        ':LABEL': node_label,
                        node_id_prop: value  # e.g., 'name': value
                    }

    for label, nodes in linked_nodes.items():
        print(f"Collected {len(nodes)} unique '{label}' nodes.")

    # 3. Write Document Nodes CSV
    doc_csv_path = os.path.join(output_dir, "documents.csv")
    # Determine header dynamically based on collected properties
    if document_nodes:
        header = list(document_nodes[list(document_nodes.keys())[0]].keys())  # Get keys from first node
        # Ensure standard columns like :ID and :LABEL are first (optional but good practice)
        standard_header = [':ID', ':LABEL']
        for col in standard_header:
            if col in header:
                header.remove(col)
        header = standard_header + header

        with open(doc_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for node_props in document_nodes.values():
                # Need to ensure all rows have keys from the header, fill missing with None
                row = {key: node_props.get(key, None) for key in header}
                # Format list properties if any (currently none explicitly added, but flexible)
                # for key, val in row.items():
                #     if isinstance(val, list):
                #         row[key] = _format_list_property(val)
                writer.writerow(row)
        print(f"Generated document nodes CSV: {doc_csv_path}")
    else:
        print("No document nodes to write.")

    # 4. Write Linked Nodes CSVs
    for label, nodes in linked_nodes.items():
        if not nodes:
            print(f"No '{label}' nodes to write.")
            continue

        node_csv_path = os.path.join(output_dir, f"{label.lower()}_nodes.csv")
        # Determine header dynamically
        header = list(list(nodes.values())[0].keys())
        standard_header = [':ID', ':LABEL']
        for col in standard_header:
            if col in header: header.remove(col)
        header = standard_header + header

        with open(node_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for node_props in nodes.values():
                row = {key: node_props.get(key, None) for key in header}
                writer.writerow(row)
        print(f"Generated '{label}' nodes CSV: {node_csv_path}")


# --- 生成关系 CSVs 的函数 ---

def generate_document_linked_relationship_csvs(records: List[Dict[str, Any]], output_dir: str,
                                               link_config: List[Dict[str, Any]] = NODE_LINK_CONFIG):
    """
    Generates CSV files for relationships between documents and linked nodes,
    based ONLY on records and link_config (excluding alias relationships).

    Args:
        records: List of cleaned record dictionaries (with original field values).
        output_dir: Directory to save the CSV files.
        link_config: Configuration list defining relationships.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Data structures to collect unique relationships by type
    # Structure: {rel_type: set((start_node_id, end_node_id))}
    document_linked_rels: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)

    # 1. Collect Document-to-Linked-Node Relationships from records
    for record in records:
        title = record.get("Title")
        if not title: continue

        doc_id = title  # Document node ID is its title

        for cfg in link_config:
            record_keys = cfg['record_keys']
            # For relationships, we link the document to each individual value found
            # This assumes records contain original, non-merged values

            rel_type = cfg['rel_type']
            rel_direction = cfg['rel_direction']
            # node_id_prop = cfg['node_id_prop'] # ID prop of the linked node (usually 'name') - not directly used here, but the value itself is the ID

            # Extract values from specified keys
            values = []
            for r_key in record_keys:
                raw_value = record.get(r_key)
                if isinstance(raw_value, str) and raw_value:
                    values.append(raw_value)
                elif isinstance(raw_value, list):
                    values.extend([item for item in raw_value if isinstance(item, str) and item])

            # For each extracted value, create a relationship instance
            for value in set(values):  # Use set to handle duplicates within a record's list for relationship creation
                linked_node_id = value  # Linked node ID is its value (name)

                # Determine start and end IDs based on direction
                if rel_direction == 'from_new':  # (LinkedNode)-[:REL]->(Document)
                    start_id = linked_node_id
                    end_id = doc_id
                else:  # 'to_new' (Document)-[:REL]->(LinkedNode)
                    start_id = doc_id
                    end_id = linked_node_id

                document_linked_rels[rel_type].add((start_id, end_id))

    for rel_type, rels in document_linked_rels.items():
        print(f"Collected {len(rels)} unique ':{rel_type}' relationships from documents.")

    # 2. Write Relationship CSVs
    # Header specifies the label of start/end nodes for clarity and safety in LOAD CSV
    # We need to figure out the labels for start and end based on rel_type and config
    rel_headers_map: Dict[str, Tuple[str, str]] = {}  # {rel_type: (start_label, end_label)}
    for cfg in link_config:
        rel_type = cfg['rel_type']
        doc_label = 'Document'  # Or specific Paper/Patent, but Document is safer for general rels
        linked_label = cfg['node_label']
        if cfg['rel_direction'] == 'from_new':
            rel_headers_map[rel_type] = (linked_label, doc_label)
        else:  # 'to_new'
            rel_headers_map[rel_type] = (doc_label, linked_label)

    for rel_type, rels in document_linked_rels.items():
        if not rels:
            print(f"No ':{rel_type}' relationships to write.")
            continue

        rel_csv_path = os.path.join(output_dir, f"{rel_type.lower()}_rels.csv")
        # Dynamically determine header based on relationship type and assumed labels
        start_label, end_label = rel_headers_map.get(rel_type, ('UnknownStart', 'UnknownEnd'))
        # Using :START_ID(:Label) format in header is recommended for LOAD CSV
        header = [f':START_ID({start_label})', f':END_ID({end_label})', ':TYPE']

        with open(rel_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for start_id, end_id in rels:
                writer.writerow([start_id, end_id, rel_type])
        print(f"Generated ':{rel_type}' relationships CSV: {rel_csv_path}")


# --- 生成近同义词/别名关系 CSVs 的函数 ---

def generate_alias_relationship_csv(refined_mapping_path: str, output_dir: str,
                                    relationship_type: str, node_label: str):
    """
    Generates a CSV file for alias relationships from a single refined mapping file.

    Args:
        refined_mapping_path: Path to the refined mapping JSON file (e.g., for Keywords).
        output_dir: Directory to save the CSV files.
        relationship_type: The type of relationship for aliases (e.g., 'ALIAS_OF').
        node_label: The label of the nodes involved in the alias relationship (e.g., 'Keyword').
    """
    os.makedirs(output_dir, exist_ok=True)

    alias_rels: Set[Tuple[str, str]] = set()  # set((original_word, representative_word))

    if os.path.exists(refined_mapping_path):
        try:
            with open(refined_mapping_path, 'r', encoding='utf-8') as f:
                refined_mapping = json.load(f)
            print(f"Loaded {len(refined_mapping)} refined mapping entries from {refined_mapping_path}.")

            # Iterate through the mapping to find aliases
            # An alias exists where original_word != representative_word
            for original_word, representative_word in refined_mapping.items():
                if original_word != representative_word:
                    # Define direction: (original_word)-[:ALIAS_OF]->(representative_word)
                    # Assuming original_word maps to a representative_word
                    alias_rels.add((original_word, representative_word))

            print(f"Collected {len(alias_rels)} unique ':{relationship_type}' relationships for '{node_label}'.")

        except Exception as e:
            print(f"Error loading or processing refined mapping file {refined_mapping_path}: {e}")
            print(f"Skipping ':{relationship_type}' relationship generation for '{node_label}'.")
            alias_rels = set()  # Ensure no alias rels are generated if there's an error

    # Write Alias Relationships CSV (if any)
    if alias_rels:
        alias_csv_path = os.path.join(output_dir, f"{node_label.lower()}_{relationship_type.lower()}_rels.csv")
        # Header specifies the label of start/end nodes
        header = [f':START_ID({node_label})', f':END_ID({node_label})', ':TYPE']

        with open(alias_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for start_id, end_id in alias_rels:
                writer.writerow([start_id, end_id, relationship_type])
        print(f"Generated ':{relationship_type}' relationships CSV for '{node_label}': {alias_csv_path}")
    else:
        print(f"No ':{relationship_type}' relationships to write for '{node_label}'.")


# --- 示例用法 ---
if __name__ == '__main__':
    # This is just a demonstration. You would call these functions

    from cleaner import cleaner_all
    from Hype import MERGED_SAVED_PATH
    from keyword_merger import keyword_merging

    all_data = cleaner_all()

    output_path = "data/neo4j_csv_import"
    generate_node_csvs(all_data, output_path, NODE_LINK_CONFIG)
    generate_document_linked_relationship_csvs(all_data, output_path, NODE_LINK_CONFIG)
    generate_alias_relationship_csv(MERGED_SAVED_PATH['Keywords'], output_path, 'ALIAS_OF', 'Keyword')
    generate_alias_relationship_csv(MERGED_SAVED_PATH['Author Address'], output_path, 'ALIAS_OF', 'Author_Address')
    generate_alias_relationship_csv(MERGED_SAVED_PATH['Publisher'], output_path, 'ALIAS_OF', 'Organization')

# --- END OF FILE csv_generator.py ---
