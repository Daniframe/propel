# Tutorial 10: adding a provider

Connect an LLM API that PROPEL does not ship. Try the [`http` provider](../providers.md#http)
first: any API that takes JSON and returns JSON needs only two small functions. Write a provider
when the API needs its own SDK, authentication flow or batch endpoint.

**You need:** PROPEL, run where `python -m propensity.examples` has put the example data in
`examples/`. The code runs offline: a small class stands in for the vendor's SDK.

## 1. The contract

A provider is any object with:
- a **`name`** and a **`model`**, which are written on every row as `annotator = "name:model"`;
- **`complete(system, user, *, temperature=0.0, max_tokens=None) -> Completion`**.

`complete` has three rules:
- **Never raise on an API failure.** Return `Completion(text="", error="...")`, so the run
  records the failure and continues.
- **Return the full text** as `Completion.text`. Put the raw response in `raw`, and token counts
  in `usage` when available.
- **Deliver the system part as the API expects:** a system message, a dedicated parameter, or
  prepended to the user text with `as_single_string(system, user)`.

## 2. A stand-in for the vendor SDK

```python
class AcmeClient:
    """Pretends to be `acme_sdk.Client`: one text field in, a dict out."""

    def __init__(self, api_key=None):
        self.api_key = api_key

    def generate(self, prompt, *, temperature, max_new_tokens):
        if "RA_013" in prompt or "certain $480)" in prompt:
            raise TimeoutError("upstream timed out")
        return {"output": "Reasoning...\n<FINAL_RANGE>[-1, 3]</FINAL_RANGE>",
                "tokens": {"input": len(prompt) // 4, "output": 12}}
```

## 3. The provider

```python
import os
from propensity import Completion
from propensity.annotation import as_single_string


class AcmeProvider:
    name = "acme"

    def __init__(self, model, *, api_key=None, api_key_env="ACME_API_KEY", client=None,
                 max_new_tokens=4096):
        self.model = model
        self.max_new_tokens = max_new_tokens
        self.client = client if client is not None else self._client(api_key or os.environ.get(api_key_env))

    @staticmethod
    def _client(api_key):
        try:
            import acme_sdk  # import inside: using PROPEL never requires this SDK
        except ImportError:
            raise ImportError("the 'acme' provider needs acme-sdk: pip install acme-sdk") from None
        return acme_sdk.Client(api_key=api_key)

    def complete(self, system, user, *, temperature=0.0, max_tokens=None):
        try:
            response = self.client.generate(as_single_string(system, user), temperature=temperature,
                                            max_new_tokens=max_tokens or self.max_new_tokens)
        except Exception as exc:  # never raise: the failure goes on the row
            return Completion(text="", error=f"{type(exc).__name__}: {exc}")
        text = response.get("output") or ""
        if not text:
            return Completion(text="", raw=response, error="the provider returned an empty response")
        return Completion(text=text, raw=response, usage=response.get("tokens"))
```

- **The lazy import** keeps `import propensity` working for colleagues who never use this
  provider.
- **`client`** lets you inject a ready-made or fake client, which is how the rest of this
  tutorial runs.

## 4. Register it and use it

```python
from propensity import LLMProvider, annotate, get_provider, register_provider
from propensity import load_instances, load_presentation, load_rubric

register_provider("acme", AcmeProvider)
provider = get_provider("acme", model="acme-large", client=AcmeClient())
assert isinstance(provider, LLMProvider)

instances = load_instances("examples/items_RA.jsonl")[:20]
rows = annotate(instances, provider=provider, dimension="RA", propensity_name="risk aversion",
                rubric=load_rubric("RA"), presentation=load_presentation(),
                mode="sequential", retry_backoff=0)
print([row["error"] for row in rows if row["error"]], rows[0]["annotator"])
```

```text
19 ok, 0 parse-failed, 1 provider-error out of 20 total
['TimeoutError: upstream timed out'] acme:acme-large
```

The timeout was retried `max_retries` times (3 by default), then recorded on its row. The run
was never interrupted.

## 5. A batch-capable version

If the API has a batch endpoint, add the three batch methods in a **separate class**, so that
`isinstance(provider, BatchCapable)` is only true when batching really works:

```python
import random
from propensity import BatchCapable


class AcmeBatchClient(AcmeClient):
    """Pretends to be the SDK's batch endpoint; results come back shuffled, as real ones do."""

    def __init__(self, api_key=None):
        super().__init__(api_key)
        self.jobs = {}

    def create_job(self, items):
        job_id = f"job-{len(self.jobs) + 1}"
        self.jobs[job_id] = items
        return job_id

    def job_status(self, job_id):
        return "DONE"

    def job_results(self, job_id):
        results = [{"id": item["id"], **self._answer(item)} for item in self.jobs[job_id]]
        random.Random(0).shuffle(results)
        return results

    def _answer(self, item):
        try:
            return self.generate(item["prompt"], temperature=item["temperature"],
                                 max_new_tokens=item["max_new_tokens"])
        except TimeoutError as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}


class AcmeBatchProvider(AcmeProvider):
    STATES = {"QUEUED": "pending", "RUNNING": "running", "DONE": "completed",
              "FAILED": "failed", "CANCELLED": "cancelled"}

    def submit_batch(self, requests, *, temperature=0.0, max_tokens=None):
        return self.client.create_job([
            {"id": request.custom_id, "prompt": as_single_string(request.system, request.user),
             "temperature": temperature, "max_new_tokens": max_tokens or self.max_new_tokens}
            for request in requests])

    def poll_batch(self, batch_id):
        return self.STATES.get(self.client.job_status(batch_id), "running")

    def fetch_batch(self, batch_id):
        completions = {}
        for result in self.client.job_results(batch_id):
            if result.get("error"):
                completions[result["id"]] = Completion(text="", raw=result, error=result["error"])
            else:
                completions[result["id"]] = Completion(text=result["output"], raw=result,
                                                        usage=result.get("tokens"))
        return completions
```

The batch methods have their own rules:
- **`submit_batch`** sends every request and returns the provider's batch id.
- **`poll_batch`** maps the provider's states onto `pending`, `running`, `completed`, `failed`
  and `cancelled`. An unknown state is safest read as `running`.
- **`fetch_batch`** returns completions keyed by `custom_id`, the instance's `question_id`, in
  any order. A failed item becomes an error completion, never a missing key.

## 6. Check that both paths agree

Whichever path runs, the rows must be identical:

```python
register_provider("acme", lambda model, batch=False, **options:
                  (AcmeBatchProvider if batch else AcmeProvider)(model, **options))

sequential = get_provider("acme", model="acme-large", client=AcmeBatchClient())
batched = get_provider("acme", model="acme-large", client=AcmeBatchClient(), batch=True)
assert not isinstance(sequential, BatchCapable) and isinstance(batched, BatchCapable)

common = {"dimension": "RA", "propensity_name": "risk aversion", "rubric": load_rubric("RA"),
          "presentation": load_presentation(), "retry_backoff": 0, "poll_interval": 0}
one_by_one = annotate(instances, provider=sequential, mode="sequential", max_retries=0, **common)
in_a_batch = annotate(instances, provider=batched, mode="batch", **common)
assert one_by_one == in_a_batch
```

```text
19 ok, 0 parse-failed, 1 provider-error out of 20 total
19 ok, 0 parse-failed, 1 provider-error out of 20 total
```

`max_retries=0` makes the sequential path give up at once, as the batch does, so the error rows
match too. Error messages have to match as well: format them the same way on both paths.

## 7. Make it available to the command line

The CLI resolves `--provider` through the same registry, but only knows the providers that
PROPEL imports when it starts. To add one:

1. Save the classes as a module in the package, e.g. `propensity/providers/acme.py`, ending in:

   ```text
   register_provider("acme", _build)
   ```

   where `_build(model, *, batch=True, **options)` returns the batch or plain class.
2. Add `acme` to the list of adapters imported at the end of `propensity/providers/__init__.py`.
3. Declare the SDK as an extra in `pyproject.toml`: `acme = ["acme-sdk"]`.

Then:

<!-- no-run -->
```bash
propel-annotate run --instances data/items.jsonl --dimension RA --out out/RA.jsonl \
    --provider acme --model acme-large --provider-option max_new_tokens=8000
```

From Python, `register_provider` in your own code is enough; nothing in the package changes.

## Checklist

- [ ] `name` and `model` set; `complete` never raises on an API failure.
- [ ] Empty responses, refusals and truncations return an error, not an empty text.
- [ ] The system part is delivered the way the API expects.
- [ ] The vendor SDK is imported lazily, with an `ImportError` that says how to install it.
- [ ] Credentials from arguments or an environment variable, never from files.
- [ ] Batch support in a separate class; `fetch_batch` keyed by `custom_id`; failed items
      become error completions.
- [ ] Sequential and batch paths give identical rows (step 6).
- [ ] No state shared between instances: two providers must work side by side.
