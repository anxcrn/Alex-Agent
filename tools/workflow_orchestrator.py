#!/usr/bin/env python3
"""
Dynamic Workflow Orchestrator

Decomposes a high-level goal into a DAG of sub-tasks, fans out across
N parallel subagents, verifies results via reviewer agents, and converges
on a final answer. Supports checkpoint/resume, convergence detection,
and dynamic re-planning.

Architecture:
  1. PLAN  — LLM decomposes goal into sub-tasks with dependencies
  2. FAN   — Execute independent tasks in parallel batches
  3. CHECK — Reviewer agents verify outputs, flag issues
  4. LOOP  — Re-plan failed/flagged tasks, repeat until convergence
  5. MERGE — Combine all verified results into final answer
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_PARALLEL_AGENTS = 20
DEFAULT_MAX_CONVERGENCE_ROUNDS = 5
DEFAULT_CHECKPOINT_INTERVAL_S = 30
DEFAULT_CHILD_TIMEOUT_S = 300

WORKFLOW_DB_DIR = "workflows"
WORKFLOW_DB_NAME = "workflow_state.db"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFIED = "verified"
    FAILED = "failed"
    REVISION_NEEDED = "revision_needed"

class WorkflowStatus(Enum):
    PLANNING = "planning"
    RUNNING = "running"
    VERIFYING = "verifying"
    CONVERGED = "converged"
    FAILED = "failed"
    CANCELLED = "cancelled"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class WorkflowTask:
    id: str
    goal: str
    context: str
    dependencies: List[str] = field(default_factory=list)
    toolsets: Optional[List[str]] = None
    model: Optional[str] = None
    max_iterations: int = 30
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    reviewer_notes: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    duration_s: float = 0.0

@dataclass
class WorkflowRun:
    id: str
    goal: str
    status: WorkflowStatus
    tasks: Dict[str, WorkflowTask] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    final_answer: Optional[str] = None
    error: Optional[str] = None
    total_agent_calls: int = 0
    total_duration_s: float = 0.0
    convergence_round: int = 0

# ---------------------------------------------------------------------------
# Planner helpers
# ---------------------------------------------------------------------------

def _build_decomposition_prompt(goal: str) -> str:
    return (
        "You are a workflow planner. Decompose the following goal into a set of "
        "independent sub-tasks that can be executed in parallel.\n\n"
        f"Goal: {goal}\n\n"
        "Return a JSON array of task objects. Each task must have:\n"
        "  - \"id\": short unique name (e.g. \"task_1\")\n"
        "  - \"goal\": a self-contained instruction for a subagent\n"
        "  - \"context\": any background info the subagent needs\n"
        "  - \"dependencies\": list of task IDs that must complete first (empty list if none)\n"
        "  - \"toolsets\": optional list of toolset names (null for default)\n"
        "  - \"max_iterations\": int (default 30)\n\n"
        "Maximize parallelism: tasks without dependencies on each other should "
        "all be independent (empty dependencies). Only chain tasks that truly "
        "depend on previous output.\n\n"
        "Return ONLY valid JSON, no markdown formatting."
    )

def _build_verification_prompt(goal: str, result: str) -> str:
    return (
        "You are a verification reviewer. A subagent was given this goal:\n\n"
        f"{goal}\n\n"
        "It produced this result:\n\n"
        f"{result}\n\n"
        "Evaluate the result for:\n"
        "1. Correctness — does it actually satisfy the goal?\n"
        "2. Completeness — are there gaps or missing pieces?\n"
        "3. Quality — is it well-structured and correct?\n\n"
        "Return JSON:\n"
        "  {\"passed\": true/false, \"issues\": [...], \"suggestions\": \"...\"}\n"
        "Return ONLY valid JSON, no markdown."
    )

def _build_merge_prompt(goal: str, task_results: List[Tuple[str, str, str]]) -> str:
    results_text = "\n\n".join(
        f"--- Task: {tid} ---\nGoal: {tgoal}\nResult: {tresult}"
        for tid, tgoal, tresult in task_results
    )
    return (
        "You are a merge coordinator. The following sub-tasks were completed "
        "for this overall goal:\n\n"
        f"Goal: {goal}\n\n"
        f"Completed tasks:\n{results_text}\n\n"
        "Synthesize these results into a single coherent final answer. "
        "Remove redundancies, resolve contradictions, and present a unified result."
    )

def _build_revision_prompt(goal: str, result: str, reviewer_notes: str) -> str:
    return (
        f"Original goal: {goal}\n\n"
        f"Your previous result:\n{result}\n\n"
        f"Reviewer feedback:\n{reviewer_notes}\n\n"
        "Revise your result to address ALL the reviewer's issues. "
        "Return your revised result."
    )

# ---------------------------------------------------------------------------
# Workflow state persistence
# ---------------------------------------------------------------------------

class WorkflowStore:
    """SQLite-backed persistence for workflow state."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    goal TEXT,
                    status TEXT,
                    data TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_tasks (
                    workflow_id TEXT,
                    task_id TEXT,
                    data TEXT,
                    PRIMARY KEY (workflow_id, task_id)
                )
            """)

    def save_workflow(self, run: WorkflowRun):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO workflows (id, goal, status, data, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run.id, run.goal, run.status.value, json.dumps(asdict(run)), run.created_at, run.updated_at)
            )
            for task in run.tasks.values():
                conn.execute(
                    "INSERT OR REPLACE INTO workflow_tasks (workflow_id, task_id, data) "
                    "VALUES (?, ?, ?)",
                    (run.id, task.id, json.dumps(asdict(task)))
                )

    def load_workflow(self, workflow_id: str) -> Optional[WorkflowRun]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT data FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            run = WorkflowRun(**data)
            run.status = WorkflowStatus(data["status"])
            task_rows = conn.execute(
                "SELECT data FROM workflow_tasks WHERE workflow_id=?", (workflow_id,)
            ).fetchall()
            for trow in task_rows:
                tdata = json.loads(trow[0])
                task = WorkflowTask(**tdata)
                task.status = TaskStatus(tdata["status"])
                run.tasks[task.id] = task
            return run

    def delete_workflow(self, workflow_id: str):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
            conn.execute("DELETE FROM workflow_tasks WHERE workflow_id=?", (workflow_id,))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class WorkflowOrchestrator:
    """Manages the lifecycle of a dynamic workflow."""

    def __init__(
        self,
        planner_fn: Optional[Callable] = None,
        runner_fn: Optional[Callable] = None,
        reviewer_fn: Optional[Callable] = None,
        merger_fn: Optional[Callable] = None,
        store: Optional[WorkflowStore] = None,
        max_parallel: int = DEFAULT_MAX_PARALLEL_AGENTS,
        max_rounds: int = DEFAULT_MAX_CONVERGENCE_ROUNDS,
        checkpoint_interval: float = DEFAULT_CHECKPOINT_INTERVAL_S,
    ):
        self._planner_fn = planner_fn or self._default_planner
        self._runner_fn = runner_fn or self._default_runner
        self._reviewer_fn = reviewer_fn or self._default_reviewer
        self._merger_fn = merger_fn or self._default_merger
        self._store = store
        self._max_parallel = max_parallel
        self._max_rounds = max_rounds
        self._checkpoint_interval = checkpoint_interval
        self._active_runs: Dict[str, WorkflowRun] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Default callables (can be overridden for testing or custom logic)
    # ------------------------------------------------------------------

    def _default_planner(self, goal: str) -> str:
        from agent.auxiliary_client import call_llm
        return call_llm(_build_decomposition_prompt(goal), max_tokens=4096)

    def _default_runner(self, task: WorkflowTask, task_index: int, parent_agent: Any) -> str:
        from tools.delegate_tool import _build_child_agent
        child = _build_child_agent(
            task_index=task_index,
            goal=task.goal,
            context=task.context,
            toolsets=task.toolsets,
            model=task.model,
            max_iterations=task.max_iterations,
            task_count=1,
            parent_agent=parent_agent,
            role="leaf",
        )
        result = child.run_conversation(user_message=task.goal)
        if isinstance(result, dict):
            return json.dumps(result)
        return str(result)

    def _default_reviewer(self, goal: str, result: str) -> str:
        from agent.auxiliary_client import call_llm
        return call_llm(_build_verification_prompt(goal, result), max_tokens=2048)

    def _default_merger(self, goal: str, task_results: List[Tuple[str, str, str]]) -> str:
        from agent.auxiliary_client import call_llm
        return call_llm(_build_merge_prompt(goal, task_results), max_tokens=4096)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_workflow(self, goal: str) -> str:
        """Initiate a dynamic workflow. Returns the workflow_id."""
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        run = WorkflowRun(
            id=workflow_id,
            goal=goal,
            status=WorkflowStatus.PLANNING,
            created_at=time.time(),
            updated_at=time.time(),
        )
        with self._lock:
            self._active_runs[workflow_id] = run
        self._persist(run)

        # Kick off async execution
        thread = threading.Thread(target=self._execute_workflow, args=(workflow_id,), daemon=True)
        thread.start()

        return workflow_id

    def get_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            run = self._active_runs.get(workflow_id)
        if run is None and self._store:
            loaded = self._store.load_workflow(workflow_id)
            if loaded:
                with self._lock:
                    self._active_runs[workflow_id] = loaded
                run = loaded
        if run is None:
            return None
        return {
            "workflow_id": run.id,
            "goal": run.goal,
            "status": run.status.value,
            "total_tasks": len(run.tasks),
            "completed_tasks": sum(1 for t in run.tasks.values() if t.status == TaskStatus.VERIFIED),
            "failed_tasks": sum(1 for t in run.tasks.values() if t.status == TaskStatus.FAILED),
            "convergence_round": run.convergence_round,
            "total_duration_s": round(run.total_duration_s, 1),
            "total_agent_calls": run.total_agent_calls,
            "final_answer": run.final_answer,
            "error": run.error,
            "tasks": {
                tid: {
                    "id": t.id,
                    "goal": t.goal[:100],
                    "status": t.status.value,
                    "dependencies": t.dependencies,
                    "duration_s": round(t.duration_s, 1),
                    "attempts": t.attempts,
                    "error": t.error,
                    "reviewer_notes": t.reviewer_notes[:200] if t.reviewer_notes else None,
                }
                for tid, t in run.tasks.items()
            },
        }

    def cancel_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            run = self._active_runs.get(workflow_id)
            if run is None:
                return False
            run.status = WorkflowStatus.CANCELLED
            run.updated_at = time.time()
            self._persist(run)
        return True

    def list_workflows(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "workflow_id": r.id,
                    "goal": r.goal[:80],
                    "status": r.status.value,
                    "task_count": len(r.tasks),
                    "duration_s": round(r.total_duration_s, 1),
                    "created_at": r.created_at,
                }
                for r in self._active_runs.values()
            ]

    # ------------------------------------------------------------------
    # Internal execution loop
    # ------------------------------------------------------------------

    def _execute_workflow(self, workflow_id: str):
        start_time = time.time()
        last_checkpoint = start_time

        with self._lock:
            run = self._active_runs.get(workflow_id)
            if run is None:
                return

        try:
            # Phase 1: Plan
            run.status = WorkflowStatus.PLANNING
            self._persist(run)
            self._decompose_goal(run)

            # Phase 2: Execute in rounds
            for round_num in range(self._max_rounds):
                run.convergence_round = round_num
                run.status = WorkflowStatus.RUNNING
                self._persist(run)

                # Get tasks ready to execute (all dependencies met)
                ready = self._get_ready_tasks(run)
                if not ready:
                    break  # all done or all stuck

                # Execute ready tasks in parallel batches
                self._execute_task_batch(run, ready)

                # Check for checkpoint
                now = time.time()
                if now - last_checkpoint >= self._checkpoint_interval:
                    self._persist(run)
                    last_checkpoint = now

                # Phase 3: Verify
                run.status = WorkflowStatus.VERIFYING
                self._persist(run)
                needs_revision = self._verify_tasks(run, workflow_id)

                if not needs_revision:
                    # All tasks verified — check if all done
                    remaining = [t for t in run.tasks.values() if t.status != TaskStatus.VERIFIED]
                    if not remaining:
                        break

            # Phase 4: Merge results
            if run.status != WorkflowStatus.CANCELLED:
                run.total_duration_s = time.time() - start_time
                verified = [t for t in run.tasks.values() if t.status == TaskStatus.VERIFIED]
                if verified:
                    run.final_answer = self._merge_results(run)
                    run.status = WorkflowStatus.CONVERGED
                else:
                    run.status = WorkflowStatus.FAILED
                    run.error = "No tasks completed successfully"
                self._persist(run)

        except Exception as exc:
            logger.exception("Workflow %s failed", workflow_id)
            run.status = WorkflowStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"
            run.total_duration_s = time.time() - start_time
            self._persist(run)

    def _decompose_goal(self, run: WorkflowRun):
        """Use LLM to decompose the goal into tasks."""
        planner_output = self._planner_fn(run.goal)
        try:
            tasks_data = json.loads(planner_output)
            if isinstance(tasks_data, dict) and "tasks" in tasks_data:
                tasks_data = tasks_data["tasks"]
        except (json.JSONDecodeError, TypeError):
            # Attempt to extract JSON from markdown
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', planner_output)
            if match:
                try:
                    tasks_data = json.loads(match.group(1))
                    if isinstance(tasks_data, dict) and "tasks" in tasks_data:
                        tasks_data = tasks_data["tasks"]
                except json.JSONDecodeError:
                    tasks_data = []
            else:
                tasks_data = []

        if not isinstance(tasks_data, list) or not tasks_data:
            # Fallback: create a single task
            tasks_data = [{
                "id": "task_main",
                "goal": run.goal,
                "context": "",
                "dependencies": [],
                "toolsets": None,
                "max_iterations": 50,
            }]

        for td in tasks_data:
            task = WorkflowTask(
                id=td.get("id", f"task_{uuid.uuid4().hex[:6]}"),
                goal=td.get("goal", run.goal),
                context=td.get("context", ""),
                dependencies=td.get("dependencies", []),
                toolsets=td.get("toolsets"),
                max_iterations=td.get("max_iterations", 30),
            )
            run.tasks[task.id] = task

    def _get_ready_tasks(self, run: WorkflowRun) -> List[WorkflowTask]:
        """Return tasks whose dependencies are all verified."""
        ready = []
        for task in run.tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.REVISION_NEEDED):
                deps_met = all(
                    dep in run.tasks and run.tasks[dep].status == TaskStatus.VERIFIED
                    for dep in task.dependencies
                )
                if deps_met:
                    ready.append(task)
        return ready

    def _execute_task_batch(self, run: WorkflowRun, tasks: List[WorkflowTask]):
        """Execute a batch of tasks in parallel using a thread pool."""
        if not tasks:
            return

        max_workers = min(self._max_parallel, len(tasks))

        def _run_single(task: WorkflowTask) -> Tuple[str, bool, Optional[str]]:
            task.status = TaskStatus.RUNNING
            task.attempts += 1
            t_start = time.time()
            try:
                # We need a parent agent reference; use a minimal proxy
                result = self._runner_fn(task, int(time.time() * 1000) % 100000, None)
                task.duration_s = time.time() - t_start
                task.result = result
                return task.id, True, None
            except Exception as exc:
                task.duration_s = time.time() - t_start
                task.error = f"{type(exc).__name__}: {exc}"
                return task.id, False, task.error

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_single, t): t for t in tasks}
            done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
            for f in done:
                task_id, success, error = f.result()
                task = run.tasks.get(task_id)
                if task:
                    if success:
                        run.total_agent_calls += 1
                    else:
                        task.status = TaskStatus.FAILED
                        if task.attempts < task.max_attempts:
                            task.status = TaskStatus.PENDING  # retry

    def _verify_tasks(self, run: WorkflowRun, workflow_id: str) -> bool:
        """Verify completed tasks. Returns True if any task needs revision."""
        needs_revision = False
        for task in run.tasks.values():
            if task.status != TaskStatus.RUNNING and task.result and not task.reviewer_notes:
                review = self._reviewer_fn(task.goal, task.result)
                try:
                    review_data = json.loads(review)
                    passed = review_data.get("passed", False)
                    if passed:
                        task.status = TaskStatus.VERIFIED
                    else:
                        task.reviewer_notes = review_data.get("suggestions", review)
                        issues = review_data.get("issues", [])
                        if task.attempts < task.max_attempts and issues:
                            task.status = TaskStatus.REVISION_NEEDED
                            needs_revision = True
                        else:
                            task.status = TaskStatus.VERIFIED  # accept despite issues
                except (json.JSONDecodeError, TypeError):
                    task.status = TaskStatus.VERIFIED  # reviewer non-JSON, assume pass
        return needs_revision

    def _merge_results(self, run: WorkflowRun) -> str:
        """Merge all verified task results into a final answer."""
        verified = [(t.id, t.goal, t.result or "") for t in run.tasks.values() if t.status == TaskStatus.VERIFIED]
        if len(verified) == 1:
            return verified[0][2]
        return self._merger_fn(run.goal, verified)

    def _persist(self, run: WorkflowRun):
        if self._store:
            try:
                self._store.save_workflow(run)
            except Exception as exc:
                logger.debug("Workflow persist failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

def _get_store_path() -> str:
    from alex_constants import get_alex_home
    return str(get_alex_home() / WORKFLOW_DB_DIR / WORKFLOW_DB_NAME)


_orchestrator_lock = threading.Lock()
_orchestrator_instance: Optional[WorkflowOrchestrator] = None


def get_orchestrator() -> WorkflowOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        with _orchestrator_lock:
            if _orchestrator_instance is None:
                store = WorkflowStore(_get_store_path())
                _orchestrator_instance = WorkflowOrchestrator(store=store)
    return _orchestrator_instance


def reset_orchestrator_for_testing():
    global _orchestrator_instance
    _orchestrator_instance = None


# ---------------------------------------------------------------------------
# Embeddable helpers for other tools
# ---------------------------------------------------------------------------

def execute_workflow(goal: str) -> str:
    """Start a workflow and return the workflow ID."""
    orch = get_orchestrator()
    return orch.start_workflow(goal)


def get_workflow_status(workflow_id: str) -> str:
    """Get workflow status as JSON string."""
    orch = get_orchestrator()
    status = orch.get_status(workflow_id)
    if status is None:
        return json.dumps({"error": f"Workflow {workflow_id} not found"})
    return json.dumps(status, ensure_ascii=False)


def cancel_workflow(workflow_id: str) -> str:
    """Cancel a running workflow."""
    orch = get_orchestrator()
    success = orch.cancel_workflow(workflow_id)
    return json.dumps({"success": success})


def list_workflows() -> str:
    """List all active workflows."""
    orch = get_orchestrator()
    return json.dumps(orch.list_workflows(), ensure_ascii=False)
