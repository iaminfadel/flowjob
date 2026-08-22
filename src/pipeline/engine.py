"""Deep PipelineCycleEngine module.

Orchestrates a single deterministic pipeline cycle: Scout -> Retry -> Analyst ->
Tailor -> Evidence Loop -> Editor -> Approval/Application over SQLite job state.
"""

from __future__ import annotations

import os
import subprocess
import time
import traceback
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlmodel import Session, select

from src.agents.runner import AgentRunner
from src.agents.scout import scrape_linkedin_jobs
from src.db.models import ErrorRecord, Job, JobState, PipelineRun
from src.db.store import is_manual_application, pipeline_only
from src.storage.document_store import DiskDocumentStore, DocumentStore
from src.utils.resume_parser import parse_master_resume


from src.pipeline.types import CycleSummaryResult, SessionHealthError  # noqa: F401


def default_notify_user(title: str, message: str) -> None:
    try:
        subprocess.run(["notify-send", title, message], check=False)
    except Exception:
        print(f"[NOTIFICATION] {title}: {message}")


def default_prompt_approval(job: Job) -> bool:
    print(f"Prompting user for job: {job.title} at {job.company}")
    default_notify_user("FlowJob: Job ready for approval!", f"{job.title} at {job.company}")
    try:
        response = input("Do you approve applying to this job? (y/n): ")
        return response.strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


class PipelineCycleEngine:
    """Deep engine encapsulating cycle execution, stage transitions, DLQ, and retry logic."""

    def __init__(
        self,
        config: Optional[Any] = None,
        agents: Optional[Dict[str, Any]] = None,
        doc_store: Optional[DocumentStore] = None,
        approval_fn: Optional[Callable[[Job], bool]] = None,
        wait_fn: Optional[Callable[[str], None]] = None,
        notify_fn: Optional[Callable[[str, str], None]] = None,
    ):
        # config is a FlowJobConfig from production hosts; tests may pass a
        # plain dict (accessed via .get below). Normalized once here.
        if config is None:
            self.config: Any = {}
        elif isinstance(config, dict):
            self.config = config
        else:
            self.config = config.model_dump()
        self.agents = agents or {}
        self.doc_store = doc_store or DiskDocumentStore()
        self.approval_fn = approval_fn or default_prompt_approval
        self.wait_fn = wait_fn
        self.notify_fn = notify_fn or default_notify_user

    def _log_job_error(self, session: Session, agent_name: str, error: Exception, job_id: str) -> int:
        statement = select(ErrorRecord).where(ErrorRecord.job_id == job_id)
        error_rec = session.exec(statement).first()

        if error_rec:
            error_rec.error_type = type(error).__name__
            error_rec.stack_trace = traceback.format_exc()
            error_rec.timestamp = datetime.now().isoformat()
            error_rec.retry_count += 1
            error_rec.agent_name = agent_name
        else:
            error_rec = ErrorRecord(
                agent_name=agent_name,
                error_type=type(error).__name__,
                stack_trace=traceback.format_exc(),
                job_id=job_id,
                timestamp=datetime.now().isoformat(),
                retry_count=1,
            )
        session.add(error_rec)
        return error_rec.retry_count

    def _handle_job_failure(
        self,
        session: Session,
        agent_name: str,
        error: Exception,
        job: Job,
        fallback_state: JobState = JobState.FAILED,
        force_fail: bool = False,
    ) -> None:
        print(f"Error applying to job {job.id}: {error}")
        session.rollback()

        retry_count = self._log_job_error(session, agent_name, error, job.id)

        if force_fail or retry_count >= 3:
            print(f"Job {job.id} failed 3 times (or forced). Moving to DLQ (FAILED).")
            job.state = JobState.FAILED
        else:
            print(f"Job {job.id} transient error ({retry_count}/3). Moving to {fallback_state}.")
            job.state = fallback_state

        session.add(job)
        session.commit()

    def _execute_stage_step(
        self,
        session: Session,
        agent_name: str,
        job: Job,
        fallback_state: JobState,
        step_func: Callable[[Job], None],
    ) -> bool:
        """Executes a single step for a job within atomic transaction boundaries."""
        try:
            step_func(job)
            session.add(job)
            session.commit()
            return True
        except RuntimeError as e:
            if str(e) == "CAPTCHA_DETECTED":
                print(f"CAPTCHA detected for job {job.id}. Halting pipeline immediately.")
                self._handle_job_failure(session, agent_name, e, job, fallback_state, force_fail=True)
                return False
            else:
                self._handle_job_failure(session, agent_name, e, job, fallback_state)
                return True
        except Exception as e:
            self._handle_job_failure(session, agent_name, e, job, fallback_state)
            return True

    def process_scout(self, session: Session, url: Optional[str] = None) -> int:
        """Scouts for new job postings and adds them to SQLite."""
        print("Scouting for jobs...")
        jobs = []
        if url:
            jobs = scrape_linkedin_jobs(url, max_jobs=1)
        else:
            scout_config = self.config.get("scout", {})
            max_scrape = scout_config.get("max_scrape_per_run", 30)
            time_filter = scout_config.get("time_filter", "any")

            time_map = {
                "past_24_hours": "r86400",
                "past_week": "r604800",
                "past_month": "r2592000",
            }

            try:
                metadata, _ = parse_master_resume("master_resume.md")
                target_roles = metadata.preferences.get("target_roles", [])
                work_types = metadata.preferences.get("work_types", [])
                target_locations = metadata.preferences.get("target_locations", [])

                queries = []
                for role in target_roles:
                    for loc in target_locations:
                        queries.append({"role": role, "location": loc, "wt": None})
                    for wt in work_types:
                        queries.append({"role": role, "location": "Worldwide", "wt": wt})

                if not queries:
                    queries = [{"role": "software engineer", "location": "Worldwide", "wt": None}]
            except Exception as e:
                print(f"Failed to parse master_resume.md for scout queries: {e}")
                queries = [{"role": "software engineer", "location": "Worldwide", "wt": None}]

            for q in queries:
                search_url = f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(q['role'])}"
                search_url += f"&location={urllib.parse.quote(q['location'])}"
                if q["wt"]:
                    wt_lower = q["wt"].lower()
                    if "remote" in wt_lower:
                        search_url += "&f_WT=2"
                    elif "hybrid" in wt_lower:
                        search_url += "&f_WT=3"
                    elif "on-site" in wt_lower or "onsite" in wt_lower:
                        search_url += "&f_WT=1"
                search_url += "&f_AL=true"
                if time_filter in time_map:
                    search_url += f"&f_TPR={time_map[time_filter]}"
                jobs.extend(scrape_linkedin_jobs(search_url, max_jobs=max_scrape))

        new_jobs_added = 0
        for j in jobs:
            existing = session.get(Job, j.id)
            if not existing:
                session.add(j)
                new_jobs_added += 1

        session.commit()
        print(f"Scout found {len(jobs)} jobs. {new_jobs_added} are new and added to DB.")
        return new_jobs_added

    def process_retries(self, session: Session) -> int:
        statement = select(ErrorRecord).where(ErrorRecord.retry_count > 0).where(ErrorRecord.retry_count < 3)
        errors = session.exec(statement).all()

        count = 0
        for err in errors:
            job = session.get(Job, err.job_id)
            if not job:
                continue

            if is_manual_application(job):
                continue

            if job.state == JobState.TAILOR_FAIL:
                job.state = JobState.ANALYZED
                count += 1
            elif job.state == JobState.EDIT_FAIL:
                job.state = JobState.DRAFTED
                count += 1
            elif job.state == JobState.FAILED and err.agent_name == "ApplicatorAgent":
                job.state = JobState.PENDING_APPROVAL
                count += 1

            if count > 0:
                session.add(job)

        if count > 0:
            session.commit()
            print(f"Retrying {count} transient errors...")
        return count

    def process_new_jobs(self, session: Session) -> int:
        """Returns transitions count, or -1 when halted (CAPTCHA)."""
        analyst_agent = self.agents.get("analyst")
        if not analyst_agent:
            return 0

        min_fit_score = self.config.get("analyst", {}).get("min_fit_score", 70)
        statement = pipeline_only(select(Job).where(Job.state == JobState.NEW))
        new_jobs = session.exec(statement).all()
        print(f"Found {len(new_jobs)} NEW jobs.")
        transitions = 0

        for job in new_jobs:
            print(f"Analyzing job: {job.title} at {job.company}")

            def _step(j):
                fit_score = analyst_agent.run({"jd_text": j.jd_text}, job_id=j.id, agent_name="AnalystAgent")
                print(f"Fit score: {fit_score.score} - Recommendation: {fit_score.recommendation}")
                j.fit_score = fit_score.score
                if fit_score.score >= min_fit_score:
                    j.state = JobState.ANALYZED
                    print(f"Job {j.id} passed fit threshold. State -> ANALYZED")
                else:
                    j.state = JobState.SKIPPED
                    print(f"Job {j.id} below fit threshold. State -> SKIPPED")

            if not self._execute_stage_step(session, "AnalystAgent", job, JobState.NEW, _step):
                return -1
            transitions += 1
        return transitions

    def process_analyzed_jobs(self, session: Session) -> int:
        """Returns transitions count, or -1 when halted (CAPTCHA)."""
        tailor_agent = self.agents.get("tailor")
        if not tailor_agent:
            return 0

        statement = pipeline_only(select(Job).where(Job.state == JobState.ANALYZED))
        analyzed_jobs = session.exec(statement).all()
        print(f"Found {len(analyzed_jobs)} ANALYZED jobs.")
        transitions = 0

        for job in analyzed_jobs:
            print(f"Tailoring resume for job: {job.title} at {job.company}")

            def _step(j):
                feedback = j.tailor_metadata.get("feedback") if j.tailor_metadata else None
                tailored_resume = tailor_agent.run(
                    jd_text=j.jd_text, feedback=feedback, job_id=job.id, agent_name="TailorAgent"
                )

                if hasattr(tailored_resume, "model_dump"):
                    draft_data = tailored_resume.model_dump()
                elif isinstance(tailored_resume, dict):
                    draft_data = tailored_resume
                else:
                    draft_data = {"content": str(tailored_resume)}

                json_path = self.doc_store.save_draft(j.id, draft_data)
                print(f"Generated tailored resume JSON: {json_path}")
                j.cv_path = json_path
                j.state = JobState.DRAFTED

            if not self._execute_stage_step(session, "TailorAgent", job, JobState.TAILOR_FAIL, _step):
                return -1
            transitions += 1
        return transitions

    def process_evidence_loop(self, session: Session) -> int:
        """Returns jobs processed count, or -1 when halted (CAPTCHA)."""
        critic_agent = self.agents.get("critic")
        writer_agent = self.agents.get("writer")
        if not (critic_agent and writer_agent):
            return 0

        statement = pipeline_only(select(Job).where(Job.state == JobState.DRAFTED))
        drafted_jobs = session.exec(statement).all()
        if not drafted_jobs:
            return 0

        print(f"Found {len(drafted_jobs)} DRAFTED jobs in evidence loop.")
        from src.agents.grilling_session import GrillingSession

        master_metadata = None
        master_resume_text = ""
        try:
            master_metadata, master_resume_text = parse_master_resume("master_resume.md")
        except Exception:
            pass

        writer_cfg = self.config.get("writer", {})
        max_rounds = 3
        if isinstance(writer_cfg, dict):
            max_rounds = writer_cfg.get("max_writer_rounds", 3)
        elif hasattr(writer_cfg, "max_writer_rounds"):
            max_rounds = writer_cfg.max_writer_rounds

        processed = 0
        for job in drafted_jobs:
            if job.cv_path and job.cv_path.endswith(".pdf") and (
                os.path.exists(job.cv_path) or job.cv_path.startswith("memory://")
            ):
                continue

            print(f"Running evidence loop for job: {job.title} at {job.company}")

            def _step(j):
                draft_data = self.doc_store.load_draft(j.id)
                grill_session = GrillingSession(session=session, job=j, doc_store=self.doc_store)
                grill_evidence_lines = grill_session.get_evidence_summary()

                for round_idx in range(max_rounds):
                    coverage_report = critic_agent.run(
                        {
                            "jd_text": j.jd_text,
                            "draft_data": draft_data,
                            "master_resume_path": "master_resume.md",
                            "grilled_evidence": "\n".join(grill_evidence_lines),
                        },
                        job_id=j.id,
                        agent_name="CoverageCritic",
                    )

                    if getattr(coverage_report, "unfixable", False):
                        print(f"Job {j.id} marked UNFIXABLE by critic.")
                        j.state = JobState.UNFIXABLE
                        self.notify_fn("FlowJob", f"Job {j.title} at {j.company} marked UNFIXABLE")
                        return

                    reqs = getattr(coverage_report, "requirements", [])
                    grill_routes = [r for r in reqs if getattr(r, "route", "") == "grill"]
                    fix_routes = [r for r in reqs if getattr(r, "route", "") == "fix"]

                    if grill_routes:
                        transcript_gaps = grill_session.transcript.gaps
                        pending_grills = [
                            r
                            for r in grill_routes
                            if transcript_gaps.get(r.requirement, None) is None
                            or transcript_gaps[r.requirement].status.value not in ("completed", "dropped")
                        ]
                        if pending_grills:
                            print(f"Job {j.id} has {len(pending_grills)} gaps requiring evidence grilling.")
                            j.state = JobState.NEEDS_EVIDENCE
                            grill_session.init_gaps_from_critic(pending_grills)
                            first_gap = getattr(pending_grills[0], "requirement", str(pending_grills[0]))
                            self.notify_fn("FlowJob Evidence Needed", f"Job {j.title} needs evidence: {first_gap}")
                            return
                        print(f"Job {j.id} grilling requirements already resolved. Continuing.")

                    if fix_routes:
                        print(f"Job {j.id} round {round_idx+1}: Writer applying fixes for {len(fix_routes)} requirements.")
                        draft_data, plan = writer_agent.run_round(
                            jd_text=j.jd_text,
                            draft_data=draft_data,
                            coverage_report=coverage_report.model_dump()
                            if hasattr(coverage_report, "model_dump")
                            else coverage_report,
                            master_resume_text=master_resume_text,
                            job_id=j.id,
                            agent_name="Writer",
                        )
                        self.doc_store.save_draft(j.id, draft_data)
                        edits = plan.get("edits", []) if isinstance(plan, dict) else getattr(plan, "edits", [])
                        if not edits:
                            print("Writer made 0 edits; converging early.")
                            break
                    else:
                        print(f"Job {j.id} evidence loop converged!")
                        break

                pdf_path = self.doc_store.compile_document(j.id, master_metadata, draft_data)
                j.cv_path = pdf_path
                print(f"Generated PDF for converged draft: {pdf_path}")

            if not self._execute_stage_step(session, "EvidenceLoop", job, JobState.TAILOR_FAIL, _step):
                return -1
            processed += 1
        return processed

    def process_drafted_jobs(self, session: Session) -> int:
        """Returns transitions count, or -1 when halted (CAPTCHA)."""
        editor_agent = self.agents.get("editor")
        if not editor_agent:
            return 0

        statement = pipeline_only(select(Job).where(Job.state == JobState.DRAFTED))
        drafted_jobs = session.exec(statement).all()
        print(f"Found {len(drafted_jobs)} DRAFTED jobs.")
        transitions = 0

        for job in drafted_jobs:
            print(f"Editing resume for job: {job.title} at {job.company}")

            def _step(j):
                pdf_path = j.cv_path if (j.cv_path and j.cv_path.endswith(".pdf")) else None
                if not pdf_path or not (os.path.exists(pdf_path) or pdf_path.startswith("memory://")):
                    draft_data = self.doc_store.load_draft(j.id)
                    try:
                        master_metadata, _ = parse_master_resume("master_resume.md")
                    except Exception:
                        master_metadata = None
                    pdf_path = self.doc_store.compile_document(j.id, master_metadata, draft_data)
                    j.cv_path = pdf_path

                edit_score = editor_agent.run(
                    {"jd_text": j.jd_text, "pdf_path": pdf_path}, job_id=job.id, agent_name="EditorAgent"
                )
                print(f"Editor score: {edit_score.score} - Passed: {edit_score.passed}")

                if edit_score.passed:
                    j.state = JobState.EDITED
                    j.tailor_metadata = {}
                    print(f"Job {j.id} passed Editor. State -> EDITED")
                else:
                    retries = j.tailor_metadata.get("retries", 0) if j.tailor_metadata else 0
                    if retries < 1:
                        print(f"Job {j.id} failed Editor. Retrying Tailor. Feedback: {edit_score.feedback}")
                        j.tailor_metadata = {"retries": retries + 1, "feedback": edit_score.feedback}
                        j.state = JobState.ANALYZED
                    else:
                        print(f"Job {j.id} failed Editor. Max retries reached. State -> EDIT_FAIL")
                        j.state = JobState.EDIT_FAIL

            if not self._execute_stage_step(session, "EditorAgent", job, JobState.DRAFTED, _step):
                return -1
            transitions += 1
        return transitions

    def process_edited_jobs(self, session: Session) -> int:
        statement = pipeline_only(select(Job).where(Job.state == JobState.EDITED))
        edited_jobs = session.exec(statement).all()
        print(f"Found {len(edited_jobs)} EDITED jobs.")

        for job in edited_jobs:
            job.state = JobState.PENDING_APPROVAL
            print(f"Job {job.id} moved to PENDING_APPROVAL.")
            session.add(job)
        session.commit()
        return len(edited_jobs)

    def process_pending_approval_jobs(self, session: Session) -> int:
        """Returns jobs processed count, or -1 when halted (CAPTCHA)."""
        applicator_agent = self.agents.get("applicator")
        if not applicator_agent:
            return 0

        statement = pipeline_only(select(Job).where(Job.state == JobState.PENDING_APPROVAL))
        pending_jobs = session.exec(statement).all()
        if pending_jobs:
            print(f"Found {len(pending_jobs)} PENDING_APPROVAL jobs.")

        processed = 0
        for job in pending_jobs:
            def _step(j):
                if self.approval_fn(j):
                    success = applicator_agent.run(j, self.wait_fn)
                    if success:
                        j.state = JobState.APPLIED
                        print(f"Job {j.id} successfully APPLIED.")
                    else:
                        j.state = JobState.FAILED
                        print(f"Job {j.id} application FAILED.")
                else:
                    print(f"Job {j.id} skipped by user.")
                    j.state = JobState.SKIPPED

            if not self._execute_stage_step(session, "ApplicatorAgent", job, JobState.FAILED, _step):
                return -1
            processed += 1
        return processed

    @staticmethod
    def _state_counts(session: Session) -> dict[str, int]:
        """Absolute counts of the summary-tracked states."""
        tracked = (JobState.APPLIED, JobState.FAILED, JobState.SKIPPED, JobState.UNFIXABLE)
        return {
            state.value: len(
                session.exec(select(Job).where(Job.state == state)).all()
            )
            for state in tracked
        }

    @staticmethod
    def _needs_evidence_count(session: Session) -> int:
        return len(session.exec(select(Job).where(Job.state == JobState.NEEDS_EVIDENCE)).all())

    def _halted(self, t0: float) -> CycleSummaryResult:
        return CycleSummaryResult(duration_s=time.monotonic() - t0, halted_reason="CAPTCHA_DETECTED")

    def run_cycle(
        self,
        session: Session,
        url: Optional[str] = None,
        dry_run: bool = False,
    ) -> CycleSummaryResult:
        """Executes a full deterministic pipeline cycle."""
        t0 = time.monotonic()
        before = self._state_counts(session)
        print(f"Pipeline cycle started with url={url} and dry_run={dry_run}")

        # NOTE: the LinkedIn session-health probe lives at the HOST layer
        # (orchestrator.run_pipeline / watch hosts) — the engine assumes a
        # healthy session and never launches a browser itself.

        # Stage 1: Scout
        jobs_scouted = self.process_scout(session, url)

        # Stage 2: Retries
        self.process_retries(session)

        # Stage 3: Analyst
        jobs_analyzed = self.process_new_jobs(session)
        if jobs_analyzed < 0:
            return self._halted(t0)

        # Stage 4: Tailor
        jobs_tailored = self.process_analyzed_jobs(session)
        if jobs_tailored < 0:
            return self._halted(t0)

        # Stage 5: Evidence Loop (Critic & Writer & Grilling)
        evidence_processed = self.process_evidence_loop(session)
        if evidence_processed < 0:
            return self._halted(t0)

        # Stage 6: Editor
        jobs_edited = self.process_drafted_jobs(session)
        if jobs_edited < 0:
            return self._halted(t0)

        # Stage 7: Edited -> Pending Approval
        moved_to_approval = self.process_edited_jobs(session)

        # Stage 8: Applicator
        applied_this_cycle = 0
        if not dry_run:
            processed = self.process_pending_approval_jobs(session)
            if processed < 0:
                return self._halted(t0)
            applied_this_cycle = processed

            run_record = PipelineRun(timestamp=datetime.now().isoformat(), success=True)
            session.add(run_record)
            session.commit()

        duration = time.monotonic() - t0
        after = self._state_counts(session)
        counts_delta = {k: after[k] - v for k, v in before.items()}
        return CycleSummaryResult(
            duration_s=duration,
            jobs_scouted=jobs_scouted,
            jobs_analyzed=max(jobs_analyzed, 0),
            jobs_tailored=max(jobs_tailored, 0),
            jobs_needs_evidence=self._needs_evidence_count(session),
            jobs_edited=moved_to_approval,
            jobs_applied=max(counts_delta.get("APPLIED", 0), applied_this_cycle),
            jobs_failed=counts_delta.get("FAILED", 0),
            jobs_skipped=counts_delta.get("SKIPPED", 0),
            jobs_unfixable=counts_delta.get("UNFIXABLE", 0),
            halted_reason=None,
            counts_delta=counts_delta,
        )
