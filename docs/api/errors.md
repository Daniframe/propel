# `propensity.errors`

```
Exception
└── PropensityError
    ├── ContractError      (also a ValueError)
    ├── ProviderError
    └── ParseError

UserWarning
└── DataWarning
```

| Class | Raised when |
|---|---|
| `PropensityError` | base class of every error PROPEL raises on purpose; catch it to handle them all |
| `ContractError` | input data breaks a data contract: missing or duplicate ids, invalid outcomes, out-of-range intervals, missing rubric, bad file type… |
| `ProviderError` | a provider is misconfigured, or asked for something it cannot do: unknown name, no batch API, missing Azure endpoint, batch ids Anthropic rejects |
| `ParseError` | not raised by PROPEL: parse failures are recorded on the row (`parse_ok` false). Available to your own code |
| `DataWarning` | usable but suspicious data: low join yield, small cells, batch ids that were never sent |

**`ContractError.rows`** lists the offending rows, ids or columns (the message previews the first
ten):

```python
from propensity import ContractError, load_outcomes

try:
    load_outcomes("results.csv")
except ContractError as error:
    print(error)          # results.csv: outcomes must be 0 or 1; got ('q7', 'gpt-4o', '0.7')
    bad = error.rows      # [('q7', 'gpt-4o', '0.7'), ...]
```

**Warnings** go through the standard `warnings` module. To treat them as errors:

```python
import warnings
from propensity import DataWarning

warnings.simplefilter("error", DataWarning)
```

**Other exceptions:**
- **Missing SDKs** raise `ImportError`, naming the extra to install.
- **Invalid arguments** to numeric functions (array shapes, non-binary outcomes, an unknown
  `likelihood` or `mode`) raise `ValueError`.
- **`profile_vector`** with an unknown subject raises `KeyError`.
