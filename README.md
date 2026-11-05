# Minimal parser compatibility update

Only `bot.py`'s `_normalize_range()` function has changed. `poker.py`, `errors.py`, the main guard, Reddit access, the validator, and equity handling remain unchanged.

Accepted inputs, and what they become internally:

- `{AAo} {KK}` -> `AA`, `KK`
- `{QQo+} {22}` -> `QQ+`, `22`
- `{,AKs,,,} {QQ}` -> `AKs`, `QQ`
- `{AA,,KK,} {QQ}` -> `AA,KK`, `QQ`
- `{,AAo,,KKo+,} {QQ}` -> `AA,KK+`, `QQ`

A field containing only commas still fails validation because it contains no hand. `AAs` remains invalid. Suitedness on non-pairs is unchanged.

To apply, replace your `bot.py` with this file (or replace only `_normalize_range`). Optionally update `tests/test_bot.py` and `batch_cases.py`: the old test versions expect now-valid comma and `AAo` cases to be errors.

Run tests **without starting the Reddit bot**:

```
py -m unittest discover -s tests -v
py batch_runner.py --quiet
```

Do NOT run `py bot.py` unless you intend to launch the bot; the existing `if __name__ == "__main__": main()` remains unchanged, per the requested limited scope.

Local results: 23 unit tests passed; 110 simulated batch cases passed. No live Reddit or compiled OMPEval integration was exercised.
