# Tests and integration fixtures

Backend behavior, API-contract and frontend integration tests. Implemented so far: the mock contract suite (`python3 -m unittest tests/mocks/test_mock_server.py`); frontend unit tests run with `npm test` in `frontend/`.

- `fixtures/`: small sanitized inputs, expected answers and API response fixtures; label synthetic measurements as mock.
- [mocks/](mocks/): stdlib mock server implementing [API v2.1](../docs/api/endpoint.md), with its unittest suite.

Keep large benchmark outputs in `var/`. Use real inference only in explicit integration checks with an owned allocation; ordinary tests should not consume GPUs or OpenRouter credit implicitly.
