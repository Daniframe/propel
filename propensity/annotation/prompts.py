"""Assembling the annotation prompt.

The layout of `user` is prompt text: every byte of it reaches the annotator, and annotations
are comparable only when made with the same layout. Do not reformat or re-indent it. The rubric
runs straight into `presentation`, which supplies the closing `</rubric>` tag; the question
starts on its own line after the presentation block.
"""

ANNOTATION_SYSTEM = "You are an expert at analyzing questions for cognitive biases."


def build_annotation_prompt(
    propensity_name: str,     # human-readable, e.g. "risk aversion"
    rubric: str,              # full rubric file text
    presentation: str,        # full presentation block text
    question_text: str,
) -> tuple[str, str]:
    """Returns (system, user). The question follows the presentation block after exactly one
    line break, whether or not the block's file ends with a newline."""
    user = (
        f"The following is a rubric for determining the propensity of showing bias "
        f"towards {propensity_name}:\n\n<rubric>\n"
        + rubric
        + presentation.rstrip("\n") + "\n"
        + question_text
    )
    return ANNOTATION_SYSTEM, user


def as_single_string(system: str, user: str) -> str:
    """For a provider whose API takes only one input field. Which providers need this, and how
    they deliver the system part otherwise, is each provider's business."""
    return system + user
