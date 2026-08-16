import pytest
from unittest.mock import MagicMock, patch
from src.agents.auditor import (
    extract_bullets,
    audit_bullet,
    audit_master_resume,
    LLMBulletAudit,
    BulletAudit,
    BankAuditReport
)

def test_extract_bullets():
    text = """
## Experience
- Led development of real-time pipeline processing 10k events/sec.
- Mentored 5 junior engineers across 2 teams.
* Designed Kubernetes operator with 99.9% uptime.
    """
    bullets = extract_bullets(text)
    assert len(bullets) == 3
    assert "10k events/sec" in bullets[0]
    assert "Mentored 5 junior engineers" in bullets[1]
    assert "Kubernetes operator" in bullets[2]

def test_audit_bullet_deterministic_fails():
    # C1 fails: no metric
    res1 = audit_bullet("- Developed backend APIs and user interfaces.")
    assert not res1.passed
    assert any("C1: Missing metric" in issue for issue in res1.issues)

    # C2 fails: weak verb
    res2 = audit_bullet("- Helped team achieve 25% faster load times.")
    assert not res2.passed
    assert any("C2: Uses weak verbs" in issue for issue in res2.issues)

    # C4 fails: too long (>250 chars)
    long_text = "- Designed " + ("a" * 260) + " resulting in 20% latency reduction."
    res3 = audit_bullet(long_text)
    assert not res3.passed
    assert any("C4: Too long" in issue for issue in res3.issues)

def test_audit_bullet_deterministic_pass_no_llm():
    res = audit_bullet("- Scaled PostgreSQL cluster reducing p99 query latency by 45%.")
    assert res.passed
    assert res.checks["C1_Quantified"]
    assert res.checks["C2_Active"]
    assert res.checks["C4_Concise"]
    assert res.checks["C3_Specific"]

@patch("src.agents.auditor.invoke_with_schema_tool")
def test_audit_bullet_with_llm(mock_invoke):
    mock_invoke.return_value = LLMBulletAudit(
        is_specific=True,
        overall_pass=True,
        issues=[]
    )
    mock_llm = MagicMock()
    res = audit_bullet("- Automated CI/CD pipelines decreasing build duration by 30%.", llm=mock_llm)
    assert res.passed
    assert res.checks["C3_Specific"]
    mock_invoke.assert_called_once()

def test_audit_master_resume_fixture(tmp_path):
    resume_file = tmp_path / "master_resume.md"
    resume_file.write_text("""---
name: John Doe
title: Software Engineer
email: john@example.com
phone: "123456"
location: SF
links: []
skills:
  Languages: [Python]
preferences: {}
personal_nudge: {}
education: []
---
# Experience
- Scaled distributed services handling 5M daily requests.
- Helped maintain database schemas.
""")
    report = audit_master_resume(master_resume_path=str(resume_file), llm=None)
    assert isinstance(report, BankAuditReport)
    assert len(report.audited) == 2
    assert report.passed_count == 1
    assert report.failed_count == 1
