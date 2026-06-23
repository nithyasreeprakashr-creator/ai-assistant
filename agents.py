import os
import json
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.exceptions import OutputParserException
from state import (
    SoftwareState,
    ModuleList,
    ArchitectureDoc,
    ModulePlan,
    ModuleFile,
    CodeReview,
)
from dotenv import load_dotenv

load_dotenv()

# ─── LLM Configuration ───


BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "minimax-m2.1:cloud")

print("BASE_URL =", os.getenv("OLLAMA_BASE_URL"))
print("MODEL =", os.getenv("OLLAMA_MODEL"))
print("API KEY EXISTS =", bool(os.getenv("OLLAMA_API_KEY")))

llm = ChatOllama(base_url=BASE_URL, model=MODEL_NAME, temperature=0)

# Structured-output LLMs (method="json_mode" for broad Ollama compatibility)
planner_llm = llm.with_structured_output(ModuleList, method="json_mode")
architect_llm = llm.with_structured_output(ArchitectureDoc, method="json_mode")
module_planner_llm = llm.with_structured_output(ModulePlan, method="json_mode")
reviewer_llm = llm.with_structured_output(CodeReview, method="json_mode")

QUALITY_GUIDE = """
## Quality Requirements

Follow these rules strictly:

### Python & FastAPI
- Use `datetime.now(timezone.utc)` NOT `datetime.utcnow()` — the latter is deprecated in 3.12+
- ALL database sessions must come via `Depends(get_db)` — never create `Session()` directly
- Use `async def` for all endpoints with async SQLAlchemy sessions where possible
- Add type hints on ALL function parameters and return values

### Security
- NEVER hardcode secrets, API keys, or passwords — use `os.getenv()` via a `config` module
- Hash passwords with bcrypt via `passlib`
- Use JWT with explicit expiration for authentication tokens
- Validate ALL user input via Pydantic schemas, not manual checks in route handlers
- No raw SQL — use SQLAlchemy ORM or 2.0 style `select()` / `update()` queries

### Architecture
- Separate files per concern: `schemas.py`, `models.py`, `crud.py`, `routes.py`
- CRUD layer must NOT raise `HTTPException` — raise custom exceptions or return result/error tuples
- API layer catches exceptions and converts to proper HTTP responses
- Use dependency injection (`Depends`) for all services and DB access

### Database
- Use proper transactions: commit in the API layer, not inside CRUD methods
- Use `selectinload` / `joinedload` to avoid N+1 queries on relationships
- Add `order_by` for all paginated queries
- Set sensible defaults AND maximum bounds for `limit` / `offset` pagination

### Code Quality
- No unused imports
- No bare `except:` — catch specific exception types
- No mutable default arguments in function signatures
- Use `enum.Enum` for fixed value sets (roles, categories, etc.)
"""

# ═══════════════════════════════════════════════
# NODE 1 — PLANNER
# ═══════════════════════════════════════════════


def _flatten_planner(raw: dict) -> ModuleList:
    stories = raw.get("stories") or raw.get("user_stories") or []
    modules = raw.get("modules") or raw.get("backend_modules") or raw.get("module_names") or []
    return ModuleList(stories=[str(s) for s in stories], modules=[str(m) for m in modules])


def planner_node(state: SoftwareState):
    print("--- 📝 PLANNER: Analyzing Requirements ---")

    prompt = ChatPromptTemplate.from_template(
        "You are a software planner. Analyze the following requirement and "
        "break it into user stories and backend modules.\n"
        "Module names must be simple lowercase strings like 'auth', 'users', 'inventory'.\n\n"
        "Requirement: {requirement}\n\n"
        "Return ONLY a single flat JSON object with exactly these two keys:\n"
        '- "stories": an array of strings\n'
        '- "modules": an array of strings\n\n'
        '{{"stories": ["..."], "modules": ["..."]}}'
    )

    chain = prompt | planner_llm

    try:
        result: ModuleList = chain.invoke({"requirement": state["requirement"]})
    except OutputParserException:
        print("   ⚠ Planner JSON parse failed; attempting fallback…")
        raw_response = llm.invoke(
            ChatPromptTemplate.from_template(
                "You are a software planner. Analyze the following requirement and "
                "break it into user stories and backend modules.\n"
                "Module names must be simple lowercase strings like 'auth', 'users', 'inventory'.\n\n"
                "Requirement: {requirement}\n\n"
                "Return ONLY raw JSON with no markdown formatting."
            ).format(requirement=state["requirement"])
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   ⚠ Planner fallback also failed; using safe defaults.")
            return {
                "stories": [f"Implement {state['requirement']}"],
                "modules": ["app"],
                "pending_modules": ["app"],
                "completed_modules": [],
                "max_fix_attempts": 3,
            }
        result = _flatten_planner(raw_dict)

    # Sanitize: ensure every module is a plain string
    clean_modules = []
    for m in result.modules:
        if isinstance(m, str):
            clean_modules.append(m)
        elif isinstance(m, dict):
            clean_modules.append(m.get("name", str(m)))
        else:
            clean_modules.append(str(m))

    print(f"   Stories: {len(result.stories)} | Modules: {clean_modules}")

    return {
        "stories": result.stories,
        "modules": clean_modules,
        "pending_modules": clean_modules,
        "completed_modules": [],
        "max_fix_attempts": 3,
    }


# ═══════════════════════════════════════════════
# NODE 2 — ARCHITECT
# ═══════════════════════════════════════════════


def _dict_to_str(val) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "\n".join(f"- {_dict_to_str(v)}" for v in val)
    if isinstance(val, dict):
        return "\n".join(f"{k}: {_dict_to_str(v)}" for k, v in val.items())
    return str(val)


def _flatten_architecture(raw: dict) -> ArchitectureDoc:
    # The LLM sometimes wraps fields under a top-level key like "system_architecture" or "architecture"
    inner = raw
    for wrapper in ("system_architecture", "architecture", "arch"):
        if wrapper in raw and isinstance(raw[wrapper], dict):
            inner = raw[wrapper]
            break

    return ArchitectureDoc(
        tech_stack=_dict_to_str(inner.get("tech_stack", "")),
        db_schema=_dict_to_str(inner.get("db_schema", "")),
        api_endpoints=_dict_to_str(inner.get("api_endpoints", "")),
        folder_structure=_dict_to_str(inner.get("folder_structure", "")),
        architecture_diagram=_dict_to_str(inner.get("architecture_diagram", "")),
    )


def architect_node(state: SoftwareState):
    print("--- 🏗️  ARCHITECT: Designing System ---")

    prompt = ChatPromptTemplate.from_template(
        "You are a software architect. Design a FastAPI backend system.\n"
        "User stories:\n{stories}\n\n"
        "Modules to design:\n{modules}\n\n"
        "Respond ONLY with a single flat JSON object containing exactly these "
        "five string fields: tech_stack, db_schema, api_endpoints, "
        "folder_structure, architecture_diagram. "
        "Each field must be a plain string (not a nested object or array).\n\n"
        "- folder_structure must be a multi-line tree format with proper indentation, "
        "not a single-line list.\n"
        "- architecture_diagram must be a text-based diagram (ASCII) showing "
        "how modules (auth, users, inventory) communicate, "
        "data flow between layers (routes → services → CRUD → DB), "
        "and authentication flow.\n\n"
        '{{"tech_stack": "...", "db_schema": "...", '
        '"api_endpoints": "...", "folder_structure": "app/\\n  api/\\n    ...", '
        '"architecture_diagram": "..."}}'
    )

    chain = prompt | architect_llm

    try:
        doc: ArchitectureDoc = chain.invoke(
            {
                "stories": state["stories"],
                "modules": state["modules"],
            }
        )
    except OutputParserException:
        print("   ⚠ Architect JSON parse failed; attempting fallback…")
        raw_response = llm.invoke(
            ChatPromptTemplate.from_template(
                "You are a software architect. Design a FastAPI backend system.\n"
                "User stories:\n{stories}\n\n"
                "Modules to design:\n{modules}\n\n"
                "Return ONLY raw JSON with no markdown formatting."
            ).format(
                stories=state["stories"],
                modules=state["modules"],
            )
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   ⚠ Architect fallback also failed; using safe defaults.")
            raw_dict = {}
        doc = _flatten_architecture(raw_dict)

    # Flatten to string for downstream prompt injection
    arch_str = f"""# Architecture Document

## Tech Stack
{doc.tech_stack}

## Database Schema
{doc.db_schema}

## API Endpoints
{doc.api_endpoints}

## Folder Structure
{doc.folder_structure}

## Architecture Diagram
{doc.architecture_diagram}
"""
    return {"architecture": arch_str, "quality_guide": QUALITY_GUIDE}


# ═══════════════════════════════════════════════
# NODE 3 — BACKEND LEAD (Dispatcher)
# ═══════════════════════════════════════════════


def backend_lead_node(state: SoftwareState):
    """
    Picks the next pending module and assigns it as current_module.
    If nothing is pending, sets current_module to None (signals QA phase).
    """
    print("--- 👷 BACKEND LEAD: Assigning Work ---")

    pending = list(state.get("pending_modules", []))

    if not pending:
        print("   No pending modules remaining.")
        return {"current_module": None}

    next_module = pending[0]
    new_pending = pending[1:]

    # Safety: coerce dict to string if sanitization somehow failed upstream
    if isinstance(next_module, dict):
        next_module = next_module.get("name", str(next_module))

    print(f"   Assigning: {next_module}  (remaining: {len(new_pending)})")

    return {
        "current_module": next_module,
        "pending_modules": new_pending,
    }


# ═══════════════════════════════════════════════
# NODE 4a — MODULE PLANNER
# ═══════════════════════════════════════════════


def _flatten_module_plan(raw: dict) -> ModulePlan:
    name = raw.get("module_name") or raw.get("name") or ""
    files_raw = raw.get("files") or []
    files = []
    for f in files_raw:
        if isinstance(f, dict):
            exports_raw = f.get("exports") or []
            files.append(ModuleFile(
                path=f.get("path", ""),
                purpose=f.get("purpose", ""),
                exports=[str(e) for e in exports_raw],
            ))
    deps = raw.get("dependencies") or raw.get("deps") or []
    routes = raw.get("api_routes") or raw.get("routes") or []
    return ModulePlan(
        module_name=name,
        files=files,
        dependencies=[str(d) for d in deps],
        api_routes=[str(r) for r in routes],
    )


def module_planner_node(state: SoftwareState):
    module = state["current_module"]
    print(f"--- 📋 MODULE PLANNER: Planning [{module}] ---")

    prompt = ChatPromptTemplate.from_template(
        "You are a senior backend architect. Plan the files needed for the '{module}' module.\n\n"
        "Architecture context:\n{architecture}\n\n"
        "Quality requirements:\n{quality_guide}\n\n"
        "Return ONLY a single flat JSON object with exactly these keys:\n"
        '- "module_name": the module name\n'
        '- "files": an array of objects, each with "path", "purpose", and "exports" (array of strings)\n'
        '- "dependencies": array of other module names this depends on\n'
        '- "api_routes": array of route path strings\n\n'
        '{{"module_name": "...", "files": [{{"path": "...", "purpose": "...", "exports": ["..."]}}], '
        '"dependencies": ["..."], "api_routes": ["..."]}}'
    )

    chain = prompt | module_planner_llm
    quality = state.get("quality_guide", "")

    try:
        plan: ModulePlan = chain.invoke({
            "module": module,
            "architecture": state["architecture"],
            "quality_guide": quality,
        })
    except OutputParserException:
        print("   ⚠ Module planner JSON parse failed; attempting fallback…")
        raw_response = llm.invoke(
            ChatPromptTemplate.from_template(
                "Plan the files needed for the '{module}' module.\n\n"
                "Architecture:\n{architecture}\n\n"
                "Return ONLY raw JSON with no markdown formatting."
            ).format(module=module, architecture=state.get("architecture", ""))
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   ⚠ Module planner fallback also failed; using empty plan.")
            raw_dict = {}
        plan = _flatten_module_plan(raw_dict)

    # Flatten the plan to a string for downstream injection
    plan_lines = [f"## Plan for {plan.module_name}"]
    plan_lines.append(f"\n### Files:")
    for f in plan.files:
        exports = ", ".join(f.exports) if hasattr(f, "exports") and f.exports else ""
        plan_lines.append(f"- {f.path}: {f.purpose} [{exports}]")
    plan_lines.append(f"\n### Dependencies: {', '.join(plan.dependencies)}")
    plan_lines.append(f"\n### API Routes:")
    for r in plan.api_routes:
        plan_lines.append(f"- {r}")

    return {"module_plan": "\n".join(plan_lines)}


# ═══════════════════════════════════════════════
# NODE 4b — MODULE CODER
# ═══════════════════════════════════════════════


def module_coder_node(state: SoftwareState):
    module = state["current_module"]
    print(f"--- 💻 MODULE CODER: Coding [{module}] ---")

    prompt = ChatPromptTemplate.from_template(
        "You are an expert Python backend developer. "
        "Write production-ready FastAPI code for the '{module}' module.\n\n"
        "Architecture context:\n{architecture}\n\n"
        "Follow this plan exactly:\n{module_plan}\n\n"
        "Quality requirements (follow EVERY rule):\n{quality_guide}\n\n"
        "Return ONLY Python code inside markdown code blocks. "
        "If there are multiple files, separate them with a header like:\n"
        "```python\n# --- filename.py ---\n...code...\n```"
    )

    chain = prompt | llm
    response = chain.invoke({
        "module": module,
        "architecture": state["architecture"],
        "module_plan": state.get("module_plan", ""),
        "quality_guide": state.get("quality_guide", ""),
    })

    content = response.content or ""
    if not content.strip():
        print(f"   ⚠ Empty response for [{module}]; generating placeholder.")
        content = f"# {module} module\n# TODO: implement\n"

    code_map = dict(state.get("generated_code", {}))
    code_map[module] = content

    return {
        "generated_code": code_map,
        "fix_attempts": 0,
    }


# ═══════════════════════════════════════════════
# NODE 5 — REVIEWER
# ═══════════════════════════════════════════════


def _flatten_review(raw: dict) -> CodeReview:
    # Map common LLM naming variations to our model's field names
    score = raw.get("score") or raw.get("quality_score") or 0
    if isinstance(score, str):
        score = int(score)

    issues_raw = raw.get("issues") or []
    issues = []
    for i in issues_raw:
        if isinstance(i, str):
            issues.append(i)
        elif isinstance(i, dict):
            issues.append(i.get("description") or i.get("message") or str(i))
        else:
            issues.append(str(i))

    logic = raw.get("logic_correctness") or raw.get("logic_correctness_analysis") or ""
    if isinstance(logic, dict):
        logic = _dict_to_str(logic)

    security = raw.get("security_check") or raw.get("security_analysis") or ""
    if isinstance(security, dict):
        security = _dict_to_str(security)

    return CodeReview(
        score=score,
        issues=issues,
        logic_correctness=logic,
        security_check=security,
    )


def reviewer_node(state: SoftwareState):
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    print(f"--- 🔍 REVIEWER: Reviewing [{module}] ---")

    if not code:
        print(f"   ⚠ No code found for [{module}]; returning failing review.")
        return {
            "review_score": 1,
            "review_issues": [f"No code generated for module '{module}'"],
        }

    prompt = ChatPromptTemplate.from_template(
        "You are a strict code reviewer. Review this code for the '{module}' module.\n\n"
        "Code:\n{code}\n\n"
        "Return ONLY a single flat JSON object with **exactly** these four top-level keys:\n"
        '- "score": an integer 1-10\n'
        '- "issues": an array of plain strings (each describing one issue)\n'
        '- "logic_correctness": a string\n'
        '- "security_check": a string\n\n'
        '{{"score": 0, "issues": ["..."], '
        '"logic_correctness": "...", "security_check": "..."}}'
    )

    chain = prompt | reviewer_llm

    try:
        review: CodeReview = chain.invoke({"module": module, "code": code})
    except OutputParserException:
        print("   ⚠ Review JSON parse failed; attempting fallback…")
        raw_response = llm.invoke(
            ChatPromptTemplate.from_template(
                "You are a strict code reviewer. Review this code for the '{module}' module.\n\n"
                "Code:\n{code}\n\n"
                "Return ONLY raw JSON with no markdown formatting."
            ).format(module=module, code=code)
        )
        try:
            raw_dict = json.loads(raw_response.content)
        except json.JSONDecodeError:
            print("   ⚠ Review fallback also failed; using safe defaults.")
            raw_dict = {}
        review = _flatten_review(raw_dict)

    print(f"   Score: {review.score}/10 | Issues: {len(review.issues)}")
    for issue in review.issues:
        print(f"     • {issue}")

    return {
        "review_score": review.score,
        "review_issues": review.issues,
    }


# ═══════════════════════════════════════════════
# NODE 6 — FIXER
# ═══════════════════════════════════════════════


def fixer_node(state: SoftwareState):
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    issues = state.get("review_issues", [])
    attempts = state.get("fix_attempts", 0) + 1

    print(f"--- 🛠️  FIXER: Fixing [{module}] (attempt {attempts}) ---")

    quality = state.get("quality_guide", "")

    prompt = ChatPromptTemplate.from_template(
        "Fix the following code based on the reviewer's issues.\n"
        "Module: {module}\n\n"
        "Current code:\n{code}\n\n"
        "Issues to fix:\n{issues}\n\n"
        "Quality requirements (follow EVERY rule):\n{quality}\n\n"
        "Return ONLY the corrected Python code in a markdown block."
    )

    chain = prompt | llm
    response = chain.invoke(
        {
            "module": module,
            "code": code,
            "issues": "\n".join(f"- {i}" for i in issues),
            "quality": quality,
        }
    )

    code_map = dict(state["generated_code"])
    code_map[module] = response.content

    return {
        "generated_code": code_map,
        "fix_attempts": attempts,
    }

# ═══════════════════════════════════════════════
# NODE 7 — COMPLETE MODULE  
# ═══════════════════════════════════════════════


def complete_module_node(state: SoftwareState):
    """
    Moves current_module from 'pending' to 'completed'.
    Resets per-module review state so the next module starts clean.
    """
    module = state["current_module"]
    print(f"--- ✅ COMPLETE: Marking [{module}] as done ---")

    completed = list(state.get("completed_modules", []))
    if module and module not in completed:
        completed.append(module)

    print(f"   Completed so far: {completed}")

    return {
        "completed_modules": completed,
        "current_module": None,
        "module_plan": None,
        "review_score": None,
        "review_issues": [],
        "fix_attempts": 0,
    }


# ═══════════════════════════════════════════════
# NODE 8 — QA AGENT
# ═══════════════════════════════════════════════


def qa_node(state: SoftwareState):
    print("--- 🧪 QA AGENT: Generating Tests ---")

    tests: dict[str, str] = {}

    for module, code in state["generated_code"].items():
        print(f"   Generating tests for [{module}]...")

        prompt = ChatPromptTemplate.from_template(
            "You are a QA engineer. Write comprehensive pytest unit tests "
            "for the following {module} module code.\n\n"
            "Code:\n{code}\n\n"
            "Include edge cases. Return ONLY Python test code in a markdown block."
        )

        chain = prompt | llm
        response = chain.invoke({"module": module, "code": code})
        tests[module] = response.content

    print(f"   Tests generated for {len(tests)} modules.")
    return {"tests": tests}


# ═══════════════════════════════════════════════
# NODE 9 — DELIVERY PACKAGE
# ═══════════════════════════════════════════════


def delivery_node(state: SoftwareState):
    print("--- 📦 DELIVERY: Compiling Package ---")

    sections = []

    sections.append("# ═══════════════════════════════════════════")
    sections.append("# SOFTWARE DELIVERY PACKAGE")
    sections.append("# ═══════════════════════════════════════════\n")

    sections.append("## Requirement\n")
    sections.append(state["requirement"])

    sections.append("\n## User Stories\n")
    for s in state.get("stories", []):
        sections.append(f"- {s}")

    sections.append("\n## Completed Modules\n")
    for m in state.get("completed_modules", []):
        sections.append(f"- {m}")

    sections.append(f"\n## Architecture\n")
    sections.append(state.get("architecture", "N/A"))

    sections.append("\n\n## ═══ SOURCE CODE ═══\n")
    for module, code in state.get("generated_code", {}).items():
        sections.append(f"\n### Module: {module}\n")
        sections.append(code)

    sections.append("\n\n## ═══ TEST CODE ═══\n")
    for module, test in state.get("tests", {}).items():
        sections.append(f"\n### Tests: {module}\n")
        sections.append(test)

    package = "\n".join(sections)

    # Persist to disk
    output_dir = os.getenv("OUTPUT_DIR", "outputs")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "delivery_package.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(package)

    print(f"   Package saved to {filepath}")
    return {"delivery_package": package}
