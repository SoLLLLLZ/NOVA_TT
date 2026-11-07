# Backend validation

Run `uv run pytest -q`. Tests cover authentication, strict settings, idempotency, profile selection, context and sampling constraints, quality failure, resource locking, cancellation, rollback, race and actions using an explicitly simulated driver. They do not claim GPU performance.

`scripts/live_byteshape.py` is the opt-in real Wright rehearsal. It runs ByteShape only; Glimmer and Flash are deferred. Test output goes to ignored `var/`.

The standalone frontend mock has its own suite: `python3 -m unittest tests/mocks/test_mock_server.py`. Frontend unit tests run with `npm test` in `frontend/`.
