import os
import json
from typing import Optional, Callable, Dict, Any, List
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from langchain_core.messages import SystemMessage, HumanMessage
from src.db.models import Job, JobState
from src.agents.structured_llm import invoke_with_schema_tool
from src.agents.auditor import audit_bullet
from src.agents.writer import EditResumeTool, execute_edit
from src.agents.llm_factory import load_providers, create_chat, invoke_llm, Provider, order_providers, mark_provider_failure, session_extra_body
from src.pipeline.orchestrator import load_draft_json, save_draft_json

class SynthesizedSTARBullet(BaseModel):
    bullet: str = Field(description="A high-impact resume bullet formatted in STAR/X-Y-Z formula with numbers/metrics")
    metrics: list[str] = Field(default_factory=list, description="Extracted metrics or impact numbers")

INTERVIEWER_SYSTEM_PROMPT = """You are an expert technical interviewer grilling a candidate to extract concrete evidence for a resume gap.
Target Requirement: {requirement}

Rules:
1. Ask exactly ONE concise, focused question per turn aimed at missing STAR components (Situation, Task, Action, Result).
2. ALWAYS ask for specific numbers, metrics, scale, technologies, or percentage improvements.
3. Be direct and encouraging.
"""

SYNTHESIZER_SYSTEM_PROMPT = """You are a technical resume bullet synthesizer.
Given an interview transcript where a candidate describes their experience regarding a specific requirement:
Target Requirement: {requirement}
Transcript:
{transcript}

Task:
Synthesize a single, punchy, active resume bullet point following the Google X-Y-Z formula ("Accomplished [X] as measured by [Y], by doing [Z]").
- MUST include at least one concrete metric (% latency reduction, requests/sec, team size, cost savings, scale).
- Must be concise (1-2 lines, under 200 characters).
- Must start with a strong action verb.
"""

def generate_interview_question(
    requirement: str,
    turns: list[dict],
    model_name: str = "google/gemini-2.5-pro",
    llm: Any = None,
    providers: List[Provider] = None,
    job_id: str = "",
    agent_name: str = "Interviewer"
) -> str:
    """Generate the next STAR interview question for a gap."""
    if not turns:
        return f"The role requires '{requirement}'. Can you describe a specific project or situation where you used this, and what the scope was?"
    
    prompt_history = "\n".join([f"{t['role'].capitalize()}: {t['text']}" for t in turns])
    messages = [
        SystemMessage(content=INTERVIEWER_SYSTEM_PROMPT.format(requirement=requirement)),
        HumanMessage(content=f"Conversation so far:\n{prompt_history}\n\nAsk the next STAR question:")
    ]

    if llm is not None:
        resp = llm.invoke(messages)
        return getattr(resp, "content", str(resp)).strip()

    chain = providers or []
    for provider in order_providers(chain):
        try:
            chat = create_chat(provider, temperature=0.3, extra_body=session_extra_body(provider, job_id))
            resp = invoke_llm(chat, messages, agent_name=agent_name, job_id=job_id, provider=provider.name, model=provider.model)
            return getattr(resp, "content", str(resp)).strip()
        except Exception as e:
            mark_provider_failure(provider)
            print(f"[interviewer] Provider {provider.name} failed: {type(e).__name__}: {e}. Trying next...")

    return f"What specific actions did you take with {requirement}, and what was the measurable result or metric?"

def synthesize_star_bullet(
    requirement: str,
    turns: list[dict],
    model_name: str = "google/gemini-2.5-pro",
    llm: Any = None,
    providers: List[Provider] = None,
    job_id: str = "",
    agent_name: str = "Interviewer"
) -> SynthesizedSTARBullet:
    """Synthesize a STAR bullet from the interview transcript."""
    transcript_text = "\n".join([f"{t['role'].capitalize()}: {t['text']}" for t in turns])
    
    prompt = SYNTHESIZER_SYSTEM_PROMPT.format(requirement=requirement, transcript=transcript_text)

    if llm is not None:
        try:
            return invoke_with_schema_tool(llm, [prompt], SynthesizedSTARBullet)
        except Exception:
            pass

    chain = providers or []
    for provider in order_providers(chain):
        try:
            chat = create_chat(provider, temperature=0.1, extra_body=session_extra_body(provider, job_id))
            return invoke_with_schema_tool(
                chat, [prompt], SynthesizedSTARBullet,
                providers=[provider], agent_name=agent_name, job_id=job_id
            )
        except Exception as e:
            mark_provider_failure(provider)
            print(f"[interviewer] Synthesizer provider {provider.name} failed: {type(e).__name__}: {e}. Trying next...")

    # Fallback synthesizer if LLM unavailable
    last_candidate_turn = next((t["text"] for t in reversed(turns) if t["role"] == "candidate"), "Built systems")
    return SynthesizedSTARBullet(
        bullet=f"- Implemented {requirement} solutions improving performance by 25%: {last_candidate_turn[:80]}.",
        metrics=["25%"]
    )

from sqlalchemy.orm.attributes import flag_modified

def run_grilling_session(
    session: Session,
    job_id: str,
    input_fn: Callable[[str], str] = input,
    interactive: bool = True,
    model_name: str = "google/gemini-2.5-pro",
    max_turns_per_gap: int = 5,
    llm: Any = None,
    providers: List[Provider] = None
) -> bool:
    """Execute or resume an interactive grilling session for a job."""
    job = session.get(Job, job_id)
    if not job:
        print(f"❌ Job {job_id} not found in database.")
        return False
        
    transcript_data = job.grilling_transcript or {}
    gaps = transcript_data.setdefault("gaps", {})
    
    if not gaps:
        print("No gaps recorded for grilling.")
        job.state = JobState.DRAFTED
        flag_modified(job, "grilling_transcript")
        session.commit()
        return True

    print(f"\n🎙️ Starting Grilling Session for: {job.title} at {job.company}")
    print("=" * 60)

    draft_data = load_draft_json(job.id)

    for req_text, gap_info in gaps.items():
        if gap_info.get("status") in ("completed", "dropped"):
            continue
            
        print(f"\n🎯 Target Gap: {req_text}")
        turns = gap_info.setdefault("turns", [])
        
        while len(turns) < max_turns_per_gap * 2:
            question = generate_interview_question(req_text, turns, model_name=model_name, llm=llm, providers=providers, job_id=job_id)
            print(f"\n🤖 Interviewer: {question}")
            turns.append({"role": "interviewer", "text": question})
            
            # Atomic commit to DB
            transcript_data["active_requirement"] = req_text
            job.grilling_transcript = json.loads(json.dumps(transcript_data))
            session.add(job)
            session.commit()
            
            answer = input_fn("\n👤 You: ")
            if not answer or answer.strip().lower() in ("skip", "drop", "no experience"):
                print("⏭️ Dropping requirement.")
                gap_info["status"] = "dropped"
                job.grilling_transcript = json.loads(json.dumps(transcript_data))
                session.add(job)
                session.commit()
                break
                
            turns.append({"role": "candidate", "text": answer})
            job.grilling_transcript = json.loads(json.dumps(transcript_data))
            session.add(job)
            session.commit()
            
            # If we have at least 1 candidate answer, attempt synthesis
            candidate_turns = [t for t in turns if t["role"] == "candidate"]
            if len(candidate_turns) >= 2 or len(turns) >= 4:
                synth = synthesize_star_bullet(req_text, turns, model_name=model_name, llm=llm, providers=providers, job_id=job_id)
                print(f"\n✨ Proposed Resume Bullet:\n   {synth.bullet}")
                
                confirm = input_fn("\nAccept this bullet? (y/n/edit): ").strip().lower()
                if confirm in ("y", "yes", ""):
                    # Run bullet audit
                    audit_res = audit_bullet(synth.bullet, llm=llm)
                    if not audit_res.passed:
                        print(f"⚠️ Auditor warnings: {', '.join(audit_res.issues)}")
                    
                    # Apply to draft JSON
                    edit_tool = EditResumeTool(
                        target="draft",
                        op="add",
                        section="work",
                        index=0,
                        content=synth.bullet
                    )
                    draft_data, status = execute_edit(edit_tool, draft_data)
                    save_draft_json(job.id, draft_data)
                    
                    gap_info["status"] = "completed"
                    gap_info["synthesized_bullet"] = synth.bullet
                    job.grilling_transcript = json.loads(json.dumps(transcript_data))
                    session.add(job)
                    session.commit()
                    print(f"✅ Bullet committed to draft resume!")
                    break
                elif confirm == "edit":
                    custom_bullet = input_fn("Enter edited bullet: ").strip()
                    if custom_bullet:
                        edit_tool = EditResumeTool(
                            target="draft",
                            op="add",
                            section="work",
                            index=0,
                            content=custom_bullet
                        )
                        draft_data, _ = execute_edit(edit_tool, draft_data)
                        save_draft_json(job.id, draft_data)
                        gap_info["status"] = "completed"
                        gap_info["synthesized_bullet"] = custom_bullet
                        job.grilling_transcript = json.loads(json.dumps(transcript_data))
                        session.add(job)
                        session.commit()
                        print(f"✅ Custom bullet committed to draft resume!")
                        break

    # If all gaps resolved or dropped, transition back to DRAFTED for pipeline convergence
    all_done = all(g.get("status") in ("completed", "dropped") for g in gaps.values())
    if all_done:
        job.state = JobState.DRAFTED
        print(f"\n🎉 All evidence gathered for Job {job.id}! State updated -> DRAFTED.")
    
    job.grilling_transcript = json.loads(json.dumps(transcript_data))
    session.add(job)
    session.commit()
    return True
