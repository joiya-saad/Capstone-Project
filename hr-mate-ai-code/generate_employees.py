import pandas as pd
from datetime import datetime, timedelta
import random
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Import data from common_data.py
from common_data import (
    employee_roles, product_pools, skill_pools, certification_pools, 
    expertise_pools, industries_master, locations_master, 
    work_flexibility_options, languages_master, fluency_levels, introduce_typo
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

def generate_employee_role_description_with_gemini(theme, products_experience, core_competencies, industry_experience, original_description):
    """Generates an employee role description using the Gemini API."""
    if not model:
        print("Gemini model not initialized. Returning original description.")
        return original_description # Fallback if API key is missing

    # Construct a detailed prompt for Gemini
    prompt = (
        f"Write a 3-4 sentence role description for an employee profile, written in the first person (e.g., 'I am a...'). "
        f"I fit the theme: '{theme}'.\n"
        f"My key product experience includes: {', '.join(products_experience)}.\n"
        f"My core competencies (skill: proficiency level) are: {', '.join([f'{k}({v})' for k, v in core_competencies.items()])}.\n"
        f"My relevant industry experience covers: {', '.join(industry_experience)}.\n"
        f"My original role idea was: '{original_description}'.\n"
        f"Based on these details, I need a description that highlights my likely responsibilities, key skills, and how I can contribute to relevant projects. "
        f"The tone should be professional yet approachable, suitable for an internal HR matching system where I'm presenting myself."
    )

    try:
        response = model.generate_content(prompt)
        # Simple error check for response structure
        if response.parts:
            generated_text = response.text.strip()
            # Further clean-up if necessary (e.g., removing markdown)
            return generated_text
        else:
            print(f"Gemini API response for role description did not contain expected parts. Response: {response}")
            return original_description # Fallback
    except Exception as e:
        print(f"Error calling Gemini API for role description: {e}")
        return original_description # Fallback in case of API error

def generate_smart_employees_full(n):
    employees = []
    for i in range(n):
        emp_template = random.choice(employee_roles)
        theme = emp_template["Theme"]

        product_experience = random.sample(product_pools[theme], k=min(len(product_pools[theme]), random.randint(1, 3)))
        core_competencies = {skill: random.randint(4, 10) for skill in random.sample(skill_pools[theme], k=min(len(skill_pools[theme]), random.randint(2, 5)))}
        certifications = random.sample(certification_pools[theme], k=min(len(certification_pools[theme]), random.randint(1, 2)))
        expertise = random.sample(expertise_pools[theme], k=min(len(expertise_pools[theme]), random.randint(1, 2)))
        industry_experience = random.sample(industries_master, k=random.randint(1, 3))

        # Generate Role Description using Gemini
        generated_role_description = generate_employee_role_description_with_gemini(
            theme=theme,
            products_experience=product_experience,
            core_competencies=core_competencies,
            industry_experience=industry_experience,
            original_description=emp_template["Role Description"] # Pass original for context
        )

        employee = {
            "EmployeeID": f"E{i+1:03d}", # Padded ID
            "Role Name": emp_template["Role Name"],
            "Role Description": generated_role_description, # Use Gemini's output
            "Theme": theme,
            "Products Experience": product_experience,
            "Core Competencies": core_competencies,
            "External/Internal Certifications": certifications,
            "Expertise Areas": expertise,
            "Industry Experience": industry_experience,
            "Work Location": random.choice(locations_master),
            "Work Flexibility": random.choice(work_flexibility_options),
            "Languages Known": {lang: random.choice(fluency_levels)
                                for lang in random.sample(languages_master, k=random.randint(1, 3))},
            "Available From": datetime.now().date() + timedelta(days=random.randint(0, 30)),
            "Weekly Availability in Hours": random.choice([10, 20, 30, 40]),
            "Cultural Awareness": random.randint(1, 10),
            "Problem Solving": random.randint(1, 10),
            "Leadership": random.randint(1, 10)
        }
        employees.append(employee)
    return pd.DataFrame(employees)

if __name__ == "__main__":
    num_employees_to_generate = 1000
    print(f"Generating {num_employees_to_generate} employee records...")
    
    # Ensure API key is loaded before generating
    if not GEMINI_API_KEY or not model:
        print("Exiting: Gemini API key not configured. Please check your .env file.")
    else:
        employees_df = generate_smart_employees_full(num_employees_to_generate)
        print("\nGenerated Employee Data:")
        print(employees_df)
        
        # Save to CSV
        csv_output_path = "generated_employees.csv"
        employees_df.to_csv(csv_output_path, index=False)
        print(f"\nEmployee data saved to {csv_output_path}")

        # Save to JSON
        json_output_path = "generated_employees.json"
        employees_df.to_json(json_output_path, orient="records", indent=4)
        print(f"Employee data saved to {json_output_path}")
