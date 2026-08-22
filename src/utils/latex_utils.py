"""LaTeX rendering helpers: escaping, date formatting, and draft normalization.

The pipeline's LLM agents emit draft JSON whose key vocabulary can drift
between providers/runs (e.g. ``degree`` vs ``studyType``, ``startDate`` vs
``start_date``). Everything is normalized here into ONE canonical vocabulary —
the master_resume.md keys — before it reaches the LaTeX template. Trailing
``[tag]`` markers and hallucinated stub entries are stripped as well.
"""

from __future__ import annotations

import re
from copy import deepcopy

MONTH_ABBREVS = {
    1: "Jan.", 2: "Feb.", 3: "Mar.", 4: "Apr.", 5: "May", 6: "Jun.",
    7: "Jul.", 8: "Aug.", 9: "Sep.", 10: "Oct.", 11: "Nov.", 12: "Dec.",
}

_UNICODE_REPLACEMENTS = [
    ("—", "---"), ("–", "--"), ("’", "'"), ("‘", "`"),
    ("“", "``"), ("”", "''"), ("…", "\\ldots{}"), ("×", "$\\times$"),
    ("°", "$^\\circ$"), (" ", "~"), ("≈", "$\\approx$"),
    ("∼", "$\\sim$"), ("€", "\\euro{}"),
]

_TRAILING_TAGS_RE = re.compile(r"(?:\s*\[[^\]\[]{1,60}\])+\s*\.?\s*$")
_STUB_NAMES = {"experience", "role", "company", "employer", "project", "name"}

# Master-resume experience header: "## Org | Role | Location | 2024-11 - 2025-09"
_EXPERIENCE_HEADER_RE = re.compile(
    r"^##\s+(?P<org>.+?)\s*\|\s*(?P<role>.+?)\s*\|\s*(?P<location>.+?)\s*\|\s*"
    r"(?P<start>\d{4}(?:-\d{2})?)\s*-\s*(?P<end>Present|\d{4}(?:-\d{2})?)\s*$",
    re.MULTILINE,
)
_ALIAS_MAP = {
    "startDate": "start_date",
    "endDate": "end_date",
    "studyType": "degree",
    "area": "degree",
    "network": "name",
    "company": "name",
    "url": "url",
}


def latex_escape(text: str) -> str:
    """Escape a dynamic string for LaTeX typesetting."""
    if text is None:
        return ""
    text = str(text)
    for src, dst in _UNICODE_REPLACEMENTS:
        text = text.replace(src, dst)
    text = text.replace("\\", "\\textbackslash{}")
    for ch in "&%$#_{}":
        text = text.replace(ch, f"\\{ch}")
    # OT1-encoded Computer Modern renders a literal "|" as an em-dash;
    # math mode keeps it a true vertical bar (matches the gold resumes).
    text = text.replace("|", "$|$")
    text = text.replace("~", "\\textasciitilde{}")
    text = text.replace("^", "\\textasciicircum{}")
    return text


def latex_escape_url(url: str) -> str:
    """Escape a URL for use inside \\href{...} (keep ~ and / literal)."""
    if not url:
        return ""
    url = str(url).replace("\\", "")
    for ch in "%&#_{}":
        url = url.replace(ch, f"\\{ch}")
    return url


def format_date(value: str) -> str:
    """Format an ISO date (``2021-09``, ``2021``) as ``Sep. 2021`` / ``2021``.

    Non-ISO values (e.g. ``Present``) pass through unchanged.
    """
    if not value:
        return ""
    value = str(value).strip()
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", value)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            return f"{MONTH_ABBREVS[month]} {year}"
    return value


def format_date_range(start: str, end: str) -> str:
    """Format a start/end pair as gold-standard ``Sep. 2021 -- Jul. 2026``."""
    start_fmt = format_date(start)
    end_fmt = format_date(end) if end else ""
    if start_fmt and end_fmt:
        if start_fmt == end_fmt:  # single-year entries: "2024", not "2024 -- 2024"
            return start_fmt
        return f"{start_fmt} -- {end_fmt}"
    return start_fmt or end_fmt


def as_model_dict(obj):
    """Normalize pydantic models or mappings to a plain dict."""
    return obj.model_dump() if hasattr(obj, "model_dump") else dict(obj)


def strip_trailing_tags(bullet: str) -> str:
    """Remove trailing ``[tag1, tag2]`` markers from a bullet string."""
    if not bullet:
        return bullet
    cleaned = _TRAILING_TAGS_RE.sub("", bullet).rstrip()
    if cleaned and cleaned[-1].isalnum():
        cleaned += "."
    return cleaned


def _canon_keys(item: dict) -> dict:
    out = {}
    for key, value in item.items():
        out[_ALIAS_MAP.get(key, key)] = value
    return out


def _build_experience_facts(master_experience_md: str) -> list[dict]:
    """Parse authoritative org/role/location/dates from master experience headers."""
    facts = []
    for m in _EXPERIENCE_HEADER_RE.finditer(master_experience_md or ""):
        facts.append({
            "org": m.group("org").strip(),
            "role": m.group("role").strip(),
            "location": m.group("location").strip(),
            "start": m.group("start").strip(),
            "end": m.group("end").strip(),
        })
    return facts


def _norm_tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if len(t) > 2}


def _date_sort_key(value: str) -> str:
    """Normalize a date to a zero-padded YYYY-MM string for sorting."""
    value = str(value or "").strip()
    match = re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?", value)
    if match:
        month = int(match.group(2) or 12)  # year-only entries sort as Dec
        return f"{match.group(1)}-{month:02d}"
    return value if value else "0000-00"


def _match_experience(org: str, role: str, facts: list[dict]) -> dict | None:
    """Fuzzy-match a draft entry to a master experience header by token overlap."""
    if not facts:
        return None
    org_tokens = _norm_tokens(org)
    best, best_score = None, 0.0
    for f in facts:
        f_org = _norm_tokens(f["org"])
        overlap = len(org_tokens & f_org) / max(len(f_org), 1)
        score = overlap
        if role and _norm_tokens(role) & _norm_tokens(f["role"]):
            score += 0.25
        if score > best_score:
            best, best_score = f, score
    return best if best_score >= 0.5 else None


def _is_stub_entry(item: dict) -> bool:
    name = str(item.get("name", "")).strip().lower()
    position = str(item.get("position", "")).strip().lower()
    highlights = item.get("highlights") or []
    if name in _STUB_NAMES or position in {"role"}:
        return True
    return name == "" and position == "" and not highlights


def normalize_draft(draft: dict, master_experience_md: str = "") -> dict:
    """Return a canonical, template-ready deep copy of a draft resume.

    - aliases mapped to master_resume vocabulary (one canonical key set)
    - trailing ``[tags]`` stripped from every bullet
    - hallucinated stub work/project entries dropped
    - work dates/location corrected against the master resume's authoritative
      experience headers (the LLM is never trusted with factual dates)
    - empty sections removed
    """
    data = deepcopy(draft or {})

    # Authoritative facts from the master resume's experience narratives,
    # keyed by fuzzy org name (LLM org names drift: "ASU ROAR" vs
    # "ASU ROAR - European Rover Challenge").
    exp_facts = _build_experience_facts(master_experience_md)

    education = []
    for item in data.get("education") or []:
        item = _canon_keys(item)
        if not item.get("institution"):
            continue
        item["date_range"] = format_date_range(item.get("start_date", ""), item.get("end_date", ""))
        education.append(item)

    def _norm_entries(entries):
        out = []
        for item in entries or []:
            item = _canon_keys(item)
            if _is_stub_entry(item):
                continue
            item["date_range"] = format_date_range(item.get("start_date", ""), item.get("end_date", ""))
            item["highlights"] = [strip_trailing_tags(h) for h in (item.get("highlights") or []) if h]
            out.append(item)
        return out

    work = _norm_entries(data.get("work"))
    for job in work:
        facts = _match_experience(job.get("name", ""), job.get("position", ""), exp_facts)
        if facts:
            # Factual fields are corrected, never trusted to LLM output.
            if facts["start"]:
                job["start_date"] = facts["start"]
            if facts["end"]:
                job["end_date"] = facts["end"]
            if facts["location"] and not job.get("location"):
                job["location"] = facts["location"]
        # Recompute the range AFTER correction.
        job["date_range"] = format_date_range(job.get("start_date", ""), job.get("end_date", ""))
        job["_sort_key"] = _date_sort_key(job.get("start_date", ""))
    # Gold convention: strictly reverse-chronological within each section.
    work.sort(key=lambda j: j["_sort_key"], reverse=True)
    for job in work:
        job.pop("_sort_key", None)
    projects = _norm_entries(data.get("projects"))
    for proj in projects:
        # Gold project headings carry a short tech list ("Multi-Agent AI
        # Pipeline, Python"), never a description sentence. A long free-text
        # `technologies`/`description` value is a mis-routed description:
        # keep only a short comma-list, move prose out of the heading.
        name_len = len(str(proj.get("name", "")))
        tech = str(proj.get("technologies", "") or proj.pop("description", "") or "")
        if len(tech) > 80 or ("," not in tech and len(tech.split()) > 6):
            # Prose, not a tech list: demote to highlights if new evidence,
            # otherwise drop from the heading entirely.
            sentence = tech.strip()
            if sentence and all(sentence not in h for h in (proj.get("highlights") or [])):
                proj.setdefault("highlights", []).insert(0, sentence)
            tech = ""
        max_tech = max(60 - name_len, 12)
        if len(tech) > max_tech:
            kept, used = [], 0
            for item in [t.strip() for t in tech.split(",") if t.strip()]:
                extra = len(item) + (2 if kept else 0)
                if used + extra > max_tech and kept:
                    break
                kept.append(item)
                used += extra
            proj["technologies"] = ", ".join(kept)

    # Gold convention: projects are also strictly reverse-chronological.
    projects.sort(key=lambda p: _date_sort_key(p.get("start_date", "")), reverse=True)

    # The Graduation Project renders as its own section — drop any duplicate
    # the LLM placed in the projects list (fuzzy title match).
    gp_title = str((data.get("graduation_project") or {}).get("title", "") or "")
    if gp_title:
        gp_tokens = _norm_tokens(gp_title)
        projects = [
            p for p in projects
            if not (gp_tokens and len(_norm_tokens(p.get("name", "")) & gp_tokens) / max(len(gp_tokens), 1) >= 0.5)
        ]

    certificates = [
        {"year": str(c.get("year", "")).strip(), "title": str(c.get("title", "")).strip()}
        for c in (data.get("certificates") or [])
        if isinstance(c, dict) and c.get("title")
    ]
    # Gold convention: most recent first.
    certificates.sort(key=lambda c: c.get("year", ""), reverse=True)

    skill_groups = []
    languages_spoken = list(data.get("languages_spoken") or [])
    for group in data.get("skills") or []:
        if isinstance(group, dict):
            keywords = ", ".join(k for k in (group.get("keywords") or group.get("items") or []) if k)
            if group.get("name") and keywords:
                # A literal "Languages" skill group IS the languages line:
                # record it and never emit a second duplicate line below.
                if group["name"].strip().lower() == "languages":
                    languages_spoken = [
                        k.strip() for k in (group.get("keywords") or group.get("items") or []) if k.strip()
                    ] or languages_spoken
                    continue
                skill_groups.append({"name": group["name"], "keywords": keywords})
        elif isinstance(group, str) and group.strip():
            skill_groups.append({"name": "", "keywords": group.strip()})

    basics = data.get("basics") or {}
    profiles = []
    for profile in basics.get("profiles") or []:
        profile = _canon_keys(profile)
        if profile.get("url"):
            profiles.append({"name": profile.get("name", ""), "url": profile["url"]})

    graduation_project = data.get("graduation_project") or None
    if graduation_project:
        graduation_project["highlights"] = [
            strip_trailing_tags(h) for h in (graduation_project.get("highlights") or []) if h
        ]
        # Normalize LLM date ranges to the gold en-dash convention.
        dr = str(graduation_project.get("date_range", "") or "")
        graduation_project["date_range"] = re.sub(r"(\d{4})\s*[-–]\s*(\d{4})", r"\1 -- \2", dr)

    return {
        "basics": basics,
        "profiles": profiles,
        "summary": (data.get("summary") or "").strip(),
        "education": education,
        "graduation_project": graduation_project,
        "work": work,
        "projects": projects,
        "certificates": certificates,
        "skill_groups": skill_groups,
        "languages_line": ", ".join(languages_spoken),
    }


def build_render_context(draft: dict, metadata=None, master_experience_md: str = "") -> dict:
    """Merge a normalized draft with locally-sourced header metadata.

    Header extras (full name, military service, availability) NEVER come from
    LLM output — they are injected here from the parsed master resume,
    preserving FlowJob's PII boundary.
    """
    ctx = normalize_draft(draft, master_experience_md)
    meta_name = getattr(metadata, "name", "") or ""
    full_name = getattr(metadata, "full_name", "") or meta_name

    # Contact info comes ONLY from locally parsed metadata — never from LLM
    # output (PII boundary). No fallback to draft basics.
    email = getattr(metadata, "email", "") or ""
    phone = getattr(metadata, "phone", "") or ""

    links = list(ctx["profiles"])
    if not links and hasattr(metadata, "links"):
        links = [
            {"name": l.get("name", ""), "url": l.get("url", "")}
            for l in (metadata.links or []) if l.get("url")
        ]
    header_links = [{"label": l["name"] or "Link", "url": l["url"]} for l in links]

    ctx["header"] = {
        "name": latex_escape(full_name),
        # mailto target must be URL-escaped, not text-escaped (underscores etc.)
        "email_url": latex_escape_url(email),
        "phone": latex_escape(phone),
        "links": [
            {"label": latex_escape(l["label"]), "url": latex_escape_url(l["url"])}
            for l in header_links
        ],
        "military_service": latex_escape(getattr(metadata, "military_service", "") or ""),
        "nationality": latex_escape(getattr(metadata, "nationality", "") or ""),
        "availability": latex_escape(getattr(metadata, "availability", "") or ""),
    }

    if not ctx["summary"] and metadata is not None:
        # Gold CVs always carry a Profile paragraph. If the Tailor omitted one,
        # fall back to the master resume's profile base rather than dropping
        # the section.
        ctx["summary"] = getattr(metadata, "profile_base", "") or ""

    for section_key in ("summary",):
        ctx[section_key] = latex_escape(ctx[section_key])

    for edu in ctx["education"]:
        edu["institution"] = latex_escape(edu["institution"])
        edu["degree"] = latex_escape(edu.get("degree", ""))
        edu["location"] = latex_escape(edu.get("location", ""))
        edu["gpa"] = latex_escape(edu.get("gpa", ""))
        edu["date_range"] = latex_escape(edu["date_range"])

    gp = ctx["graduation_project"]
    if gp:
        gp["title"] = latex_escape(gp.get("title", ""))
        gp["url"] = latex_escape_url(gp.get("url", ""))
        gp["date_range"] = latex_escape(gp.get("date_range", ""))
        gp["highlights"] = [latex_escape(h) for h in gp["highlights"]]

    for job in ctx["work"]:
        job["position"] = latex_escape(job.get("position", ""))
        job["name"] = latex_escape(job.get("name", ""))
        job["location"] = latex_escape(job.get("location", ""))
        job["date_range"] = latex_escape(job["date_range"])
        job["highlights"] = [latex_escape(h) for h in job["highlights"]]

    for proj in ctx["projects"]:
        proj["name"] = latex_escape(proj.get("name", ""))
        proj["technologies"] = latex_escape(proj.get("technologies", ""))
        proj["url"] = latex_escape_url(proj.get("url", ""))
        proj["date_range"] = latex_escape(proj["date_range"])
        proj["highlights"] = [latex_escape(h) for h in proj["highlights"]]

    for cert in ctx["certificates"]:
        cert["year"] = latex_escape(cert["year"])
        cert["title"] = latex_escape(cert["title"])

    for group in ctx["skill_groups"]:
        group["name"] = latex_escape(group["name"])
        group["keywords"] = latex_escape(group["keywords"])

    ctx["languages_line"] = latex_escape(ctx["languages_line"])

    if not ctx["graduation_project"] and metadata is not None:
        gp_meta = getattr(metadata, "graduation_project", None)
        if gp_meta is not None:
            gp_data = as_model_dict(gp_meta)
            if gp_data.get("title"):
                ctx["graduation_project"] = {
                    "title": latex_escape(gp_data.get("title", "")),
                    "url": latex_escape_url(gp_data.get("url", "")),
                    "date_range": latex_escape(gp_data.get("date_range", "")),
                    "highlights": [latex_escape(strip_trailing_tags(h)) for h in gp_data.get("highlights", [])],
                }
            else:
                ctx["graduation_project"] = None

    if not ctx["languages_line"] and metadata is not None:
        langs = getattr(metadata, "languages_spoken", None) or []
        ctx["languages_line"] = latex_escape(", ".join(langs))

    if not ctx["certificates"] and metadata is not None:
        certs_meta = getattr(metadata, "certificates_awards", None) or []
        certs = []
        for cert in certs_meta:
            cert_data = as_model_dict(cert)
            if cert_data.get("title"):
                certs.append({
                    "year": latex_escape(cert_data.get("year", "")),
                    "title": latex_escape(cert_data.get("title", "")),
                })
        ctx["certificates"] = certs

    return ctx
