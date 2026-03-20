import json
import os
import sys
from pathlib import Path
import google.generativeai as genai

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROJECTS_DIR    = BASE_DIR / "projects"

def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("gemini_api_key", "")
    except Exception:
        return ""

def _ensure_projects_dir():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── CORE PROJECT PLANNER LOGIC ──────────────────────────────────────────────

def generate_project_plan(project_description: str) -> dict:
    """Uses Gemini to generate a structured project plan."""
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API key missing"}

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""
    You are a Senior Project Manager and Architect.
    Generate a highly detailed, professional project plan for the following description:
    "{project_description}"

    Return the result ONLY as a valid JSON object with the following structure:
    {{
      "project_name": "Clear and concise name",
      "overview": "High-level summary of the project",
      "objectives": ["List of primary goals"],
      "milestones": [
        {{ "name": "Milestone 1", "description": "Goal", "tasks": ["Task A", "Task B"] }}
      ],
      "tasks": ["Detailed technical and operational tasks"],
      "timeline": "Estimated total duration and phase breakdown",
      "technologies": ["Required tech stack, tools, or resources"],
      "risks": ["Potential bottlenecks and mitigation strategies"],
      "success_metrics": ["How to measure progress and final success"]
    }}

    Ensure the content is actionable, technical, and realistic.
    """

    try:
        response = model.generate_content(prompt)
        # Extract JSON from potential markdown blocks
        raw_text = response.text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
        
        return json.loads(raw_text)
    except Exception as e:
        return {"error": f"Failed to generate plan: {str(e)}"}

def export_project_plan(plan: dict, format: str = "markdown") -> str:
    """Exports the plan to a file in the projects directory."""
    _ensure_projects_dir()
    name_slug = plan.get("project_name", "untitled_project").lower().replace(" ", "_")
    
    if format.lower() == "markdown":
        filename = f"{name_slug}.md"
        filepath = PROJECTS_DIR / filename
        
        md_content = f"# Project Plan: {plan.get('project_name')}\n\n"
        md_content += f"## Overview\n{plan.get('overview')}\n\n"
        md_content += "## Objectives\n" + "\n".join([f"- {o}" for o in plan.get('objectives', [])]) + "\n\n"
        md_content += "## Milestones\n"
        for m in plan.get('milestones', []):
            md_content += f"### {m.get('name')}\n- **Description:** {m.get('description')}\n"
            md_content += "- **Tasks:**\n" + "\n".join([f"  - {t}" for t in m.get('tasks', [])]) + "\n\n"
        md_content += f"## Timeline\n{plan.get('timeline')}\n\n"
        md_content += "## Technologies\n" + ", ".join(plan.get('technologies', [])) + "\n\n"
        md_content += "## Risks\n" + "\n".join([f"- {r}" for r in plan.get('risks', [])]) + "\n\n"
        md_content += "## Success Metrics\n" + "\n".join([f"- {s}" for s in plan.get('success_metrics', [])]) + "\n"
        
        filepath.write_text(md_content, encoding="utf-8")
        return str(filepath)
    
    elif format.lower() == "json":
        filename = f"{name_slug}.json"
        filepath = PROJECTS_DIR / filename
        filepath.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return str(filepath)
    
    return "Unsupported format"

def project_planner(parameters: dict, player=None, speak=None) -> str:
    """Main tool entry point."""
    desc = parameters.get("project_description", "")
    if not desc:
        # Friendly alias for older prompts/routines.
        desc = parameters.get("description", "") or parameters.get("project", "")
    fmt  = parameters.get("output_format", "markdown")
    if not fmt:
        fmt = parameters.get("format", "markdown")
    
    if not desc:
        return json.dumps({"status": "error", "message": "No project description provided."})

    if player:
        player.write_log(f"Planning Project: {desc[:30]}...", tag="sys")

    plan = generate_project_plan(desc)
    
    if "error" in plan:
        return json.dumps({"status": "error", "message": plan["error"]})

    file_path = export_project_plan(plan, fmt)
    
    result = {
        "status": "success",
        "project_name": plan.get("project_name"),
        "file_saved": file_path,
        "plan_summary": plan.get("overview")[:200] + "..."
    }
    
    if player:
        player.write_log(f"Plan Generated: {plan.get('project_name')}", tag="ai")
        player.write_log(f"Saved to: {file_path}", tag="sys")
    
    return json.dumps(result)
