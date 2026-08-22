# Gap Analysis: Gold LaTeX Resumes vs FlowJob Pipeline Outputs

**Date:** 2026-08-21 · **Type:** Research (no code changes)
**Gold corpus:** 8 hand-crafted Jake's-Resume `.tex` files in `/home/iaminfadel/resumes/*/` (canonical: `EgSA_Space_Internship_2026/Amin_Fadel_CV_EgSA_Internship.tex`)
**Pipeline outputs:** `data/resumes/<hash>/resume.{json,html,pdf}` (analyzed: `040608ed5151`, `1f9a9646daa7`, `600aeb77b47d`, `dadd0765048c`, `f64072071744`)
**Pipeline code:** `src/agents/tailor.py` (`ResumeOutput`), `src/utils/resume_template.html`, `src/utils/document_generator.py`, `src/utils/resume_parser.py`
**Source of truth:** `master_resume.md`

---

## 1. Verdict

The pipeline PDFs are structurally broken and content-thin compared to gold:

| Metric | Gold (LaTeX) | Pipeline (HTML→Playwright) |
|---|---|---|
| Font | Computer Modern family (CMBX/CMR/CMTI/CMCSC) | LiberationSerif (Times fallback) |
| Pages | 1–3 (mostly 2) | 2 |
| Extracted text density | ~6,800–7,300 chars | **~3,000–3,400 chars (<50%)** |
| Sections rendered | 7 (Profile → Skills) | 4 (Education, Experience, Projects, Technical Skills) |
| Education line | Full degree + honors + GPA + rank + dates | Renders literally as **"–"** and **"in"** (empty fields) |
| Contact line | Email \| phone \| LinkedIn \| GitHub \| nationality \| military | Phone \| email \| Cairo, Egypt \| **\| \|** (empty link texts) |

---

## 2. Master Gap Table

| # | Gap | Gold behavior | Pipeline behavior | Fix locus |
|---|-----|---------------|-------------------|-----------|
| G1 | **Education renders empty** ("in" / "–") | `BSc. Mechatronics and Robotics Engineering — With Honors` + `Sep. 2021 – Jun. 2026` + bold GPA line | Template reads `edu.studyType`/`edu.area`/`edu.startDate`; newer JSONs carry `degree`/`start_date`/`gpa` (master_resume.md keys). Three-way key drift: master_resume ↔ pydantic schema ↔ template. GPA never rendered by template at all. | Schema + template (+ normalize in tailor.py re-injection) |
| G2 | **Profile section missing** | Tailored 4–6 line summary under `\section{Profile}` — first thing after header; mentions GPA/rank, domain fit, availability | No field in `ResumeOutput`; template has no block. `personal_nudge` exists in master_resume but is never surfaced as a Profile. | Schema + template + prompts |
| G3 | **Certificates & Awards missing** | Dedicated section, year-prefixed lines (`\textbf{2026} -- 1st Place, Global HackAtom Egypt…`) | Absent from schema, template, and master_resume.md entirely | master_resume data + schema + template |
| G4 | **Graduation Project missing as section** | Own section between Education and Experience with 3 bullets (PMSM/EV platform) | PMSM appears only sometimes as a generic project; no dedicated slot | Schema + template + prompts (or promote in master_resume projects w/ flag) |
| G5 | **Header identity truncated** | `Amin Moustafa Fadel` (full name), links shown as words "Email/LinkedIn/GitHub", plus `Egyptian/Canadian` and `Military Service: Exempted` | Name = "Amin Fadel"; template prints `profile.network` but JSON stores `name` → empty `<a></a>`; no nationality/military fields anywhere | master_resume data + template (key mismatch `network` vs `name`) |
| G6 | **Raw ISO dates** | `Sep. 2021 -- Jun. 2026`, `Apr. 2025 -- Mar. 2026`, `Feb. 2026 -- Present` (abbrev month + period, en-dash) | `2021-09 – 2026-07`, `2025-04 – Present` | Template formatter or prompt post-process |
| G7 | **No location on work/project entries** | Every role right-aligned location: `Cairo, Egypt` / `Remote` | `WorkItem`/`ProjectItem` have no location field; master_resume headers contain it but parser drops it into the title string only | Schema + parser + template |
| G8 | **Section order & set wrong** | Profile → Education → Graduation Project → Experience → Selected Projects → Certificates & Awards → Technical Skills (2 files swap GradProj/Experience) | Education → Experience → Projects → Technical Skills (ALL-CAPS titles) | Template |
| G9 | **Skills grouping weak** | 6–8 JD-tailored groups per resume (e.g., "Sensors & Instrumentation", "Automotive & Safety"), incl. optional `Languages: Arabic (Native), English (Fluent)` line | Fixed 3–4 generic groups recycled from master taxonomy ("Languages" group = programming languages! name collision with spoken-languages meaning) | Prompts + master_resume data |
| G10 | **Content density ~half of gold** | 16–22 bullets/resume, median 163–218 chars each | 11–17 bullets, many shorter; whole Profile/Certificates sections absent explains most of the deficit | Prompts + sections above |
| G11 | **LLM hallucination/mangling leaks** | n/a (human) | `600aeb77b47d`: phantom entry `{"company": "Experience", "position": "Role"}`; bullets leak raw tags `- Designed … [electrical-wiring, hardware-troubleshooting, schematics]`; duplicate ADR bullet pasted into ASU ROAR role | Prompts + validation (reject placeholder entries, strip `[tags]`) |
| G12 | **Schema drift between runs** | n/a | Older output `dadd0765048c` uses `area/studyType/startDate` (matches pydantic); newer `040608ed5151` uses `degree/start_date/gpa` (matches master_resume.md, violates pydantic). Same code produced both → structured-output enforcement is not airtight across providers. | Schema (align all three to ONE key set) + strict validation |
| G13 | **Typography/layout** | Jake's class: smallcaps section heads + rule, tabular* two-column headers, tight negative vspace, `\small` bullets, linespread 1.1 | Generic HTML: uppercase bold titles + full-width border, flex rows, 11pt Times/Liberation, loose spacing | Template (CSS rewrite toward Jake's look) |
| G14 | **Project heading format** | `**Name** \| *tech stack*` + date on right; links hyperlinked | Name + description paragraph + dates; tech stack buried in description text | Prompts (emit `tech` field) + template |
| G15 | **Availability line** | Gold profiles end with availability ("Available full-time July 1 – September 30") | Never present | master_resume data + prompts |

---

## 3. Bullet-Style Rules Distilled from Gold (n=8 resumes, 143 bullets)

**Counts**
- Total bullets per resume: 11–22 (median ≈ 18).
- Bullets per role: top/current role gets **3** (occasionally 4–5); mid roles **1–2**; old/minor roles exactly **1**.
- Graduation Project: always **3** bullets.
- Projects: flagship 2–3, rest **1** each.

**Length**
- Char length per bullet: min 94, **median ≈ 200**, max 283. Sweet spot 140–250 chars (~15–30 words). One sentence, occasionally two joined by `;`.

**Verbs (first word)**
- Always past tense (except current-role "Act/Share" rare cases), strong action verbs, almost never repeated twice in one resume except "Designed/Developed/Built".
- Top verbs by frequency: Designed (17), Built (9), Developed (9), Implemented (7), Led (7), Automated (6), Authored (6), Integrated (6), Owned (5), Coordinated (5), Collaborated (4), Completed (4), Directed (3), Achieved (3), Contributed (3), Maintained (2), Established (2), Increased (2), Reduced (2).
- Banned/absent: "Responsible for", "Worked on" (only 2 "Worked" total), "Helped".

**Metrics**
- 33–62% of bullets contain hard numbers (median ≈ 55%): team size (10-person), rank (21st place, 5th place), % improvements (90%, 35–50%, 40%, 28%), counts (11 ADRs, 15+ members), specs (300 Hz, 5-degree accuracy).
- Numbers prefer concrete outcomes over tool lists.

**Structure patterns**
- Pattern A (ownership): "Owned the complete X lifecycle for Y: from A through B and C."
- Pattern B (result): "<Action verb> <system> by <means>, achieving <metric>."
- Pattern C (scope): "Led a N-person team to <result>, owning <architecture scope>."
- Tech names inline (STM32, ROS, TensorRT) rather than in separate parentheticals.

**Skills groups**: 6–8 groups, renamed per JD; each group 4–12 comma-separated items; optional final `Languages:` spoken-languages line.

**Dates**: `Mon. YYYY -- Mon. YYYY` (3-letter month + period, en-dash with spaces); years alone for projects (`2025 -- 2026`) or empty for undated projects.

---

## 4. Section Order + Conditional Rendering Recommendations

Canonical order (matches 6/8 gold files):

1. **Header** — full name; contact row: Email | phone | LinkedIn | GitHub | nationality* | Military Service: Exempted*
2. **Profile** — render if `profile_summary` present (always tailor per JD)
3. **Education** — institution+location / degree+honors / dates / bold GPA-rank line
4. **Graduation Project** — render if `graduation_project.enabled` AND relevant to JD (skip for pure-software JDs? gold keeps it in 7/8)
5. **Experience** — sorted desc; hide entries irrelevant to JD (gold drops EVER/ARL/Honda freely)
6. **Selected Projects** — 4–6 max, JD-ranked
7. **Certificates & Awards** — render if non-empty; prune to ≤6 most relevant
8. **Technical Skills** — 6–8 JD-shaped groups + Languages line

Conditional rules observed in gold:
- Nationality dropped when space is tight (EgSA, Cairomotive keep Military only).
- Spoken-Languages skills line omitted in 3/8 (Scalvy, Sensor_Integration, Cairomotive).
- Certificates pruned from 7 entries down to 4 (Scalvy).
- Section order swap Experience↔Graduation Project in 2/8 (RoboticsEngineer, Sensor_Integration) — treat as allowed variance, default Graduation-Project-first.
- One-page variant exists (Sensor_Integration, 1p): achieved by cutting to 11 bullets + 5 projects.

---

## 5. New `master_resume.md` Frontmatter Fields Needed

Currently frontmatter has: name, title, email, phone, location, links, skills, preferences, personal_nudge, education. **Missing:**

```yaml
name: "Amin Moustafa Fadel"        # FIX: use full legal name (currently "Amin Fadel")
nationality: "Egyptian/Canadian"    # NEW — header line
military_service: "Exempted"        # NEW — header line
languages_spoken:                   # NEW — skills "Languages:" line
  - "Arabic (Native)"
  - "English (Fluent)"
  - "French (Beginner)"
availability: "Available full-time" # NEW — Profile closing line (or per-JD override)
certificates_awards:                # NEW — section data
  - year: 2026
    text: "1st Place, Global HackAtom Egypt (Rosatom & NPPA)"
  - year: 2025
    text: "Senior System Engineer | Head of Software | Mission Leader, ERC 2025 (European Space Foundation)"
  - year: 2025
    text: "1st Place, AI Competition, Ain Shams University Faculty of Engineering"
  - year: 2024
    text: "2nd Place, Machathon 5.0 Autonomous Vehicle Challenge"
  - year: 2024
    text: "Innovation and Entrepreneurship Training, InnovEgypt (TIEC)"
  - year: 2024
    text: "Embedded Systems Intermediate, AMIT / Orange Digital Center"
  - year: 2023
    text: "5th Place, Formula Student AI UK, IMechE"
profile_base: >                     # NEW — reusable raw material for tailored Profile
  Mechatronics & Robotics Engineering graduate (Honors, GPA 3.84/4.0, Class Rank 1st)…
graduation_project:                 # NEW — promoted from projects[] so it can render as its own section
  title: "Advanced PMSM Control & Testing Platform for Electric Vehicles"
  sponsor: "Sponsored by eJad"
  dates: "2025 -- 2026"
  highlights: [ ...3 bullets... ]
```

Plus **education key alignment** (pick ONE canonical set everywhere):
- master_resume.md currently: `degree / start_date / end_date / gpa / location`
- pydantic `EducationItem`: `area / studyType / startDate / endDate` (no gpa, no location)
- template: `studyType / area / startDate / endDate` (no gpa)
→ Recommend standardizing on master_resume's keys (`degree`, `start_date`, `end_date`, `gpa`, `location`) and updating pydantic + template to match, since that's the human-authored source of truth.

Also add to `WorkItem`/`ProjectItem`: `location: str` (already present in master_resume markdown headers, just needs parsing).

---

## 6. Surprises

1. **Data present but not rendered (worst bug):** education `degree/gpa/dates` exist in the newest resume.json files, yet the PDF shows `"in"` and `"–"` — template expects `studyType/area/startDate`. GPA is never printed by any template path.
2. **Empty link texts:** template iterates `basics.profiles` printing `{{ profile.network }}`, but tailor.py re-injects `metadata.links` whose key is `name` → renders `| <a href="…"></a>`. LinkedIn/GitHub labels vanish from the PDF header.
3. **Two different schemas in the wild:** older pipeline runs emit pydantic-faithful `area/studyType`; newest emit master_resume-style `degree/start_date/gpa` — evidence the structured-output layer doesn't enforce the declared model consistently across LLM providers/failover paths.
4. **Hallucinated skeleton entry:** `600aeb77b47d` contains `{"company": "Experience", "position": "Role"}` — an LLM-invented placeholder that passed validation because `company` isn't even a declared field (extra keys tolerated).
5. **Tag leakage:** master_resume bullet tags like `[electrical-wiring, hardware-troubleshooting]` leaked verbatim into rendered highlight bullets in `600aeb77b47d`.
6. **personal_nudge is dead weight:** rich tone/themes data exists in frontmatter specifically "for AI Summary Generation," but no Profile field exists anywhere downstream — it's never used.
7. **Gold PDFs are 2 pages at ~7k chars; pipeline hits 2 pages at ~3k chars** — the pipeline wastes a page on sparse styling (large fonts/margins), i.e., layout alone burns the second page.
8. **ATS check is too weak:** document_generator.py only asserts name+email appear in extracted text — passes even when education/links are visibly broken.
9. **master_resume.md already contains everything needed for great bullets** (metrics, tags, contexts) — the trash output is a rendering/schema problem more than a data problem.
