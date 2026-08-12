# Research: ATS Scoring Methods & AI Resume Screening Approaches

> Resolves [#5](https://github.com/iaminfadel/flowjob/issues/5)

## Sources

- Web research on ATS algorithms and AI resume screening (2024–2026)
- Industry analysis from apply-mate.com, getaligncv.com, dover.com, resumeadapter.com

## How Modern ATS Systems Work (2025–2026)

### The Pipeline

1. **Parsing** — resume is ingested and converted to structured data (name, contact, work history, skills, education). Poor formatting breaks the parser.
2. **Keyword extraction** — JD is parsed for required skills, qualifications, and terms.
3. **Matching** — resume fields are compared against JD requirements.
4. **Scoring/Ranking** — candidates are scored and ranked on a dashboard for recruiters.

### Evolution: From Keyword Matching to Semantic AI

| Era | Method | What it does |
|-----|--------|-------------|
| Pre-2020 | **Exact keyword match** | Counts occurrences of JD keywords in resume. "Project Lead" ≠ "Project Manager". |
| 2020–2024 | **NLP-based matching** | Uses embeddings/vectors to understand semantic similarity. Recognizes synonyms. |
| 2024+ | **LLM-powered screening** | Companies use GPT/Claude/Gemini to evaluate resumes holistically — context, achievements, fit. |

**Key insight**: Modern AI screeners look for **context and impact**, not just keyword presence. "Managed a team of 8 engineers delivering a $2M project on time" scores higher than "team management, project management, leadership" listed as bullet points.

## What ATS Systems Check

### 1. Format Compliance (Binary — pass/fail per element)

| Rule | Why |
|------|-----|
| Standard section headings ("Work Experience" not "Where I've Worked") | Parsers map content by heading recognition |
| Single-column layout | Multi-column confuses reading order |
| No tables/text boxes | Parser skips or garbles table content |
| No images/icons for text content | OCR is unreliable; text-based content only |
| No headers/footers for critical info | Many parsers ignore page headers/footers |
| Standard file format (PDF with text layer, or DOCX) | Image-based PDFs are unparseable |
| Standard fonts | Exotic fonts may not render in the parser |

### 2. Keyword Matching (Scored)

| Dimension | Method |
|-----------|--------|
| **Hard skills** | Exact or near-exact match against JD terms (e.g., "Python", "React", "AWS") |
| **Soft skills** | Semantic match (e.g., "stakeholder management" ≈ "cross-functional collaboration") |
| **Job titles** | Match against JD title and related titles |
| **Tools & technologies** | Exact match (case-insensitive) |
| **Certifications** | Exact match against mentioned certifications |
| **Education** | Degree level, field, institution matching |

### 3. AI/LLM Screening (Holistic — new in 2024+)

Modern AI screeners evaluate:
- **Relevance of experience** — does the candidate's trajectory align with the role?
- **Quantified achievements** — numbers and metrics signal real impact
- **Career progression** — promotions and increasing responsibility
- **Skill depth vs. breadth** — expertise in required areas, not just a keyword list
- **Writing quality** — clear, professional language signals competence
- **Red flags** — gaps, inconsistencies, overused buzzwords, keyword stuffing

## Scoring Model for FlowJob's Checker Agent

### Proposed Three-Layer Score

```
ATS Score = weighted_avg(keyword_score, format_score, ai_recruiter_score)

keyword_score (0-100):
  - Extract keywords from JD (skills, tools, qualifications)
  - Count matches in tailored CV
  - Weight by importance (required > preferred > nice-to-have)
  - Penalize keyword stuffing (repeated keywords without context)
  
format_score (0-100):
  - Check: standard section headings present? ✓/✗
  - Check: single-column layout? ✓/✗
  - Check: no tables/images? ✓/✗
  - Check: standard fonts? ✓/✗
  - Check: text is selectable (not image-based)? ✓/✗
  - Check: consistent date formatting? ✓/✗
  - Check: contact info at top? ✓/✗
  
ai_recruiter_score (0-100):
  - Prompt an LLM to role-play as a senior recruiter/AI screener
  - Feed it the JD + tailored CV
  - Ask: "Score this resume 0-100 for this role. Explain your reasoning."
  - The LLM evaluates holistically: relevance, impact, fit, red flags
```

### Threshold

- **Pass**: overall score ≥ 80 (configurable in YAML)
- **Iterate**: if score < 80, the Checker returns feedback to the Tailor with specific improvement suggestions
- **Max iterations**: 3 (configurable)
- **Bail**: if still < 80 after max iterations, log as "low confidence" and apply anyway (since rate limiting is the only safety rail)

## Adversarial Testing Approach

The Checker agent's "AI Recruiter Simulator" should use a prompt like:

```
You are a senior technical recruiter screening resumes for the following role:

[JD TEXT]

Evaluate this resume:

[TAILORED CV TEXT]

Score the resume 0-100 based on:
1. Keyword relevance (do the skills match?)
2. Experience relevance (is their background a fit?)
3. Impact & achievements (do they show measurable results?)
4. Professionalism (is it well-written and formatted?)
5. Red flags (gaps, keyword stuffing, vague claims)

Return:
- score: int (0-100)
- strengths: list of what works
- weaknesses: list of what's missing or weak
- suggestions: specific improvements to make
- verdict: "PASS" or "REVISE"
```

## Known Pitfalls to Avoid

1. **Keyword stuffing** — AI screeners detect and penalize cramming keywords without context. The Tailor must weave keywords into achievement descriptions naturally.
2. **White text tricks** — some people hide keywords in white text. Modern ATS/AI detects this. Never do it.
3. **Generic summaries** — "Results-driven professional with 5+ years experience" reads as template filler. Tailored summaries must be specific to the role.
4. **Inconsistent dates** — mixing date formats (Jan 2024, 01/2024, 2024-01) triggers formatting penalties.
5. **Missing context** — listing "Python" as a skill without showing where/how it was used in experience bullets.
