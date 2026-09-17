"""Assembling the annotation prompt: CLAUDE.md §7.3.

The byte layout of `user` is validated prompt text: this exact wording produced the project's
existing annotation data. Do not reformat, re-indent or insert separators. The seams are
deliberately unspaced, and `presentation` supplies the closing `</rubric>` tag.
"""

ANNOTATION_SYSTEM = "You are an expert at analyzing questions for cognitive biases."


def build_annotation_prompt(
    propensity_name: str,     # human-readable, e.g. "risk aversion"
    rubric: str,              # full rubric file text
    presentation: str,        # full presentation block text
    question_text: str,
) -> tuple[str, str]:
    """Returns (system, user)."""
    user = (
        f"The following is a rubric for determining the propensity of showing bias "
        f"towards {propensity_name}:\n\n<rubric>\n"
        + rubric
        + presentation
        + question_text
    )
    return ANNOTATION_SYSTEM, user


def as_single_string(system: str, user: str) -> str:
    """For a provider whose API takes only one input field. Which providers need this, and how
    they deliver the system part otherwise, is the adapter's business (§4.1 rule 6)."""
    return system + user
