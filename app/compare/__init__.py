from app.compare.xml_normalizer import normalize_l5x
from app.compare.deterministic_diff import compute_text_diff, compute_xml_sections_diff, extract_section
from app.compare.ai_compare import AiCompareAdapter
from app.compare.prompts import CONTROLS_ENGINEERING_PROMPT, build_user_prompt

__all__ = [
    "normalize_l5x",
    "compute_text_diff",
    "compute_xml_sections_diff",
    "extract_section",
    "AiCompareAdapter",
    "CONTROLS_ENGINEERING_PROMPT",
    "build_user_prompt",
]
