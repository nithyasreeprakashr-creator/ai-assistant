from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from state import SoftwareState
from agents import (
    planner_node,
    architect_node,
    backend_lead_node,
    module_planner_node,
    module_coder_node,
    reviewer_node,
    fixer_node,
    complete_module_node,
    qa_node,
    delivery_node,
)


# ─── Conditional Routing Functions ───

def route_after_backend_lead(state: SoftwareState) -> Literal["module_planner", "qa"]:
    """
    If a module was assigned, go plan it.
    If no modules remain, go to QA.
    """
    if state.get("current_module"):
        return "module_planner"
    return "qa"


def route_after_review(state: SoftwareState) -> Literal["fixer", "complete_module"]:
    """
    Three-way decision:
      1. score >= threshold       → complete (pass)
      2. attempts >= max_attempts → complete (force, prevent infinite loop)
      3. otherwise                → fixer
    """
    score = state.get("review_score", 0) or 0
    attempts = state.get("fix_attempts", 0)
    max_attempts = state.get("max_fix_attempts", 3)
    threshold = 8

    if score >= threshold:
        print(f"   ✓ Review PASSED (score={score}/{threshold}). Completing module.")
        return "complete_module"

    if attempts >= max_attempts:
        print(
            f"   ⚠ Max fix attempts reached ({attempts}/{max_attempts}). "
            f"Force-completing module (score={score})."
        )
        return "complete_module"

    print(
        f"   ✗ Review FAILED (score={score}/{threshold}, "
        f"attempts={attempts}/{max_attempts}). Sending to fixer."
    )
    return "fixer"


# ─── Graph Construction ───

workflow = StateGraph(SoftwareState)

# Register all nodes
workflow.add_node("planner", planner_node)
workflow.add_node("architect", architect_node)
workflow.add_node("backend_lead", backend_lead_node)
workflow.add_node("module_planner", module_planner_node)
workflow.add_node("module_coder", module_coder_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("fixer", fixer_node)
workflow.add_node("complete_module", complete_module_node)
workflow.add_node("qa", qa_node)
workflow.add_node("delivery", delivery_node)

# Linear edges
workflow.set_entry_point("planner")
workflow.add_edge("planner", "architect")
workflow.add_edge("architect", "backend_lead")

# Backend Lead dispatches: plan next module OR move to QA
workflow.add_conditional_edges(
    "backend_lead",
    route_after_backend_lead,
    {
        "module_planner": "module_planner",
        "qa": "qa",
    },
)

# Plan → Code → Review
workflow.add_edge("module_planner", "module_coder")
workflow.add_edge("module_coder", "reviewer")

# Review → Fix (retry) OR Complete (pass/force)
workflow.add_conditional_edges(
    "reviewer",
    route_after_review,
    {
        "fixer": "fixer",
        "complete_module": "complete_module",
    },
)

# Fix → Review (loop back)
workflow.add_edge("fixer", "reviewer")

# Complete → Backend Lead (pick next module or finish)
workflow.add_edge("complete_module", "backend_lead")

# QA → Delivery → END
workflow.add_edge("qa", "delivery")
workflow.add_edge("delivery", END)

# ─── Compile with Checkpointing ───

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
