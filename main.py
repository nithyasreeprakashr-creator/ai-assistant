import sys
from graph import app
from state import SoftwareState

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

initial_state: SoftwareState = {
    "requirement": "Build an Inventory Management System with Authentication and User Management.",
    "stories": [],
    "architecture": None,
    "modules": [],
    "quality_guide": None,
    "pending_modules": [],
    "completed_modules": [],
    "current_module": None,
    "module_plan": None,
    "generated_code": {},
    "tests": {},
    "review_score": None,
    "review_issues": [],
    "fix_attempts": 0,
    "max_fix_attempts": 2,
    "delivery_package": None,
}

if __name__ == "__main__":
    print("🚀 Starting AI Software Delivery Team...\n")

    config = {
        "configurable": {"thread_id": "delivery-1"},
        "recursion_limit": 150,
    }

    result = app.invoke(initial_state, config=config)

    # ─── Summary ───
    print("\n\n" + "=" * 60)
    print("🎉  WORKFLOW COMPLETE")
    print("=" * 60)

    print(f"\nModules Completed: {result['completed_modules']}")
    print(f"Total Code Files: {len(result['generated_code'])}")
    print(f"Total Test Files: {len(result.get('tests', {}))}")

    print("\n--- Architecture (first 500 chars) ---")
    arch = result.get("architecture", "")
    print(arch[:500] + "..." if len(arch) > 500 else arch)

    print("\n--- Generated Code Modules ---")
    for module, code in result["generated_code"].items():
        print(f"\n[{module}] ({len(code)} chars)")
        print(code[:300] + "...")

    print("\n--- Delivery Package ---")
    package = result.get("delivery_package", "")
    print(f"Total size: {len(package)} chars")
    print(f"Saved to: outputs/delivery_package.md")
