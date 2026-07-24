# NeighborTools

**Simple shared tool inventory for neighbors and friends.**  
No accounts. Optional PIN. Everyone with the link (and PIN) sees and edits the same list.

---

## Features

- Shared live tool list (owner + who has it now)
- Loan / return in one tap
- **Borrow myself** quick action
- **Multi-select** tools and loan them out together
- Optional photo per tool (compressed)
- Per-tool **history** (who had it, when)
- Highlight loans out longer than 14 days
- People list with addresses
- Activity log
- Filters + search
- Backup download / restore + **CSV export**
- Optional **PIN** (setup or `CONFIG.pin`)
- **Norwegian / English** UI toggle
- Dark mode (system)
- Installable PWA
- Store-like **responsive grid**
- Whitelabel via `CONFIG`
- Docker / Portainer ready

UI: Norwegian + English  
Code/docs: English

---

## Quick start

```bash
docker compose up -d --build
```

Open: `http://localhost:8787`

### Whitelabel / PIN in config

```js
var CONFIG = {
  name: 'NeighborTools',
  shortName: 'NeighborTools',
  tagline: 'Shared tools with your neighbors – no login needed.',
  storageKey: 'neighbortools',
  defaultLang: 'nb',
  longLoanDays: 14,
  pin: ''   // set e.g. '1234' to require PIN
};
```

PIN can also be set during first-run setup (stored in data).

---

## Data & safety

- Stored in `data.json` (Docker volume `neighbortools-data`)
- Share URL only with trusted people
- Prefer Cloudflare Access for stronger protection

---

## Development

```bash
python3 server.py
python3 tests/api_test.py http://127.0.0.1:8080
```

See [MANUAL_TEST.md](MANUAL_TEST.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT – see [LICENSE](LICENSE).
