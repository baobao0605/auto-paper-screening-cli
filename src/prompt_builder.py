"""Prompt construction for full-text screening."""

from __future__ import annotations

from src.utils import normalize_whitespace


JSON_CONTRACT = """
Return JSON only with exactly these 6 keys and no markdown fences:
{
  "Title": "",
  "DOI": "",
  "Decision": "INCLUDE",
  "Exclude reason": "",
  "Construct": "target construct",
  "Note": ""
}
""".strip()


def build_prompt(
    *,
    criteria_prompt: str,
    full_text: str,
    file_name: str,
    title_hint: str | None,
    doi_hint: str | None,
) -> str:
    """Compose the screening prompt sent to Gemini."""

    title_value = title_hint or "Unknown"
    doi_value = doi_hint or ""
    return (
        "You are screening the FULL TEXT of an academic paper.\n"
        "Base the decision on the full text below, not on abstract-only cues.\n"
        "Prefer MAYBE over guessing when the full text is unclear.\n\n"
        f"{criteria_prompt.strip()}\n\n"
        f"{JSON_CONTRACT}\n\n"
        "Known metadata:\n"
        f"- File name: {normalize_whitespace(file_name)}\n"
        f"- Title hint: {normalize_whitespace(title_value)}\n"
        f"- DOI hint: {doi_value}\n\n"
        "Paper full text starts below.\n"
        "----- BEGIN FULL TEXT -----\n"
        f"{full_text}\n"
        "----- END FULL TEXT -----\n"
    )
