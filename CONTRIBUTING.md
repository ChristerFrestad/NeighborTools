# Contributing to NeighborTools

Thanks for helping improve a simple tool for sharing tools.

## Principles

1. **Keep it simple** – one HTML file, one CSS file, one Python server, Docker-ready.
2. **UI in Norwegian + English**, code/docs in English.
3. **No login** – trust is handled by who gets the URL (or Cloudflare Access).
4. **Mobile first**.

## Development

```bash
python3 server.py
# open http://localhost:8080
```

No build step. Edit `index.html` and refresh.

## Checks before a PR

1. `python3 -m py_compile server.py`
2. Run API smoke tests on empty data (same `DATA_DIR` in both processes):
   ```bash
   DATA_DIR=/tmp/nt-data PORT=8080 python3 server.py &
   DATA_DIR=/tmp/nt-data python3 tests/api_test.py http://127.0.0.1:8080
   ```
3. Walk through [MANUAL_TEST.md](MANUAL_TEST.md)

## Whitelabel

Only change the `CONFIG` object at the top of `index.html`.

## Scope to avoid

- User accounts / OAuth
- Heavy frameworks
- Native mobile apps
