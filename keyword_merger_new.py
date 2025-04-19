# --- START OF FILE keyword_merger_optimized.py ---

from sentence_transformers import SentenceTransformer
import numpy as np
import json
import os
from tqdm import tqdm
import faiss # For ANN
import networkx as nx # For graph components
import gc # Garbage collector

# Assume cleaner_all can be modified or wrapped to yield records
# Example wrapper if cleaner_all returns a list:
def stream_records(root_dir='data/src_data/', batch_size=1000):
    """
    Generator function to yield records in batches or one by one
    Modify this based on how cleaner_all actually works or reads data.
    This example assumes cleaner_all loads everything, so we just iterate.
    Ideally, cleaner_all itself would stream from source files.
    """
    # If cleaner_all MUST load all records first:
    print("Warning: cleaner_all loads all data. Streaming applied *after* initial load.")
    from cleaner import cleaner_all # Assuming cleaner.py is available
    all_records = cleaner_all(root_dir=root_dir)
    print(f"Loaded {len(all_records)} records initially.")
    yield from all_records # Yield one by one

    # --- Ideal Scenario (if cleaner_all could be modified) ---
    # file_paths = [...] # Get list of source files
    # for file_path in file_paths:
    #     with open(file_path, 'r') as f:
    #         # Process file line by line or chunk by chunk
    #         for record in parse_records_from_file(f): # Hypothetical parser
    #              yield cleaner(record) # Clean record individually
    # ---------------------------------------------------------


# Initialize the model globally or pass it if needed
try:
    model = SentenceTransformer("shibing624/text2vec-base-chinese", cache_folder=".cache")
except Exception as e:
    print(f"Error loading SentenceTransformer model: {e}")
    print("Please ensure the model is available or network connection is working.")
    model = None # Indicate model loading failure

def get_unique_values(record_stream, key_names):
    """Extracts unique string values from specified keys in a stream of records."""
    all_values = set()
    print("Extracting unique values...")
    for record in tqdm(record_stream, desc="Scanning records for values"):
        for key_name in key_names:
            value = record.get(key_name)
            if isinstance(value, str) and value:
                all_values.add(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item:
                        all_values.add(item)
    return list(all_values)

def build_faiss_index(values_list, batch_size=256):
    """Computes embeddings in batches and builds a FAISS index."""
    if not model:
        raise ValueError("SentenceTransformer model not loaded.")
    if not values_list:
        return None, {}

    print(f"Building FAISS index for {len(values_list)} unique values...")
    # Get embedding dimension
    try:
        dummy_embedding = model.encode(["test"])
        dimension = dummy_embedding.shape[1]
    except Exception as e:
        print(f"Error getting embedding dimension: {e}")
        # Fallback dimension or raise error - using common 768
        dimension = 768
        print(f"Warning: Could not detect embedding dimension, assuming {dimension}.")


    # Using IndexFlatIP for cosine similarity after normalization
    # Normalize vectors to unit length for IndexFlatIP to work with cosine similarity
    index = faiss.IndexFlatIP(dimension)
    value_map = {i: value for i, value in enumerate(values_list)} # map faiss index id to value

    num_batches = (len(values_list) + batch_size - 1) // batch_size

    all_embeddings_list = [] # Temporarily store normalized embeddings

    for i in tqdm(range(num_batches), desc="Computing embeddings and indexing"):
        batch_values = values_list[i * batch_size:(i + 1) * batch_size]
        if not batch_values: continue

        try:
             embeddings = model.encode(batch_values, show_progress_bar=False, batch_size=batch_size) # Internal batching
        except Exception as e:
            print(f"\nError encoding batch {i+1}/{num_batches}: {e}")
            print(f"Problematic values might be: {batch_values[:5]}...") # Show first few
            continue # Skip problematic batch? Or handle more gracefully

        # Normalize embeddings for cosine similarity using IndexFlatIP
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        normalized_embeddings = embeddings / norms
        # Handle potential zero vectors after normalization (if norm was 0)
        normalized_embeddings = np.nan_to_num(normalized_embeddings)

        index.add(normalized_embeddings.astype('float32'))
        # Instead of adding to index immediately, store temporarily if index creation itself is slow
        # all_embeddings_list.append(normalized_embeddings.astype('float32'))

        # Optional: Clear memory if embeddings are large
        del embeddings, norms, normalized_embeddings
        gc.collect()

    # If embeddings were stored temporarily:
    # if all_embeddings_list:
    #     print("Adding all embeddings to FAISS index...")
    #     all_embeddings_np = np.vstack(all_embeddings_list)
    #     index.add(all_embeddings_np)
    #     del all_embeddings_list, all_embeddings_np
    #     gc.collect()
    #     print("FAISS index built.")

    print(f"FAISS index built successfully. Total vectors: {index.ntotal}")
    return index, value_map


def find_similar_pairs(index, num_values, similarity_threshold, search_batch_size=1024):
    """Uses FAISS range search to find pairs exceeding the similarity threshold."""
    if not index:
        return []

    print("Finding similar pairs using FAISS range search...")
    graph = nx.Graph()
    graph.add_nodes_from(range(num_values)) # Add nodes representing original index

    # FAISS range_search needs query vectors. We search the index against itself.
    # We need to retrieve the vectors stored in the index if we didn't keep them.
    # IndexFlatIP stores vectors, we can reconstruct them (or query using IDs).
    # Let's query batch by batch to avoid loading all vectors if index is large

    vectors_to_query = []
    # Efficiently get all vectors if index allows (IndexFlatIP does via reconstruct)
    # Reconstructing might be memory intensive if index is huge.
    # Alternative: Query using vectors computed during indexing if stored temporarily.
    # Safest (memory-wise) if slow: Re-compute or fetch in batches.

    print("Querying index batch by batch...")
    # Check if index supports reconstruction
    if hasattr(index, 'reconstruct_n'):
        print("Reconstructing vectors from index for querying (can use memory)...")
        all_vectors = index.reconstruct_n(0, index.ntotal)
    else:
        # Fallback: Need to recompute or have stored the vectors elsewhere.
        # This part depends heavily on FAISS index type and memory constraints.
        # Assuming reconstruction is feasible for IndexFlatIP:
        print("Warning: Index type might not support efficient reconstruction. Querying may be slow or fail.")
        # If reconstruction fails or is too memory-heavy, this approach needs rethinking
        # (e.g., storing embeddings temporarily on disk or using different index type)
        # For now, assume reconstruction works.
        try:
             all_vectors = index.reconstruct_n(0, index.ntotal)
        except Exception as e:
             print(f"FATAL: Could not get vectors for querying. Error: {e}")
             print("Optimization failed. Consider reducing data or using more memory.")
             return []


    edges = []
    for i in tqdm(range(0, num_values, search_batch_size), desc="Range searching"):
        batch_indices = list(range(i, min(i + search_batch_size, num_values)))
        if not batch_indices: continue

        query_vectors = all_vectors[batch_indices]

        # Perform range search: find neighbors with distance < threshold
        # For IndexFlatIP (cosine sim), distance = 1 - sim. We want sim > T, so dist < 1 - T
        # However, FAISS IP returns dot product. Since vectors are normalized, dot product = cosine sim.
        # So we search for neighbors with score > similarity_threshold.
        # range_search returns distances/scores, indices, and limits per query
        lims, D, I = index.range_search(query_vectors, thresh=similarity_threshold)

        # Process results: lims[k] points to the start of results for query k in D and I
        for k in range(len(batch_indices)):
            query_idx = batch_indices[k] # The actual index in the original list
            start = lims[k]
            end = lims[k+1]
            for j in range(start, end):
                neighbor_idx = I[j]
                # score = D[j] # The similarity score
                # Avoid self-loops and duplicate edges (graph takes care of duplicates)
                if query_idx != neighbor_idx:
                    edges.append((query_idx, neighbor_idx))

        # Optional memory cleanup per batch
        del query_vectors, lims, D, I
        gc.collect()

    print(f"Found {len(edges)} potential similarity edges (before graph processing).")
    del all_vectors # Free memory from reconstructed vectors
    gc.collect()
    return edges


def create_mapping_from_graph(edges, value_map):
    """Builds clusters from graph edges and creates the representative mapping."""
    print("Building graph and finding connected components...")
    graph = nx.Graph()
    graph.add_nodes_from(value_map.keys())
    graph.add_edges_from(edges)

    mapping = {}
    merged_count = 0
    num_clusters = 0
    print("Generating representative mapping from clusters...")
    # Find connected components (each component is a cluster)
    for component in tqdm(nx.connected_components(graph), desc="Processing clusters"):
        num_clusters += 1
        # Component contains original indices (0 to N-1)
        if not component: continue

        # Get the actual string values for this component
        group_values = [value_map[idx] for idx in component]
        if not group_values: continue

        # Choose representative (e.g., alphabetically first)
        rep = min(group_values)

        is_merged_group = len(group_values) > 1
        if is_merged_group:
            merged_count += (len(group_values) - 1)
            # print(f"Merging group: {group_values} -> '{rep}'") # Optional debug

        # Create mapping for all values in the group
        for val_idx in component:
             original_value = value_map[val_idx]
             mapping[original_value] = rep

    print(f"Mapping generated. Found {num_clusters} clusters.")
    print(f"Total items merged into representatives: {merged_count}")
    return mapping


def keyword_merging_optimized(
    record_source, # Can be a generator or function returning an iterator
    key_names: list,
    similarity_threshold: float = 0.9,
    mapping_file_path: str = None,
    force_recompute: bool = False,
    batch_size_embed: int = 128, # Batch size for sentence transformer
    batch_size_search: int = 1024 # Batch size for FAISS search
) -> list: # Modified: Returns list for now, but ideally would write to file/yield
    """
    Optimized keyword merging using FAISS and graph components for lower memory.

    Args:
        record_source: A function/generator yielding records (e.g., stream_records('data/src_data/')).
        key_names: List of keys to merge values from.
        similarity_threshold: Cosine similarity threshold for merging.
        mapping_file_path: Path to load/save the computed mapping (JSON).
        force_recompute: Ignore existing mapping file if True.
        batch_size_embed: Batch size for computing embeddings.
        batch_size_search: Batch size for querying the FAISS index.

    Returns:
        List of updated records. (Caution: This still collects all results in memory)
        Consider modifying to write updated records to a file instead.
    """
    if not model:
        print("Error: SentenceTransformer model failed to load. Aborting.")
        # Depending on use case, you might want to return empty list or raise error
        return [] # Or raise RuntimeError("Model not available")

    if not key_names:
        print("Warning: No key_names provided for merging.")
        # Return original data stream/list if possible, or empty
        # This depends on how record_source works. Assuming it needs to be consumed:
        return list(record_source()) # Consume the generator if needed

    mapping = None

    # 1. Load or Compute Mapping
    if mapping_file_path and not force_recompute and os.path.exists(mapping_file_path):
        try:
            with open(mapping_file_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            print(f"Successfully loaded mapping from {mapping_file_path}.")
        except (json.JSONDecodeError, IOError, TypeError) as e: # Added TypeError for robustness
            print(f"Error loading mapping file {mapping_file_path}: {e}. Recomputing.")
            mapping = None

    if mapping is None:
        print(f"Computing new mapping for keys: {key_names}")
        # Use a separate call to the generator for unique values
        all_values_list = get_unique_values(record_source(), key_names) # Consumes the generator once

        if not all_values_list:
            print("No values found to merge.")
            mapping = {}
        else:
            print(f"Found {len(all_values_list)} unique values.")
            try:
                # Build FAISS index
                index, value_map = build_faiss_index(all_values_list, batch_size=batch_size_embed)

                if index:
                     # Find similar pairs using FAISS
                     # Make sure threshold is valid
                     if not (0 < similarity_threshold < 1):
                         print(f"Warning: similarity_threshold ({similarity_threshold}) should be between 0 and 1. Clamping.")
                         similarity_threshold = max(0.01, min(0.99, similarity_threshold))

                     edges = find_similar_pairs(index, index.ntotal, similarity_threshold, search_batch_size=batch_size_search)

                     # Create mapping from graph components
                     mapping = create_mapping_from_graph(edges, value_map)

                     # Clean up FAISS index explicitly
                     del index
                     gc.collect()
                else:
                     print("FAISS index creation failed or returned empty. Creating empty mapping.")
                     mapping = {}


            except ImportError:
                print("Error: FAISS or NetworkX library not found. Please install them.")
                print("pip install faiss-cpu networkx")
                return list(record_source()) # Return original data
            except Exception as e:
                print(f"An error occurred during mapping computation: {e}")
                import traceback
                traceback.print_exc() # Print detailed traceback
                print("Aborting mapping computation.")
                # Decide whether to proceed with empty mapping or stop
                return list(record_source()) # Stop and return original

        # Save computed mapping
        if mapping_file_path and mapping is not None: # Ensure mapping is not None
            print(f"Saving computed mapping to {mapping_file_path}...")
            try:
                os.makedirs(os.path.dirname(mapping_file_path), exist_ok=True)
                with open(mapping_file_path, 'w', encoding='utf-8') as f:
                    json.dump(mapping, f, ensure_ascii=False, indent=4)
                print("Mapping saved successfully.")
            except (IOError, TypeError) as e: # Added TypeError
                print(f"Error saving mapping file {mapping_file_path}: {e}")

    # 3. Apply Mapping
    print(f"Applying mapping to records...")
    updated_records = []
    # Use a NEW call to the record source generator to process records again
    record_iterator = record_source()

    # Check if mapping is empty (e.g., no values found or error during computation)
    if not mapping:
        print("Mapping is empty. Applying trivial mapping (value -> value).")
        # If mapping is empty, just return the original records
        # Be careful if record_source is a one-time generator
        # You might need a way to "rewind" or recreate the iterator
        # Assuming record_source() creates a new iterator each time:
        print("Returning original records as mapping is empty.")
        return list(record_iterator)


    for record in tqdm(record_iterator, desc="Applying mapping"):
        for key_name in key_names:
            if key_name in record:
                original_value = record[key_name]
                if isinstance(original_value, str):
                    record[key_name] = mapping.get(original_value, original_value)
                elif isinstance(original_value, list):
                    new_list = [mapping.get(item, item) for item in original_value if isinstance(item, str)]
                    record[key_name] = list(dict.fromkeys(new_list)) # Deduplicate preserving order

        updated_records.append(record) # Collect updated records

    print("Finished applying mapping.")

    # **** MEMORY WARNING ****
    # This return statement still collects all updated records in memory.
    # If the output dataset is also too large, modify this function to
    # write updated_records to a file line-by-line or yield them.
    # Example:
    # with open("output_file.jsonl", "w", encoding="utf-8") as outfile:
    #     for record in tqdm(record_iterator, desc="Applying mapping and writing"):
    #         # ... (apply mapping logic) ...
    #         outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
    # return None # Indicate completion, data is in file
    # ************************

    return updated_records


if __name__ == '__main__':
    print("Starting optimized keyword merging process...")

    # Ensure the model can be loaded before proceeding
    if model is None:
        print("Exiting due to model loading failure.")
        exit(1)

    # Define how to get the stream of records
    # Replace this with the actual way you get your data stream
    def my_record_stream():
        # Example: Use the wrapper around cleaner_all
        yield from stream_records(root_dir='data/src_data/')
        # Or if cleaner_all itself can yield:
        # from cleaner import cleaner_all_stream # hypothetical streaming version
        # yield from cleaner_all_stream(root_dir='data/src_data/')

    output_save_path = "data/merged_keywords_optimized.json" # Save results here if needed
    mapping_save_path = "data/keywords_mapping.json" # Save mapping here

    try:
        # Run the optimized merging
        fully_cleaned_records = keyword_merging_optimized(
            record_source=my_record_stream, # Pass the generator function
            key_names=["Keywords"],          # Keys to merge
            similarity_threshold=0.95,       # Similarity threshold
            mapping_file_path=mapping_save_path, # Path for mapping cache
            force_recompute=False,          # Set to True to ignore cache
            batch_size_embed=64,             # Smaller batch for embedding if GPU memory is low
            batch_size_search=512            # Batch size for FAISS search
        )

        print(f"Processing complete. {len(fully_cleaned_records)} records processed.")

        # Optional: Save the final result (still loads all into memory first)
        # Consider modifying the main function to write directly to file for large results
        if fully_cleaned_records:
             print(f"Saving final results to {output_save_path}...")
             try:
                 # Create directory if it doesn't exist
                 os.makedirs(os.path.dirname(output_save_path), exist_ok=True)
                 with open(output_save_path, 'w', encoding='utf-8') as f:
                     # Save as JSON array (one object per line might be better for huge files - jsonl)
                     json.dump(fully_cleaned_records, f, ensure_ascii=False, indent=2)
                 print("Final results saved.")
             except (IOError, TypeError) as e:
                 print(f"Error saving final results: {e}")
        else:
             print("No records were processed or returned.")


    except Exception as e:
        print(f"An unexpected error occurred in the main block: {e}")
        import traceback
        traceback.print_exc()

# --- END OF FILE keyword_merger_optimized.py ---
