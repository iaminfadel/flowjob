"""Deep GrillingSession module managing human-in-the-loop evidence extraction,
transcript state machine, STAR bullet synthesis, hygiene auditing, and draft commits.
"""

from __future__ import annotations

import json
from typing import Any, Callable, List, Optional
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session

from src.agents.auditor import audit_bullet
from src.agents.grilling_models import GapRecord, GapStatus, GrillingTranscript, TurnRecord
from src.agents.llm_factory import Provider, load_providers
from src.agents.writer import EditResumeTool, execute_edit
from src.db.models import Job, JobState
from src.storage.document_store import DocumentStore, DiskDocumentStore


class GrillingSession:
    """Deep module encapsulating the complete evidence gathering lifecycle for one job."""

    def __init__(
        self,
        session: Session,
        job: Job,
        doc_store: Optional[DocumentStore] = None,
        providers: Optional[List[Provider]] = None,
        llm: Any = None,
        model_name: str = "google/gemini-2.5-pro",
    ):
        self.session = session
        self.job = job
        self.doc_store = doc_store or DiskDocumentStore()
        self.providers = providers or load_providers()
        self.llm = llm
        self.model_name = model_name

        # Parse or initialize transcript
        raw_transcript = job.grilling_transcript or {}
        if isinstance(raw_transcript, dict):
            # Normalize dictionary into model
            normalized_gaps = {}
            for req, data in raw_transcript.get("gaps", {}).items():
                if isinstance(data, dict):
                    normalized_gaps[req] = GapRecord(
                        requirement=req,
                        must_have=data.get("must_have", True),
                        status=GapStatus(data.get("status", "pending")),
                        turns=[TurnRecord(**t) if isinstance(t, dict) else TurnRecord(role="system", text=str(t)) for t in data.get("turns", [])],
                        synthesized_bullet=data.get("synthesized_bullet"),
                        note=data.get("note", ""),
                    )
            self.transcript = GrillingTranscript(
                active_requirement=raw_transcript.get("active_requirement"),
                gaps=normalized_gaps,
            )
        else:
            self.transcript = GrillingTranscript()

    def _persist(self) -> None:
        """Commit transcript changes atomically to SQLite."""
        self.job.grilling_transcript = self.transcript.model_dump()
        flag_modified(self.job, "grilling_transcript")
        self.session.add(self.job)
        self.session.commit()

    def get_evidence_summary(self) -> List[str]:
        """Return list of candidate-verified evidence bullets for completed gaps."""
        evidence = []
        for req, gap in self.transcript.gaps.items():
            if gap.status == GapStatus.COMPLETED and gap.synthesized_bullet:
                evidence.append(f"- {req}: {gap.synthesized_bullet}")
        return evidence

    def init_gaps_from_critic(self, pending_reqs: list) -> None:
        """Initialize or merge pending requirements flagged by the Per-run Critic."""
        for r in pending_reqs:
            req_text = getattr(r, "requirement", str(r))
            must_have = getattr(r, "must_have", True)
            if req_text not in self.transcript.gaps:
                self.transcript.gaps[req_text] = GapRecord(
                    requirement=req_text,
                    must_have=must_have,
                    status=GapStatus.PENDING,
                )
        if pending_reqs and not self.transcript.active_requirement:
            first_req = getattr(pending_reqs[0], "requirement", str(pending_reqs[0]))
            self.transcript.active_requirement = first_req
        self._persist()

    def is_finished(self) -> bool:
        """True if all gaps are completed or dropped."""
        if not self.transcript.gaps:
            return True
        return all(g.status in (GapStatus.COMPLETED, GapStatus.DROPPED) for g in self.transcript.gaps.values())

    def run_cli(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
        max_turns_per_gap: int = 5,
    ) -> bool:
        """Execute full interactive grilling session via standard or custom I/O callbacks."""
        from src.agents.interviewer import generate_interview_question, synthesize_star_bullet

        if not self.transcript.gaps:
            output_fn("No gaps recorded for grilling.")
            self.job.state = JobState.DRAFTED
            self.session.add(self.job)
            self.session.commit()
            return True

        output_fn(f"\n🎙️ Starting Grilling Session for: {self.job.title} at {self.job.company}")
        output_fn("=" * 60)

        draft_data = self.doc_store.load_draft(self.job.id)

        for req_text, gap in self.transcript.gaps.items():
            if gap.status in (GapStatus.COMPLETED, GapStatus.DROPPED):
                continue

            output_fn(f"\n🎯 Target Gap: {req_text}")
            self.transcript.active_requirement = req_text
            gap.status = GapStatus.ACTIVE
            self._persist()

            turns_list = [{"role": t.role, "text": t.text} for t in gap.turns]

            while len(turns_list) < max_turns_per_gap * 2:
                question = generate_interview_question(
                    req_text,
                    turns_list,
                    model_name=self.model_name,
                    llm=self.llm,
                    providers=self.providers,
                    job_id=self.job.id,
                )
                output_fn(f"\n🤖 Interviewer: {question}")
                gap.turns.append(TurnRecord(role="interviewer", text=question))
                turns_list.append({"role": "interviewer", "text": question})
                self._persist()

                answer = input_fn("\n👤 You: ")
                if not answer or answer.strip().lower() in ("skip", "drop", "no experience"):
                    output_fn("⏭️ Dropping requirement.")
                    gap.status = GapStatus.DROPPED
                    self._persist()
                    break

                gap.turns.append(TurnRecord(role="candidate", text=answer))
                turns_list.append({"role": "candidate", "text": answer})
                self._persist()

                candidate_turns = [t for t in turns_list if t["role"] == "candidate"]
                if len(candidate_turns) >= 2 or len(turns_list) >= 4:
                    synth = synthesize_star_bullet(
                        req_text,
                        turns_list,
                        model_name=self.model_name,
                        llm=self.llm,
                        providers=self.providers,
                        job_id=self.job.id,
                    )
                    output_fn(f"\n✨ Proposed Resume Bullet:\n   {synth.bullet}")

                    confirm = input_fn("\nAccept this bullet? (y/n/edit): ").strip().lower()
                    if confirm in ("y", "yes", ""):
                        audit_res = audit_bullet(synth.bullet, llm=self.llm)
                        if not audit_res.passed:
                            output_fn(f"⚠️ Auditor warnings: {", ".join(audit_res.issues)}")

                        edit_tool = EditResumeTool(
                            target="draft",
                            op="add",
                            section="work",
                            index=0,
                            content=synth.bullet,
                        )
                        draft_data, _ = execute_edit(edit_tool, draft_data)
                        self.doc_store.save_draft(self.job.id, draft_data)

                        gap.status = GapStatus.COMPLETED
                        gap.synthesized_bullet = synth.bullet
                        self._persist()
                        output_fn("✅ Bullet committed to draft resume!")
                        break
                    elif confirm == "edit":
                        custom_bullet = input_fn("Enter edited bullet: ").strip()
                        if custom_bullet:
                            edit_tool = EditResumeTool(
                                target="draft",
                                op="add",
                                section="work",
                                index=0,
                                content=custom_bullet,
                            )
                            draft_data, _ = execute_edit(edit_tool, draft_data)
                            self.doc_store.save_draft(self.job.id, draft_data)
                            gap.status = GapStatus.COMPLETED
                            gap.synthesized_bullet = custom_bullet
                            self._persist()
                            output_fn("✅ Custom bullet committed to draft resume!")
                            break

        if self.is_finished():
            self.job.state = JobState.DRAFTED
            output_fn(f"\n🎉 All evidence gathered for Job {self.job.id}! State updated -> DRAFTED.")

        self._persist()
        return True
