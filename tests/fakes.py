"""Fake SDK clients: the slice of each vendor SDK its adapter touches, and nothing else.

Each takes `respond`, a function from the request the adapter built to the answer text, so a batch
can be answered from what was actually submitted, and in shuffled order, as real batches return.
"""

import json
import random
from types import SimpleNamespace


# --- OpenAI and Azure OpenAI -------------------------------------------------------------

class OpenAIResponse:
    def __init__(self, text, usage=None):
        self.choices = ([SimpleNamespace(message=SimpleNamespace(content=text))]
                        if text is not None else [])
        self.usage = usage

    def model_dump(self):
        return {"choices": [{"message": {"content": choice.message.content}}
                            for choice in self.choices], "usage": self.usage}


def chat_result(custom_id, text, status=200, usage=None):
    """One line of an OpenAI batch output file."""
    return {"custom_id": custom_id, "response": {"status_code": status,
            "body": {"choices": [{"message": {"content": text}}], "usage": usage}}}


class FakeOpenAIClient:
    """Chat completions, Files and Batches. `output` fixes the batch output file; left unset, it
    is built from the uploaded batch by applying `respond` to each line's body."""

    def __init__(self, text="answer", *, respond=None, usage=None, raises=None,
                 status="completed", output=None, errors=(), batches=True, seed=0):
        self.bodies, self.uploads, self.submitted, self.fetched = [], [], [], []
        self.respond = respond or (lambda body: text)
        self.usage, self.raises, self.status = usage, raises, status
        self.output, self.errors, self.seed = output, list(errors), seed
        self.batches_supported = batches
        self.probes = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.files = SimpleNamespace(create=self._upload, content=self._content)
        self.batches = SimpleNamespace(create=self._submit, retrieve=self._retrieve,
                                       list=self._list)

    def uploaded_lines(self):
        _, payload = self.uploads[-1]["file"]
        return [json.loads(line) for line in payload.decode().splitlines()]

    def _create(self, **body):
        self.bodies.append(body)
        if self.raises:
            raise self.raises
        return OpenAIResponse(self.respond(body), self.usage)

    def _upload(self, *, file, purpose):
        self.uploads.append({"file": file, "purpose": purpose})
        return SimpleNamespace(id="file-1")

    def _submit(self, **kwargs):
        self.submitted.append(kwargs)
        return SimpleNamespace(id="batch-1")

    def _retrieve(self, batch_id):
        self.fetched.append(batch_id)
        return SimpleNamespace(id=batch_id, status=self.status, output_file_id="out-1",
                               error_file_id="err-1" if self.errors else None)

    def _content(self, file_id):
        if file_id == "err-1":
            lines = self.errors
        elif self.output is not None:
            lines = self.output
        else:
            lines = [chat_result(line["custom_id"], self.respond(line["body"]), usage=self.usage)
                     for line in self.uploaded_lines()]
            random.Random(self.seed).shuffle(lines)
        return SimpleNamespace(text="\n".join(json.dumps(line) for line in lines))

    def _list(self, limit=None):
        self.probes += 1
        if not self.batches_supported:
            raise RuntimeError("404 page not found")
        return SimpleNamespace(data=[])


# --- Anthropic ---------------------------------------------------------------------------

def anthropic_message(text, stop_reason="end_turn", usage=None):
    """A Message: a thinking block, as current models send, then the text blocks."""
    texts = [text] if isinstance(text, str) else list(text or [])
    content = [SimpleNamespace(type="thinking", thinking="let me see")]
    content += [SimpleNamespace(type="text", text=part) for part in texts]
    return SimpleNamespace(
        content=content, stop_reason=stop_reason, usage=usage,
        model_dump=lambda: {"content": [vars(block) for block in content],
                            "stop_reason": stop_reason, "usage": usage})


class FakeAnthropicClient:
    """Messages and Message Batches. `results` fixes the batch results; left unset, they are
    built from the submitted requests by applying `respond` to each request's params."""

    def __init__(self, text="answer", *, respond=None, stop_reason="end_turn", usage=None,
                 raises=None, status="ended", results=None, seed=0):
        self.params, self.submitted, self.retrieved = [], [], []
        self.respond = respond or (lambda params: text)
        self.stop_reason, self.usage, self.raises = stop_reason, usage, raises
        self.status, self.results, self.seed = status, results, seed
        batches = SimpleNamespace(create=self._submit, retrieve=self._retrieve,
                                  results=self._results)
        self.messages = SimpleNamespace(create=self._create, batches=batches)

    def _create(self, **params):
        self.params.append(params)
        if self.raises:
            raise self.raises
        return anthropic_message(self.respond(params), self.stop_reason, self.usage)

    def _submit(self, *, requests):
        self.submitted.append(list(requests))
        return SimpleNamespace(id="msgbatch_1")

    def _retrieve(self, batch_id):
        self.retrieved.append(batch_id)
        return SimpleNamespace(id=batch_id, processing_status=self.status)

    def _results(self, batch_id):
        if self.results is not None:
            return iter(self.results)
        entries = [SimpleNamespace(custom_id=request["custom_id"], result=SimpleNamespace(
                       type="succeeded", message=anthropic_message(
                           self.respond(request["params"]), self.stop_reason, self.usage)))
                   for request in self.submitted[-1]]
        random.Random(self.seed).shuffle(entries)
        return iter(entries)


# --- Google ------------------------------------------------------------------------------

class FakeGenAIClient:
    """models.generate_content, returning `.text`, `.candidates` and usage_metadata."""

    def __init__(self, text="answer", *, respond=None, usage=None, raises=None,
                 finish_reason="STOP"):
        self.calls = []
        self.respond = respond or (lambda call: text)
        self.usage, self.raises, self.finish_reason = usage, raises, finish_reason
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, *, model, contents, config=None):
        call = {"model": model, "contents": contents, "config": config}
        self.calls.append(call)
        if self.raises:
            raise self.raises
        text = self.respond(call)
        candidate = SimpleNamespace(finish_reason=SimpleNamespace(value=self.finish_reason))
        return SimpleNamespace(text=text, candidates=[candidate], model_dump=lambda: {
            "candidates": [{"text": text}], "usage_metadata": self.usage})


# --- plain HTTP --------------------------------------------------------------------------

class FakeHTTPResponse:
    def __init__(self, status_code, payload):
        self.status_code, self.payload = status_code, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeHTTPClient:
    """An httpx.Client's post(url, json=..., headers=...)."""

    def __init__(self, payload=None, *, status=200, raises=None):
        self.posts = []
        self.payload, self.status, self.raises = payload, status, raises

    def post(self, url, *, json, headers):
        self.posts.append({"url": url, "json": json, "headers": headers})
        if self.raises:
            raise self.raises
        return FakeHTTPResponse(self.status, self.payload)
