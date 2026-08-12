---
# ==============================================================================
# FLOWJOB MASTER RESUME SCHEMA
# ==============================================================================
# This is the single source of truth for your professional history.
# The Tailor agent will parse this file and extract only the relevant pieces
# to generate a targeted CV for each job application.
# ==============================================================================

# 1. PERSONAL DETAILS
name: "Jane Doe"
title: "Senior Full Stack Engineer"
email: "jane.doe@example.com"
phone: "+1 555-010-2020"
location: "San Francisco, CA"

# 2. LINKS
links:
  - name: "LinkedIn"
    url: "https://linkedin.com/in/janedoe"
  - name: "GitHub"
    url: "https://github.com/janedoe"
  - name: "Portfolio"
    url: "https://janedoe.dev"

# 3. SKILLS TAXONOMY
# Group skills logically so the Analyst agent can easily compute fit scores.
skills:
  languages: ["Python", "TypeScript", "Go", "SQL", "HTML/CSS"]
  frameworks: ["React", "FastAPI", "Next.js", "Django", "Node.js"]
  tools: ["Docker", "Kubernetes", "AWS", "GCP", "Git", "Playwright"]
  databases: ["PostgreSQL", "MongoDB", "Redis", "Elasticsearch"]
  concepts: ["Microservices", "System Design", "CI/CD", "Agile", "TDD"]

# 4. PREFERENCES & TARGET ROLES
# This helps the Analyst agent filter out jobs that don't match your goals.
preferences:
  target_roles: ["Senior Software Engineer", "Full Stack Engineer", "Backend Engineer"]
  avoid_roles: ["Frontend Developer", "DevOps Engineer"]
  work_types: ["Remote", "Hybrid"]
  min_salary_usd: null # Optional, set to null if not applicable

# 5. PERSONAL NUDGE / TONE (For AI Summary Generation)
# The Tailor agent will write a custom 2-3 sentence summary for each JD.
# Use this section to guide its tone and give it personal flavor to inject.
personal_nudge:
  tone: "Professional but punchy, results-oriented, slightly conversational."
  key_themes: ["Building systems from 0 to 1", "Mentoring junior devs", "Shipping fast"]
  personal_flavor: "I love mentioning that I brew my own coffee and obsess over clean code."

# 5. EDUCATION
education:
  - institution: "University of Technology"
    degree: "B.S. Computer Science"
    location: "Seattle, WA"
    start_date: "2015-09"
    end_date: "2019-05"
    gpa: "3.8/4.0" # Optional

---

# ==============================================================================
# EXPERIENCE NARRATIVES
# ==============================================================================
# Format:
# ## [Company] | [Role] | [Location] | [Start Date] - [End Date]
# 
# ### Context
# (Optional) A brief paragraph about the company/team to provide context.
#
# ### Achievements
# Write exhaustive bullet points here. Write EVERY achievement, even if it makes
# the resume 10 pages long. The Tailor agent will select the top 3-5 most 
# relevant bullets for each specific JD.
# 
# Tagging (Optional):
# You can append tags like [leadership], [scale], [python] to bullets to help 
# the Tailor agent pick the right ones.
# ==============================================================================

## TechCorp Inc. | Senior Backend Engineer | Remote | 2021-06 - Present

### Context
TechCorp is a high-growth fintech startup. I joined as an early engineer and helped scale the core transaction engine.

### Achievements
- Architected and deployed a new microservices-based transaction processing engine using Go and Kubernetes, increasing system throughput by 300% and reducing latency by 45%. [architecture, scale, go, kubernetes]
- Led the migration of a legacy monolithic PostgreSQL database to a sharded architecture, achieving zero downtime during the cutover and supporting a 5x increase in daily active users. [database, postgres, leadership]
- Mentored a team of 4 junior engineers, establishing code review standards and introducing TDD practices that reduced production bugs by 30%. [leadership, mentoring, tdd]
- Designed and implemented a robust API rate-limiting service using Redis, preventing abuse and ensuring platform stability during peak traffic events. [redis, api, backend]
- Integrated third-party payment gateways (Stripe, Plaid), writing robust error handling and retry mechanisms for network failures. [integrations, payments]


## StartupX | Full Stack Engineer | San Francisco, CA | 2019-07 - 2021-05

### Context
A B2B SaaS platform for inventory management.

### Achievements
- Developed the core frontend dashboard using React and Redux, translating complex Figma designs into responsive, accessible components. [frontend, react, ui]
- Built RESTful APIs using Python and Django to support new inventory forecasting features, integrating with a machine learning backend. [python, django, backend]
- Optimized slow SQL queries and added caching layers, reducing page load times for the main dashboard from 4.2s to 0.8s. [performance, sql]
- Implemented a comprehensive automated testing suite using Cypress (E2E) and Jest (unit), achieving 85% code coverage. [testing, cypress, jest]


# ==============================================================================
# PROJECTS
# ==============================================================================
# Format:
# ## [Project Name] | [Role] | [Dates] | [Link]
# ==============================================================================

## FlowJob | Creator & Lead Maintainer | 2026 - Present | https://github.com/iaminfadel/flowjob
- Designed and built an open-source, multi-agent AI pipeline for automated job applications using the Google Antigravity SDK. [ai, python, agents]
- Implemented robust browser automation with Playwright to navigate LinkedIn's Easy Apply flow while bypassing bot detection. [automation, playwright]
- Engineered a feedback loop between a CV Generation agent and an ATS-Checking agent to iteratively optimize resumes for AI screeners. [prompt-engineering, ats]
