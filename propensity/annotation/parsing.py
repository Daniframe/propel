"""Extracting the demand interval from an annotator's response.

The contract is that the last line of the response is `<FINAL_RANGE>[LB, UB]</FINAL_RANGE>` and
nothing follows it. Two legacy phrasings are accepted as fallbacks, because earlier tooling
asked for them and their responses are still worth reading.

Nothing here raises: a failure comes back as a ParsedRange with `parse_ok` false and a reason,
because the annotation layer counts failures and never dies mid-run. The full response text is
always kept by the caller, whatever happens here.
"""

import re
from dataclasses import dataclass

# The tag the output contract asks for, then the two legacy phrasings, tried in this order.
FINAL_RANGE_RE = re.compile(r"<FINAL_RANGE>\s*\[\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]\s*</FINAL_RANGE>")
LEGACY_PHRASE_RE = re.compile(r"[Tt]he propensity range is\s*\[\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]")
BARE_BRACKET_RE = re.compile(r"\[\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\]")
PATTERNS = (("final_range", FINAL_RANGE_RE),
            ("legacy_phrase", LEGACY_PHRASE_RE),
            ("legacy_bracket", BARE_BRACKET_RE))
SCALE = (-3, 3)


@dataclass(frozen=True)
class ParsedRange:
    """`method` says which pattern matched, for the audit trail; `error` says why not."""

    lower: int | None
    upper: int | None
    parse_ok: bool
    method: str | None = None
    error: str | None = None


def parse_final_range(text: str) -> ParsedRange:
    """Reads the demand interval out of a free-text response.

    Takes the **last** match of each pattern, never the first: reasoning text quotes the tag
    illustratively before committing to an answer. Bounds outside -3 <= lower <= upper <= 3 are
    reported as a failure and never clamped, because a clamped interval is a fabricated one.
    """
    low, high = SCALE
    for method, pattern in PATTERNS:
        matches = pattern.findall(text or "")
        if not matches:
            continue
        lower, upper = (int(bound) for bound in matches[-1])
        if not low <= lower <= upper <= high:
            return ParsedRange(None, None, False, method,
                               f"[{lower}, {upper}] violates {low} <= lower <= upper <= {high}")
        return ParsedRange(lower, upper, True, method)
    return ParsedRange(None, None, False, None, "no propensity range found in the response")
