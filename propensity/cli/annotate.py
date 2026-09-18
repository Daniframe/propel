"""propel-annotate: label task instances with propensity demand intervals, using an LLM and a rubric.

    propel-annotate run    --instances items.jsonl --dimension RA --out RA_annotations.jsonl
    propel-annotate submit --instances items.jsonl --dimension RA --out RA_annotations.jsonl
    propel-annotate status --job RA_annotations.jsonl.job.json
    propel-annotate fetch  --job RA_annotations.jsonl.job.json

`run` calls the provider once per instance. `submit` uses the provider's batch API, about half
the price where it exists, and writes a job file *before* it starts polling, so a multi-hour
batch survives a closed laptop: `status` and `fetch` pick it up from that file.
"""

import argparse
import hashlib
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

from ..annotation import (
    annotate,
    build_requests,
    collect,
    load_dimensions,
    load_presentation,
    load_rubric,
    rows_from_completions,
    submit,
    summarise,
    wait_for_batch,
)
from ..annotation.rubrics import DEFAULT_VERSION
from ..errors import ContractError, PropensityError, ProviderError
from ..modelling.io import load_instances, write_table
from ..providers import get_provider
from . import load_config, load_dotenv_if_available

DEFAULT_CONFIG = "config/annotation.yaml"
# Never written into a job file, which sits on disk next to the annotations.
SECRET_OPTIONS = ("api_key", "token", "secret", "password")
JOB_CONFIG_HELP = "accepted for symmetry; the job file holds every setting"


def build_parser():
    parser = argparse.ArgumentParser(prog="propel-annotate", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def with_inputs(command):
        command.add_argument("--instances", required=True, help="instances file (.jsonl or .csv)")
        command.add_argument("--dimension", required=True, help="dimension code, e.g. RA")
        command.add_argument("--out", required=True, help="where to write the annotation rows")
        command.add_argument("--propensity-name",
                             help="the trait in words, as the prompt names it (default: the catalogue's)")
        command.add_argument("--rubrics-dir",
                             help="a rubrics directory of your own (default: the rubrics PROPEL ships)")
        command.add_argument("--rubric-version",
                             help="rubric version: v2 reads {CODE}/{CODE}_v2.md (default: the catalogue's)")
        command.add_argument("--provider", help="provider name, e.g. openai or mock")
        command.add_argument("--model", help="model name; for azure, the deployment name")
        command.add_argument("--provider-option", action="append", default=[], metavar="KEY=VALUE",
                             help="extra provider argument, e.g. base_url=... (repeatable)")
        command.add_argument("--max-workers", type=int, help="parallel calls for run (default: 8)")
        command.add_argument("--max-retries", type=int,
                             help="retries per instance after a provider error (default: 3)")
        command.add_argument("--config", default=DEFAULT_CONFIG,
                             help=f"settings file (default: {DEFAULT_CONFIG})")

    with_inputs(sub.add_parser("run", help="one call per instance (the reference path)"))
    submit_command = sub.add_parser("submit", help="send a batch and write a job file")
    with_inputs(submit_command)
    submit_command.add_argument("--wait", action="store_true",
                                help="poll until the batch finishes, then fetch it")

    status_command = sub.add_parser("status", help="ask how a submitted batch is doing")
    status_command.add_argument("--job", required=True, help="the .job.json file submit wrote")
    status_command.add_argument("--config", default=DEFAULT_CONFIG, help=JOB_CONFIG_HELP)

    fetch_command = sub.add_parser("fetch", help="collect a finished batch into annotation rows")
    fetch_command.add_argument("--job", required=True, help="the .job.json file submit wrote")
    fetch_command.add_argument("--out", help="override the job's output path")
    fetch_command.add_argument("--force", action="store_true",
                               help="fetch even though the prompts no longer match the job")
    fetch_command.add_argument("--config", default=DEFAULT_CONFIG, help=JOB_CONFIG_HELP)
    return parser


def coerce(text):
    """"true" -> True, "8" -> 8, everything else stays a string."""
    lowered = text.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("none", "null"):
        return None
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def resolve(args):
    """Config file first, command-line flags on top."""
    config = load_config(args.config)
    options = dict(config.get("provider_options") or {})
    for pair in args.provider_option:
        key, separator, value = pair.partition("=")
        if not separator:
            raise ContractError(f"--provider-option takes KEY=VALUE, got {pair!r}")
        options[key.strip()] = coerce(value)

    rubrics_dir = args.rubrics_dir or config.get("rubrics_dir")  # None: the packaged rubrics
    catalogued = load_dimensions(rubrics_dir).get(args.dimension)
    settings = {
        "provider": args.provider or config.get("provider"),
        "model": args.model or config.get("model"),
        "options": options,
        "rubrics_dir": rubrics_dir,
        "rubric_version": (args.rubric_version or config.get("rubric_version")
                           or (catalogued.version if catalogued else DEFAULT_VERSION)),
        "temperature": config.get("temperature", 0.0),
        "max_tokens": config.get("max_tokens"),
        "max_workers": args.max_workers or config.get("max_workers", 8),
        "max_retries": config.get("max_retries", 3) if args.max_retries is None else args.max_retries,
        "poll_interval": config.get("poll_interval_s", 60),
        "propensity_name": (args.propensity_name or (config.get("dimensions") or {}).get(args.dimension)
                            or (catalogued.name if catalogued else None)),
    }
    if not settings["provider"] or not settings["model"]:
        raise ContractError("no provider or model; pass --provider and --model, or set them in "
                            f"{args.config}")
    if not settings["propensity_name"]:
        raise ContractError(f"no name in words for dimension {args.dimension!r}: it is not in the "
                            "dimension catalogue; pass --propensity-name, or add it under "
                            f"'dimensions' in {args.config}")
    return settings


def build_provider(name, model, options):
    try:
        return get_provider(name, model=model, **options)
    except (PropensityError, ImportError):
        raise
    except Exception as exc:  # an unknown option, or a vendor SDK refusing to start
        raise ProviderError(f"could not start the {name!r} provider: {type(exc).__name__}: "
                            f"{exc}") from exc


def prompts_digest(requests):
    """A fingerprint of every prompt, so `fetch` can tell whether the inputs moved since submit."""
    digest = hashlib.sha256()
    for request in requests:
        for part in (request.custom_id, request.system, request.user):
            digest.update(part.encode("utf-8"))
            digest.update(b"\x00")
    return digest.hexdigest()


def prepare(settings, instances_path, dimension):
    """The instances and the prompts, built the same way for every command."""
    instances = load_instances(instances_path)
    requests = build_requests(
        instances,
        propensity_name=settings["propensity_name"],
        rubric=load_rubric(dimension, settings["rubrics_dir"], settings["rubric_version"]),
        presentation=load_presentation(settings["rubrics_dir"]),
    )
    return instances, requests


def progress_reporter(every=25):
    def report(done, total):
        if done == total or done % every == 0:
            print(f"annotated {done}/{total}", file=sys.stderr)
    return report


def do_run(args):
    settings = resolve(args)
    instances = load_instances(args.instances)
    provider = build_provider(settings["provider"], settings["model"], settings["options"])
    rows = annotate(
        instances, provider=provider, dimension=args.dimension,
        propensity_name=settings["propensity_name"],
        rubric=load_rubric(args.dimension, settings["rubrics_dir"], settings["rubric_version"]),
        presentation=load_presentation(settings["rubrics_dir"]),
        mode="sequential", temperature=settings["temperature"], max_tokens=settings["max_tokens"],
        max_workers=settings["max_workers"], max_retries=settings["max_retries"],
        on_progress=progress_reporter(),
    )
    write_table(rows, args.out)
    print(f"wrote {args.out}")
    return 0


def do_submit(args):
    settings = resolve(args)
    _, requests = prepare(settings, args.instances, args.dimension)
    provider = build_provider(settings["provider"], settings["model"], settings["options"])
    batch_id = submit(provider, requests, temperature=settings["temperature"],
                      max_tokens=settings["max_tokens"])

    job_path = Path(f"{args.out}.job.json")
    job = {
        "batch_id": batch_id,
        "provider": settings["provider"],
        "model": settings["model"],
        "provider_options": {k: v for k, v in settings["options"].items()
                             if not any(secret in k.lower() for secret in SECRET_OPTIONS)},
        "dimension": args.dimension,
        "propensity_name": settings["propensity_name"],
        "instances": str(args.instances),
        "rubrics_dir": None if settings["rubrics_dir"] is None else str(settings["rubrics_dir"]),
        "rubric_version": settings["rubric_version"],
        "out": str(args.out),
        "n_requests": len(requests),
        "prompts_sha256": prompts_digest(requests),
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")  # before any polling
    print(f"submitted batch {batch_id} with {len(requests)} requests")
    print(f"wrote {job_path}")
    print(f"next: propel-annotate status --job {job_path}")

    if args.wait:
        state = wait_for_batch(provider, batch_id, poll_interval=settings["poll_interval"])
        print(f"batch {batch_id} ended as {state}")
        return do_fetch(argparse.Namespace(job=str(job_path), out=args.out, force=False,
                                           config=args.config))
    return 0


def read_job(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractError(f"{path}: no such job file") from None
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path}: not valid JSON ({exc.msg})") from None


def do_status(args):
    job = read_job(args.job)
    provider = build_provider(job["provider"], job["model"], job.get("provider_options") or {})
    state = provider.poll_batch(job["batch_id"])
    print(f"batch {job['batch_id']}: {state}")
    print(f"  {job['n_requests']} requests for {job['dimension']} via "
          f"{job['provider']}:{job['model']}, submitted {job['submitted_at']}")
    if state == "completed":
        print(f"  next: propel-annotate fetch --job {args.job}")
    return 0


def do_fetch(args):
    job = read_job(args.job)
    settings = {"rubrics_dir": job["rubrics_dir"], "rubric_version": job["rubric_version"],
                "propensity_name": job["propensity_name"]}
    instances, requests = prepare(settings, job["instances"], job["dimension"])
    if prompts_digest(requests) != job["prompts_sha256"] and not args.force:
        print(f"error: the prompts no longer match the ones submitted as {job['batch_id']}, so "
              "the instances or the rubric changed since. Submit again, or pass --force to "
              "fetch anyway and accept rows attributed to prompts that have moved.",
              file=sys.stderr)
        return 2

    provider = build_provider(job["provider"], job["model"], job.get("provider_options") or {})
    state = provider.poll_batch(job["batch_id"])
    if state in ("failed", "cancelled"):
        print(f"batch {job['batch_id']} ended as {state}; nothing to fetch. Submit it again.")
        return 1
    if state != "completed":
        print(f"batch {job['batch_id']} is {state}; nothing to fetch yet")
        return 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        completions = collect(provider, job["batch_id"], requests)
    for warning in caught:
        print(f"warning: {warning.message}", file=sys.stderr)

    rows = rows_from_completions(instances, completions, dimension=job["dimension"],
                                 annotator=f"{provider.name}:{provider.model}")
    out = args.out or job["out"]
    write_table(rows, out)
    print(summarise(rows))
    print(f"wrote {out}")
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    load_dotenv_if_available()
    args = build_parser().parse_args(argv)
    commands = {"run": do_run, "submit": do_submit, "status": do_status, "fetch": do_fetch}
    try:
        return commands[args.command](args)
    except (PropensityError, ImportError) as exc:  # ImportError names the extra to install
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
