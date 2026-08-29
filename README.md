# NeighborTools

**Shared tool list for people who already trust each other. No accounts, no spreadsheet, no group chat.**

[Live](https://neighbor-tools.com/) · [Docker](#quick-start-docker) · [Contributing](CONTRIBUTING.md) · MIT

Borrow a drill from next door. Everyone who knows the group's PIN sees the same live list. One server can host several independent groups.

<p>
  <img src="assets/landing/saw.jpg" alt="Mitre saw" width="22%">
  <img src="assets/landing/grinder.webp" alt="Angle grinder" width="22%">
  <img src="assets/landing/driver.jpg" alt="Impact driver" width="22%">
  <img src="assets/landing/compressor.jpg" alt="Compressor" width="22%">
</p>

## Who this is for

- Housing co-ops and sameier that already share a drill, ladder or tile cutter
- Friends, cabin groups, tool libraries
- Anyone who wants a live list on the phone without creating accounts

## Who this is not for

- Renting tools to strangers (no payments, deposits or public listings)
- A city-wide marketplace — that is a different product, with a similar name
- Teams that need SSO, audit logs or a native app

## How it works

```
Phone / PWA  --PIN or invite-->  Python server  -->  /data/groups/<id>.json
                                 (no framework)      /data/img/<id>/
```

1. Start a group and pick a PIN (4–32 characters; six or more is safer).
2. Share the URL + PIN, or an invite link.
3. Each person picks their name on that device.
4. Add tools (optional photo). Loan and return in one tap.

The PIN is the key to the group. It is checked on the server and stored as a PBKDF2 hash. Several groups can live on one Docker host without seeing each other.

## Features

- Shared live tool list (owner + who has it now)
- Loan / return in one tap, with an optional **damage / return note**
- **Due date** defaults to *no end date*; the borrower can set or change it later. Overdue tags + in-app reminder
- **Web Push** – optional notifications on loan, queue and upcoming due dates
- **Reservations** – queue up for a tool that is out; the owner gets a one-tap “loan to the next in line”
- **Loan outside the group** – lend to someone who is not on the list, with contact note and full history
- **Invite link** – join without already knowing the PIN
- **First person is admin**; admins can grant admin to some or all
- **Forgotten PIN** – if an admin has registered an email, a reset link is queued. Wire up Resend (`RESEND_API_KEY`) when you want mail to actually send
- **Requests ("etterlysninger")** – ask your group for something you need
- **Neighborhood requests** – opt-in: ask other groups on the same server, matched by how far *you* are willing to travel (postal-code distance, no external map API)
- **Borrow myself** and **multi-select** loan
- Optional photo per tool, stored as **files** (auto-compressed; v1 cap 500)
- Category tidy-up that remembers your decision
- Per-tool history, activity log, filters + search
- Highlight loans out longer than 14 days
- People list with addresses
- Backup download / restore + **CSV export and import**
- Several tool groups on one server
- Norwegian + English UI (browser language on first visit; explicit choice sticks)
- Theme: system / light / dark
- Installable PWA
- Whitelabel via `CONFIG`
- Docker / Portainer ready

UI: Norwegian + English · Code/docs: English · License: MIT

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
python3 -m pip install -r requirements.txt   # Web Push; optional
python3 server.py
```

Open the address printed in the terminal (default port 8080).

### Environment (optional)

| Variable | Purpose |
| --- | --- |
| `RESEND_API_KEY` | Send forgotten-PIN mail via [Resend](https://resend.com). Without it the reset link is only queued in `/data/mail-queue.json`. |
| `MAIL_FROM` | From-address when Resend is on (`NeighborTools <noreply@example.com>`) |
| `PUBLIC_URL` | Public origin used in reset links, e.g. `https://neighbor-tools.com` |
| `VAPID_MAILTO` | VAPID subject (`mailto:admin@example.com`) |

### Upgrading from the single-file version

This release is a clean break: data is stored per group, and a `data.json` from the old single-group version is **not** carried over. Pull, redeploy, and create your group from the front page. The old file is ignored and can be deleted from the volume. If you want the old list back, download a backup from the old version first and use **Restore** in the Log tab after creating the group.

## Groups and PINs

The front page has two ways in:

- **Open group** – type the PIN your neighbors gave you.
- **Start a new tool group** – run the setup wizard and pick your own PIN.

The PIN (4–32 characters) can only belong to one group. If it is taken, pick another. Use the padlock in the header to log out and switch group. The group and PIN are remembered on the device.

## First-time setup

1. Choose **Start a new tool group**
2. Add the people who share tools (at least two names) and pick a PIN – six characters is safer than four
3. Share the address and the PIN, or an invite link
4. Each person picks **who they are** (stored only on that device)
5. Add tools and start lending

## Architecture

| Piece | What it is |
| --- | --- |
| `index.html` + `app.css` | Whole UI. No build step, no framework. |
| `server.py` | `http.server` + JSON files. PIN / grant auth. |
| `/data/groups/<id>.json` | One file per group (Docker volume). |
| `/data/img/<id>/` | Tool photos as files, not inside the JSON. |
| `postnummer.json` | Norwegian postal-code centroids for neighborhood distance. |
| `sw.js` + `manifest.webmanifest` | Installable PWA + Web Push. |

Auth: `X-Pin` (PBKDF2-SHA256, 100k rounds, install-wide salt) or a hashed invite grant. Writes use a revision number; a stale client gets HTTP 409.

## Whitelabel

Edit the top of `index.html`:

```js
var CONFIG = {
  name: 'NeighborTools',
  shortName: 'NeighborTools',
  tagline: 'Shared tools with your neighbors – no login needed.',
  storageKey: 'neighbortools',
  autoLang: true,      // match the browser's language on the first visit
  defaultLang: 'en',   // fallback when autoLang finds no match (or is off)
  longLoanDays: 14,
  pin: '',             // only used without a server (offline / artifact mode)
  githubUrl: 'https://github.com/ChristerFrestad/NeighborTools'
};
```

The logo and page title update automatically from `CONFIG.name`.

## Loans, due dates and reservations

A loan defaults to **no end date** (“ubestemt tid”). The person who borrowed the tool – anyone in the same group – can set or change the date afterwards. The card shows “due in 3 days” or “2 days overdue”, and the borrower gets an in-app reminder plus an optional Web Push.

Returning a tool can include a **note or damage flag**. That line is stored on the tool and in the history.

Turn on **notifications** from the profile menu. The service worker shows a system notification when someone borrows, queues, or when a due date is close. This needs `pywebpush` (installed in the Docker image).

If a tool is already out, tap **Reserve** to queue up. When the tool comes home the owner gets a **“Loan to &lt;name&gt;”** button for whoever is first in line.

**Loan outside the group** records a loan to someone who is not on the people list. It shows up in the list, the history and the CSV export like any other loan.

## Requests and the neighborhood

The **Requests** tab is a wanted-board. Optionally you can ask the **neighborhood** too – every other group on the same server, within 5 / 10 / 25 / 50 km.

How it stays private:

- Everything is **opt-in**: a request only leaves your group if you choose “Group + neighborhood”, and a group only sees the neighborhood board after flipping the switch on the Requests tab.
- Distance comes from **postal-code centroids** bundled as `postnummer.json`. No map service is called.
- Other groups see only your **first name, postal code area and distance** – never your address, your group, or your tool list.
- Replies are free text. Requests expire from the shared board after 30 days.

Postal-code coordinates: [Erik Bolstad's postnummer register](https://www.erikbolstad.no/postnummer-koordinatar/) (CC BY 4.0).

This feature only becomes useful when several groups on the *same* server opt in. A single family group will not see a neighborhood board.

## Import and export

From the **Log** tab:

- **Download** / **Restore** – full JSON backup of the group. Photos stay as files on the volume (`img: "file"` in the JSON).
- **Export CSV** / **Import CSV** – the tool list as a spreadsheet

CSV import accepts comma- or semicolon-separated files (Norwegian Excel uses semicolons) with either English (`name, type, owner, holder, since, due, notes`) or Norwegian (`navn, eier, låner …`) headers. Only `name` is required. A row matching a tool that is already there (same name and owner) is skipped. Unknown owners are created as people.

## Admins, invites and forgotten PIN

The **first person** in a new group is admin. Admins can grant admin to individual people or to everyone, and they can add an email on their profile.

**Invite link** (profile menu) lets a neighbour join without the PIN. The device then uses a hashed grant instead of the PIN.

**Forgot PIN** requires that at least one admin has registered an email. The backend queues a reset mail (`/data/mail-queue.json`). Actual sending is **not** on until the host sets `RESEND_API_KEY` (and usually `MAIL_FROM` + `PUBLIC_URL`).

## Data and safety

- Each group is one file: `/data/groups/<id>.json` (Docker volume `neighbortools-data`)
- Tool photos live under `/data/img/<group>/`. The client compresses to max 960 px JPEG before upload.
- PINs are never stored in plain text – only a PBKDF2 hash, salted per installation (`/data/pin-salt`; deleting it makes every existing PIN unusable)
- Invite grants and recovery tokens are stored hashed
- The server refuses to read or write a group without its PIN or a valid grant
- `GET /api/groups` is unauthenticated but returns ids and counts only – never names or tools
- Web Push subscriptions sit in `/data/push/`, not in the synced group JSON
- For stronger protection, put **Cloudflare Access** (free) in front of the URL
- Download a backup from the Log tab when it matters

This is built for a trusted circle, not for the open internet. Treat the PIN like a house key. Self-host if the data should stay on your own machine.

## Development and tests

The API tests need an empty data directory:

```bash
DATA_DIR=/tmp/nt PORT=9876 python3 server.py
DATA_DIR=/tmp/nt python3 tests/api_test.py http://127.0.0.1:9876
```

See [MANUAL_TEST.md](MANUAL_TEST.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Solo-maintained. Small, focused pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Issues without a patch are read; there is no SLA.

## License

MIT – see [LICENSE](LICENSE).
