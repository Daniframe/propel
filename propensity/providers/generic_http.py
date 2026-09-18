"""A last resort, for an endpoint no other adapter covers.

The caller supplies the URL, any headers, and two callables: `build_payload` turns a prompt into
the JSON body the endpoint expects, and `extract_text` pulls the answer back out of the JSON it
returns. How the system part is delivered is up to `build_payload`. Not batch-capable.
httpx is imported lazily.
"""

import importlib
import importlib.util
import os
from pathlib import Path

from ..errors import ProviderError
from . import register_provider
from .base import Completion


class GenericHTTPProvider:
    """Posts each prompt to `url` as the body `build_payload(system, user, model=...,
    temperature=..., max_tokens=...)` returns, and reads the answer with
    `extract_text(response_json)`. Either callable can be named by a "path/to/file.py:function"
    or "module:function" string, which is how `propel-annotate` passes one. A key from `api_key` or
    `api_key_env` is sent as `Authorization: Bearer`; `headers` adds anything else."""

    name = "http"

    def __init__(self, model: str, *, url: str, build_payload, extract_text, headers=None,
                 api_key=None, api_key_env=None, timeout: float = 120.0, client=None):
        self.model = model
        self.url = url
        self.build_payload = _resolve(build_payload)
        self.extract_text = _resolve(extract_text)
        key = api_key or (os.environ.get(api_key_env) if api_key_env else None)
        self.headers = {**({"Authorization": f"Bearer {key}"} if key else {}), **(headers or {})}
        self.client = client if client is not None else self._client(timeout)

    @staticmethod
    def _client(timeout):
        try:
            import httpx
        except ImportError:
            raise ImportError("the 'http' provider needs the httpx package: "
                              'pip install "propel[http]"') from None
        return httpx.Client(timeout=timeout)

    def complete(self, system: str, user: str, *, temperature: float = 0.0,
                 max_tokens: int | None = None) -> Completion:
        raw = None
        try:
            payload = self.build_payload(system, user, model=self.model, temperature=temperature,
                                         max_tokens=max_tokens)
            response = self.client.post(self.url, json=payload, headers=self.headers)
            response.raise_for_status()
            raw = response.json()
            text = self.extract_text(raw)
        except Exception as exc:  # never raise: the run records failures and carries on
            return Completion(text="", raw=raw, error=f"{type(exc).__name__}: {exc}")
        if not text:
            return Completion(text="", raw=raw, error="the provider returned an empty response")
        return Completion(text=text, raw=raw)


def _resolve(function):
    """A callable, or a string naming one: "path/to/file.py:function", or "module:function" for
    a module on the import path. A console script does not put the working directory on that
    path, so a file of your own is best named by its path."""
    if not isinstance(function, str):
        return function
    source, _, attribute = function.rpartition(":")  # the last colon: C:\... paths have one too
    try:
        if source.endswith(".py"):
            spec = importlib.util.spec_from_file_location(Path(source).stem, source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(source)
        return getattr(module, attribute)
    except (ImportError, OSError, AttributeError, ValueError) as exc:
        raise ProviderError(f"the 'http' provider cannot load {function!r} ({type(exc).__name__}: "
                            f"{exc}); name it as path/to/file.py:function or module:function") from None


register_provider("http", GenericHTTPProvider)
