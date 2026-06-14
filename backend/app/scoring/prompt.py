"""System rubric + JSON schema for content credibility scoring."""

RED_FLAG_TYPES = [
    "clickbait",
    "sensationalism",
    "unsourced_claim",
    "emotional_manipulation",
    "missing_attribution",
    "conspiracy",
    "misleading_headline",
    "lack_of_evidence",
    "biased_language",
    "other",
]

SYSTEM_PROMPT = """You are a media-literacy analyst assessing the CONTENT of a \
news article for credibility signals. You are NOT fact-checking specific claims \
against the outside world — you assess how the article is written, sourced, and \
framed, independent of which outlet published it.

Return a JSON object with:
- content_subscore: integer 0-100. 100 = reads as careful, well-sourced, neutral \
reporting; 50 = mixed; 0 = reads as fabricated, manipulative, or entirely \
unsourced. Judge ONLY the writing and sourcing.
- red_flags: a list of specific issues found (empty list if none). Each item:
    - type: one of clickbait, sensationalism, unsourced_claim, \
emotional_manipulation, missing_attribution, conspiracy, misleading_headline, \
lack_of_evidence, biased_language, other
    - severity: low, medium, or high
    - evidence: a short quote or paraphrase from the article showing the issue
- rationale: one concise paragraph (2-4 sentences) explaining the score.

Be specific and fair. Few or no red flags should yield a high score; multiple \
high-severity flags should yield a low score. Base every red flag on something \
actually present in the text."""

# JSON schema passed to Ollama's `format` parameter (constrains generation).
CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "content_subscore": {"type": "integer", "minimum": 0, "maximum": 100},
        "red_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": RED_FLAG_TYPES},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "evidence": {"type": "string"},
                },
                "required": ["type", "severity", "evidence"],
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["content_subscore", "red_flags", "rationale"],
}


def build_user_prompt(title: str | None, text: str | None, max_chars: int = 8000) -> str:
    body = (text or "")[:max_chars]
    return f"TITLE: {title or '(no title)'}\n\nARTICLE:\n{body}"
