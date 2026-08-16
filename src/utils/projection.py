def project_resume_to_markdown(resume_data: dict) -> str:
    lines = []
    
    basics = resume_data.get("basics", {})
    if basics:
        name = basics.get("name", "")
        if name:
            lines.append(f"# {name}")
        
        contact = []
        if basics.get("email"):
            contact.append(basics.get("email"))
        if basics.get("phone"):
            contact.append(basics.get("phone"))
        if basics.get("location"):
            loc = basics.get("location")
            if isinstance(loc, dict):
                loc_str = ", ".join(str(v) for v in [loc.get("city"), loc.get("region"), loc.get("countryCode")] if v)
                if loc_str:
                    contact.append(loc_str)
            elif isinstance(loc, str):
                contact.append(loc)
        if basics.get("url"):
            contact.append(basics.get("url"))
            
        if contact:
            lines.append(" | ".join(contact))
        lines.append("")
    
    summary = resume_data.get("summary", "")
    if summary:
        lines.append("## Summary")
        lines.append(summary)
        lines.append("")
        
    skills = resume_data.get("skills", [])
    if skills:
        lines.append("## Skills")
        for skill_group in skills:
            if isinstance(skill_group, dict):
                cat = skill_group.get("category", "")
                items = skill_group.get("items", [])
                if cat and items:
                    lines.append(f"- **{cat}**: {', '.join(items)}")
                elif items:
                    lines.append(f"- {', '.join(items)}")
            elif isinstance(skill_group, str):
                lines.append(f"- {skill_group}")
        lines.append("")

    work = resume_data.get("work", [])
    if work:
        lines.append("## Experience")
        for job in work:
            company = job.get("company", "")
            title = job.get("position", job.get("title", ""))
            date = job.get("date", "")
            if not date and job.get("startDate"):
                date = f"{job.get('startDate')} - {job.get('endDate', 'Present')}"
            
            header = []
            if title: header.append(f"**{title}**")
            if company: header.append(company)
            if date: header.append(date)
            
            if header:
                lines.append(" | ".join(header))
            
            highlights = job.get("highlights", [])
            for h in highlights:
                lines.append(f"- {h}")
            lines.append("")
            
    projects = resume_data.get("projects", [])
    if projects:
        lines.append("## Projects")
        for proj in projects:
            name = proj.get("name", "")
            desc = proj.get("description", "")
            if name:
                lines.append(f"**{name}**")
            if desc:
                lines.append(desc)
            highlights = proj.get("highlights", [])
            for h in highlights:
                lines.append(f"- {h}")
            lines.append("")

    education = resume_data.get("education", [])
    if education:
        lines.append("## Education")
        for edu in education:
            inst = edu.get("institution", "")
            area = edu.get("area", "")
            studyType = edu.get("studyType", "")
            date = edu.get("date", "")
            if not date and edu.get("startDate"):
                date = f"{edu.get('startDate')} - {edu.get('endDate', 'Present')}"
                
            degree = f"{studyType} in {area}" if studyType and area else (studyType or area)
            
            edu_lines = []
            if inst: edu_lines.append(f"**{inst}**")
            if degree: edu_lines.append(degree)
            if date: edu_lines.append(date)
            
            if edu_lines:
                lines.append(" | ".join(edu_lines))
        lines.append("")
        
    return "\n".join(lines).strip()
