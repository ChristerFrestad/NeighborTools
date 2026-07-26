# NeighborTools

**Keep track of shared tools – without spreadsheets, group chats, or accounts.**

Borrow a drill from a neighbor, return it when you’re done. Everyone who knows the group's PIN sees the same live list. One server can host several independent groups.

Built for real life: housing co-ops, friends who share gear, tool libraries, cabin groups.

---

## Features

- Shared live tool list (owner + who has it now)
- Loan / return in one tap
- **Agreed return date** with a reminder for the borrower, and overdue tags
- **Reservations** – queue up for a tool that is out; the owner gets a
  one-tap “loan to the next in line” when it comes back
- **Loan outside the group** – lend to a neighbor who is not on the list,
  with contact note and full history
- **Requests ("etterlysninger")** – ask your group for something you need
- **Neighborhood requests** – opt-in: ask other groups on the same server,
  matched by how far *you* are willing to travel (postal-code distance, no
  external services)
- **Borrow myself** quick action
- **Multi-select** tools and loan them out together
- Optional photo per tool (compressed)
- Per-tool **history** (who had it, when)
- Highlight loans out longer than 14 days
- People list with addresses
- Activity log
- Filters + search
- Backup download / restore + **CSV export and import**
- **Several tool groups on one server** – the PIN is the key to the group
- PIN checked server-side and stored hashed (PBKDF2)
- **Norwegian / English** – full UI in both languages, English by default,
  switched with a NO/EN control that shows which one is active
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

### Upgrading from the single-file version

This release is a clean break: data is stored per group, and a `data.json` from
the old single-group version is **not** carried over. Pull, redeploy, and create
your group from the front page. Nothing else is needed — no migration step, no
manual cleanup. The old file is simply ignored and can be deleted from the
volume. If you want the old list back, download a backup from the old version
first and use **Restore** in the Log tab after creating the group.

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

## Groups and PINs

The front page has two ways in:

- **Open group** – type the PIN your neighbors gave you.
- **Start a new tool group** – run the setup wizard and pick your own PIN.

The PIN (4–32 characters) is the key to a group, so it can only belong to one:
if the PIN you pick is taken, you are asked to choose another. Several
independent groups can share one server without seeing each other's lists.

Use the padlock button in the header to log out and switch group. The group and
its PIN are remembered on the device, so you stay logged in between visits.

---

## First-time setup

1. Choose **Start a new tool group**
2. Add the people who share tools (at least two names) and pick a PIN – six digits is safer than four
3. Share the address and the PIN with your neighbors
4. Each person picks **who they are** (stored only on that device)
5. Add tools and start lending

---

## Whitelabel

Edit the top of `index.html`:

```js
var CONFIG = {
  name: 'NeighborTools',
  shortName: 'NeighborTools',
  tagline: 'Shared tools with your neighbors – no login needed.',
  storageKey: 'neighbortools',
  defaultLang: 'en',   // 'en' or 'nb' – what a first-time visitor sees
  longLoanDays: 14,
  pin: ''   // only used without a server (offline / artifact mode)
};
```

---

## Loans, due dates and reservations

When you lend a tool out you can set an **agreed return date**. The borrower
sees a reminder on the Tools tab as the date approaches, and the card shows
“due in 3 days” or “2 days overdue”. The date is optional – leave it empty and
nothing changes from before.

If a tool is already out, tap **Reserve** to queue up. The queue is shown on
the card, and when the tool comes home the owner gets a **“Loan to <name>”**
button for whoever is first in line. Receiving the tool clears your spot.

**Loan outside the group** (in the loan sheet) records a loan to someone who
is not on the people list – a neighbor who answered a request, for example.
Enter their name and an optional contact note; the loan appears in the list,
the history and the CSV export just like any other, so nothing disappears
from the overview.

---

## Requests and the neighborhood

The **Requests** tab is a wanted-board: post what you are looking for
(“tile cutter for the weekend”) and your group sees it. Optionally you can ask
the **neighborhood** too – every other group on the same server, within the
distance *you* are willing to travel to pick up and return the item
(5 / 10 / 25 / 50 km).

How it stays private:

- Everything is **opt-in**: a request only leaves your group if you choose
  “Group + neighborhood”, and a group only sees the neighborhood board after
  flipping the switch on the Requests tab. Nothing else is ever shared.
- Distance is computed from **postal-code centroids** bundled with the app
  (`postnummer.json`), so no map service or external API is ever called.
- Other groups see only your **first name, postal code area and distance** –
  never your address, your group, or anything on your tool list.
- Replies are free text: the responder decides what to share (phone number,
  pickup spot). You pick up and return the item yourself.
- Requests expire from the shared board after 30 days; the requester can
  remove them at any time.

Postal-code coordinates: [Erik Bolstad's postnummer register](https://www.erikbolstad.no/postnummer-koordinatar/)
(CC BY 4.0).

---

## Import and export

From the **Log** tab:

- **Download** / **Restore** – full JSON backup of the group, images included
- **Export CSV** / **Import CSV** – the tool list as a spreadsheet

CSV import accepts comma- or semicolon-separated files (Norwegian Excel uses
semicolons) with either English (`name, type, owner, holder, since, due, notes`)
or Norwegian (`navn, eier, låner …`) headers. Only `name` is required. Tools are
added to the existing list; a row matching a tool that is already there (same
name and owner) is skipped, so importing the same file twice is safe. Owners
that do not exist yet are created as people.

---

## Data & safety

- Each group is one file: `/data/groups/<id>.json` (Docker volume `neighbortools-data`)
- PINs are never stored in plain text – only a PBKDF2 hash, salted per installation
  (`/data/pin-salt`; deleting it makes every existing PIN unusable)
- The server refuses to read or write a group without its PIN
- `GET /api/groups` is unauthenticated but returns ids and counts only – never
  names or tools
- A forgotten PIN cannot be recovered: it is the only way into the group
- For stronger protection, put **Cloudflare Access** (free) in front of the URL
- Download a backup from the Log tab when it matters

---

## Development & tests

The API tests need an empty data directory:

```bash
DATA_DIR=/tmp/nt PORT=9876 python3 server.py
python3 tests/api_test.py http://127.0.0.1:9876
```

See [MANUAL_TEST.md](MANUAL_TEST.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT – see [LICENSE](LICENSE).
