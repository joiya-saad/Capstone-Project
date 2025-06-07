import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil import parser as date_parser # Renamed to avoid conflict with other parsers
from fuzzywuzzy import fuzz
import json # For parsing metadata if it was stringified
from config import SCORING_WEIGHTS, HOURS_PER_WORKDAY, WORKDAYS_PER_WEEK

# --- Global Variables and Constants ---
fuzzy_match_threshold = 70  # Default threshold for fuzzy matching

# CEFR scale for language proficiency
cefr_scale = {
    "A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6,
    "Native": 6 # Assuming native is equivalent to C2 for scoring
}

# --- Helper Functions ---
def fuzzy_match(text1, text2, threshold=fuzzy_match_threshold):
    if not text1 or not text2:
        return False
    return fuzz.ratio(str(text1).lower(), str(text2).lower()) >= threshold

def normalize(value, min_val, max_val):
    if max_val == min_val:
        return 0.0 if value <= min_val else 1.0 # Avoid division by zero, return 0 or 1
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

def normalize_flexibility(flexibility_text):
    flexibility_text = str(flexibility_text).lower()
    if "remote" in flexibility_text:
        return 0
    elif "hybrid" in flexibility_text:
        return 1
    elif "on-site" in flexibility_text or "onsite" in flexibility_text:
        return 2
    return 3 # Unknown or other

def cefr_to_numerical(level_str):
    """Converts CEFR level string to a numerical value."""
    return cefr_scale.get(str(level_str).strip().upper(), 0) # Convert to uppercase for matching

def best_fuzzy_match(query_lang, employee_langs_dict, threshold=70):
    """
    Finds the best fuzzy match for a query language in employee's language dictionary.
    Returns the matched employee language key if score is above threshold, else None.
    """
    best_match_score = 0
    best_match_lang = None
    for emp_lang_key in employee_langs_dict.keys():
        score = fuzz.ratio(str(query_lang).lower(), str(emp_lang_key).lower())
        if score > best_match_score:
            best_match_score = score
            best_match_lang = emp_lang_key
    
    if best_match_score >= threshold:
        return best_match_lang
    return None

def calculate_language_coverage(project_langs, employee_langs):
    """
    Calculates language score based on project requirements and employee proficiency.
    Returns a score (float) and a details string.
    """
    details_log = [] # For constructing the details string

    if not project_langs:
        return 1.0, "No specific languages required by project."
    if not employee_langs:
        return 0.0, "Employee has no listed language proficiency."

    matched_details = [] # To store tuples of (p_lang, matched_lang_key, p_level_str, e_level_str)
    
    for p_lang, p_level_str in project_langs.items():
        matched_lang_key = best_fuzzy_match(p_lang, employee_langs) # Using the new helper
        if matched_lang_key:
            e_level_str = employee_langs[matched_lang_key]
            matched_details.append((p_lang, matched_lang_key, p_level_str, e_level_str))
            details_log.append(f"Project requires '{p_lang}' ({p_level_str}). Matched with employee's '{matched_lang_key}' ({e_level_str}).")
        else:
            details_log.append(f"Project requires '{p_lang}' ({p_level_str}). No suitable match found in employee's languages.")

    if not matched_details:
        details_log.append("No language matches found.")
        return 0.0, "; ".join(details_log)

    coverage = len(matched_details) / len(project_langs)
    details_log.append(f"Language Coverage: {coverage:.2f} ({len(matched_details)} of {len(project_langs)} required languages matched)")
    
    level_scores = []
    for p_lang, matched_lang_key, p_level_str, e_level_str in matched_details:
        required_numeric = cefr_scale.get(str(p_level_str).strip().upper(), 0)
        actual_numeric = cefr_scale.get(str(e_level_str).strip().upper(), 0)
        
        level_score = 0.0
        if actual_numeric >= required_numeric:
            level_score = 1.0
        else:
            # Score is 0 if actual is 0, otherwise proportional to how close it is.
            # Max difference is 6 (e.g. C2=6, A0=0). If required is C2 and actual is B2, diff is 2. Score = 1 - 2/6 = 0.66
            if required_numeric > 0: # Avoid division by zero if somehow required_numeric is 0
                level_score = max(0.0, 1.0 - ( (required_numeric - actual_numeric) / 6.0) )
        
        level_scores.append(level_score)
        details_log.append(f"  - Match '{p_lang}' ({p_level_str}/{required_numeric}) vs '{matched_lang_key}' ({e_level_str}/{actual_numeric}): Proficiency Fit Score: {level_score:.2f}")

    avg_fit = 0.0
    if level_scores:
        avg_fit = sum(level_scores) / len(level_scores)
    details_log.append(f"Average Proficiency Fit for matched languages: {avg_fit:.2f}")
    
    final_score = coverage * avg_fit
    details_log.append(f"Final Language Score (Coverage * Avg Fit): {final_score:.2f}")
    
    return round(final_score, 3), "; ".join(details_log)

# --- Individual Scoring Functions (adapted from capstone_project.py) ---

def availability_score(project_effort_input_hours, project_end_input, employee_available_from_input, employee_weekly_capacity):
    details_dict = {
        "raw_project_effort_hours": project_effort_input_hours,
        "raw_project_end_input": project_end_input,
        "parsed_project_end_date": None,
        "raw_employee_available_from_input": employee_available_from_input,
        "parsed_employee_available_date": None,
        "raw_employee_weekly_capacity": employee_weekly_capacity,
        "project_effort_calculated_days": 0.0, # Calculated from input hours
        "employee_weekly_capacity_hours": 0.0,
        "calculated_project_end_for_employee": None,
        "days_over_under": 0,
        "status_message": "",
        "original_detail_string": ""
    }
    try:
        # Parse project end date
        if project_end_input is not None:
            if isinstance(project_end_input, (int, float)):
                project_end_date = datetime.fromtimestamp(project_end_input / 1000)
                details_dict["parsed_project_end_date"] = project_end_date
            elif isinstance(project_end_input, str):
                project_end_date = date_parser.parse(project_end_input)
                details_dict["parsed_project_end_date"] = project_end_date
            else:
                # Default to a far future date if type is unexpected or handle as error
                project_end_date = datetime.now() + timedelta(days=365*5) # Option 2: Assume far future
                details_dict["status_message"] = "Project end date format invalid or missing, assuming far future."
                # return 0.0, details_dict # Option 1: Strict
        else:
            project_end_date = datetime.now() + timedelta(days=365*5) # Assume far future if not specified
            details_dict["status_message"] = "Project end date not specified, assuming far future."
        details_dict["parsed_project_end_date"] = project_end_date # Ensure it's set even if defaulted

        # Parse employee available from date
        if employee_available_from_input is not None:
            if isinstance(employee_available_from_input, (int, float)):
                employee_available_date = datetime.fromtimestamp(employee_available_from_input / 1000)
                details_dict["parsed_employee_available_date"] = employee_available_date
            elif isinstance(employee_available_from_input, str):
                employee_available_date = date_parser.parse(employee_available_from_input)
                details_dict["parsed_employee_available_date"] = employee_available_date
            else:
                 details_dict["status_message"] = "Employee available from date format invalid."
                 details_dict["original_detail_string"] = details_dict["status_message"]
                 return 0.0, details_dict
        else:
            details_dict["status_message"] = "Employee available from date not specified."
            details_dict["original_detail_string"] = details_dict["status_message"]
            return 0.0, details_dict

        # Ensure employee_weekly_capacity is a number, default to 0 if not or invalid
        try:
            employee_weekly_capacity = float(employee_weekly_capacity if employee_weekly_capacity is not None else 0)
            details_dict["employee_weekly_capacity_hours"] = employee_weekly_capacity
        except ValueError:
            employee_weekly_capacity = 0.0
            details_dict["employee_weekly_capacity_hours"] = employee_weekly_capacity
        
        # Ensure project_effort is a number, default to 0 if not or invalid
        try:
            # Input is now project_effort_input_hours
            project_effort_hours_val = float(project_effort_input_hours if project_effort_input_hours is not None else 0)
            details_dict["raw_project_effort_hours"] = project_effort_hours_val # Store the validated hour value
            details_dict["project_effort_calculated_days"] = project_effort_hours_val / HOURS_PER_WORKDAY if HOURS_PER_WORKDAY > 0 else 0
        except ValueError:
            project_effort_hours_val = 0.0
            details_dict["raw_project_effort_hours"] = project_effort_hours_val
            details_dict["project_effort_calculated_days"] = 0.0

        if employee_weekly_capacity <= 0:
            details_dict["status_message"] = "Employee weekly capacity is zero or not specified."
            details_dict["original_detail_string"] = details_dict["status_message"]
            return 0.0, details_dict
        if project_effort_hours_val <= 0:
            # If project effort is zero, employee is considered fully available for it.
            details_dict["status_message"] = "Project effort is zero or not specified (considered fully available)."
            details_dict["original_detail_string"] = details_dict["status_message"]
            return 1.0, details_dict

        # Calculate project duration in weeks for the employee
        # Project effort is now in hours, employee_weekly_capacity is also in hours
        project_duration_weeks_for_employee = project_effort_hours_val / employee_weekly_capacity

        # Calculate actual end date based on employee's capacity
        # This simplistic model assumes continuous work. A more complex model might factor in weekends explicitly.
        calendar_days_needed = project_duration_weeks_for_employee * 7 
        calculated_project_end_for_employee = employee_available_date + timedelta(days=calendar_days_needed)
        details_dict["calculated_project_end_for_employee"] = calculated_project_end_for_employee

        # Check if the employee can finish before the project's requested end date
        if calculated_project_end_for_employee <= project_end_date:
            score = 1.0
            details_dict["status_message"] = "Employee can complete on time."
            details_dict["days_over_under"] = (calculated_project_end_for_employee - project_end_date).days # Will be <= 0
            details_dict["original_detail_string"] = f"Employee can complete. Proj End: {project_end_date.strftime('%Y-%m-%d')}, Emp Calc End: {calculated_project_end_for_employee.strftime('%Y-%m-%d')}. Effort: {details_dict['project_effort_calculated_days']:.1f}d, Emp Cap: {employee_weekly_capacity:.1f}hrs/wk."
        else:
            days_over = (calculated_project_end_for_employee - project_end_date).days
            details_dict["days_over_under"] = days_over # Will be > 0
            details_dict["status_message"] = f"Employee may not complete on time. Estimated over by {days_over} days."
            max_acceptable_overrun_days = 30.0 
            score = max(0.0, 1.0 - (days_over / max_acceptable_overrun_days))
            details_dict["original_detail_string"] = f"Employee may not complete on time. Proj End: {project_end_date.strftime('%Y-%m-%d')}, Emp Calc End: {calculated_project_end_for_employee.strftime('%Y-%m-%d')}. Over by {days_over} days. Effort: {project_effort_hours_val:.1f}hrs ({details_dict['project_effort_calculated_days']:.1f}d), Emp Cap: {employee_weekly_capacity:.1f}hrs/wk."
        
        return round(score, 3), details_dict

    except Exception as e:
        details_dict["status_message"] = f"Error in availability_score: {str(e)}."
        details_dict["original_detail_string"] = f"Error in availability_score: {str(e)}. Inputs: P_Effort='{project_effort_input_hours}', P_End='{project_end_input}', E_Avail='{employee_available_from_input}', E_Cap='{employee_weekly_capacity}'"
        return 0.0, details_dict

def product_score(project_products, employee_products):
    if not project_products: # List of products for the project
        return 1.0, "No specific products required by project."
    if not employee_products: # List of products employee has experience with
        return 0.0, "Employee has no listed product experience."
    
    # Ensure inputs are lists
    if isinstance(project_products, str): project_products = [project_products]
    if isinstance(employee_products, str): employee_products = [employee_products]

    matches = 0
    details = []
    for p_prod in project_products:
        matched_this_product = False
        for e_prod in employee_products:
            if fuzzy_match(p_prod, e_prod):
                matches += 1
                details.append(f"Matched: Project '{p_prod}' with Employee '{e_prod}'")
                matched_this_product = True
                break
        if not matched_this_product:
            details.append(f"No match for Project product: '{p_prod}'")
            
    score = matches / len(project_products) if project_products else 0.0
    return round(score, 3), "; ".join(details)

def location_score(project_loc, project_flex, employee_loc, employee_flex):
    # Normalize flexibility text to numerical values
    # 0: Remote, 1: Hybrid, 2: On-site
    p_flex_norm = normalize_flexibility(project_flex)
    e_flex_norm = normalize_flexibility(employee_flex)
    details = [f"Project: Loc='{project_loc}', Flex='{project_flex}'({p_flex_norm}). Employee: Loc='{employee_loc}', Flex='{employee_flex}'({e_flex_norm})"]

    # Case 1: Project is Remote
    if p_flex_norm == 0: # Project is remote
        if e_flex_norm == 0: # Employee prefers remote
            details.append("Match: Project remote, Employee remote.")
            return 1.0, "; ".join(details)
        elif e_flex_norm == 1: # Employee prefers hybrid (can do remote)
            details.append("Match: Project remote, Employee hybrid (can do remote).")
            return 1.0, "; ".join(details) # Slight penalty for not being fully remote preference
        else: # Employee prefers on-site
            details.append("Match: Project remote, Employee on-site.")
            return 1.0, "; ".join(details) # Low score as it's a mismatch

    # Case 2: Project is On-site
    elif p_flex_norm == 2: # Project is on-site
        if fuzzy_match(project_loc, employee_loc): # Locations match
            if e_flex_norm == 2: # Employee prefers on-site
                details.append("Match: Project on-site, Employee on-site, Locations match.")
                return 1.0, "; ".join(details)
            elif e_flex_norm == 1: # Employee prefers hybrid
                details.append("Partial Match: Project on-site, Employee hybrid, Locations match.")
                return 0.5, "; ".join(details)
            else: # Employee prefers remote
                details.append("Mismatch: Project on-site, Employee remote, Locations match but flex mismatch.")
                return 0.0, "; ".join(details)
        else: # Locations do not match
            details.append("Mismatch: Project on-site, Locations do not match.")
            return 0.0, "; ".join(details) # Location mismatch for on-site project is critical

    # Case 3: Project is Hybrid
    elif p_flex_norm == 1: # Project is hybrid
        if fuzzy_match(project_loc, employee_loc): # Locations match for the on-site part of hybrid
            if e_flex_norm == 1: # Employee prefers hybrid
                details.append("Match: Project hybrid, Employee hybrid, Locations match.")
                return 1.0, "; ".join(details)
            elif e_flex_norm == 0: # Employee prefers remote (can do hybrid's remote part)
                details.append("Mismatch: Project hybrid, Employee remote (can do remote part), Locations match.")
                return 0.0, "; ".join(details) # Can do remote part, but might not be ideal for on-site part
            elif e_flex_norm == 2: # Employee prefers on-site (can do hybrid's on-site part)
                details.append("Match: Project hybrid, Employee on-site (can do on-site part), Locations match.")
                return 1.0, "; ".join(details) # Good for on-site part
        else: # Locations do not match for hybrid project
            if e_flex_norm == 0: # Employee prefers remote, location mismatch doesn't matter as much for remote part
                details.append("Mismatch: Project hybrid, Employee remote, Locations mismatch (employee can do remote part).")
                return 0.0, "; ".join(details)
            else: # Employee prefers hybrid or on-site, but locations don't match
                details.append("Mismatch: Project hybrid, Locations do not match for employee preferring hybrid/on-site.")
                return 0.0, "; ".join(details)
    
    details.append("Unknown project/employee flexibility, low score.")
    return 0.0, "; ".join(details) # Default for unhandled cases

def language_score(project_langs_dict, employee_langs_dict):
    # project_langs_dict: e.g., {"English": "C1", "French": "B2"}
    # employee_langs_dict: e.g., {"English": "C2", "Spanish": "B1"}
    return calculate_language_coverage(project_langs_dict, employee_langs_dict)

def industry_score(project_industry, employee_industries):
    if not project_industry:
        return 1.0, "No specific industry required by project."
    if not employee_industries:
        return 0.0, "Employee has no listed industry experience."

    # Ensure employee_industries is a list
    if isinstance(employee_industries, str): employee_industries = [employee_industries]

    details = [f"Project Industry: {project_industry}. Employee Industries: {', '.join(employee_industries)}"]
    for e_ind in employee_industries:
        if fuzzy_match(project_industry, e_ind):
            details.append(f"Match: Project '{project_industry}' with Employee '{e_ind}'")
            return 1.0, "; ".join(details)
    details.append("No industry match found.")
    return 0.0, "; ".join(details)

def skill_match_score_with_fuzzy_keys(project_skills_dict, project_complexity_int, core_competency_dict):
    """
    Calculates skill match score using fuzzy key matching and new complexity adjustment.
    project_complexity_int: Integer 0-10 from project data.
    """
    details_log = []

    # Retaining complexity validation as it's an input parameter and good practice.
    if not isinstance(project_complexity_int, (int, float)):
        details_log.append(f"Warning: Invalid project complexity '{project_complexity_int}', defaulting to 5 for safety.")
        project_complexity_int = 5 
    project_complexity_int = max(0, min(10, project_complexity_int)) # Clamp between 0-10

    details_log.append(f"Project Skills: {len(project_skills_dict) if project_skills_dict else 0}, Emp Competencies: {len(core_competency_dict) if core_competency_dict else 0}, Proj Complexity: {project_complexity_int}")

    matched_pairs = []
    if project_skills_dict and core_competency_dict: # Proceed only if both dicts are non-empty
        for p_skill, required_level in project_skills_dict.items():
            matched_skill_key = best_fuzzy_match(p_skill, core_competency_dict, threshold=70) 
            if matched_skill_key:
                actual_level = core_competency_dict[matched_skill_key]
                matched_pairs.append((p_skill, matched_skill_key, required_level, actual_level))
                details_log.append(f"  Match: Proj '{p_skill}'({required_level}) with Emp '{matched_skill_key}'({actual_level})")
            else:
                details_log.append(f"  No Match: Proj '{p_skill}'({required_level})")
    elif not project_skills_dict:
        details_log.append("No specific skills required by project (project_skills_dict is empty/None).")
        # As per user snippet, if project_skills_dict is empty, matched_pairs is empty, leads to 0.0
        # However, to avoid ZeroDivisionError later if project_skills_dict is None/empty, it's safer to handle here.
        # The user's snippet: `if not matched_pairs: return 0.0` handles this implicitly.
        # Let's rely on that. If project_skills_dict is empty, matched_pairs will be empty.
        pass # Matched_pairs will remain empty
    elif not core_competency_dict:
        details_log.append("Employee has no listed core competencies (core_competency_dict is empty/None).")
        pass # Matched_pairs will remain empty

    if not matched_pairs:
        details_log.append("No skill matches found (or inputs were empty).")
        return 0.0, "; ".join(details_log) # Return 0.0 as per snippet

    # If project_skills_dict is empty, the 'if not matched_pairs' check above would have caught it.
    # Thus, len(project_skills_dict) should be > 0 here.
    coverage = len(matched_pairs) / len(project_skills_dict)
    details_log.append(f"Coverage: {coverage:.2f} ({len(matched_pairs)}/{len(project_skills_dict)}) ")

    expertise_scores = []
    for _, _, required, actual in matched_pairs:
        individual_skill_score = 0.0
        if actual >= required:
            individual_skill_score = 1.0
        else:
            # EXACTLY as per user snippet: 1 - (required - actual) / 10
            individual_skill_score = 1.0 - ((required - actual) / 10.0) 
        expertise_scores.append(individual_skill_score)
        details_log.append(f"    Expertise Fit: ReqLvl={required}, EmpLvl={actual}, Score={individual_skill_score:.2f}")
    
    expertise_fit = sum(expertise_scores) / len(expertise_scores)
    details_log.append(f"Avg Expertise Fit: {expertise_fit:.2f}")

    capability = coverage * expertise_fit
    details_log.append(f"Capability (Coverage * Expertise Fit): {capability:.3f}")

    complexity_target = project_complexity_int / 10.0
    details_log.append(f"Complexity Target: {complexity_target:.2f}")

    final_score = 0.0
    # EXACTLY as per user snippet: 1.0 if capability >= complexity_target else round(capability / complexity_target, 2)
    if capability >= complexity_target:
        final_score = 1.0
        details_log.append(f"Final Score: 1.0 (Capability {capability:.3f} >= Target {complexity_target:.2f})")
    else:
        # This will raise ZeroDivisionError if complexity_target is 0, as per direct translation
        raw_final_score_else = capability / complexity_target 
        final_score = round(raw_final_score_else, 2) # Round to 2 decimal places
        details_log.append(f"Final Score: {final_score:.2f} (Capability {capability:.3f} / Target {complexity_target:.2f}, Raw: {raw_final_score_else:.3f})")
        
    return final_score, "; ".join(details_log)

def certification_score(project_certs, employee_certs):
    # project_certs: list of required certs
    # employee_certs: list of employee's certs
    if not project_certs:
        return 1.0, "No specific certifications required by project."
    if not employee_certs:
        return 0.0, "Employee has no listed certifications."

    if isinstance(project_certs, str): project_certs = [project_certs]
    if isinstance(employee_certs, str): employee_certs = [employee_certs]

    matches = 0
    details = []
    for p_cert in project_certs:
        matched_this_cert = False
        for e_cert in employee_certs:
            if fuzzy_match(p_cert, e_cert):
                matches += 1
                details.append(f"Matched: Project cert '{p_cert}' with Employee cert '{e_cert}'")
                matched_this_cert = True
                break
        if not matched_this_cert:
            details.append(f"No match for Project cert: '{p_cert}'")

    score = matches / len(project_certs) if project_certs else 0.0
    return round(score, 3), "; ".join(details)

def expertise_score(project_expertise, employee_expertise):
    # project_expertise: list of required expertise areas
    # employee_expertise: list of employee's expertise areas
    if not project_expertise:
        return 1.0, "No specific expertise areas required by project."
    if not employee_expertise:
        return 0.0, "Employee has no listed expertise areas."

    if isinstance(project_expertise, str): project_expertise = [project_expertise]
    if isinstance(employee_expertise, str): employee_expertise = [employee_expertise]

    matches = 0
    details = []
    for p_exp in project_expertise:
        matched_this_exp = False
        for e_exp in employee_expertise:
            if fuzzy_match(p_exp, e_exp):
                matches += 1
                details.append(f"Matched: Project expertise '{p_exp}' with Employee expertise '{e_exp}'")
                matched_this_exp = True
                break
        if not matched_this_exp:
            details.append(f"No match for Project expertise: '{p_exp}'")
            
    score = matches / len(project_expertise) if project_expertise else 0.0
    return round(score, 3), "; ".join(details)

# --- Main Scoring Orchestration ---

def _safely_get_and_parse_json_field(record, field_name, default_value=None):
    """Helper to get a field and parse it if it's a JSON string, especially from Chroma metadata."""
    if default_value is None:
        default_value = {} if field_name.endswith('Dict') or field_name.endswith('s') else []
        if field_name.endswith('Dict'): default_value = {} # e.g. project_skills_dict
        elif 'Langs' in field_name: default_value = {} # e.g. project_langs_dict
        elif 'Experience' in field_name or 'Certifications' in field_name or 'Expertise' in field_name or 'Industries' in field_name:
             default_value = []
        else: default_value = '' # Default for simple string fields if missing
        
    val = record.get(field_name, default_value)
    if isinstance(val, str):
        try:
            # Attempt to parse if it looks like a JSON list or dict
            if (val.startswith('[') and val.endswith(']')) or (val.startswith('{') and val.endswith('}')):
                return json.loads(val)
        except json.JSONDecodeError:
            # If it's not valid JSON but was a string, return as a single-item list if appropriate for the field
            if isinstance(default_value, list): return [val] 
            return val # Or return the string itself if default was not a list
    return val if val is not None else default_value

def score_employee_against_project(employee_record, project_record, custom_weights=None):
    """Calculates all scores for a single employee against a single project."""
    scores = {
        "EmployeeID": employee_record.get("EmployeeID"),
        "ProjectID": project_record.get("ProjectID"),
        "Scores": {},
        "Details": {}
    }

    # 2. Availability Score
    project_end_val = project_record.get("Requested End Date") # Prefer 'Requested End Date'
    if project_end_val is None:
        project_end_val = project_record.get("Requested End") # Fallback to 'Requested End'

    avail_score, avail_details = availability_score(
        project_effort_input_hours=project_record.get("Effort"),
        project_end_input=project_end_val, # Changed from project_end_str
        employee_available_from_input=employee_record.get("Available From"), # Changed from employee_available_from_str
        employee_weekly_capacity=employee_record.get("Weekly Availability in Hours")
    )
    scores["Scores"]["AvailabilityScore"] = avail_score
    scores["Details"]["AvailabilityScore"] = avail_details
    scores["Scores"]["IsFullyAvailable"] = 1 if avail_score == 1.0 else 0

    # 3. Product Experience Score
    proj_products = _safely_get_and_parse_json_field(project_record, "Products Involved", [])
    emp_products = _safely_get_and_parse_json_field(employee_record, "Products Experience", [])
    prod_score, prod_details = product_score(proj_products, emp_products)
    scores["Scores"]["ProductScore"] = prod_score
    scores["Details"]["ProductScore"] = prod_details

    # 4. Location Score
    loc_score, loc_details = location_score(
        project_loc=project_record.get("Work Location"),
        project_flex=project_record.get("Work Flexibility"),
        employee_loc=employee_record.get("Work Location"),
        employee_flex=employee_record.get("Work Flexibility")
    )
    scores["Scores"]["LocationScore"] = loc_score
    scores["Details"]["LocationScore"] = loc_details

    # 5. Language Score
    proj_langs = _safely_get_and_parse_json_field(project_record, "Languages Required", {})
    emp_langs = _safely_get_and_parse_json_field(employee_record, "Languages Known", {})
    lang_score, lang_details = language_score(proj_langs, emp_langs)
    scores["Scores"]["LanguageScore"] = lang_score
    scores["Details"]["LanguageScore"] = lang_details

    # 6. Industry Score
    proj_industry = project_record.get("Customer Industry")
    emp_industries = _safely_get_and_parse_json_field(employee_record, "Industry Experience", [])
    ind_score, ind_details = industry_score(proj_industry, emp_industries)
    scores["Scores"]["IndustryScore"] = ind_score
    scores["Details"]["IndustryScore"] = ind_details

    # 7. Skill Match Score
    proj_skills = _safely_get_and_parse_json_field(project_record, "Required Skills and Expertise", {})
    emp_competencies = _safely_get_and_parse_json_field(employee_record, "Core Competencies", {})
    # Assuming 'Complexity' in JSON is numerical (e.g., 1-5 or 1-10). Default to 3 if not found.
    # The skill_match_score_with_fuzzy_keys might need to be adapted if it expects string categories.
    project_complexity_val = project_record.get("Complexity")
    if not isinstance(project_complexity_val, (int, float)):
        # Attempt to convert if it's a string representation of a number
        try:
            project_complexity_val = int(project_complexity_val)
        except (ValueError, TypeError):
            project_complexity_val = 5 # Default if conversion fails or type is unsuitable
    project_complexity_val = max(0, min(10, int(project_complexity_val))) # Clamp to 0-10

    skill_score, skill_details = skill_match_score_with_fuzzy_keys(
        project_record.get("Required Skills and Expertise", {}),
        project_complexity_val, # Pass the integer complexity
        employee_record.get("Core Competencies", {})
    )
    scores["Scores"]["SkillMatchScore"] = skill_score
    scores["Details"]["SkillMatchScore"] = skill_details

    # 8. Certification Score
    proj_certs = _safely_get_and_parse_json_field(project_record, "Customer Preferences (Certifications)", [])
    emp_certs = _safely_get_and_parse_json_field(employee_record, "External/Internal Certifications", [])
    cert_score, cert_details = certification_score(proj_certs, emp_certs)
    scores["Scores"]["CertificationScore"] = cert_score
    scores["Details"]["CertificationScore"] = cert_details

    # 9. Years of Experience Score (USER REQUEST: Optionally remove - currently commented out)
    # years_exp = employee_record.get("Years of Experience", 0)
    # if isinstance(years_exp, str): # Handle cases like 'N/A' or if it's read as string
    #     try:
    #         years_exp = float(years_exp)
    #     except ValueError:
    #         years_exp = 0
    # # Normalize years of experience, e.g., cap at 30 years for scoring
    # max_exp_for_scoring = 30.0
    # years_exp_score = normalize(years_exp, 0, max_exp_for_scoring)
    # scores["Scores"]["YearsExperienceScore"] = years_exp_score
    # scores["Details"]["YearsExperienceScore"] = f"Raw: {years_exp} yrs, Normalized (0-{max_exp_for_scoring} yrs): {years_exp_score:.3f}"

    # 10. Retriever Relevance Score (from document_score in Chroma results)
    # Assuming 'document_score' is passed in employee_record and is 0-1 (higher is better)
    retriever_score = employee_record.get('document_score', 0.0) 
    scores["Scores"]["RetrieverScore"] = retriever_score
    scores["Details"]["RetrieverScore"] = f"Raw document_score from retriever: {retriever_score:.3f}"

    # 11. Project Complexity Score (USER REQUEST: Remove - currently commented out)
    # # project_complexity_val is already fetched (e.g., 1-5). Let's normalize it (assuming 1-5 scale).
    # # If it's already used in skill score, this is a standalone representation of it.
    # # You might want a more sophisticated way to score complexity or just use the raw value if the scale is small.
    # # Assuming a 1-5 scale for complexity from project data for normalization here.
    # # If your complexity from project_record.get("Complexity", 3) is already normalized, adjust this.
    # raw_proj_complexity = project_record.get("Complexity", 3) # This is what project_complexity_val was based on
    # # Normalize assuming complexity is e.g. 1 (low) to 5 (high)
    # # A high complexity project might be 'harder' to match, so this score could be inverse or handled by weights.
    # # For now, let's assume higher complexity value means more complex, and normalize it.
    # # This interpretation might need review based on how you want complexity to affect the overall score.
    # # Let's treat it as a factor where higher project complexity might be a neutral or slightly positive attribute if well-matched.
    # # Normalizing (1-5 scale to 0-1)
    # normalized_proj_complexity = normalize(raw_proj_complexity, 1, 5) # Example: 1=0, 3=0.5, 5=1
    # scores["Scores"]["ProjectComplexityScore"] = normalized_proj_complexity
    # scores["Details"]["ProjectComplexityScore"] = f"Raw Project Complexity: {raw_proj_complexity}, Normalized (1-5 scale): {normalized_proj_complexity:.3f}"

    # 12. Expertise Score
    proj_expertise = _safely_get_and_parse_json_field(project_record, "Integration Requirements (Expertise Areas)", [])
    emp_expertise = _safely_get_and_parse_json_field(employee_record, "Expertise Areas", [])
    exp_score, exp_details = expertise_score(proj_expertise, emp_expertise)
    scores["Scores"]["ExpertiseScore"] = exp_score
    scores["Details"]["ExpertiseScore"] = exp_details

    # 10. Direct Employee Attribute Scores (Normalized)
    # Assuming these are 1-10 scales in the data, normalize to 0-1
    cultural_awareness = employee_record.get("Cultural Awareness", 0)
    problem_solving = employee_record.get("Problem Solving", 0)
    leadership = employee_record.get("Leadership", 0)
    
    scores["Scores"]["CulturalAwarenessScore"] = normalize(cultural_awareness, 0, 10)
    scores["Details"]["CulturalAwarenessScore"] = f"Raw: {cultural_awareness}, Normalized: {scores['Scores']['CulturalAwarenessScore']:.2f}"
    scores["Scores"]["ProblemSolvingScore"] = normalize(problem_solving, 0, 10)
    scores["Details"]["ProblemSolvingScore"] = f"Raw: {problem_solving}, Normalized: {scores['Scores']['ProblemSolvingScore']:.2f}"
    scores["Scores"]["LeadershipScore"] = normalize(leadership, 0, 10)
    scores["Details"]["LeadershipScore"] = f"Raw: {leadership}, Normalized: {scores['Scores']['LeadershipScore']:.2f}"

    # --- Calculate Overall Weighted Score ---
    active_scoring_weights = custom_weights if custom_weights is not None else SCORING_WEIGHTS
    
    overall_score_sum = 0
    total_weight_applied = 0

    for score_name, weight in active_scoring_weights.items():
        if score_name in scores["Scores"] and isinstance(scores["Scores"][score_name], (int, float)):
            overall_score_sum += scores["Scores"][score_name] * weight
            total_weight_applied += weight
        elif score_name in scores["Scores"]:
            # Handle cases where a score might not be numeric (e.g. if an error occurred upstream)
            # For now, we'll just skip it for weighting, but logging would be good here.
            pass # Or log: print(f"Warning: Score {score_name} is not numeric, skipping for weighting.")

    # Normalize the overall score if total_weight_applied is not 1 (e.g. due to missing scores or weights not summing to 1)
    if total_weight_applied > 0:
        normalized_overall_score = overall_score_sum / total_weight_applied
        # If weights are designed to sum to 1 and all scores are present, this division isn't strictly needed,
        # but it makes the calculation robust to changes in weights or missing scores.
    else:
        normalized_overall_score = 0 # Default to 0 if no weights applied or no scores

    scores["OverallWeightedScore"] = round(normalized_overall_score, 4)
    scores["Details"]["OverallWeightedScoreCalculation"] = f"Calculated based on predefined weights. Sum of (score*weight): {overall_score_sum:.4f}. Total weight applied: {total_weight_applied:.2f}. Final Score: {scores['OverallWeightedScore']:.4f}"

    return scores

def generate_detailed_scores_for_candidates(project_record, candidate_employee_records, custom_weights=None):
    """Generates detailed scores for a list of candidate employees against a single project."""
    all_scored_candidates = []
    for emp_record in candidate_employee_records:
        # The emp_record from retriever might have JSON stringified metadata.
        # The score_employee_against_project will use _safely_get_and_parse_json_field for its needs.
        # So, we can pass the employee record (which is typically a dict from Chroma's metadata) directly.
        
        # However, the Chroma metadata might be the *processed* metadata (with JSON strings).
        # It's better if the `candidate_employee_records` are the original, full employee dicts.
        # We'll assume `main_matcher.py` provides the full original employee dicts for scoring.
        
        detailed_scores = score_employee_against_project(emp_record, project_record, custom_weights=custom_weights)
        all_scored_candidates.append(detailed_scores)
    return all_scored_candidates

# Example of how to call this if you were testing (not for direct run in this file normally)
# if __name__ == '__main__':
#     # This would require sample_project and sample_employees data to be loaded/defined
#     # For example:
#     sample_project = {
#         "ProjectID": "P001", "Project Summary": "Build a new AI tool for HR.", 
#         "Scope and Deliverables": "Analyze data, develop model, test.",
#         "Effort": 100, "Requested End": "2024-12-31",
#         "Products Required": ["Python", "TensorFlow"], # List
#         "Project Location": "New York", "Location Flexibility": "Hybrid",
#         "Languages Required": {"English": "C1"}, # Dict
#         "Industry Vertical": "Technology",
#         "Skills Required": {"Machine Learning": 4, "Data Analysis": 3}, # Dict
#         "Project Complexity": "High",
#         "Certifications Required": ["PMP"], # List
#         "Expertise Areas Required": ["AI Development"] # List
#     }
#     sample_employees = [
#         {
#             "EmployeeID": "E001", "Role Description": "I am an AI engineer.",
#             "Available From": "2024-01-01", "Weekly Availability in Hours": 40,
#             "Products Experience": ["Python", "PyTorch"], # List
#             "Location": "New York", "Work Flexibility": "Hybrid",
#             "Languages Spoken": {"English": "C2"}, # Dict
#             "Industry Experience": ["Technology", "Finance"], # List
#             "Core Competencies": {"Machine Learning": 5, "Python": 5}, # Dict
#             "External/Internal Certifications": ["TensorFlow Developer Certificate"], # List
#             "Expertise Areas": ["AI Development", "NLP"], # List
#             "Cultural Awareness": 8, "Problem Solving": 9, "Leadership": 7
#         }
#         # ... more employees
#     ]
#     scored_data = generate_detailed_scores_for_candidates(sample_project, sample_employees)
#     print(json.dumps(scored_data, indent=2))
