# NeighborTools

**Keep track of shared tools – without spreadsheets, group chats, or accounts.**

Borrow a drill from a neighbor, return it when you’re done. Everyone with the link sees the same live list. Optional PIN for a bit of privacy.

Built for real life: housing co-ops, friends who share gear, tool libraries, cabin groups.

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
- Installable PWA (Add to Home Screen)
- Store-like **responsive grid**
- Whitelabel via `CONFIG`
- Docker / Portainer ready

UI: Norwegian + English  
Code/docs: English  
License: MIT

---

## Quick start (Docker)

```bash
git clone https://github.com/ChristerFrestad/NeighborTools.git
cd NeighborTools
docker compose up -d --build
```

Open: `http://localhost:8787`

### Portainer

1. Stacks → Add stack
2. Paste `docker-compose.yml` (or point to this repo)
3. Deploy
4. Open port **8787**

### Without Docker

```bash
python3 server.py
```

Open the address printed in the terminal (default port 8080).

---

## First-time setup

1. Add the people who share tools (at least two names)
2. Optionally set a PIN
3. Each person opens the link and picks **who they are** (stored only on that device)
4. Add tools and start lending

---

## Whitelabel / PIN in config

Edit the top of `index.html`:

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

- All data lives in one file: `data.json` (Docker volume `neighbortools-data`)
- **No accounts** means anyone with the URL can edit – share only with people you trust
- For stronger protection, put **Cloudflare Access** (free) in front of the URL
- Download a backup from the Log tab when it matters

---

## Development & tests

```bash
python3 server.py
python3 tests/api_test.py http://127.0.0.1:8080
```

See [MANUAL_TEST.md](MANUAL_TEST.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT – see [LICENSE](LICENSE).
