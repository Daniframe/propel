# Installation

## Requirements

- Python 3.10 or later.
- The core depends on numpy, scipy, pandas, statsmodels and PyYAML.
- Everything provider- or plot-specific is an optional extra.

## Install

From a copy of the repository:

```bash
pip install ".[openai,plot]"         # or: pip install -e ".[openai,plot]" to edit the code
```

Pick the extras you need; installing one provider's SDK is never required to use another's.

| Extra | Installs | Needed for |
|---|---|---|
| `openai` | `openai` | OpenAI, and OpenAI-compatible servers (vLLM, Ollama, LM Studio, OpenRouter, Together, …) |
| `azure` | `openai` | Azure OpenAI |
| `anthropic` | `anthropic` | Anthropic |
| `google` | `google-genai` | Google Gemini |
| `http` | `httpx` | any other HTTP endpoint |
| `plot` | `matplotlib`, `seaborn` | every figure, and `propel-fit --plots` |
| `dotenv` | `python-dotenv` | reading credentials from a `.env` file |
| `dev` | `pytest` | running the test suite |

Several at once: `pip install ".[openai,anthropic,google,http,plot,dotenv]"`.

Using a provider, or drawing a figure, without its extra raises an `ImportError` that names the
extra to install. Importing `propensity` itself never needs any of them.

## Check the installation

```bash
propel-annotate --help
propel-fit --help
python -c "import propensity; print(propensity.available_providers())"
```

The last line prints `['anthropic', 'azure', 'google', 'http', 'mock', 'openai']`.

## Where to run from

The rubrics ship inside the package, so the commands work from any directory. They also read
an optional settings file, `config/annotation.yaml` or `config/modelling.yaml`, relative to the
working directory. Run from the project root to use the ones in the repository, or pass
`--config` ([Configuration](configuration.md)).

## Credentials

Credentials are read from environment variables, never from configuration files.

| Provider | Variables |
|---|---|
| `openai` | `OPENAI_API_KEY` |
| `azure` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `google` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) |
| `http` | whichever you name with `api_key_env` |

Set them in the shell:

```bash
export OPENAI_API_KEY="sk-..."           # bash, zsh
```

```powershell
$env:OPENAI_API_KEY = "sk-..."           # PowerShell
```

Or install the `dotenv` extra and put them in a `.env` file in the working directory, which
`propel-annotate` loads automatically:

```ini
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

Keep `.env` out of version control.

## Shell syntax in these docs

Commands are written for bash. In PowerShell, replace the line continuation `\` with a
backtick `` ` ``, or put the command on one line.
