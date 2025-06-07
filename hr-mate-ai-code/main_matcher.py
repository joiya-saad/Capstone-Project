import json
import os
from retriever import initialize_retriever_system
from scorer import generate_detailed_scores_for_candidates, score_employee_against_project
from config import (CHROMA_DB_PATH, CHROMA_COLLECTION_NAME, 
                    EMBEDDING_MODEL_NAME, EMPLOYEE_DATA_PATH, 
                    PROJECT_DATA_PATH, DEFAULT_TOP_N_CANDIDATES,
                    SCORED_EMPLOYEE_DATA_PATH) # Added SCORED_EMPLOYEE_DATA_PATH

# Configuration is now imported from config.py
# TOP_N_CANDIDATES is now DEFAULT_TOP_N_CANDIDATES from config

def load_json_data(file_path):
    """Loads data from a JSON file."""
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading {file_path}: {e}")
        return None

def main():
    """Main function to orchestrate employee-project matching."""
    print("Initializing Employee-Project Matcher...")

    # Load project and employee data
    projects_data = load_json_data(PROJECT_DATA_PATH)
    all_employees_data_list = load_json_data(EMPLOYEE_DATA_PATH)

    if not projects_data or not all_employees_data_list:
        print("Failed to load necessary data. Exiting.")
        return

    # Convert employee list to a dictionary for easy lookup by EmployeeID
    all_employees_map = {emp['EmployeeID']: emp for emp in all_employees_data_list}

    # Initialize the retriever system
    print("\nInitializing retriever system...")
    # Explicitly pass model_name to initialize_retriever_system if it expects it
    retriever_system = initialize_retriever_system(
        model_name_for_embedding=EMBEDDING_MODEL_NAME, 
        chroma_db_path=CHROMA_DB_PATH, 
        collection_name=CHROMA_COLLECTION_NAME,
        employee_data_path=EMPLOYEE_DATA_PATH, # Pass the path to populate ChromaDB
        force_repopulate=False # Set to True to force repopulation from employee_data_path
    )
    if not retriever_system:
        print("Failed to initialize retriever system. Exiting.")
        return
    
    print("Retriever system initialized.")

    # --- Project Selection (Example: Select the first project) ---
    if not projects_data:
        print("No projects available to process.")
        return
    
    # For demonstration, let's pick the first project
    # In a real application, you'd have a mechanism for the user to select a project.
    selected_project_index = 0 # or some other index
    if selected_project_index >= len(projects_data):
        print(f"Selected project index {selected_project_index} is out of bounds.")
        return
    
    selected_project = projects_data[selected_project_index]
    project_id = selected_project.get('ProjectID', f'Project_{selected_project_index}')
    project_query = selected_project.get('Project Summary', '') + " - " + selected_project.get('Scope and Deliverables', '')

    print(f"\n--- Processing Project: {project_id} ---")
    print(f"Project Query: {project_query[:200]}...") # Print a snippet

    # 1. Retrieve top N candidate employees
    print(f"\nRetrieving top {DEFAULT_TOP_N_CANDIDATES} candidates for project {project_id}...")
    retrieved_candidate_info = retriever_system.retrieve_top_n_employees(project_query, top_n=DEFAULT_TOP_N_CANDIDATES)

    if not retrieved_candidate_info:
        print(f"No candidates retrieved for project {project_id}. Exiting.")
        return

    candidate_employees_for_scoring = []
    print("\nFetching full details for retrieved candidates...")
    for candidate in retrieved_candidate_info:
        emp_id = candidate['employee'].get('EmployeeID')
        similarity = candidate.get('similarity_score', 0.0) # Get similarity_score from retriever output
        if emp_id and emp_id in all_employees_map:
            employee_record = all_employees_map[emp_id].copy() # Get a copy to modify
            employee_record['document_score'] = similarity # Add the similarity score
            candidate_employees_for_scoring.append(employee_record)
            print(f"  - Fetched details for {emp_id}, Similarity: {similarity:.4f}")
        else:
            print(f"  - Warning: Could not find full details for EmployeeID: {emp_id} from retriever output.")
    
    if not candidate_employees_for_scoring:
        print(f"No valid candidate details found for scoring. Exiting.")
        return

    # 2. Generate detailed scores for these candidates
    print(f"\nScoring {len(candidate_employees_for_scoring)} candidates against project {project_id}...")
    
    # The scorer expects the project object and a list of employee objects.
    # Ensure selected_project has all necessary fields for scoring (e.g., 'Required Skills', 'Complexity', etc.)
    detailed_scores_data = generate_detailed_scores_for_candidates(
        selected_project, 
        candidate_employees_for_scoring
    )

    # 3. Print the results
    print(f"\n--- Detailed Scores for Project: {project_id} ---")
    if detailed_scores_data:
        for score_info in detailed_scores_data:
            print(f"\n  Employee ID: {score_info['EmployeeID']}")
            print(f"  Overall Weighted Score: {score_info['OverallWeightedScore']:.4f}")
            print("  Individual Scores:")
            for category, value in score_info['Scores'].items():
                print(f"    {category}: {value}")
            # Optionally print details if needed, can be verbose
            # print("  Score Details:")
            # for category, detail_text in score_info['Details'].items():
            #     print(f"    {category}: {detail_text}")
            print("  ----")
    else:
        print("No scores were generated.")

    # Save the detailed scores data to a file
    if detailed_scores_data:
        try:
            with open(SCORED_EMPLOYEE_DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump(detailed_scores_data, f, indent=4)
            print(f"\nSuccessfully saved detailed scores for {len(detailed_scores_data)} candidates to {SCORED_EMPLOYEE_DATA_PATH}")
        except IOError as e:
            print(f"\nError saving scores to {SCORED_EMPLOYEE_DATA_PATH}: {e}")
    else:
        print("\nNo scores generated, so nothing to save.")

    print("\nEmployee-Project Matcher finished.")

if __name__ == "__main__":
    main()
