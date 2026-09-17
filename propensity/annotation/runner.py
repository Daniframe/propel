"""Running an annotation pass: CLAUDE.md §8.

Both dispatch paths — one call per instance, or the provider's native batch API — build their
prompts with `build_requests` and write their rows with `rows_from_completions`. Correctness
therefore cannot depend on which one ran, which is what acceptance test T7 asserts.

Provider errors are recorded on the row, never raised: a 480-of-500 run has to be visibly
different from a 500-of-500 one.
"""

import logging
import time
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from ..errors import ContractError, DataWarning, ProviderError
from ..providers.base import BatchCapable, BatchRequest, Completion
from .parsing import parse_final_range
from .prompts import build_annotation_prompt

logger = logging.getLogger(__name__)

# §6.2's canonical fields, in order; the instance's other fields follow them on each row.
ROW_FIELDS = ("question_id", "dimension", "lower", "upper", "annotator", "explanation",
              "parse_ok", "error", "parse_error", "parse_method")
DONE_STATES = ("completed", "failed", "cancelled")
MODES = ("auto", "batch", "sequential")


def build_requests(instances, *, propensity_name, rubric, presentation) -> list[BatchRequest]:
    """One (system, user) prompt per instance, keyed by question_id.

    question_id uniqueness is checked before anything else: a duplicate would collide in the
    batch path and silently overwrite a row in either.
    """
    ids = [instance.get("question_id") for instance in instances]
    missing = [i for i, qid in enumerate(ids) if qid is None]
    if missing:
        raise ContractError(f"instances have no question_id at rows {missing[:10]}", rows=missing)
    duplicates = sorted(str(qid) for qid, n in Counter(map(str, ids)).items() if n > 1)
    if duplicates:
        raise ContractError(f"duplicate question_id {duplicates[:10]}", rows=duplicates)
    no_text = [str(instance["question_id"]) for instance in instances
               if not str(instance.get("question_text") or "").strip()]
    if no_text:
        raise ContractError(f"instances have no question_text: {no_text[:10]}", rows=no_text)

    requests = []
    for instance in instances:
        system, user = build_annotation_prompt(propensity_name, rubric, presentation,
                                               instance["question_text"])
        requests.append(BatchRequest(custom_id=str(instance["question_id"]), system=system, user=user))
    return requests


def run_sequential(provider, requests, *, temperature=0.0, max_tokens=None, max_workers=8,
                   max_retries=3, retry_backoff=1.0, on_progress=None) -> dict[str, Completion]:
    """One `complete` call per request, through a thread pool, with bounded retry.

    A provider error is retried up to `max_retries` times with exponential backoff. A parse
    failure is not: at temperature 0 the same prompt returns the same answer.
    """
    def ask(request):
        completion = None
        for attempt in range(max_retries + 1):
            completion = provider.complete(request.system, request.user,
                                           temperature=temperature, max_tokens=max_tokens)
            if completion.error is None or attempt == max_retries:
                break
            delay = retry_backoff * 2 ** attempt
            logger.info("retrying %s in %.1fs after: %s", request.custom_id, delay, completion.error)
            if delay:
                time.sleep(delay)
        return completion

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for request, completion in zip(requests, pool.map(ask, requests)):
            results[request.custom_id] = completion
            if on_progress:
                on_progress(len(results), len(requests))
    return results


def require_batch(provider) -> None:
    """Batching is an optional capability, never an assumption (§4.1 rule 5)."""
    if not isinstance(provider, BatchCapable):
        raise ProviderError(f"provider {getattr(provider, 'name', provider)!r} has no batch API; "
                            "use mode='sequential'")


def submit(provider, requests, *, temperature=0.0, max_tokens=None) -> str:
    """Hands the whole set to the provider's batch API and returns its id."""
    require_batch(provider)
    return provider.submit_batch(list(requests), temperature=temperature, max_tokens=max_tokens)


def wait_for_batch(provider, batch_id, *, poll_interval=60.0) -> str:
    """Polls until the batch is finished, and returns the state it finished in.

    The CLI exposes submit, status and fetch separately so that a multi-hour batch never
    depends on one process staying alive; this loop is for short runs and for tests.
    """
    require_batch(provider)
    while True:
        state = provider.poll_batch(batch_id)
        if state in DONE_STATES:
            return state
        logger.info("batch %s is %s; polling again in %.0fs", batch_id, state, poll_interval)
        if poll_interval:
            time.sleep(poll_interval)


def collect(provider, batch_id, requests=None) -> dict[str, Completion]:
    """Fetches a finished batch, keyed by custom_id.

    Batch output order does not match input order, so callers rejoin by id and never by
    position. An id that comes back without having been sent is reported and dropped.
    """
    require_batch(provider)
    results = dict(provider.fetch_batch(batch_id))
    if requests is not None:
        unknown = sorted(set(results) - {request.custom_id for request in requests})
        if unknown:
            warnings.warn(f"batch {batch_id} returned {len(unknown)} id(s) that were never sent: "
                          f"{unknown[:5]}", DataWarning, stacklevel=2)
            for custom_id in unknown:
                results.pop(custom_id)
    return results


def rows_from_completions(instances, completions, *, dimension, annotator) -> list[dict]:
    """One row per input instance, in input order, always — including the failures (§6.2).

    The full response text is kept as `explanation` whatever happened: it is the only audit
    trail. Bounds are null unless the parse succeeded, so a clamped or half-read interval can
    never reach the fit.
    """
    rows = []
    for instance in instances:
        question_id = str(instance["question_id"])
        completion = completions.get(question_id)
        row = dict.fromkeys(ROW_FIELDS)
        row.update(question_id=question_id, dimension=dimension, annotator=annotator,
                   explanation="", parse_ok=False)

        if completion is None:
            row["error"] = "missing from the batch output"
        elif completion.error is not None:
            row.update(explanation=completion.text or "", error=completion.error)
        else:
            parsed = parse_final_range(completion.text)
            row.update(explanation=completion.text, parse_ok=parsed.parse_ok, lower=parsed.lower,
                       upper=parsed.upper, parse_error=parsed.error, parse_method=parsed.method)

        for key, value in instance.items():  # §6.1: every other field passes through untouched
            row.setdefault(key, value)
        rows.append(row)
    return rows


def summarise(rows) -> str:
    """The §8 summary line: how many worked, and how each of the rest failed."""
    ok = sum(1 for row in rows if row["parse_ok"])
    provider_error = sum(1 for row in rows if row["error"])
    parse_failed = len(rows) - ok - provider_error
    return (f"{ok} ok, {parse_failed} parse-failed, {provider_error} provider-error "
            f"out of {len(rows)} total")


def annotate(instances, *, provider, dimension, propensity_name, rubric, presentation,
             mode="auto", temperature=0.0, max_tokens=None, max_workers=8, max_retries=3,
             on_progress=None, retry_backoff=1.0, poll_interval=60.0) -> list[dict]:
    """Annotates every instance on one dimension with one provider, returning §6.2 rows.

    mode: "batch" requires a batch-capable provider; "sequential" calls the provider once per
    instance; "auto" takes the batch API when there is one and says so when it falls back.

    temperature stays at 0: the intervals are a property of the instance, and have to be stable
    across reruns.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if temperature:
        logger.warning("temperature is %s rather than 0: intervals will not be stable across "
                       "reruns", temperature)

    requests = build_requests(instances, propensity_name=propensity_name, rubric=rubric,
                              presentation=presentation)
    annotator = f"{provider.name}:{provider.model}"

    if mode == "batch":
        require_batch(provider)
    elif mode == "auto":
        mode = "batch" if isinstance(provider, BatchCapable) else "sequential"
        if mode == "sequential":
            logger.info("provider %r has no batch API; using the sequential path",
                        getattr(provider, "name", provider))

    if mode == "sequential":
        completions = run_sequential(provider, requests, temperature=temperature,
                                     max_tokens=max_tokens, max_workers=max_workers,
                                     max_retries=max_retries, retry_backoff=retry_backoff,
                                     on_progress=on_progress)
    else:
        batch_id = submit(provider, requests, temperature=temperature, max_tokens=max_tokens)
        state = wait_for_batch(provider, batch_id, poll_interval=poll_interval)
        if state == "completed":
            completions = collect(provider, batch_id, requests)
        else:  # a failed batch is recorded on every row, not raised
            completions = {request.custom_id: Completion(text="", error=f"batch {batch_id} ended as {state}")
                           for request in requests}

    rows = rows_from_completions(instances, completions, dimension=dimension, annotator=annotator)
    print(summarise(rows))
    return rows
