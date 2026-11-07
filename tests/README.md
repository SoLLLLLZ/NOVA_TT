# Tests and integration fixtures

Reserved for future backend behavior, API-contract and frontend integration tests. No test suite or runner is implemented yet.

- `fixtures/`: small sanitized inputs, expected answers and API response fixtures; label synthetic measurements as mock.
- [mocks/](mocks/): future frontend mock server implementing [API v2](../docs/api/endpoint.md).

Keep large benchmark outputs in `var/`. Use real inference only in explicit integration checks with an owned allocation; ordinary tests should not consume GPUs or OpenRouter credit implicitly.
