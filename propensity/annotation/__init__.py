"""Turning instances into demand intervals: CLAUDE.md §7 and §8."""

from .parsing import ParsedRange, parse_final_range
from .prompts import ANNOTATION_SYSTEM, as_single_string, build_annotation_prompt
from .rubrics import available_dimensions, load_presentation, load_rubric, rubric_path_for
from .runner import (
    annotate,
    build_requests,
    collect,
    require_batch,
    rows_from_completions,
    run_sequential,
    submit,
    summarise,
    wait_for_batch,
)
