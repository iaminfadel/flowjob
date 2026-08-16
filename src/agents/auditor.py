import re
import os
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from src.agents.structured_llm import invoke_with_schema_tool
from src.utils.resume_parser import parse_master_resume

class LLMBulletAudit(BaseModel):
    is_specific: bool = Field(description="Does the bullet specify what was done, how, and why without being vague?")
    overall_pass: bool = Field(description="Does the bullet pass the overall quality audit?")
    issues: list[str] = Field(default_factory=list, description="List of issues identified, if any.")

class BulletAudit(BaseModel):
    bullet: str
    passed: bool
    checks: dict[str, bool]
    issues: list[str] = Field(default_factory=list)

class BankAuditReport(BaseModel):
    audited: list[BulletAudit]
    passed_count: int
    failed_count: int

def extract_bullets(text: str) -> list[str]:
    lines = text.split('\n')
    bullets = []
    current_bullet = []
    for line in lines:
        if re.match(r'^\s*[-*]\s+', line):
            if current_bullet:
                bullets.append('\n'.join(current_bullet))
            current_bullet = [line.strip()]
        elif current_bullet and line.strip() != "":
            current_bullet.append(line.strip())
        elif line.strip() == "":
            if current_bullet:
                bullets.append('\n'.join(current_bullet))
                current_bullet = []
    if current_bullet:
        bullets.append('\n'.join(current_bullet))
    return bullets

def audit_bullet(bullet: str, llm=None) -> BulletAudit:
    bullet_stripped = bullet.strip()
    clean_bullet = re.sub(r'^\s*[-*]\s*', '', bullet_stripped)
    
    checks = {
        "C1_Quantified": False,
        "C2_Active": False,
        "C4_Concise": False,
        "C3_Specific": False
    }
    issues = []
    
    # C1: Quantified
    if re.search(r'\d+%?|\b\d+\b|~|\$', clean_bullet):
        checks["C1_Quantified"] = True
    else:
        issues.append("C1: Missing metric (% or number)")
        
    # C2: Active verb
    weak_verbs_pattern = r'\b(helped|assisted|worked on|responsible for|participated in)\b'
    if re.search(weak_verbs_pattern, clean_bullet, re.IGNORECASE):
        issues.append("C2: Uses weak verbs (e.g. helped, assisted, worked on)")
    else:
        checks["C2_Active"] = True
        
    # C4: Concise (<= 250 characters and <= 2 lines)
    line_count = len(bullet_stripped.split('\n'))
    if len(bullet_stripped) <= 250 and line_count <= 2:
        checks["C4_Concise"] = True
    else:
        issues.append("C4: Too long or exceeds 2 lines")
        
    # If deterministic checks fail, fast-fail without token spend
    if not (checks["C1_Quantified"] and checks["C2_Active"] and checks["C4_Concise"]):
        return BulletAudit(
            bullet=bullet,
            passed=False,
            checks=checks,
            issues=issues
        )
        
    # LLM fuzzy residue check for C3 Specific + overall verdict
    if llm is not None:
        try:
            prompt = (
                f"You are a strict resume auditor evaluating bullet point quality.\n"
                f"Bullet: \"{clean_bullet}\"\n"
                f"Evaluate if the bullet is specific (names concrete tools, technologies, scale, or outcomes) "
                f"and does not use vague buzzwords."
            )
            llm_result = invoke_with_schema_tool(llm, [prompt], LLMBulletAudit)
            checks["C3_Specific"] = llm_result.is_specific
            if not llm_result.is_specific or not llm_result.overall_pass:
                issues.extend(llm_result.issues or ["C3: Lacks technical specificity"])
        except Exception as e:
            # Fallback gracefully if LLM fails
            checks["C3_Specific"] = True
    else:
        checks["C3_Specific"] = True
        
    passed = all(checks.values())
    return BulletAudit(
        bullet=bullet,
        passed=passed,
        checks=checks,
        issues=issues
    )

def audit_master_resume(master_resume_path: str = "master_resume.md", llm=None, model_name: str = "google/gemini-2.5-pro") -> BankAuditReport:
    _, md_content = parse_master_resume(master_resume_path)
    bullets = extract_bullets(md_content)
    
    if llm is None and os.environ.get("OPENROUTER_API_KEY"):
        llm = ChatOpenAI(
            model=model_name,
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            temperature=0.0
        )
        
    audited = []
    passed_count = 0
    failed_count = 0
    
    for b in bullets:
        res = audit_bullet(b, llm=llm)
        audited.append(res)
        if res.passed:
            passed_count += 1
        else:
            failed_count += 1
            
    return BankAuditReport(
        audited=audited,
        passed_count=passed_count,
        failed_count=failed_count
    )
