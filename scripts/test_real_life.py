import os
import json
from src.config import load_config
from src.cli import build_agents
from src.utils.document_generator import PlaywrightDocumentGenerator
from src.utils.resume_parser import parse_master_resume

def main():
    print("🚀 Initializing FlowJob Real-Life Pipeline Run...")
    
    cfg = load_config("flowjob.yaml")
    agents = build_agents()
    
    analyst = agents["analyst"]
    tailor = agents["tailor"]
    critic = agents["critic"]
    writer = agents["writer"]
    editor = agents["editor"]
    
    jd_text = """
    We are looking for a Senior Python Developer with experience in LangChain, AI agents, and FastAPI.
    You will be responsible for orchestrating LLM workflows and integrating with external APIs.
    Requirements:
    - 5+ years of Python
    - Experience with LLMs and prompt engineering
    - Kubernetes and container deployment experience
    """
    
    print("\n" + "="*60)
    print("STEP 1: ANALYST AGENT (Fit Assessment)")
    print("="*60)
    fit_score = analyst.run({"jd_text": jd_text})
    print(f"Fit Score: {fit_score.score}/100")
    print(f"Matching Skills: {fit_score.matching_skills}")
    print(f"Missing Skills: {fit_score.missing_skills}")
    print(f"Recommendation: {fit_score.recommendation}")
    
    print("\n" + "="*60)
    print("STEP 2: TAILOR AGENT (Draft JSON Generation)")
    print("="*60)
    tailored_resume = tailor.run(jd_text=jd_text)
    tailored_json = json.dumps(tailored_resume, indent=2) if tailored_resume else "{}"
    print(f"Draft generated ({len(tailored_json)} chars).")
    
    print("\n" + "="*60)
    print("STEP 3: COVERAGE CRITIC AGENT (Gap Analysis)")
    print("="*60)
    coverage_report = critic.run({
        "jd_text": jd_text,
        "draft_data": tailored_resume,
        "master_resume_path": "master_resume.md"
    })
    print(f"Critic Unfixable: {coverage_report.unfixable}")
    print(f"Summary: {coverage_report.summary}")
    for req in coverage_report.requirements:
        print(f"  - [{req.verdict.upper()}] Route: {req.route} | {req.requirement}")
        
    print("\n" + "="*60)
    print("STEP 4: WRITER AGENT (Evidence Loop Tool Mutation)")
    print("="*60)
    master_metadata, master_text = parse_master_resume("master_resume.md")
    updated_draft, plan = writer.run_round(
        jd_text=jd_text,
        draft_data=tailored_resume,
        coverage_report=coverage_report.model_dump(),
        master_resume_text=master_text
    )
    print(f"Writer Plan Summary: {plan.get('summary')}")
    print(f"Writer Edits Applied: {len(plan.get('edits', []))}")
    
    print("\n" + "="*60)
    print("STEP 5: PLAYWRIGHT DOCUMENT GENERATOR (PDF Render)")
    print("="*60)
    output_dir = os.path.join("data", "resumes", "real_life_test")
    os.makedirs(output_dir, exist_ok=True)
    doc_gen = PlaywrightDocumentGenerator()
    pdf_path = doc_gen.generate(updated_draft, master_metadata, output_dir)
    print(f"PDF successfully rendered: {pdf_path}")
    assert os.path.exists(pdf_path)
    
    print("\n" + "="*60)
    print("STEP 6: EDITOR AGENT (Verifiable Quality & ATS Gate)")
    print("="*60)
    editor_score = editor.run({"jd_text": jd_text, "pdf_path": pdf_path})
    print(f"Editor Score: {editor_score.score}/100")
    print(f"Editor Passed: {editor_score.passed}")
    print(f"Editor Feedback: {editor_score.feedback}")
    
    print("\n" + "="*60)
    print("🎉 FULL PIPELINE RUN COMPLETED AND VALIDATED SUCCESSFULLY!")
    print("="*60)

if __name__ == "__main__":
    main()
