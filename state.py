from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel, Field


# ─── Pydantic Models for Structured Output ───

class ModuleList(BaseModel):
    """Output from the Planner."""
    stories: List[str] = Field(description="User stories derived from requirements")
    modules: List[str] = Field(description="Backend module names (e.g., auth, users, inventory)")


class ArchitectureDoc(BaseModel):
    tech_stack: str = Field(description="Primary tech stack")
    db_schema: str = Field(description="Database schema definitions")
    api_endpoints: str = Field(description="Key API endpoint designs")
    folder_structure: str = Field(description="Project folder structure")
    architecture_diagram: str = Field(
        description="Text-based architecture diagram"
    )
    
class ModuleFile(BaseModel):
    path: str
    purpose: str
    exports: List[str] = Field(default_factory=list)

class ModulePlan(BaseModel):
    module_name: str
    files: List[ModuleFile]
    dependencies: List[str] = Field(default_factory=list)
    api_routes: List[str] = Field(default_factory=list)

class CodeReview(BaseModel):
    """Output from the Reviewer."""
    score: int = Field(description="Code quality score from 1 to 10")
    issues: List[str] = Field(description="List of issues found")
    logic_correctness: str = Field(description="Brief logic correctness analysis")
    security_check: str = Field(description="Brief security analysis")


# ─── Graph State ───

class SoftwareState(TypedDict):
    # Input
    requirement: str

    # Planning artifacts
    stories: List[str]
    architecture: Optional[str]
    modules: List[str]

    # Execution tracking
    pending_modules: List[str]
    completed_modules: List[str]
    current_module: Optional[str]

    # Code artifacts
    generated_code: Dict[str, str]       # module_name → code
    tests: Dict[str, str]                # module_name → test_code

    # Review loop
    review_score: Optional[int]
    review_issues: List[str]
    fix_attempts: int
    max_fix_attempts: int

    # Final output
    delivery_package: Optional[str]
