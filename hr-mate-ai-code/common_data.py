import random

# --- Define Employee Roles with Themes (Templates for Role Name and Theme) ---
employee_roles = [
    {"Role Name": "Solution Architect", "Role Description": "Designs high-level technical solutions for enterprise customers.", "Theme": "Technical"},
    {"Role Name": "Sales Account Manager", "Role Description": "Manages customer accounts and drives sales processes.", "Theme": "Sales"},
    {"Role Name": "Digital Marketing Specialist", "Role Description": "Executes online campaigns, SEO, and branding strategies.", "Theme": "Marketing"},
    {"Role Name": "Senior HR Manager", "Role Description": "Manages HR operations and employee relations.", "Theme": "HR"},
    {"Role Name": "Legal Counsel", "Role Description": "Provides legal support for contracts and compliance.", "Theme": "Legal"},
    {"Role Name": "IT Systems Engineer", "Role Description": "Maintains and optimizes internal IT infrastructure.", "Theme": "Technical"},
    {"Role Name": "Workflow Consultant", "Role Description": "Analyzes business processes and recommends workflow improvements.", "Theme": "Consulting"},
    {"Role Name": "Project Manager", "Role Description": "Oversees project delivery and coordinates cross-functional teams.", "Theme": "Consulting"},
    {"Role Name": "Data Analyst", "Role Description": "Analyzes data and delivers business insights.", "Theme": "Technical"},
    {"Role Name": "Customer Success Manager", "Role Description": "Supports post-sales success and client satisfaction.", "Theme": "Sales"},
    {"Role Name": "Field Support Engineer", "Role Description": "Provides onsite technical support for Canon products.", "Theme": "Technical"},
    {"Role Name": "Pre-Sales Engineer", "Role Description": "Prepares technical demos and solution proposals for prospects.", "Theme": "Sales"},
    {"Role Name": "Compliance Manager", "Role Description": "Ensures adherence to regulations and company standards.", "Theme": "Legal"},
    {"Role Name": "HR Business Partner", "Role Description": "Collaborates with leadership to align HR strategy.", "Theme": "HR"},
    {"Role Name": "Corporate Trainer", "Role Description": "Designs and delivers employee training programs.", "Theme": "HR"},
    {"Role Name": "Technical Support Specialist", "Role Description": "Resolves technical issues reported by customers.", "Theme": "Technical"},
    {"Role Name": "Content Creator", "Role Description": "Develops written, video, and visual content for marketing.", "Theme": "Marketing"},
    {"Role Name": "Solutions Support Consultant", "Role Description": "Provides technical guidance and second-line support for Canon solutions during and after customer deployment.", "Theme": "Technical"},
    {"Role Name": "Integration Developer", "Role Description": "Develops integrations between Canon products and third-party systems.", "Theme": "Technical"},
    {"Role Name": "Strategy Consultant", "Role Description": "Advises leadership on business growth and optimization strategies.", "Theme": "Consulting"},
]

# --- Define Project Summaries with Themes (Templates for Theme, and context for Gemini) ---
project_summary_templates = [
    {"Project Summary": "Implement scalable workflow automation system", "Scope and Deliverables": "Deploy Workflow2000, integrate with client systems", "Theme": "Technical"},
    {"Project Summary": "CRM integration for loyalty program", "Scope and Deliverables": "Customize CRM modules and train sales team", "Theme": "Sales"},
    {"Project Summary": "Launch digital marketing portal", "Scope and Deliverables": "Create website, SEO, lead funnels", "Theme": "Marketing"},
    {"Project Summary": "HR digital onboarding system", "Scope and Deliverables": "Implement HRIS system, self-service portals", "Theme": "HR"},
    {"Project Summary": "Contract management system deployment", "Scope and Deliverables": "Deploy document archiving and e-signature workflows", "Theme": "Legal"},
    {"Project Summary": "Upgrade internal IT infrastructure", "Scope and Deliverables": "Replace old servers, migrate systems to cloud", "Theme": "Technical"},
    {"Project Summary": "Business workflow audit", "Scope and Deliverables": "Map processes and suggest automation improvements", "Theme": "Consulting"},
    {"Project Summary": "Manage ERP migration project", "Scope and Deliverables": "Deliver milestones for new ERP roll-out", "Theme": "Consulting"},
    {"Project Summary": "Data warehouse design", "Scope and Deliverables": "Create new analytics-ready database", "Theme": "Technical"},
    {"Project Summary": "Post-sale onboarding program", "Scope and Deliverables": "Develop client onboarding workflow", "Theme": "Sales"},
    {"Project Summary": "Onsite print solutions setup", "Scope and Deliverables": "Install Print2.0 platform for retail client", "Theme": "Technical"},
    {"Project Summary": "Pre-sales technical proof-of-concept setup", "Scope and Deliverables": "Build demo environments for prospects", "Theme": "Sales"},
    {"Project Summary": "Regulatory compliance documentation project", "Scope and Deliverables": "Standardize processes, deliver compliance documentation", "Theme": "Legal"},
    {"Project Summary": "Organizational culture development initiative", "Scope and Deliverables": "Conduct workshops, employee surveys", "Theme": "HR"},
    {"Project Summary": "Employee training", "Scope and Deliverables": "Give overview on Learning Management System (LMS)", "Theme": "HR"},
    {"Project Summary": "Customer remote support setup", "Scope and Deliverables": "Setup online ticketing and remote assistance systems", "Theme": "Technical"},
    {"Project Summary": "Content library migration", "Scope and Deliverables": "Migrate marketing content to new CMS", "Theme": "Marketing"},
    {"Project Summary": "Quality assurance framework rollout", "Scope and Deliverables": "Implement QA policies across departments", "Theme": "Technical"},
    {"Project Summary": "API and system integration project", "Scope and Deliverables": "Develop middleware for integration of ERP/CRM", "Theme": "Technical"},
    {"Project Summary": "Business strategy development program", "Scope and Deliverables": "Assist C-suite with market expansion strategy", "Theme": "Consulting"},
]

# Controlled Product Pools per Theme
product_pools = {
    "Technical": ["Workflow2000", "Print2.0", "AIScan", "CloudSuite", "IntegrationHub"],
    "Sales": ["CRM Pro", "Sales Enablement Suite", "Loyalty CRM", "SalesForce Light"],
    "Marketing": ["Digital Campaign Manager", "SEO Toolkit", "Content CMS", "Social Media Manager"],
    "HR": ["HRIS Plus", "Onboarding Suite", "Employee Experience Platform"],
    "Legal": ["Compliance Suite", "Contract Manager Pro", "Regulatory Tracker"],
    "Consulting": ["ERP Migration Tool", "Business Analysis Framework", "Strategy Kit"]
}

# Controlled Skill Pools per Theme
skill_pools = {
    "Technical": ["Data Analysis", "Workflow Automation", "Cloud Services", "IT Infrastructure", "API Development"],
    "Sales": ["CRM Integration", "Negotiation", "Client Management", "Customer Relationship Management"],
    "Marketing": ["SEO Optimization", "Content Strategy", "Campaign Management", "Copywriting", "Branding"],
    "HR": ["Digital HR", "Organizational Development", "Talent Management", "Communication Skills"],
    "Legal": ["Contract Management", "Regulatory Knowledge", "Document Review", "Compliance Documentation"],
    "Consulting": ["Business Analysis", "Strategic Planning", "Workflow Optimization", "Project Management", "Change Management"]
}

# Controlled Certifications Pool per Theme
certification_pools = {
    "Technical": ["ITIL", "ISO 27001", "Microsoft Azure Certification"],
    "Sales": ["Certified Sales Professional (CSP)", "CRM Specialist Certification"],
    "Marketing": ["Digital Marketing Certification", "Google Ads Certification", "HubSpot Marketing Certification"],
    "HR": ["PMP", "SHRM-CP", "HR Analytics Certification"],
    "Legal": ["Certified Compliance Officer", "GDPR Certification", "Contract Law Certification"],
    "Consulting": ["PMP", "Six Sigma", "Agile Practitioner", "Business Analysis Certification"]
}

# Controlled Expertise Areas Pool per Theme
expertise_pools = {
    "Technical": ["Scripting", "API Integration", "Cloud Infrastructure", "Networking", "Cybersecurity"],
    "Sales": ["CRM Integration", "Sales Pipeline Automation", "Client Relationship Systems"],
    "Marketing": ["SEO Optimization", "Content Management Systems", "Social Media Integration"],
    "HR": ["HRIS Systems", "Employee Experience Platforms", "Organizational Development Systems"],
    "Legal": ["Document Archiving", "Contract Management Systems", "Regulatory Compliance Tools"],
    "Consulting": ["Strategic Planning", "Business Workflow Optimization", "ERP Systems Integration"]
}

# Predefined vocabularies
locations_master = ["Berlin", "Vienna", "London"]
work_flexibility_options = ["onsite", "remote", "hybrid"]
languages_master = ["English", "French", "German", "Italian"]
fluency_levels = ["A1", "A2", "B1", "B2", "C1", "C2"]
industries_master = ["Healthcare", "Education", "Finance", "Manufacturing", "Retail"]

# --- Typo Function ---
def introduce_typo(text):
    if len(text) < 4:
        return text
    idx = random.randint(0, len(text) - 2)
    return text[:idx] + text[idx+1] + text[idx] + text[idx+2:]
