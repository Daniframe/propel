# `propensity.providers`

The narrow interface between PROPEL and any LLM. The options of each shipped provider are in
[Providers](../providers.md); this page covers the protocol, the registry and the classes.

## Protocol

`propensity.providers.base`.

### `LLMProvider`

What every provider implements. Checked structurally: `isinstance(p, LLMProvider)`.

```python
class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int | None = None) -> Completion: ...
```

**`complete` must not raise on a provider failure.** It returns
`Completion(text="", error="...")` instead, so a run records the failure and continues.

### `BatchCapable`

Optional; implement it only where the API has a native batch endpoint.

```python
class BatchCapable(Protocol):
    def submit_batch(self, requests: list[BatchRequest], *, temperature: float = 0.0,
                     max_tokens: int | None = None) -> str: ...        # returns a batch id
    def poll_batch(self, batch_id: str) -> BatchState: ...
    def fetch_batch(self, batch_id: str) -> dict[str, Completion]: ...  # keyed by custom_id
```

- **`BatchState`** is one of `"pending"`, `"running"`, `"completed"`, `"failed"` or
  `"cancelled"`.
- **Order.** Batch results come back in any order; callers rejoin them by `custom_id`.
- **Truthful capability.** Ship batch support as a separate class, so that
  `isinstance(p, BatchCapable)` is true only when batching really works.

### `Completion`

Frozen dataclass: one response.

| Field | Type | Meaning |
|---|---|---|
| `text` | str | the full response text; `""` when `error` is set |
| `raw` | dict or None | the provider's response, for auditing |
| `usage` | dict or None | token counts, when available |
| `error` | str or None | set when the call failed |

### `BatchRequest`

Frozen dataclass: one prompt in a batch.

| Field | Type | Meaning |
|---|---|---|
| `custom_id` | str | the instance's `question_id` |
| `system` | str | system part |
| `user` | str | user part |

The system and user parts always travel separately; each provider decides how to deliver the
system part.

## Registry

`propensity.providers`.

```python
get_provider(name, **kwargs)
register_provider(name, factory) -> None
available_providers() -> list[str]
```

| Function | Does |
|---|---|
| `get_provider` | builds the named provider, passing `kwargs` to its factory. Raises `ProviderError` for an unknown name (listing the available ones), and `ImportError` naming the extra when the SDK is missing |
| `register_provider` | registers `factory(**kwargs) -> provider` under `name`, replacing any existing one; a class works as a factory |
| `available_providers` | the registered names, sorted |

The registry is the only module-level state in PROPEL. Providers themselves share nothing, so
several can be used side by side.

```python
from propensity import available_providers, get_provider

available_providers()   # ['anthropic', 'azure', 'google', 'http', 'mock', 'openai']
provider = get_provider("openai", model="gpt-4.1", base_url="http://localhost:8000/v1", api_key="x")
```

## Shipped classes

| Registered as | Class | Batch class | Module |
|---|---|---|---|
| `openai` | `OpenAICompatProvider` | `OpenAIBatchProvider` | `providers.openai_compat` |
| `azure` | `AzureOpenAIProvider` | `AzureOpenAIBatchProvider` | `providers.azure_openai` |
| `anthropic` | `AnthropicProvider` | `AnthropicBatchProvider` | `providers.anthropic` |
| `google` | `GoogleProvider` | none | `providers.google` |
| `http` | `GenericHTTPProvider` | none | `providers.generic_http` |
| `mock` | `MockProvider` | `MockBatchProvider` | `providers.mock` |

`get_provider` picks the class:
- `batch=` chooses for `openai`, `azure`, `anthropic` and `mock`;
- `openai` detects batch support when `batch` is not given;
- `google` and `http` do not take `batch`.

Constructors:

```python
OpenAICompatProvider(model, *, api_key=None, api_key_env=None, base_url=None, client=None,
                     request_options=None, send_temperature=True, **client_options)
AzureOpenAIProvider(model, *, endpoint=None, endpoint_env=None, api_version=None, **kwargs)
AnthropicProvider(model, *, api_key=None, api_key_env=None, client=None, send_temperature=True,
                  request_options=None, **client_options)
GoogleProvider(model, *, api_key=None, api_key_env=None, client=None, send_temperature=True,
               config_options=None, **client_options)
GenericHTTPProvider(model, *, url, build_payload, extract_text, headers=None, api_key=None,
                    api_key_env=None, timeout=120.0, client=None)
MockProvider(model="mock-1", *, response=DEFAULT_RESPONSE, key=None, transient_failures=0)
MockBatchProvider(model="mock-1", *, scramble=True, drop=(), unknown=(), states=None, seed=0,
                  state_path=None, **kwargs)
```

- `**client_options` go to the vendor SDK's client constructor.
- `client` injects a ready-made SDK client, which is also how to test a provider without a
  network.

**Attributes useful from Python:**

| Class | Attribute | Holds |
|---|---|---|
| every provider | `name`, `model` | written on rows as `annotator = f"{name}:{model}"` |
| `MockProvider` | `calls` | every `(system, user)` it received, in order |
| `MockProvider` | `attempts` | `{key: times asked}` |
| `MockBatchProvider` | `batches` | `{batch_id: requests}` |
| `MockBatchProvider` | `polls` | `{batch_id: times polled}` |

**Constants:**

| Module | Constant | Value |
|---|---|---|
| `providers.anthropic` | `DEFAULT_MAX_TOKENS` | `16000` |
| `providers.anthropic` | `CUSTOM_ID` | the id pattern Message Batches accepts |
| `providers.openai_compat` | `BATCH_STATES` | vendor state → `BatchState` |
| `providers.anthropic` | `BATCH_STATES` | vendor state → `BatchState` |
| `providers.mock` | `DEFAULT_RESPONSE` | the mock's default answer |

Writing your own provider: [Tutorial 10](../tutorials/10-adding-a-provider.md).
