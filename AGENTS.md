# Agents -- Operational Notes

## Backend

- Python 3.14 is installed on this machine. Use a venv: `.venv` in `backend/`.
- System python is externally-managed (PEP 668) -- always use venv.
- Run tests: `source .venv/bin/activate && python -m pytest test_main.py -v`
- Lint: `source .venv/bin/activate && ruff check . && mypy main.py`
- Tests use `anyio` marker (`@pytest.mark.anyio`) with httpx `ASGITransport`.
