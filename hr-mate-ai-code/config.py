# Configuration file for HR Mate AI
import json
import os
from datetime import datetime

# Scoring weights for employee-project matching
# These weights determine the importance of each factor in the overall score.
# The sum of weights does not necessarily have to be 1.0, as the final score is normalized
# by the sum of weights for components that are actually present and scored.
SCORING_WEIGHTS = {
    "SkillMatchScore": 0.25,        # Alignment of employee skills with project requirements
    "AvailabilityScore": 0.15,      # Employee's availability for the project duration/effort
    "ProductScore": 0.05,           # Experience with specific products/tools required
    "IndustryScore": 0.05,          # Relevant industry experience
    "ExpertiseScore": 0.10,         # Alignment of expertise areas
    "LanguageScore": 0.05,          # Proficiency in required languages
    "CertificationScore": 0.05,     # Possession of required certifications
    "LocationScore": 0.00,          # Match of location and flexibility (often a filter or low weight)
    "CulturalAwarenessScore": 0.02, # Employee's cultural awareness rating
    "ProblemSolvingScore": 0.04,    # Employee's problem-solving skill rating
    "LeadershipScore": 0.04,         # Employee's leadership skill rating
    # "YearsExperienceScore": 0.05,    # Normalized years of experience
    "RetrieverScore": 0.25,        # Semantic relevance score from document retriever (now primary for role/text fit)
    # "ProjectComplexityScore": 0.03  # Normalized project complexity
    # Ensure the sum of weights reflects desired priorities.
    # Example: If LocationScore is critical, increase its weight and ensure project/employee data supports it.
}

# Standard work definitions
HOURS_PER_WORKDAY = 8
WORKDAYS_PER_WEEK = 5

# Path to the ChromaDB database
CHROMA_DB_PATH = "./chroma_db"

# Name of the ChromaDB collection for employee profiles
CHROMA_COLLECTION_NAME = "employee_profiles"

# Model used for generating embeddings (ensure this matches retriever.py)
EMBEDDING_MODEL_NAME = "BAAI/bge-large-en-v1.5"

# Data file paths
EMPLOYEE_DATA_PATH = "generated_employees.json"
PROJECT_DATA_PATH = "generated_projects.json"
SCORED_EMPLOYEE_DATA_PATH = "employee_data_with_scores.json"  # File to store employee data with match scores

# Top N candidates to retrieve and score by default in command-line main_matcher
# For Streamlit app, this will likely be a user input.
DEFAULT_TOP_N_CANDIDATES = 10

def load_data(file_path):
    """Loads data from a JSON file."""
    if not os.path.exists(file_path):
        print(f"Error: Data file not found at {file_path}")
        return None # Or consider returning [] if an empty list is a better default
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}")
        return None # Or consider returning []
    except Exception as e:
        print(f"An unexpected error occurred while loading data from {file_path}: {e}")
        return None # Or consider returning []


def format_timestamp_to_date(timestamp_input):
    """Formats various timestamp inputs to 'YYYY-MM-DD' string. Handles integers, floats, and ISO-like date strings."""
    if timestamp_input is None or str(timestamp_input).strip() == '':
        return "N/A"
    try:
        # If it's already a datetime object
        if isinstance(timestamp_input, datetime):
            return timestamp_input.strftime('%Y-%m-%d')
        
        # Try to parse as a number (Unix timestamp in seconds or milliseconds)
        if isinstance(timestamp_input, (int, float)):
            # Heuristic: if it's a large number (e.g., > 1 Jan 2000 in ms), assume milliseconds
            if timestamp_input > 946684800000: # Approx 2000-01-01T00:00:00Z in milliseconds
                 timestamp_input /= 1000
            return datetime.fromtimestamp(float(timestamp_input)).strftime('%Y-%m-%d')
        
        # Try to parse as an ISO-like date string
        if isinstance(timestamp_input, str):
            # Clean up common variations like 'Z' for UTC or extra spaces
            timestamp_str = timestamp_input.strip().replace('Z', '')
            # Handle potential microseconds by splitting them off
            if '.' in timestamp_str:
                timestamp_str = timestamp_str.split('.')[0]
            
            # Attempt to parse common ISO-like formats
            if 'T' in timestamp_str:
                 dt_obj = datetime.fromisoformat(timestamp_str.replace('T', ' '))
            else: # Assume it's just a date string YYYY-MM-DD
                 dt_obj = datetime.strptime(timestamp_str, '%Y-%m-%d')
            return dt_obj.strftime('%Y-%m-%d')
            
    except (ValueError, TypeError) as e:
        # print(f"Warning: Could not parse date: {timestamp_input} due to {e}. Returning as is.")
        if isinstance(timestamp_input, str) and '-' in timestamp_input:
            parts = timestamp_input.split('T')[0].split('-')
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                 if len(parts[0]) == 4 and len(parts[1]) <= 2 and len(parts[2]) <= 2:
                    return timestamp_input.split('T')[0]
        return str(timestamp_input) # Fallback for other errors or unparseable formats
    except Exception as e:
        # print(f"Unexpected error formatting date {timestamp_input}: {e}")
        return str(timestamp_input) # Fallback for other errors

    # Default fallback if no case matched or if input was problematic from the start
    return str(timestamp_input) if timestamp_input is not None else "N/A"
