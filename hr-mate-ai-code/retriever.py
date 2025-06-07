import json
from sentence_transformers import SentenceTransformer
import torch
import os
import chromadb
from chromadb.utils import embedding_functions

# --- Constants ---
DEFAULT_EMPLOYEE_DATA_PATH = 'generated_employees.json'
DEFAULT_MODEL_NAME = 'BAAI/bge-large-en-v1.5'
DEFAULT_CHROMA_DB_PATH = './chroma_db'
DEFAULT_COLLECTION_NAME = 'employee_profiles'

# --- Helper Functions ---
def load_employee_data(file_path):
    """Loads employee data from a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Successfully loaded {len(data)} employee records from {file_path}")
        return data
    except FileNotFoundError:
        print(f"Error: Employee data file not found at {file_path}")
        return []
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}")
        return []

def preprocess_employee_text_for_corpus(employees):
    """Combines 'Role Name' and 'Role Description' for each employee for corpus embedding."""
    employee_texts = []
    for emp in employees:
        role_name = emp.get('Role Name', '')
        role_description = emp.get('Role Description', '')
        combined_text = f"{role_name}. {role_description}"
        employee_texts.append(combined_text)
    return employee_texts

def _prepare_metadata_for_chroma(employee_record):
    """Converts list/dict fields in an employee record to JSON strings for ChromaDB compatibility."""
    processed_metadata = {}
    for key, value in employee_record.items():
        if isinstance(value, (list, dict)):
            processed_metadata[key] = json.dumps(value)
        elif value is None:
            processed_metadata[key] = '' # Handle None as empty string or based on schema
        elif not isinstance(value, (str, int, float, bool)):
            processed_metadata[key] = str(value) # Fallback for unexpected types
        else:
            processed_metadata[key] = value
    return processed_metadata

def populate_chroma_collection_if_needed(collection, employees_data_list, force_repopulate=False):
    """Populates the ChromaDB collection if it's empty, data count differs, or force_repopulate is True."""
    current_count = collection.count()
    target_count = len(employees_data_list)

    if not force_repopulate and current_count == target_count and current_count > 0:
        print(f"ChromaDB collection '{collection.name}' is already populated with {current_count} items and matches source count. No repopulation needed.")
        return

    if force_repopulate:
        print(f"Force repopulate is True. Clearing and repopulating collection '{collection.name}'.")
    elif current_count != target_count:
        print(f"ChromaDB collection '{collection.name}' has {current_count} items, but source has {target_count}. Repopulating...")
    
    if current_count > 0:
        print(f"Clearing existing items from collection '{collection.name}' before repopulating.")
        existing_ids = collection.get(include=[])['ids']
        if existing_ids:
            collection.delete(ids=existing_ids)
            print(f"Deleted {len(existing_ids)} items.")

    corpus_texts = preprocess_employee_text_for_corpus(employees_data_list)
    
    batch_size = 100
    for i in range(0, len(employees_data_list), batch_size):
        batch_employees = employees_data_list[i:i+batch_size]
        batch_corpus_texts = corpus_texts[i:i+batch_size]
        
        current_batch_docs = []
        current_batch_metadatas = []
        current_batch_ids = []

        for emp, text_content in zip(batch_employees, batch_corpus_texts):
            employee_id = emp.get('EmployeeID')
            if not employee_id:
                print(f"Warning: Employee record missing 'EmployeeID', skipping: {emp}")
                continue
            current_batch_docs.append(text_content)
            current_batch_metadatas.append(_prepare_metadata_for_chroma(emp))
            current_batch_ids.append(employee_id)
        
        if current_batch_ids:
            # print(f"Adding batch of {len(current_batch_ids)} employees to ChromaDB...")
            collection.add(
                documents=current_batch_docs,
                metadatas=current_batch_metadatas,
                ids=current_batch_ids
            )
    final_count = collection.count()
    print(f"Successfully populated ChromaDB collection '{collection.name}' with {final_count} items.")

# --- Retriever Class ---
class EmployeeRetriever:
    def __init__(self, collection, query_model):
        self.collection = collection
        self.query_model = query_model
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

    def retrieve_top_n_employees(self, project_query, top_n=50):
        """Retrieves the top N most similar employees from ChromaDB for a given project query."""
        if self.collection.count() == 0:
            print("Warning: ChromaDB collection is empty. Cannot retrieve.")
            return []

        # For BGE models, instruction is added to the query for retrieval tasks
        query_with_instruction = f"Represent this sentence for searching relevant passages: {project_query}"
        # print(f"Generating embedding for project query: '{project_query[:100]}...' (with instruction)")
        
        project_embedding = self.query_model.encode(query_with_instruction, device=self.device).tolist()

        # print("Querying ChromaDB...")
        results = self.collection.query(
            query_embeddings=[project_embedding],
            n_results=min(top_n, self.collection.count()),
            include=["metadatas", "documents", "distances"]
        )

        retrieved_items = []
        if results and results['ids'] and results['ids'][0]:
            # print(f"Top {len(results['ids'][0])} retrieval results from ChromaDB:")
            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                document_text = results['documents'][0][i] if results.get('documents') and results['documents'][0] else "N/A"
                
                similarity_score = 1 - distance # Chroma's cosine distance is 1 - similarity
                
                retrieved_items.append({
                    "employee": metadata,
                    "similarity_score": similarity_score,
                    "distance": distance,
                    "rank": i + 1,
                    "document_text": document_text
                })
        else:
            print("No results returned from ChromaDB query.")
        
        # Sort by similarity score descending (as higher similarity is better)
        retrieved_items.sort(key=lambda x: x['similarity_score'], reverse=True)
        return retrieved_items

# --- Initialization Function --- 
def initialize_retriever_system(
    model_name_for_embedding=DEFAULT_MODEL_NAME,
    chroma_db_path=DEFAULT_CHROMA_DB_PATH,
    collection_name=DEFAULT_COLLECTION_NAME,
    employee_data_path=None, # Path to employee data for populating if needed
    force_repopulate=False     # Force repopulation even if counts match
):
    """Initializes the full retriever system including model and ChromaDB."""
    print("Initializing retriever system...")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")

    print(f"Loading sentence transformer model: {model_name_for_embedding} for query embedding")
    try:
        query_model = SentenceTransformer(model_name_for_embedding, device=device)
        print("Query model loaded successfully.")
    except Exception as e:
        print(f"Error loading query model {model_name_for_embedding}: {e}")
        return None

    print(f"Initializing ChromaDB client with path: {chroma_db_path}")
    try:
        client = chromadb.PersistentClient(path=chroma_db_path)
        
        print(f"Setting up ChromaDB embedding function with model: {model_name_for_embedding}")
        chroma_embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name_for_embedding,
            device=device
        )
        
        print(f"Getting or creating ChromaDB collection: {collection_name}")
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=chroma_embedding_function,
            metadata={"hnsw:space": "cosine"}
        )
        print(f"Collection '{collection.name}' ready with {collection.count()} items.")

    except Exception as e:
        print(f"Error initializing ChromaDB: {e}")
        return None

    # Populate collection if employee_data_path is provided
    if employee_data_path:
        print(f"Employee data path provided: {employee_data_path}. Checking population status.")
        employees_list = load_employee_data(employee_data_path)
        if employees_list:
            populate_chroma_collection_if_needed(collection, employees_list, force_repopulate=force_repopulate)
        else:
            print(f"Could not load employee data from {employee_data_path}. Collection may not be populated as expected.")
    
    return EmployeeRetriever(collection, query_model)

# --- Main Execution Block (for standalone testing/demonstration) ---
if __name__ == '__main__':
    print("--- Running Retriever Standalone Demonstration ---")
    
    # Initialize the system, this will also populate the DB if 'generated_employees.json' is present and DB is empty/mismatched.
    retriever_instance = initialize_retriever_system(
        employee_data_path=DEFAULT_EMPLOYEE_DATA_PATH, # Specify path to ensure population check
        force_repopulate=False # Set to True to force deleting and re-adding all data
    )

    if not retriever_instance:
        print("Failed to initialize retriever system. Exiting demonstration.")
        exit()

    # Example Project Query
    sample_project_summary = "Develop a new cloud-based CRM system for sales automation."
    sample_project_scope = "- Design and implement database schema.\\n- Develop front-end interface.\\n- Integrate with existing marketing tools.\\n- Provide user training and documentation."
    sample_project_query = f"{sample_project_summary} {sample_project_scope}"
    
    print(f"\n--- Running Sample Retrieval for Project --- ")
    print(f"Project Query (first 100 chars): {sample_project_query[:100]}...")

    top_n = 5
    retrieved_items = retriever_instance.retrieve_top_n_employees(
        project_query=sample_project_query, 
        top_n=top_n
    )

    if retrieved_items:
        print(f"\n--- Top {len(retrieved_items)} Retrieved Employees (from __main__) --- ")
        for item in retrieved_items:
            emp_metadata = item['employee']
            print(f"  Rank: {item['rank']}")
            print(f"    Employee ID: {emp_metadata.get('EmployeeID')}")
            print(f"    Role Name: {emp_metadata.get('Role Name')}")
            
            role_desc_raw = emp_metadata.get('Role Description', '')
            if isinstance(role_desc_raw, str):
                try:
                    parsed_desc = json.loads(role_desc_raw) 
                    role_desc = parsed_desc if isinstance(parsed_desc, str) else role_desc_raw
                except json.JSONDecodeError:
                    role_desc = role_desc_raw
            else:
                role_desc = str(role_desc_raw)
            
            print(f"    Role Description (first 100 chars): {role_desc[:100]}...")
            print(f"    Similarity Score: {item['similarity_score']:.4f} (Distance: {item['distance']:.4f})")
            # print(f"    Embedded Text (from Chroma): {item.get('document_text', 'N/A')[:100]}...")
            print("  ----")
    else:
        print("No employees retrieved for the sample query in __main__.")

    print("\nRetriever system demonstration finished.")