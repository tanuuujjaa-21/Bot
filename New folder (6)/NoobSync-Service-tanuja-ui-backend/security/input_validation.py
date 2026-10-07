"""
input_validation.py
Security layer — Akshada / akshada-security-docs branch

Validates and sanitizes the raw question string before it ever reaches
the RAG pipeline (Anushka's answer_question()) or the LLM.

Usage (once Tanuja's FastAPI /ask endpoint exists):

    from input_validation import validate_question, ValidationError

    @app.post("/ask")
    def ask(payload: dict):
        try:
            clean_question = validate_question(payload.get("question", ""))
        except ValidationError as e:
            return {"error": str(e)}, 400
        answer = answer_question(clean_question)
        return {"answer": answer}
"""

import re
import unicodedata

MAX_QUESTION_LENGTH = 500        # characters — generous for a real question, blocks abuse
MIN_QUESTION_LENGTH = 3          # blocks empty / near-empty submissions

# Characters that have no legitimate place in a natural-language question
# and are commonly used in injection / control-character attacks.
_DANGEROUS_CHARS_PATTERN = re.compile(r"[<>{}\\`]")

# Collapses runs of whitespace (including tabs/newlines used to pad attacks)
_WHITESPACE_PATTERN = re.compile(r"\s+")


class ValidationError(Exception):
    """Raised when a question fails validation. Message is safe to show the user."""
    pass


def validate_question(raw_question: str) -> str:
    """
    Validates and sanitizes a user-submitted question.

    Returns the cleaned question string on success.
    Raises ValidationError with a user-friendly message on failure.
    """
    if raw_question is None:
        raise ValidationError("Question cannot be empty.")

    if not isinstance(raw_question, str):
        raise ValidationError("Question must be text.")

    # Normalize unicode (defends against lookalike-character tricks)
    question = unicodedata.normalize("NFKC", raw_question)

    # Strip control characters (invisible chars sometimes used to hide instructions)
    question = "".join(ch for ch in question if unicodedata.category(ch)[0] != "C")

    # Collapse whitespace and trim
    question = _WHITESPACE_PATTERN.sub(" ", question).strip()

    if len(question) < MIN_QUESTION_LENGTH:
        raise ValidationError("Please enter a real question.")

    if len(question) > MAX_QUESTION_LENGTH:
        raise ValidationError(
            f"Question is too long (max {MAX_QUESTION_LENGTH} characters)."
        )

    # Remove characters with no legitimate use in a question
    question = _DANGEROUS_CHARS_PATTERN.sub("", question)

    if len(question) < MIN_QUESTION_LENGTH:
        raise ValidationError("Please enter a real question.")

    return question


if __name__ == "__main__":
    # Quick manual smoke test — run: python input_validation.py
    test_cases = [
        "What is ConnectOps?",
        "",
        "   ",
        "a" * 600,
        "What is <script>alert(1)</script> ConnectOps?",
        "hi",
    ]
    for case in test_cases:
        try:
            result = validate_question(case)
            print(f"OK   -> {result!r}")
        except ValidationError as e:
            print(f"FAIL -> {e}")
