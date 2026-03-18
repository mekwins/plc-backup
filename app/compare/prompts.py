"""
AI prompt templates for PLC backup comparison.
"""
from __future__ import annotations

import json
from typing import Dict, Any

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

CONTROLS_ENGINEERING_PROMPT = """You are an expert controls engineer and PLC programmer specialising in \
Rockwell Automation Allen-Bradley systems (ControlLogix, CompactLogix, GuardLogix).

Your task is to analyse the differences between two versions of a PLC project exported in L5X format \
and produce a concise, actionable engineering report.

When reviewing the diff, focus on:

1. **Functional Logic Changes**
   - New or removed ladder rungs, function block connections, structured text sections
   - Modified setpoints, timer/counter presets, PID tuning parameters
   - Changes to sequencer steps, state machine transitions
   - Permissive logic modifications (interlocks, enables, safety bypasses)

2. **Safety and Operational Risk**
   - Modifications to safety-rated routines or GuardLogix safety tasks
   - Changes to E-stop logic, guard monitoring, or safety I/O mappings
   - Alarm inhibit or acknowledge logic changes
   - Any removal of protective conditions or added overrides

3. **I/O and Module Configuration**
   - New, removed, or reconfigured I/O modules
   - Changes to I/O tag mappings
   - Motion axis parameter changes (velocity, acceleration, torque limits)

4. **Program Structure**
   - New or deleted Programs, Tasks, Routines, AOIs, or UDTs
   - Schedule or periodic task interval changes
   - AOI definition changes (interface pins, local tags, internal logic)

5. **Tag and Data Changes**
   - New or removed controller-scoped tags
   - Data type modifications
   - Preset value changes in tag initial values

6. **Cosmetic vs Functional**
   - Clearly distinguish comment-only changes or whitespace from functional logic changes
   - Attribute reordering or formatting differences should be flagged as cosmetic

Output format:
- **summary**: 2-4 sentence plain-English summary suitable for a non-programmer manager
- **riskLevel**: one of "none" | "low" | "medium" | "high" | "critical"
- **highlights**: bullet list of the most important changes (max 10)
- **sections**: per-section breakdown (routines, tags, aois, udts, modules, programs)
- Be concise. Do not repeat information. Engineers value precision over verbosity.
"""


# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

def build_user_prompt(
    plc_name: str,
    sections_diff: Dict[str, Any],
    diff_excerpt: str,
) -> str:
    """
    Build the user-turn prompt for the AI comparison request.

    Parameters
    ----------
    plc_name:
        Logical name of the PLC being compared.
    sections_diff:
        Output of ``compute_xml_sections_diff`` — per-section change counts.
    diff_excerpt:
        Truncated unified diff text (already capped at max_input_chars).
    """
    sections_summary = _format_sections_summary(sections_diff)

    return f"""## PLC Project Comparison Request

**PLC Name:** {plc_name}

### Section-Level Change Summary
{sections_summary}

### Unified Diff (excerpt)
```diff
{diff_excerpt}
```

Please analyse the changes above and return a JSON object with this exact structure:
{{
  "summary": "<plain-English summary>",
  "riskLevel": "<none|low|medium|high|critical>",
  "highlights": ["<bullet 1>", "<bullet 2>", ...],
  "sections": {{
    "routines": {{"changed": <count>, "details": "<brief>"}},
    "tags": {{"changed": <count>, "details": "<brief>"}},
    "aois": {{"changed": <count>, "details": "<brief>"}},
    "udts": {{"changed": <count>, "details": "<brief>"}},
    "modules": {{"changed": <count>, "details": "<brief>"}},
    "programs": {{"changed": <count>, "details": "<brief>"}}
  }}
}}
"""


def _format_sections_summary(sections_diff: Dict[str, Any]) -> str:
    lines = []
    for section, counts in sections_diff.items():
        added = counts.get("added", 0)
        removed = counts.get("removed", 0)
        modified = counts.get("modified", 0)
        if added or removed or modified:
            lines.append(
                f"- **{section}**: +{added} added, -{removed} removed, ~{modified} modified"
            )
    if not lines:
        return "- No structural section changes detected."
    return "\n".join(lines)
