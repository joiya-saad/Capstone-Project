import streamlit as st
import pandas as pd # Added
import re
import json
import plotly.express as px
from datetime import datetime as dt_datetime, timedelta
from dateutil import parser as date_parser
import os # Ensure os is imported if used for css_file_path
from config import (
    PROJECT_DATA_PATH, 
    EMPLOYEE_DATA_PATH, 
    load_data, 
    format_timestamp_to_date, 
    DEFAULT_TOP_N_CANDIDATES,
    SCORING_WEIGHTS # Added
)
from retriever import initialize_retriever_system
from scorer import generate_detailed_scores_for_candidates, fuzzy_match, fuzzy_match_threshold
from fuzzywuzzy import fuzz # Added for direct ratio calculation


def create_radar_chart(scores_dict, score_names_map, scoring_weights_config):
    """Creates a radar chart from the raw scores dictionary."""
    data = []
    # Consider scores that have a display name and are relevant (e.g., in SCORING_WEIGHTS or fundamental)
    # Or, more simply, iterate through SCORE_DISPLAY_NAMES to ensure we only plot what's meant to be user-facing
    for score_key, display_name in score_names_map.items():
        # Only include scores that are part of the defined scoring system
        if score_key not in scoring_weights_config and score_key != 'document_score': # 'document_score' is an alias for RetrieverScore sometimes
            continue

        raw_score = float(scores_dict.get(score_key, 0.0))
        # Special handling for RetrieverScore possibly being under 'document_score'
        if score_key == "RetrieverScore" and score_key not in scores_dict:
            raw_score = float(scores_dict.get('document_score', 0.0))
        
        # Ensure scores are capped at 1.0 for radar chart visualization consistency if some raw scores can exceed 1.0
        raw_score = min(raw_score, 1.0)
        raw_score = max(raw_score, 0.0) # Ensure non-negative for radar

        data.append({'Metric': display_name, 'Score': raw_score})

    if not data:
        return None

    df = pd.DataFrame(data)
    if df.empty:
        return None

    fig = px.line_polar(df, r='Score', theta='Metric', line_close=True,
                        range_r=[0,1],  # Scores are normalized or assumed to be 0-1
                        title="Employee Score Profile")
    fig.update_traces(fill='toself')
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1]
            )
        ),
        showlegend=False,
        height=600,  # Increased height
        width=700,   # Added width
        title_font_size=20, # Larger title font
        title_x=0.5 # Center title
    )
    return fig


# --- Attribute Comparison Configuration ---
ATTRIBUTE_COMPARISON_CONFIG = [
    {
        "label": "Skills",
        "score_key": "SkillMatchScore",
        "project_key": "Required Skills and Expertise",      # Expected in project_details: dict, e.g., {"Python": 4}
        "employee_key": "Core Competencies", # Expected in candidate_data: dict, e.g., {"Python": 5}
        "render_function_name": "render_skills_comparison",
    },
    {
        "label": "Products Experience",
        "score_key": "ProductScore",
        "project_key": "Products Involved",         # Expected: list of strings
        "employee_key": "Products Experience",    # Expected: list of strings
        "render_function_name": "render_list_comparison",
        "item_name_singular": "Product",
        "item_name_plural": "Products"
    },
    {
        "label": "Certifications",
        "score_key": "CertificationScore",
        "project_key": "Customer Preferences (Certifications)",             # Expected: list of strings
        "employee_key": "External/Internal Certifications", # Expected: list of strings
        "render_function_name": "render_list_comparison",
        "item_name_singular": "Certification",
        "item_name_plural": "Certifications"
    },

    {
        "label": "Availability & FTE",
        "score_key": "AvailabilityScore", # Assumes scorer.py provides this
        "render_function_name": "render_availability_comparison",
        # These keys tell the render function what fields to look for in project_details and candidate_data
        "detail_keys": {
            "project_start": "Project Start Date", # Ensure this key is correct for your project data if applicable
            "project_end": "Requested End",      # Mapped to project's 'Requested End' (timestamp)
            "project_fte": "Effort",             # Mapped to project's 'Effort' (e.g., total hours)
            "employee_from": "Available from", # e.g., "YYYY-MM-DD" or timestamp
            "employee_until": "Available until",  # e.g., "YYYY-MM-DD", timestamp, or "Open"
            "employee_fte_current": "Current FTE %" # e.g., "20%" or 20
        }
    },
    {
        "label": "Expertise Areas",
        "score_key": "ExpertiseScore",
        "project_key": "Integration Requirements (Expertise Areas)",      # Expected: list of strings
        "employee_key": "Expertise Areas",    # Expected: list of strings
        "render_function_name": "render_list_comparison",
        "item_name_singular": "Expertise Area",
        "item_name_plural": "Expertise Areas"
    },
    # {
    #     "label": "Years of Experience",
    #     "score_key": "YearsExperienceScore",
    #     "project_key": "RequiredExperienceYears", # Expected: int or float
    #     "employee_key": "Years of Experience",   # Expected: int or float
    #     "render_function_name": "render_numerical_comparison",
    #     "unit": "years"
    # },
    {
        "label": "Location",
        "score_key": "LocationScore", # This score might be 0 if location is a hard filter
        "project_key": "Work Location",    # Expected: string
        "employee_key": "Work Location",   # Expected: string
        "render_function_name": "render_string_comparison"
    },
    {
        "label": "Work Modality",
        "score_key": None, # May not have a direct score component if it's about compatibility
        "project_key": "Work Flexibility", 
        "employee_key": "Work Flexibility",
        "render_function_name": "render_work_modality_comparison"
    },

    {
        "label": "Languages",
        "score_key": "LanguageScore",
        "project_key": "Languages Required",      # Expected: list of dicts, e.g., [{"Language": "English", "Proficiency": "Fluent"}]
        "employee_key": "Languages Known",            # Expected: dict, e.g., {"English": "C1"}
        "render_function_name": "render_languages_comparison"
    },
    {
        "label": "Industry Vertical",
        "score_key": "IndustryScore",
        "project_key": "Customer Industry",  # Key in project_details
        "employee_key": "Industry Experience", # Key in candidate_data
        "render_function_name": "render_list_comparison",
        "item_name_singular": "Industry",
        "item_name_plural": "Industries"
    }
]

# --- Placeholder Helper Functions for Attribute Comparison ---
def render_skills_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    st.subheader(config_entry['label'])

    raw_project_skills = project_value if isinstance(project_value, dict) else {}
    raw_employee_skills = employee_value if isinstance(employee_value, dict) else {}

    project_skills_orig_filtered = {k: v for k, v in raw_project_skills.items() if isinstance(k, str)}
    employee_skills_orig_filtered = {k: v for k, v in raw_employee_skills.items() if isinstance(k, str)}

    project_skills_map_lower_to_orig = {k.lower().strip(): k for k in project_skills_orig_filtered.keys()}
    project_skills_lower = {k.lower().strip(): v for k, v in project_skills_orig_filtered.items()}

    employee_skills_map_lower_to_orig = {k.lower().strip(): k for k in employee_skills_orig_filtered.keys()}
    employee_skills_lower = {k.lower().strip(): v for k, v in employee_skills_orig_filtered.items()}

    comparison_data = []
    processed_employee_skills_lower = set()

    # Iterate through project skills to find matches, excesses, or misses
    for p_skill_lower, p_level in project_skills_lower.items():
        p_skill_orig = project_skills_map_lower_to_orig.get(p_skill_lower, p_skill_lower)
        p_level_display = f"L{p_level}"

        if p_skill_lower in employee_skills_lower:
            e_skill_orig = employee_skills_map_lower_to_orig.get(p_skill_lower, p_skill_lower)
            e_level = employee_skills_lower[p_skill_lower]
            e_level_display = f"L{e_level}"
            processed_employee_skills_lower.add(p_skill_lower)

            status = ""
            if e_level > p_level:
                status = "✅ Exceeds"
            elif e_level == p_level:
                status = "✔️ Meets"
            else:
                status = "⚠️ Below"
            
            comparison_data.append({
                "Project Skill": p_skill_orig,
                "Required Level": p_level_display,
                "Employee Has": e_skill_orig, # Should be same as p_skill_orig if matched
                "Employee Level": e_level_display,
                "Status": status
            })
        else:
            comparison_data.append({
                "Project Skill": p_skill_orig,
                "Required Level": p_level_display,
                "Employee Has": "-",
                "Employee Level": "-",
                "Status": "❌ Missing"
            })

    # Add additional skills from employee not in project requirements
    for e_skill_lower, e_level in employee_skills_lower.items():
        if e_skill_lower not in processed_employee_skills_lower:
            e_skill_orig = employee_skills_map_lower_to_orig.get(e_skill_lower, e_skill_lower)
            e_level_display = f"L{e_level}"
            comparison_data.append({
                "Project Skill": "-",
                "Required Level": "-",
                "Employee Has": e_skill_orig,
                "Employee Level": e_level_display,
                "Status": "✨ Additional"
            })

    if not comparison_data:
        if not project_skills_lower and not employee_skills_lower:
            st.caption("No skills specified for project or employee, or skills data is malformed.")
        elif not project_skills_lower:
            st.caption("No skills specified for the project.")
        elif not employee_skills_lower:
            st.caption("No skills specified for the employee.")
        st.markdown("---")
        return

    df = pd.DataFrame(comparison_data)

    def style_status(row):
        style = ''
        if row['Status'] == "✅ Exceeds":
            style = 'background-color: #c8e6c9; color: #2e7d32;'
        elif row['Status'] == "✔️ Meets":
            style = 'background-color: #dcedc8; color: #388e3c;'
        elif row['Status'] == "⚠️ Below":
            style = 'background-color: #fff9c4; color: #f57f17;'
        elif row['Status'] == "❌ Missing":
            style = 'background-color: #ffcdd2; color: #c62828;'
        elif row['Status'] == "✨ Additional":
            style = 'background-color: #e3f2fd; color: #0d47a1;'
        return [style] * len(row)

    # Apply styling. Using st.dataframe which handles styling differently than pure pandas styling.
    # For more complex styling, might need HTML table or investigate aggrid.
    # For now, let's use st.dataframe and keep the summary separate.
    st.dataframe(df.style.apply(style_status, axis=1), use_container_width=True, hide_index=True)

    # Recalculate summary counts based on the DataFrame statuses
    summary_counts = df['Status'].value_counts().to_dict()
    summary_parts = []
    if summary_counts.get("✅ Exceeds", 0) > 0:
        summary_parts.append(f"<span style='color: #2e7d32;'>**{summary_counts['✅ Exceeds']} Exceeded**</span>")
    if summary_counts.get("✔️ Meets", 0) > 0:
        summary_parts.append(f"<span style='color: #388e3c;'>**{summary_counts['✔️ Meets']} Met**</span>")
    if summary_counts.get("⚠️ Below", 0) > 0:
        summary_parts.append(f"<span style='color: #f57f17;'>**{summary_counts['⚠️ Below']} Below Level**</span>")
    if summary_counts.get("❌ Missing", 0) > 0:
        summary_parts.append(f"<span style='color: #c62828;'>**{summary_counts['❌ Missing']} Missing** from Employee</span>")
    if summary_counts.get("✨ Additional", 0) > 0:
        summary_parts.append(f"<span style='color: #0d47a1;'>**{summary_counts['✨ Additional']} Additional** in Employee</span>")

    if summary_parts:
        st.markdown("**Summary:** " + " | ".join(summary_parts), unsafe_allow_html=True)
    st.markdown("---") # Visual separator requires {len(project_skills_lower)} skills; employee has none._")

def render_list_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    label = config_entry.get('label', 'Items')
    st.subheader(label)

    project_items_raw = project_value if isinstance(project_value, list) else ([] if project_value is None else [str(project_value)])
    employee_items_raw = employee_value if isinstance(employee_value, list) else ([] if employee_value is None else [str(employee_value)])

    project_items_orig_list = [str(item).strip() for item in project_items_raw if item is not None and str(item).strip()]
    employee_items_orig_list = [str(item).strip() for item in employee_items_raw if item is not None and str(item).strip()]

    # For fuzzy matching, it's better to have a list of originals to iterate and match against
    # project_items_lower_map = {item.lower(): item for item in project_items_orig_list}
    # employee_items_lower_map = {item.lower(): item for item in employee_items_orig_list}

    comparison_data = []
    processed_employee_indices = set()
    project_col_name = f"Project {config_entry.get('item_name_singular', 'Requirement')}" # Changed 'Item' to 'Requirement' for clarity
    employee_col_name = f"Employee {config_entry.get('item_name_singular', 'Experience')}" # Changed 'Has' to 'Experience'
    status_col_name = "Status"
    fuzzy_match_threshold = 85 # Threshold for considering a fuzzy match valid

    if not project_items_orig_list and not employee_items_orig_list:
        st.caption(f"No {label.lower()} specified for the project or the employee.")
        st.markdown("---")
        return

    for p_idx, p_item_orig in enumerate(project_items_orig_list):
        p_item_lower = p_item_orig.lower()
        best_match_score = 0
        best_e_match_idx = -1
        best_e_item_orig = "-" # Default if no match

        for e_idx, e_item_orig in enumerate(employee_items_orig_list):
            if e_idx in processed_employee_indices:
                continue # Already matched this employee item
            
            e_item_lower = e_item_orig.lower()
            current_match_score = fuzz.ratio(p_item_lower, e_item_lower)
            
            if current_match_score > best_match_score:
                best_match_score = current_match_score
                best_e_match_idx = e_idx
                best_e_item_orig = e_item_orig
        
        row = {
            project_col_name: p_item_orig,
            employee_col_name: "-",
            status_col_name: "❌ Missing"
        }

        if best_match_score >= fuzzy_match_threshold:
            row[employee_col_name] = best_e_item_orig
            processed_employee_indices.add(best_e_match_idx)
            if p_item_lower == best_e_item_orig.lower(): # Check if it was a direct match after lowercasing
                row[status_col_name] = "✔️ Matched"
            else:
                row[status_col_name] = f"✔️ Matched (Fuzzy: {best_e_item_orig})"
        comparison_data.append(row)

    # Add any additional employee items not processed
    for e_idx, e_item_orig in enumerate(employee_items_orig_list):
        if e_idx not in processed_employee_indices:
            row = {
                project_col_name: "-",
                employee_col_name: e_item_orig,
                status_col_name: "✨ Additional"
            }
            comparison_data.append(row)
    
    if not comparison_data:
        # This block might be reached if only one side has items and no matches/additional are generated
        # The initial check for both empty handles one case. This handles others.
        if project_items_orig_list and not employee_items_orig_list:
            st.caption(f"Employee has no listed {label.lower()} to compare against project requirements.")
        elif not project_items_orig_list and employee_items_orig_list:
            st.caption(f"No specific {label.lower()} required by project. Employee has {len(employee_items_orig_list)} listed.")
        else: # Both had items, but somehow comparison_data is empty (e.g. all project items processed, no additional employee items)
            st.caption(f"No specific comparison details to display for {label.lower()}.")
        st.markdown("---")
        return

    df = pd.DataFrame(comparison_data)
    df_columns = [project_col_name, employee_col_name, status_col_name]
    df = df[df_columns] # Ensure column order and presence

    def style_status_list(row):
        style = [''] * len(row)
        status_val = row.get(status_col_name, '')
        if status_val.startswith("✔️ Matched"):
            style = ['background-color: #dcedc8; color: #388e3c;'] * len(row)
        elif status_val == "❌ Missing":
            style = ['background-color: #ffcdd2; color: #c62828;'] * len(row)
        elif status_val == "✨ Additional":
            style = ['background-color: #e3f2fd; color: #0d47a1;'] * len(row)
        return style

    if not df.empty:
        st.dataframe(df.style.apply(style_status_list, axis=1), use_container_width=True, hide_index=True)
    else:
        st.caption(f"No relevant {label.lower()} data to display after comparison.")

    st.markdown("---")


def render_industry_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    label = config_entry.get('label', 'Industry Vertical')
    st.markdown(f"<h5 style='margin-bottom: 0.1rem;'>{label}</h5>", unsafe_allow_html=True)

    project_industry = project_value # Directly use passed project_value
    employee_industries = employee_value # Directly use passed employee_value

    # Ensure employee_industries is a list, even if it's a single string from JSON/data
    if isinstance(employee_industries, str):
        # Basic assumption: if it's a string, treat it as a single industry unless it's clearly JSON
        try:
            if employee_industries.startswith('[') and employee_industries.endswith(']'):
                parsed_industries = json.loads(employee_industries)
                if isinstance(parsed_industries, list):
                    employee_industries = parsed_industries
                else: # Not a list after parsing, treat original string as one item
                    employee_industries = [employee_industries]
            else: # Not a JSON list string, treat as single item
                employee_industries = [employee_industries.strip()] 
        except json.JSONDecodeError:
            employee_industries = [employee_industries.strip()] # If JSON parse fails, treat as single
    elif not isinstance(employee_industries, list):
        employee_industries = [] # Default to empty list if not string or list
    
    # Filter out any None or empty strings from employee_industries after processing
    employee_industries = [str(ei).strip() for ei in employee_industries if ei and str(ei).strip()]
    project_industry_str = str(project_industry).strip() if project_industry and str(project_industry).strip() else None

    match_found = False
    matched_employee_industry = None

    if project_industry_str and employee_industries:
        for emp_ind in employee_industries:
            if fuzzy_match(project_industry_str, emp_ind):
                match_found = True
                matched_employee_industry = emp_ind
                break

    # Determine display text and style
    display_text = ""
    status_color = "grey"

    if not project_industry_str:
        status_text = "ℹ️ Project industry not specified."
        proj_display_str = "Not Specified"
        emp_display_str = f"{', '.join(employee_industries)}" if employee_industries else "Not Specified"
    elif not employee_industries:
        status_text = f"⚠️ Employee has no listed industry experience. Project requires: {project_industry_str}."
        status_color = "orange"
        proj_display_str = project_industry_str
        emp_display_str = "Not Specified"
    elif match_found:
        status_text = f"✅ Match Found (Project: '{project_industry_str}', Employee: '{matched_employee_industry}')."
        status_color = "green"
        proj_display_str = project_industry_str
        emp_display_str = f"{', '.join(employee_industries)} (Matched: {matched_employee_industry})"
        # Consider listing only the matched and then 'others' if list is long
    else: # No match found, project and employee industries are specified
        status_text = f"ℹ️ No direct match. Project: '{project_industry_str}'. Employee: '{', '.join(employee_industries)}'."
        status_color = "#808080" # Darker grey or orange for noticeable difference
        proj_display_str = project_industry_str
        emp_display_str = f"{', '.join(employee_industries)}"

    st.markdown(f"**Project Requirement:** {proj_display_str}")
    st.markdown(f"**Employee Experience:** {emp_display_str}")
    if status_text:
        st.markdown(f"**Status:** <span style='color: {status_color};'>{status_text}</span>", unsafe_allow_html=True)

    st.markdown("---")

def render_numerical_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    label = config_entry.get('label', 'Numerical Value')
    unit = config_entry.get('unit', '')
    st.subheader(label)

    def _try_convert_to_float(val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            val_stripped = val.strip()
            if not val_stripped:
                return None
            try:
                return float(val_stripped)
            except ValueError:
                cleaned_val = re.sub(r"[^\d\.]", "", val_stripped)
                if cleaned_val and cleaned_val != ".":
                    try:
                        return float(cleaned_val)
                    except ValueError:
                        return None
                return None
        return None

    proj_val_num = _try_convert_to_float(project_value)
    emp_val_num = _try_convert_to_float(employee_value)

    unit_str = f" {unit}" if unit else ""

    proj_display_str = f"{proj_val_num:.1f}{unit_str}" if proj_val_num is not None else "Not Specified"
    emp_display_str = f"{emp_val_num:.1f}{unit_str}" if emp_val_num is not None else "Not Specified"
    
    status = ""
    if proj_val_num is not None and emp_val_num is not None:
        if emp_val_num > proj_val_num:
            status = "✅ Exceeds"
        elif emp_val_num == proj_val_num:
            status = "✔️ Meets"
        else:
            status = f"⚠️ Below (Needs {proj_val_num - emp_val_num:.1f}{unit_str})"
    elif proj_val_num is not None and emp_val_num is None:
        status = "❓ Employee Data Missing/Invalid"
    elif proj_val_num is None and emp_val_num is not None:
        status = "ℹ️ Project Requirement Not Specified"
    else: # Both are None or invalid
        status = "ℹ️ Data Not Available"

    comparison_table_data = [{
        "Description": label,
        "Project Requirement": proj_display_str,
        "Employee Has": emp_display_str,
        "Status": status
    }]

    df = pd.DataFrame(comparison_table_data)

    def style_numerical_status(row):
        style = [''] * len(row)
        status_val = row.get('Status', '')
        if "✅ Exceeds" in status_val:
            style = ['background-color: #c8e6c9; color: #2e7d32;'] * len(row)
        elif "✔️ Meets" in status_val:
            style = ['background-color: #dcedc8; color: #388e3c;'] * len(row)
        elif "⚠️ Below" in status_val:
            style = ['background-color: #fff9c4; color: #f57f17;'] * len(row)
        elif "❓ Employee Data Missing/Invalid" in status_val:
            style = ['background-color: #f5f5f5; color: #757575;'] * len(row) # Light grey for missing data
        elif "ℹ️" in status_val: # Catches "Not Specified" and "Data Not Available"
            style = ['background-color: #e3f2fd; color: #0d47a1;'] * len(row) # Blue for info
        return style

    st.dataframe(df.style.apply(style_numerical_status, axis=1), use_container_width=True, hide_index=True)
    st.markdown("---")

def render_string_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    label = config_entry.get('label', 'String Value')
    st.subheader(label)

    proj_val_str = str(project_value).strip() if project_value is not None and project_value != "" else ""
    emp_val_str = str(employee_value).strip() if employee_value is not None and employee_value != "" else ""

    proj_display_str = proj_val_str if proj_val_str else "Not Specified"
    emp_display_str = emp_val_str if emp_val_str else "Not Specified"

    status = ""
    if proj_val_str and emp_val_str:
        if proj_val_str.lower() == emp_val_str.lower():
            status = "✔️ Matched"
        else:
            status = "⚠️ Mismatched"
    elif proj_val_str and not emp_val_str:
        status = "❓ Employee Data Missing/Not Specified"
    elif not proj_val_str and emp_val_str:
        status = "ℹ️ Project Requirement Not Specified"
    else: # Both are empty or initially unspecified
        status = f"ℹ️ Data Not Available"

    comparison_table_data = [{
        "Description": label,
        "Project Requirement": proj_display_str,
        "Employee Has": emp_display_str,
        "Status": status
    }]

    df = pd.DataFrame(comparison_table_data)

    def style_string_status(row):
        style = [''] * len(row)
        status_val = row.get('Status', '')
        if "✔️ Matched" in status_val:
            style = ['background-color: #dcedc8; color: #388e3c;'] * len(row)
        elif "⚠️ Mismatched" in status_val:
            style = ['background-color: #fff9c4; color: #f57f17;'] * len(row)
        elif "❓ Employee Data Missing/Not Specified" in status_val:
            style = ['background-color: #f5f5f5; color: #757575;'] * len(row)
        elif "ℹ️" in status_val: # Catches "Project Requirement Not Specified" and "Data Not Available"
            style = ['background-color: #e3f2fd; color: #0d47a1;'] * len(row)
        return style

    st.dataframe(df.style.apply(style_string_status, axis=1), use_container_width=True, hide_index=True)
    st.markdown("---")

def render_work_modality_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    label = config_entry.get('label', "Work Modality")
    st.subheader(label)

    # project_value and employee_value are already the direct values from config
    # No need to use project_details.get(project_modality_key) if project_value is passed correctly
    project_modality_raw = project_value
    employee_preference_raw = employee_value

    project_modality = str(project_modality_raw).strip() if project_modality_raw is not None and str(project_modality_raw).strip() else "Not Specified"
    employee_preference = str(employee_preference_raw).strip() if employee_preference_raw is not None and str(employee_preference_raw).strip() else "Not Specified"

    p_mod_lower = project_modality.lower()
    e_pref_lower = employee_preference.lower()

    compatibility_status = ""

    if p_mod_lower == "not specified" and e_pref_lower == "not specified":
        compatibility_status = "ℹ️ Data Not Available"
    elif p_mod_lower == "not specified":
        compatibility_status = "ℹ️ Project Requirement Not Specified"
    elif e_pref_lower == "not specified":
        compatibility_status = "❓ Employee Preference Not Specified"
    elif p_mod_lower == e_pref_lower:
        compatibility_status = "✅ Compatible"
    # Specific compatibility checks (more nuanced than simple match/mismatch)
    elif ("hybrid" in p_mod_lower and ("hybrid" in e_pref_lower or "remote" in e_pref_lower or "flexible" in e_pref_lower or "open" in e_pref_lower)) or \
         ("remote" in p_mod_lower and ("remote" in e_pref_lower or "flexible" in e_pref_lower or "open" in e_pref_lower)):
        compatibility_status = "⚠️ Potentially Compatible (Discuss)"
    elif "flexible" in e_pref_lower or "open to" in e_pref_lower or "open" == e_pref_lower:
        # If project requires something specific (not 'Not Specified') and employee is flexible
        compatibility_status = "⚠️ Potentially Compatible (Employee Flexible)"
    else:
        compatibility_status = "❌ Mismatch"

    comparison_table_data = [{
        "Description": label,
        "Project Requirement": project_modality,
        "Employee Preference": employee_preference,
        "Compatibility": compatibility_status
    }]

    df = pd.DataFrame(comparison_table_data)

    def style_modality_status(row):
        style = [''] * len(row)
        status_val = row.get('Compatibility', '')
        if "✅ Compatible" in status_val:
            style = ['background-color: #dcedc8; color: #388e3c;'] * len(row) # Green
        elif "⚠️ Potentially Compatible" in status_val: # Catches both 'Discuss' and 'Employee Flexible'
            style = ['background-color: #fff9c4; color: #f57f17;'] * len(row) # Yellow/Orange
        elif "❌ Mismatch" in status_val:
            style = ['background-color: #ffcdd2; color: #c62828;'] * len(row) # Red
        elif "❓ Employee Preference Not Specified" in status_val:
            style = ['background-color: #f5f5f5; color: #757575;'] * len(row) # Grey for missing preference
        elif "ℹ️" in status_val: # Catches "Project Requirement Not Specified" and "Data Not Available"
            style = ['background-color: #e3f2fd; color: #0d47a1;'] * len(row) # Blue for info
        return style

    st.dataframe(df.style.apply(style_modality_status, axis=1), use_container_width=True, hide_index=True)
    st.markdown("---")

def format_date_for_display(date_obj):
    if date_obj and isinstance(date_obj, dt_datetime):
        return date_obj.strftime('%Y-%m-%d')
    if isinstance(date_obj, str): # If it's already a string (e.g. from parsing error)
        return date_obj
    return "N/A"

def render_availability_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    """
    Renders the availability comparison using the structured dictionary from availability_score.
    'employee_value' is expected to be the dictionary from scores['Details']['AvailabilityScore'].
    """
    
    label = config_entry.get('label', "Timeline & Availability Assessment") # Use label from config, fallback if needed
    st.subheader(label)

    if not isinstance(employee_value, dict):
        st.error("Availability details are not in the expected format. Please check scoring logic.")
        # st.write(f"DEBUG: Received employee_value type: {type(employee_value)}, value: {employee_value}") # For debugging
        st.markdown("---")
        return

    # Extract data from the employee_value (which is the details_dict)
    proj_effort_hours = employee_value.get("raw_project_effort_hours", "N/A")
    proj_effort_calculated_days = employee_value.get("project_effort_calculated_days", "N/A")
    parsed_proj_end_date = employee_value.get("parsed_project_end_date")
    
    parsed_emp_avail_date = employee_value.get("parsed_employee_available_date")
    emp_weekly_capacity_hours = employee_value.get("employee_weekly_capacity_hours", "N/A")
    calculated_emp_end_date = employee_value.get("calculated_project_end_for_employee")
    
    days_over_under = employee_value.get("days_over_under", 0) # positive if over, negative if under/on_time
    status_message = employee_value.get("status_message", "Details not available.")
    original_detail_string = employee_value.get("original_detail_string", "")

    # --- Display Project Requirements ---
    st.markdown("##### Project Requirements")
    col1_proj, col2_proj, col3_proj = st.columns(3)
    with col1_proj:
        value_display_hours = f"{proj_effort_hours:.1f}" if isinstance(proj_effort_hours, float) else str(proj_effort_hours)
        st.metric(label="Required Effort (Person-Hours)", value=value_display_hours)
    with col2_proj:
        value_display_days = f"{proj_effort_calculated_days:.1f}" if isinstance(proj_effort_calculated_days, float) else str(proj_effort_calculated_days)
        st.metric(label="Equivalent (Person-Days)", value=value_display_days)
    with col3_proj:
        st.metric(label="Requested Project Deadline", value=format_date_for_display(parsed_proj_end_date))

    # --- Display Employee Availability & Projection ---
    st.markdown("##### Employee Availability & Projection")
    col1_emp, col2_emp, col3_emp = st.columns(3)
    with col1_emp:
        st.metric(label="Available From", value=format_date_for_display(parsed_emp_avail_date))
    with col2_emp:
        value_display_cap = f"{emp_weekly_capacity_hours:.1f}" if isinstance(emp_weekly_capacity_hours, float) else str(emp_weekly_capacity_hours)
        st.metric(label="Weekly Capacity (Hours)", value=value_display_cap)
    with col3_emp:
        st.metric(label="Est. Completion by Employee", value=format_date_for_display(calculated_emp_end_date))
        
    # --- Assessment ---
    st.markdown("##### Assessment Summary")
    
    timeline_fit_label = "Timeline Fit Assessment"
    
    if "error" in status_message.lower():
        st.error(status_message)
        st.metric(label=timeline_fit_label, value="Error in calculation", delta_color="off")
    elif days_over_under > 0 : # Employee is late
        st.warning(status_message) # Use warning for 'may not complete' or 'over by'
        st.metric(label=timeline_fit_label, value=f"{days_over_under} days LATE", delta_color="normal") # 'normal' makes positive delta red if it's bad
    elif days_over_under <= 0 and "can complete" in status_message.lower(): # Employee is on time or early
        st.success(status_message)
        if days_over_under < 0:
             st.metric(label=timeline_fit_label, value=f"{abs(days_over_under)} days EARLY", delta_color="inverse") # 'inverse' makes negative delta green
        else: # days_over_under == 0
            st.metric(label=timeline_fit_label, value="ON TIME", delta_color="off") # 'off' is neutral
    else: # Neutral or other non-error/non-completion messages from scorer
        st.info(status_message)
        st.metric(label=timeline_fit_label, value="See message", delta_color="off")

    st.markdown("###### Original Calculation Details")
    st.text(original_detail_string if original_detail_string else "No raw detail string available.")

    st.markdown("---") # Adds a horizontal line for separation


def render_languages_comparison(project_value, employee_value, project_details, candidate_data, config_entry):
    label = config_entry.get('label', 'Languages')
    st.subheader(label)

    raw_project_langs = project_value if isinstance(project_value, dict) else {}
    raw_employee_langs = employee_value if isinstance(employee_value, dict) else {}

    PROFICIENCY_ORDER = {"native": 7, "c2": 6, "c1": 5, "b2": 4, "b1": 3, "a2": 2, "a1": 1, "": 0, "not specified": 0}
    # PROFICIENCY_DISPLAY_MAP = {v: k.upper() for k, v in PROFICIENCY_ORDER.items()} # Not directly used for display in table, levels are uppercased manually

    project_langs_parsed = {str(k).lower().strip(): {"original": str(k), "level_str": str(v).lower(), "level_val": PROFICIENCY_ORDER.get(str(v).lower(), 0)} 
                               for k, v in raw_project_langs.items() if isinstance(k, str) and isinstance(v, str)}

    employee_langs_parsed = {str(k).lower().strip(): {"original": str(k), "level_str": str(v).lower(), "level_val": PROFICIENCY_ORDER.get(str(v).lower(), 0)} 
                                for k, v in raw_employee_langs.items() if isinstance(k, str) and isinstance(v, str)}

    comparison_data = []
    processed_employee_langs = set()

    # Handle empty cases early
    if not project_langs_parsed and not employee_langs_parsed:
        st.caption("Language requirements and employee languages are both unspecified.")
        st.markdown("---")
        return
    if not project_langs_parsed:
        st.caption("No language requirements specified for this project.")
    if not employee_langs_parsed:
        st.caption("No languages listed for this employee.")
    
    # Process project requirements
    for p_lang_lower, p_data in project_langs_parsed.items():
        p_level_display = p_data["level_str"].upper() if p_data["level_str"] else "N/A"
        row = {
            "Project Language": p_data["original"],
            "Required Level": p_level_display,
            "Employee Language": "N/A",
            "Employee Level": "N/A",
            "Status": "❌ Language Missing"
        }
        best_match_score = 0
        matched_e_lang_lower = None
        matched_e_data = None

        for e_lang_lower, e_data_loop_var in employee_langs_parsed.items():
            current_match_score = fuzz.token_sort_ratio(p_lang_lower, e_lang_lower)
            if current_match_score > best_match_score and current_match_score >= 80: 
                best_match_score = current_match_score
                matched_e_lang_lower = e_lang_lower
                matched_e_data = e_data_loop_var
        
        if matched_e_data:
            row["Employee Language"] = matched_e_data["original"]
            e_level_display = matched_e_data["level_str"].upper() if matched_e_data["level_str"] else "N/A"
            row["Employee Level"] = e_level_display
            processed_employee_langs.add(matched_e_lang_lower)
            
            # Determine status based on proficiency levels
            if matched_e_data["level_val"] == 0 and p_data["level_val"] > 0 : # Employee level not specified, project requires one
                 row["Status"] = "❓ Proficiency Unspecified"
            elif matched_e_data["level_val"] >= p_data["level_val"]:
                row["Status"] = "✔️ Meets/Exceeds"
            else:
                row["Status"] = "⚠️ Below Proficiency"
        comparison_data.append(row)

    # Add any additional languages employee has that weren't matched to project requirements
    for e_lang_lower, e_data in employee_langs_parsed.items():
        if e_lang_lower not in processed_employee_langs:
            e_level_display = e_data["level_str"].upper() if e_data["level_str"] else "N/A"
            row = {
                "Project Language": "N/A",
                "Required Level": "N/A",
                "Employee Language": e_data["original"],
                "Employee Level": e_level_display,
                "Status": "✨ Additional Language"
            }
            comparison_data.append(row)

    if comparison_data:
        df = pd.DataFrame(comparison_data)
        df = df[["Project Language", "Required Level", "Employee Language", "Employee Level", "Status"]]
        
        def style_language_status(row):
            status = row.get('Status', '')
            style = [''] * len(row)
            if "✔️ Meets/Exceeds" in status:
                style = ['background-color: #dcedc8; color: #388e3c;'] * len(row)  # Green
            elif "⚠️ Below Proficiency" in status:
                style = ['background-color: #fff9c4; color: #f57f17;'] * len(row)  # Yellow/Orange
            elif "❌ Language Missing" in status:
                style = ['background-color: #ffcdd2; color: #c62828;'] * len(row)  # Red
            elif "✨ Additional Language" in status:
                style = ['background-color: #e3f2fd; color: #0d47a1;'] * len(row)  # Blue for info
            elif "❓ Proficiency Unspecified" in status:
                style = ['background-color: #f5f5f5; color: #757575;'] * len(row) # Grey for unspecified
            return style

        st.dataframe(df.style.apply(style_language_status, axis=1), use_container_width=True, hide_index=True)
        st.markdown("---") # End of the main comparison block
    elif project_langs_parsed and not employee_langs_parsed:
        # This case handles when there are project requirements but no employee languages listed (after initial captions)
        st.info("Employee has no listed languages to compare against project requirements.")
        st.markdown("---")
    # The final st.markdown("---") ensures separation before the next section regardless of which path was taken.
    # If the initial early return for 'both unspecified' happens, this final separator won't be hit, which is fine.
    # If only one is unspecified leading to a caption, and comparison_data is empty, this will add a separator.
    # This might be redundant if the st.caption already has a following st.markdown("---"), 
    # but it's harmless and ensures separation if st.dataframe wasn't called.
    # We can refine this if it causes double separators in some flows.
    # For now, ensuring the main flow for comparison_data has its own separator.
    # The line `st.markdown("---") # Corrected from ---SUMMARY---` seems like a leftover or a comment for a different section.
    # I will remove it if it's not part of the intended structure after this fix.
    # Let's assume the goal is one separator after this entire language comparison section.
    # Given the original code had st.markdown("---") after the df display, and an st.info part,
    # it seems the goal is to have a separator after the table OR after the st.info.
    # The very last st.markdown("---") from line 797 in view_line_range will be kept as the section ender.

# --- UI Enhancements: Score Display Configuration ---
SCORE_DISPLAY_NAMES = {
    "SkillMatchScore": "Skill Match",
    "AvailabilityScore": "Availability Match",
    "ProductScore": "Product Match",
    "IndustryScore": "Industry Vertical Match",
    "ExpertiseScore": "Expertise Area Match",
    "LanguageScore": "Language Proficiency Match",
    "CertificationScore": "Certification Match",
    "LocationScore": "Location & Flexibility Match",
    "CulturalAwarenessScore": "Cultural Awareness Rating",
    "ProblemSolvingScore": "Problem Solving Rating",
    "LeadershipScore": "Leadership Rating",
    # "YearsExperienceScore": "Years of Experience", # USER REQUEST: Optionally remove
    "RetrieverScore": "Retriever Relevance (Semantic)",
    # "ProjectComplexityScore": "Project Complexity Alignment" # USER REQUEST: Remove
}

SCORE_EXPLANATIONS = {
    "SkillMatchScore": "How well the employee's skills and proficiency levels match the project's skill requirements.",
    "AvailabilityScore": "Considers if the employee is available for the project's duration and can meet the required effort within their weekly capacity.",
    "ProductScore": "Measures the match between products/tools required by the project and those experienced by the employee.",
    "IndustryScore": "Reflects whether the employee has experience in the project's customer industry.",
    "ExpertiseScore": "Alignment of the employee's expertise areas with the project's integration requirements or specific expertise needs.",
    "LanguageScore": "Assesses if the employee meets the language proficiency levels required for the project.",
    "CertificationScore": "Checks if the employee possesses certifications preferred or required by the project.",
    "LocationScore": "Considers the match between project's work location/flexibility and the employee's preferences/location.",
    "CulturalAwarenessScore": "Employee's self-rated cultural awareness. Its impact on the overall score is determined by its weight.",
    "ProblemSolvingScore": "Employee's self-rated problem-solving ability. Its impact on the overall score is determined by its weight.",
    "LeadershipScore": "Employee's self-rated leadership skill. Its impact on the overall score is determined by its weight.",
    # "YearsExperienceScore": "Reflects the employee's years of professional experience, normalized. Its impact on the overall score is determined by its weight.", # USER REQUEST: Optionally remove
    "RetrieverScore": "Primary score for textual role fit. Based on semantic similarity (Chroma DB embeddings) between the project query and the employee's profile.",
    # "ProjectComplexityScore": "How well the employee's profile aligns with the project's complexity level (based on heuristics in the scoring logic)." # USER REQUEST: Remove
}

# Original line that was targeted for replacement was 'import streamlit as st',
# so we assume the next original line of the file would typically follow here.
# If 'import streamlit as st' was the very first line, this structure is correct.
import pandas as pd
import json
import os
import datetime
from retriever import initialize_retriever_system # Assuming EmployeeRetriever is part of this
from scorer import generate_detailed_scores_for_candidates
from config import (
    CHROMA_DB_PATH, CHROMA_COLLECTION_NAME, 
    EMBEDDING_MODEL_NAME, EMPLOYEE_DATA_PATH, 
    PROJECT_DATA_PATH, DEFAULT_TOP_N_CANDIDATES
)

# --- Page Configuration ---
st.set_page_config(
    page_title="HR Mate AI - Project Matching",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Load Custom CSS ---
# This function will load your custom CSS file
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"Custom CSS file '{file_name}' not found. Using default styles.")

# Attempt to load custom CSS - ensure 'assets/custom.css' path is correct
css_file_path = os.path.join(os.path.dirname(__file__), 'assets', 'custom.css')
local_css(css_file_path)

# --- Helper function for date formatting ---
def format_timestamp_to_date(timestamp_ms):
    if isinstance(timestamp_ms, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            return str(timestamp_ms) # Return as string if conversion fails
    return str(timestamp_ms) # Return as string if not a number

# --- Caching Data Loading and Initialization ---
@st.cache_resource # Cache the retriever system for performance
def load_retriever_system():
    print("Initializing retriever system for Streamlit app...")
    retriever = initialize_retriever_system(
        model_name_for_embedding=EMBEDDING_MODEL_NAME,
        chroma_db_path=CHROMA_DB_PATH,
        collection_name=CHROMA_COLLECTION_NAME,
        employee_data_path=EMPLOYEE_DATA_PATH,
        force_repopulate=False
    )
    print("Retriever system initialized.")
    return retriever

@st.cache_data # Cache data loading
def load_data(file_path):
    if not os.path.exists(file_path):
        st.error(f"Error: File not found at {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading data from {file_path}: {e}")
        return None

# --- Main Application Logic ---
from PIL import Image # Add import for Image

def get_score_badge_html(score_value, score_name, icon):
    color = "#757575"  # Default grey for undefined scores or issues
    if isinstance(score_value, (int, float)):
        if score_value >= 0.8:
            color = "#4CAF50"  # Green
        elif score_value >= 0.6:
            color = "#FFC107"  # Amber
        elif score_value >= 0.0:
            color = "#F44336"  # Red
    else:
        score_value = "N/A"

    badge_style = f"display: inline-block; padding: 0.3em 0.6em; font-size: 0.9em; font-weight: 600; line-height: 1; text-align: center; white-space: nowrap; vertical-align: baseline; border-radius: 0.25rem; color: white; background-color: {color}; margin-right: 5px;"
    score_display = f"{score_value:.2f}" if isinstance(score_value, float) else str(score_value)
    return f'<span style="{badge_style}">{icon} {score_name}: {score_display}</span>'

def run_app():
    # Display Canon logo
    try:
        logo = Image.open("media/logo.png")
        st.image(logo, width=150)  # Adjust width as needed
    except FileNotFoundError:
        st.warning("Logo file not found at media/logo.png. Please check the path.")
    except Exception as e:
        st.error(f"Error loading logo: {e}")

    # Initialize custom_weights in session state if it doesn't exist
    if 'custom_weights' not in st.session_state:
        st.session_state.custom_weights = SCORING_WEIGHTS.copy()

    st.title("HR Mate AI ✨ - Employee-Project Matching")
    st.markdown("### Find the best talent for your projects effortlessly.")

    # Load data and retriever
    projects_data = load_data(PROJECT_DATA_PATH)
    all_employees_list = load_data(EMPLOYEE_DATA_PATH)
    retriever_system = load_retriever_system()

    if not projects_data or not all_employees_list or not retriever_system:
        st.error("Failed to load essential data or initialize the matching system. Please check configurations and data files.")
        return

    all_employees_map = {emp['EmployeeID']: emp for emp in all_employees_list}

    # --- Project Selection in Main Area ---
    st.subheader("1. Select a Project")
    project_names = [p.get('ProjectName', f"Project ID: {p.get('ProjectID', 'Unknown')}") for p in projects_data]
    selected_project_name = st.selectbox("Choose a project to find matching employees for:", project_names, label_visibility="collapsed")
    
    selected_project = None
    for p in projects_data:
        if p.get('ProjectName', f"Project ID: {p.get('ProjectID', 'Unknown')}") == selected_project_name:
            selected_project = p
            break

    if not selected_project:
        st.error("Project data is available, but the selected project could not be found. This is unexpected.")
        return

    # --- Display Selected Project Details ---
    st.subheader(f"Project Details: {selected_project.get('ProjectName', selected_project.get('ProjectID'))}")
    
    # Using columns for better layout of project details
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Project ID:** {selected_project.get('ProjectID', 'N/A')}")
        st.markdown(f"**Customer Industry:** {selected_project.get('Customer Industry', 'N/A')}")
        st.markdown(f"**Work Location:** {selected_project.get('Work Location', 'N/A')}")
        st.markdown(f"**Work Flexibility:** {selected_project.get('Work Flexibility', 'N/A')}")
        st.markdown(f"**Complexity:** {selected_project.get('Complexity', 'N/A')}")
        
    with col2:
        requested_end_date = selected_project.get('Requested End Date') # Key from original capstone doc often has spaces
        if requested_end_date is None: # Try another common variation if first fails
            requested_end_date = selected_project.get('Requested End') 
        st.markdown(f"**Requested End Date:** {format_timestamp_to_date(requested_end_date) if requested_end_date else 'N/A'}")
        st.markdown(f"**Effort (hours):** {selected_project.get('Effort', 'N/A')}")
        if isinstance(selected_project.get('Languages Required'), dict):
            langs = ", ".join([f"{lang} ({level})" for lang, level in selected_project.get('Languages Required').items()])
            st.markdown(f"**Languages Required:** {langs if langs else 'N/A'}")
        else:
            st.markdown(f"**Languages Required:** {selected_project.get('Languages Required', 'N/A')}")

    with st.expander("View Full Project Summary and Scope", expanded=False):
        st.markdown("**Project Summary:**")
        st.markdown(selected_project.get('Project Summary', 'N/A'))
        st.markdown("**Scope and Deliverables:**")
        st.markdown(selected_project.get('Scope and Deliverables', 'N/A'))

    # Displaying Skills, Products, Certifications, Expertise using chips-like display (basic markdown for now)
    def display_list_as_chips(title, items_list_or_dict, is_dict_with_levels=False):
        if items_list_or_dict:
            chip_html = f"**{title}:** "
            if is_dict_with_levels and isinstance(items_list_or_dict, dict):
                chip_html += ", ".join([f"<span class='chip skill'>{str(skill)} (Lvl: {str(level)})</span>" for skill, level in items_list_or_dict.items()])
            elif isinstance(items_list_or_dict, list):
                chip_html += ", ".join([f"<span class='chip product'>{str(item)}</span>" for item in items_list_or_dict])
            elif isinstance(items_list_or_dict, dict): # Fallback for dicts not treated as skills with levels
                 chip_html += ", ".join([f"<span class='chip'>{str(key)}</span>" for key in items_list_or_dict.keys()])
            else:
                chip_html += "N/A"
            st.markdown(chip_html, unsafe_allow_html=True)
        else:
            st.markdown(f"**{title}:** N/A")

    display_list_as_chips("Required Skills and Expertise", selected_project.get('Required Skills and Expertise'), is_dict_with_levels=True)
    display_list_as_chips("Products Involved", selected_project.get('Products Involved'))
    display_list_as_chips("Customer Preferences (Certifications)", selected_project.get('Customer Preferences (Certifications)'))
    display_list_as_chips("Integration Requirements (Expertise Areas)", selected_project.get('Integration Requirements (Expertise Areas)'))
    
    st.markdown("___") # Divider

    # --- Controls remain in Sidebar (for now) ---
    st.sidebar.header("Match Controls")
    num_candidates = st.sidebar.number_input(
        "Number of Top Employees to Find:", 
        min_value=1, 
        max_value=50, 
        value=DEFAULT_TOP_N_CANDIDATES, 
        step=1
    )

    availability_filter_options = {
        "Fully Available (Score = 1.0)": "1.0",
        "Good Availability (0.5 < Score < 1.0)": "0.75",
        "Limited Availability (0.0 < Score <= 0.5)": "0.25",
        "Not Available (Score = 0.0)": "0.0"
    }
    selected_availability_keys = st.sidebar.multiselect(
        "Filter by Availability Score:", 
        options=list(availability_filter_options.keys()),
        help="Select one or more availability score buckets to filter candidates."
    )

    if st.sidebar.button("Find Matching Employees", type="primary"):
        project_query = selected_project.get('Project Summary', '') + " - " + selected_project.get('Scope and Deliverables', '')
        
        with st.spinner(f"Searching for top {num_candidates} employees for '{selected_project_name}'..."):
            retrieved_candidate_info = retriever_system.retrieve_top_n_employees(project_query, top_n=num_candidates)
            # st.json({"DEBUG_STREAMLIT_RETRIEVED_CANDIDATE_INFO": retrieved_candidate_info}) # DEBUG OUTPUT REMOVED
            
            if not retrieved_candidate_info:
                st.warning("No candidates found for this project query.")
                return

            candidate_employees_for_scoring = []
            if retrieved_candidate_info: # Ensure it's not empty before iterating
                for cand_info in retrieved_candidate_info:
                    # Ensure 'employee' key exists and has 'EmployeeID'
                    employee_details_from_retriever = cand_info.get('employee')
                    if not employee_details_from_retriever:
                        st.warning(f"Retriever returned an item without 'employee' details: {cand_info}")
                        continue # Skip this problematic item
                    
                    emp_id = employee_details_from_retriever.get('EmployeeID')
                    if emp_id and emp_id in all_employees_map:
                        employee_record = all_employees_map[emp_id].copy() # Important: Work on a copy
                        
                        # Extract similarity_score from retriever output and add it as document_score
                        similarity = cand_info.get('similarity_score', 0.0)
                        employee_record['document_score'] = similarity
                        
                        candidate_employees_for_scoring.append(employee_record)
                    else:
                        if not emp_id:
                            st.warning(f"Retriever returned an item with 'employee' details but no 'EmployeeID': {employee_details_from_retriever}")
                        else: # emp_id was present but not in all_employees_map
                            st.warning(f"Could not find full details in all_employees_map for EmployeeID: {emp_id} (from retriever output). Anomalous data?")
            
            if not candidate_employees_for_scoring:
                st.error("No valid candidate details found for scoring.")
                return

            # Score candidates
            detailed_scores_data = generate_detailed_scores_for_candidates(
                selected_project, 
                candidate_employees_for_scoring,
                custom_weights=st.session_state.custom_weights # Pass the dynamic weights
            )

            # Sort candidates by OverallWeightedScore (descending)
            sorted_candidates = sorted(detailed_scores_data, key=lambda x: x.get('OverallWeightedScore', 0), reverse=True)
            
            st.session_state['sorted_candidates'] = sorted_candidates
            st.session_state['selected_project_for_results'] = selected_project

    # --- Scoring Weights Adjustment Panel ---
    with st.sidebar.expander("⚙️ Adjust Scoring Weights", expanded=False):
        for weight_key, weight_value in st.session_state.custom_weights.items():
            display_name = SCORE_DISPLAY_NAMES.get(weight_key, weight_key.replace("Score", " Score"))
            new_weight = st.slider(
                display_name,
                min_value=0.0,
                max_value=1.0,
                value=float(weight_value), # Ensure value is float for slider
                step=0.01,
                key=f"weight_{weight_key}"
            )
            st.session_state.custom_weights[weight_key] = new_weight
        
        # Optional: Display sum of weights to help user balance them, though normalization handles it.
        current_total_weight = sum(st.session_state.custom_weights.values())
        st.sidebar.caption(f"Sum of current weights: {current_total_weight:.2f}")
        if not (0.99 <= current_total_weight <= 1.01) and current_total_weight > 0:
             st.sidebar.warning("Weights ideally sum to 1.0 for direct interpretation, but scores are normalized.")

    # --- Display Results --- 
    if 'sorted_candidates' in st.session_state and 'selected_project_for_results' in st.session_state:
        # Apply Availability Filter if any selected
        candidates_to_display = st.session_state['sorted_candidates']
        if selected_availability_keys:
            filtered_candidates = []
            for cand_score_info in st.session_state['sorted_candidates']:
                avail_score = cand_score_info.get('Scores', {}).get('AvailabilityScore', -1) # Default to -1 if not found
                
                matched_filter = False
                for key in selected_availability_keys:
                    filter_type = availability_filter_options[key]
                    if filter_type == "1.0" and avail_score == 1.0:
                        matched_filter = True
                        break
                    elif filter_type == "0.75" and 0.5 < avail_score < 1.0:
                        matched_filter = True
                        break
                    elif filter_type == "0.25" and 0.0 < avail_score <= 0.5:
                        matched_filter = True
                        break
                    elif filter_type == "0.0" and avail_score == 0.0:
                        matched_filter = True
                        break
                if matched_filter:
                    filtered_candidates.append(cand_score_info)
            candidates_to_display = filtered_candidates

        st.subheader(f"Top Matching Employees for: {st.session_state['selected_project_for_results'].get('ProjectName', st.session_state['selected_project_for_results'].get('ProjectID'))}")

        # --- Sorting Options for Displayed Candidates ---
        sort_options = ["Overall Match (Default)", "Availability (Highest First)"]
        selected_sort_option = st.selectbox(
            "Sort displayed results by:", 
            options=sort_options,
            index=0, # Default to 'Overall Match'
            key='candidate_sort_option'
        )

        # Apply sorting based on selection
        if selected_sort_option == "Availability (Highest First)":
            candidates_to_display = sorted(
                candidates_to_display, 
                key=lambda x: x.get('Scores', {}).get('AvailabilityScore', 0), 
                reverse=True
            )
        # Else, it remains sorted by OverallWeightedScore (its original state or if filtered, it preserved relative order)
        # If it was filtered and we want to re-sort by OverallWeightedScore explicitly:
        elif selected_sort_option == "Overall Match (Default)" and selected_availability_keys: # only re-sort if filters were applied
             candidates_to_display = sorted(
                candidates_to_display, 
                key=lambda x: x.get('OverallWeightedScore', 0), 
                reverse=True
            )

        
        # Enhanced display for matched employees
        if not candidates_to_display:
            st.info("No candidates match the selected availability criteria.")
        for rank, emp_score_info in enumerate(candidates_to_display, 1):
            employee_id = emp_score_info.get('EmployeeID')
            candidate_data = all_employees_map.get(employee_id)
            
            if candidate_data:
                employee_name = candidate_data.get('Full Name', f"Employee ID: {employee_id}")
                overall_score = emp_score_info.get('OverallWeightedScore', 0)
                # Ensure OverallWeightedScore from scorer is consistently scaled (e.g. 0-100 or 0-1)
                # For display, if it's 0-1, multiply by 100 for percentage or show as decimal.
                # Current scorer.py seems to produce scores that can be > 1, so direct .2f is better.
                # Generate score badges HTML for the title
                overall_badge_html = get_score_badge_html(overall_score, "Overall", "🎯")
                avail_score_val = emp_score_info.get('Scores', {}).get('AvailabilityScore', 0.0)
                avail_badge_html = get_score_badge_html(avail_score_val, "Avail.", "⏱️")
                
                expander_title_html = f"Rank {rank}: {employee_name} &nbsp; {overall_badge_html} {avail_badge_html}"

                # Render the custom HTML title using st.markdown
                st.markdown(expander_title_html, unsafe_allow_html=True)
                
                # Use a minimal label for the expander itself
                with st.expander("Details", expanded=(rank==1)):
                    # Scores are now in the st.markdown title above.
                    # The <hr> divider might still be useful to separate title from content if we re-add it.
                    # For now, let's see how it looks without it.

                    # Define data needed across columns first
                    individual_scores_dict = emp_score_info.get('Scores', {})
                    project_details = st.session_state['selected_project_for_results']

                    col1, col2 = st.columns([0.55, 0.45]) # Main layout: Left for profile & radar, Right for details

                    with col1: # Left Column: Profile Summary + Radar Chart
                        # Name is now in expander title, scores are displayed as badges above.
                        st.caption(f"Employee ID: {employee_id} | Current Role: {candidate_data.get('Role Name', 'N/A')}")
                        # The st.markdown("---_score_divider---") above handles separation now.

                        # Key Profile Information
                        st.markdown("**Key Information:**")
                        availability_date = candidate_data.get('Available From')
                        availability_date_formatted = format_timestamp_to_date(availability_date) if availability_date else 'N/A'
                        st.markdown(f"- **Available From:** {availability_date_formatted}")
                        st.markdown(f"- **Work Location:** {candidate_data.get('Work Location', 'N/A')}")
                        if 'Role Description' in candidate_data:
                            with st.popover("View Full Role Description"):
                                st.markdown(candidate_data['Role Description'])
                        st.markdown("<br>", unsafe_allow_html=True)

                        # Chips for Skills, Products, Certifications (using existing HTML chip style for now)
                        employee_skills = candidate_data.get('Core Competencies')
                        if isinstance(employee_skills, dict) and employee_skills:
                            skills_html = "**Core Competencies:** " + ", ".join([f"<span class='chip skill'>{str(skill)} (Lvl: {str(level)})</span>" for skill, level in employee_skills.items()])
                            st.markdown(skills_html, unsafe_allow_html=True)
                        elif isinstance(employee_skills, list) and employee_skills:
                            skills_html = "**Core Competencies:** " + ", ".join([f"<span class='chip skill'>{str(skill)}</span>" for skill in employee_skills])
                            st.markdown(skills_html, unsafe_allow_html=True)
                        else:
                            st.markdown("**Core Competencies:** N/A")

                        employee_products = candidate_data.get('Products Experience')
                        if employee_products and isinstance(employee_products, list):
                            products_html = "**Products Experience:** " + ", ".join([f"<span class='chip product'>{str(prod)}</span>" for prod in employee_products])
                            st.markdown(products_html, unsafe_allow_html=True)
                        else:
                            st.markdown("**Products Experience:** N/A")
                        
                        employee_certs = candidate_data.get('External/Internal Certifications')
                        if employee_certs and isinstance(employee_certs, list):
                            certs_html = "**Certifications:** " + ", ".join([f"<span class='chip'>{str(cert)}</span>" for cert in employee_certs])
                            st.markdown(certs_html, unsafe_allow_html=True)
                        else:
                            st.markdown("**Certifications:** N/A")
                        st.markdown("---")

                        # Radar Chart
                        st.markdown("##### Score Profile")
                        radar_fig = create_radar_chart(individual_scores_dict, SCORE_DISPLAY_NAMES, SCORING_WEIGHTS)
                        if radar_fig:
                            st.plotly_chart(radar_fig, use_container_width=True, key=f"radar_chart_main_{employee_id}")
                        else:
                            st.caption("Not enough score data to display radar chart.")

                with col2: # Right Column: Tabs for Detailed Breakdowns
                    st.subheader("Detailed Assessment")
                    attr_tab, scores_tab, raw_data_tab = st.tabs(["🔍 Attribute Comparison", "📊 Detailed Scores", "📄 Raw Data"])

                    with attr_tab:
                        st.markdown("This section provides a detailed comparison of project requirements against the employee's attributes.")
                        st.markdown("---")
                        if not project_details or not candidate_data:
                            st.warning("Project or candidate data is missing. Cannot display attribute comparisons.")
                        else:
                            for config_entry in ATTRIBUTE_COMPARISON_CONFIG:
                                label = config_entry["label"]
                                render_function_name = config_entry.get("render_function_name")
                                render_function = globals().get(render_function_name)
                                if render_function:
                                    project_value = None
                                    employee_value = None
                                    project_data_key = config_entry.get("project_key")
                                    if project_data_key:
                                        project_value = project_details.get(project_data_key)
                                    employee_data_key = config_entry.get("employee_key")
                                    if employee_data_key:
                                        employee_value = candidate_data.get(employee_data_key)
                                    try:
                                        score_key = config_entry.get("score_key")
                                        if score_key == "AvailabilityScore" and "Details" in emp_score_info and "AvailabilityScore" in emp_score_info["Details"]:
                                            employee_value = emp_score_info["Details"]["AvailabilityScore"]
                                        render_function(
                                            project_value=project_value, 
                                            employee_value=employee_value,
                                            project_details=project_details, 
                                            candidate_data=candidate_data,
                                            config_entry=config_entry
                                        )
                                    except Exception as e:
                                        st.error(f"Error rendering '{label}': {e}")
                                else:
                                    st.warning(f"Render function '{render_function_name}' for '{label}' not found.")
                    
                    with scores_tab:
                        st.markdown("##### Detailed Score Breakdown")
                        st.caption("Review the individual components contributing to the overall match score. Each score is weighted to reflect its importance.")
                        st.markdown("---")
                        score_detail_cols = st.columns(2)
                        score_keys_ordered = list(SCORE_DISPLAY_NAMES.keys()) # Ensure consistent order if needed

                        for i, score_key in enumerate(score_keys_ordered):
                            display_name = SCORE_DISPLAY_NAMES[score_key]
                            raw_score_value = individual_scores_dict.get(score_key, 0.0)
                            # Special handling for RetrieverScore if its primary key isn't found
                            if score_key == "RetrieverScore" and score_key not in individual_scores_dict:
                                raw_score_value = individual_scores_dict.get('document_score', 0.0) # Assuming 'document_score' is the alternative
                            
                            explanation = SCORE_EXPLANATIONS.get(score_key, "No explanation available.")
                            weight = SCORING_WEIGHTS.get(score_key, 0.0) # Ensure weight is float for consistent formatting
                            
                            current_col = score_detail_cols[i % 2]
                            
                            current_col.markdown(f"**{display_name}**")
                            current_col.metric(label="Match Score", value=f"{float(raw_score_value):.2f}", delta=f"Weight: {weight:.2f}", delta_color="off")
                            current_col.caption(explanation)
                            if i < len(score_keys_ordered) - 2: # Add separator if not one of the last two items (one for each col)
                               current_col.markdown("---")

                    with raw_data_tab:
                        st.caption("Raw score and details JSON for this candidate.")
                        display_scores = emp_score_info.get('Details', emp_score_info)
                        st.json(display_scores)

            else:
                st.warning(f"Could not retrieve full data for Employee ID: {employee_id}. Scores: {emp_score_info.get('OverallWeightedScore', 0):.2f}")
            st.markdown("---") # Divider after each employee expander

if __name__ == "__main__":
    run_app()
