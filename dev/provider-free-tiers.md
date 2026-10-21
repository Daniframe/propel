# Testing the providers without a budget

Which providers can be exercised against their real API for free, what that would prove, and
what it would not. Researched 19–20 September 2026; prices and free tiers move, so re-check
before relying on any line here. Claims marked **unverified** come from secondary sources.

Why it matters: every adapter is covered by tests against fake clients, and `test_adapters.py`
builds each SDK's real client, but until October 2026 **no adapter had ever completed a real
annotation call**. That was the main thing keeping PROPEL below 1.0.

**`google` is now proven end to end.** On 21 October 2026 it annotated the 200-instance
MetaSafetyBench sample battery on `gemini-3.8-flash` from a Kaggle notebook: two dimensions
completed (400 calls, 388 parsed) before the run was stopped by hand. Authentication, the
`system_instruction` transport, usage reporting, interval parsing and the written rows all
worked on the first real attempt. Two defects surfaced, neither in the request path: the
notebook's progress lines were swallowed by a `redirect_stdout` (notebook-side), and an empty
response dropped its finish reason when the SDK returned it as a plain string rather than an
enum (fixed in 0.5.2, with the fake extended to cover both shapes).

What that leaves: `openai`, `azure`, `anthropic` and `http` still have no real annotation call
behind them, and no batch path has ever been submitted to a real queue.

## What a test needs

A pilot of 20 instances on one rubric: 20 requests, roughly 2,400 input and 900 output tokens
each, about 50k input and 18k output tokens in total. Any free tier that allows ~20 requests a
day and a 3k-token context covers it. A smoke test of 3 requests is enough to prove an adapter
works at all.

## The shortest path to covering every adapter

| Adapter | Free route | Cost | Proves |
|---|---|---|---|
| `google` | Gemini API free tier, through Google AI Studio | free, no card | the adapter end to end, including `system_instruction` and the usage fields |
| `openai` | OpenRouter's `:free` models, or Groq, as an OpenAI-compatible endpoint (`base_url`) | free, no card | the adapter's request shape, parsing and usage handling, but against someone else's server |
| `http` | the same endpoints, or a local Ollama | free | `build_payload` / `extract_text` against a real HTTP API |
| `openai`, at api.openai.com | data-sharing free tokens, after reaching usage tier 1 | one $5 top-up, then free | the real endpoint, prompt caching, and the `cached_input_tokens` column |
| `anthropic` | a reported $5 trial credit on a new console account (**unverified**) | free or ~$1 | the adapter, its `max_tokens` requirement and its cache accounting |
| `azure` | no free route found | a working key for the lab's resource | the only adapter with a different client, endpoint shape and API version |
| batch paths | none: every batch API needs a funded account | a few cents, once funded | `submit`/`poll`/`fetch` against a real queue |

**Read that as: about $5–10 of credit covers everything, and most of it can be done for free.**

## Provider by provider

**Google Gemini.** A real free tier: free input and output tokens on the Flash models, no
credit card, keys from Google AI Studio. The catch is written into the pricing page: on the
free tier "content is used to improve our products", whereas the paid tier says it is not.
Rate limits are per model and are not published on the pricing page. This is the one provider
whose own adapter can be exercised for nothing.

**OpenAI.** No automatic signup credits since late 2025: the API needs a payment method, and
the minimum top-up is $5. Two ways round it:
- **Data-sharing free tokens.** Opt in on the data-sharing settings page and eligible
  organisations get daily complimentary tokens (reported as up to 1M/day on large models,
  10M/day on mini and nano). Eligibility starts at usage tier 1, which requires having paid $5
  at some point, so this is "free after the first $5", not free.
- **Researcher Access Program.** Up to $1,000 in credits for people with an active university
  affiliation, which applies here. Worth an application: it would cover the annotation budget
  as well as the tests.

**OpenAI-compatible endpoints.** These exercise our `openai` adapter code with a different
`base_url`, which is exactly how a self-hosted server is used:
- **OpenRouter:** 20+ models with `:free` ids, no credit card, 20 requests/minute and 50/day
  (a one-time $10 purchase raises the daily cap). Enough for a 20-instance pilot per day.
- **Groq:** free tier, 30 requests/minute, OpenAI-compatible, no card.
- **Ollama, local:** no account, no limits, no network. Already used once in this project for a
  20-instance check. It proves the request shape but not a vendor's server.
- **GitHub Models** was the obvious candidate, but one source says it was retired on
  2026-07-30 (**unverified**). Check before counting on it.

**Anthropic.** No published free tier. Several sources describe a one-time $5 credit for a new
console account with phone verification; one says it no longer exists (**unverified, and they
contradict each other**). Failing that, $5 of credit buys far more than the tests need: the
20-instance pilot costs cents.

**Azure OpenAI.** No free route found. Azure for Students gives $100 without a credit card, but
at least one Microsoft source says the credit does not apply to Azure OpenAI (**unverified**).
The practical path is the lab's existing resource, `openaiazureprop`, once its key works: the
key at hand is rejected by both OpenAI and that resource.

**Batch APIs.** OpenAI's Files+Batches and Anthropic's Message Batches both need a funded
account; neither is part of any free tier. Our batch logic is covered by the path-equivalence
tests against fakes, but a real submit/poll/fetch has never run. A batch of 3 short requests
costs about a cent once an account is funded.

## Caveats worth weighing before using a free tier

- **Free tiers train on what you send.** Gemini's free tier and OpenAI's data-sharing tokens
  both feed the provider's models. For the example data, that is harmless. For unpublished
  safety instances, or rubrics whose copyright is not settled, it is not: a free tier is the
  wrong place for them. Use the public example instances for adapter tests.
- **A free tier proves the adapter, not the annotations.** Free models are small; their
  intervals are not the ones a study would use. Adapter coverage and annotation quality are
  separate questions.
- **Rate limits shape the test.** 50 requests a day is fine for a 20-instance pilot, and
  useless for a bank of 3,000.

## Suggested order

1. **Gemini free tier** — the `google` adapter, free, today.
2. **OpenRouter or Groq** — the `openai` adapter against a real server, free, today.
3. **Ollama** — the `http` adapter, free, offline.
4. **Apply to the Researcher Access Program**; if it lands, it covers OpenAI, its batch API and
   the annotation budget.
5. **$5 on Anthropic** if no trial credit appears, for the `anthropic` adapter and its batches.
6. **The lab's Azure key**, for the one adapter nothing else can reach.
