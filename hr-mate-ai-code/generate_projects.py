import pandas as pd
from datetime import datetime, timedelta
import random
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json

# Import data from common_data.py
from common_data import (
    project_summary_templates, product_pools, skill_pools, certification_pools, 
    expertise_pools, industries_master, locations_master, work_flexibility_options, 
    languages_master, fluency_levels, introduce_typo
)

# Load environment variables from .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure the Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash') # Or your preferred model
else:
    print("GEMINI_API_KEY not found in .env file. Please set it up.")
    model = None # Or handle this case as an error

def generate_project_details_with_gemini(theme, products_involved, required_skills, customer_industry, complexity, original_summary, original_scope):
    """Generates project summary and scope/deliverables using the Gemini API."""
    if not model:
        print("Gemini model not initialized. Returning original details.")
        return {"Project Summary": original_summary, "Scope and Deliverables": original_scope}

    # Construct a detailed prompt for Gemini
    prompt = (
        f"Generate a concise project summary (2-3 sentences) and a bulleted list of scope/deliverables for a new project. "
        f"The project's theme is: '{theme}'.\n"
        f"Products involved: {', '.join(products_involved)}.\n"
        f"Required skills (skill: proficiency level) and expertise: {', '.join([f'{k}({v})' for k, v in required_skills.items()])}.\n"
        f"The customer's industry is: '{customer_industry}'.\n"
        f"Project complexity level (1-10): {complexity}.\n"
        f"The original project idea was: Summary: '{original_summary}', Scope: '{original_scope}'.\n"
        f"Based on these details, create a compelling Project Summary and a list of key Scope and Deliverables. "
        f"Format the Scope and Deliverables as a bulleted list (e.g., '- Deliverable 1\n- Deliverable 2')."
        f"Output should be a JSON string with two keys: \"Project Summary\" and \"Scope and Deliverables\". For example: "
        f"{{\"Project Summary\": \"Your generated summary here.\", \"Scope and Deliverables\": \"- Item 1\n- Item 2\"}}"
    )

    try:
        response = model.generate_content(prompt)
        generated_text = response.text.strip()
        
        # Attempt to parse the JSON-like string from Gemini
        # This is a simplified parser; a more robust one might be needed for complex cases
        try:
            # Clean the text if it's wrapped in markdown for JSON
            if generated_text.startswith("```json"):
                generated_text = generated_text[7:-3].strip()
            elif generated_text.startswith("```") and generated_text.endswith("```"):
                generated_text = generated_text[3:-3].strip()

            # Attempt to parse the string as JSON
            data = json.loads(generated_text)
            parsed_summary = data.get("Project Summary", original_summary)
            parsed_scope = data.get("Scope and Deliverables", original_scope)
            return {"Project Summary": parsed_summary, "Scope and Deliverables": parsed_scope}
        
        except json.JSONDecodeError as json_err:
            print(f"JSONDecodeError parsing Gemini response: {json_err}. Raw response: {generated_text}")
            # Fallback if JSON parsing fails
            return {"Project Summary": original_summary, "Scope and Deliverables": original_scope}
        except Exception as e:
            print(f"Unexpected error parsing Gemini response: {e}. Raw response: {generated_text}")
            return {"Project Summary": original_summary, "Scope and Deliverables": original_scope}
            
    except Exception as e:
        print(f"Error calling Gemini API for project details: {e}")
        return {"Project Summary": original_summary, "Scope and Deliverables": original_scope} # Fallback

def generate_smart_projects_full(n):
    projects = []
    for i in range(n):
        proj_template = random.choice(project_summary_templates)
        theme = proj_template["Theme"]

        products = [introduce_typo(p) if random.random() < 0.4 else p
                    for p in random.sample(product_pools[theme], k=min(len(product_pools[theme]), random.randint(1, 3)))]
        required_skills = {
            (introduce_typo(skill) if random.random() < 0.4 else skill): random.randint(5, 10)
            for skill in random.sample(skill_pools[theme], k=min(len(skill_pools[theme]), random.randint(2, 5)))
        }
        certifications = random.sample(certification_pools[theme], k=min(len(certification_pools[theme]), random.randint(1, 2)))
        expertise = random.sample(expertise_pools[theme], k=min(len(expertise_pools[theme]), random.randint(1, 2)))
        project_industry = introduce_typo(random.choice(industries_master)) if random.random() < 0.4 else random.choice(industries_master)
        project_complexity = random.randint(1, 10)

        # Generate Project Summary and Scope using Gemini
        gemini_details = generate_project_details_with_gemini(
            theme=theme,
            products_involved=products,
            required_skills=required_skills,
            customer_industry=project_industry,
            complexity=project_complexity,
            original_summary=proj_template["Project Summary"],
            original_scope=proj_template["Scope and Deliverables"]
        )

        project = {
            "ProjectID": f"P{i+1:03d}", # Padded ID
            "Project Summary": gemini_details["Project Summary"],
            "Scope and Deliverables": gemini_details["Scope and Deliverables"],
            "Theme": theme,
            "Products Involved": products,
            "Required Skills and Expertise": required_skills,
            "Customer Preferences (Certifications)": certifications,
            "Integration Requirements (Expertise Areas)": expertise,
            "Customer Industry": project_industry,
            "Work Location": introduce_typo(random.choice(locations_master)) if random.random() < 0.3 else random.choice(locations_master),
            "Work Flexibility": random.choice(work_flexibility_options),
            "Languages Required": {introduce_typo(lang) if random.random() < 0.3 else lang: random.choice(fluency_levels)
                                   for lang in random.sample(languages_master, k=random.randint(1, 3))},
            "Complexity": project_complexity,
            "Effort": random.choice(list(range(20, 241, 10))),
            "Requested End": datetime.now().date() + timedelta(days=random.randint(30, 150))
        }
        projects.append(project)
    return pd.DataFrame(projects)

if __name__ == "__main__":
    num_projects_to_generate = 100
    print(f"Generating {num_projects_to_generate} project records...")

    if not GEMINI_API_KEY or not model:
        print("Exiting: Gemini API key not configured. Please check your .env file.")
    else:
        projects_df = generate_smart_projects_full(num_projects_to_generate)
        print("\nGenerated Project Data:")
        print(projects_df)
        
        # Save to CSV
        csv_output_path = "generated_projects.csv"
        projects_df.to_csv(csv_output_path, index=False)
        print(f"\nProject data saved to {csv_output_path}")

        # Save to JSON
        json_output_path = "generated_projects.json"
        projects_df.to_json(json_output_path, orient="records", indent=4)
        print(f"Project data saved to {json_output_path}")
