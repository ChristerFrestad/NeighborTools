# Manual E2E test checklist

Run through this before tagging a release or pushing to a public repo.

## Front page & groups
- [ ] Fresh server (no groups) shows the front page with PIN box + “Start new tool group”
- [ ] Wrong PIN shows “no group found” and stays on the front page
- [ ] Creating a group with a PIN already in use keeps the form and asks for another PIN
- [ ] PIN shorter than 4 or longer than 32 characters cannot be submitted
- [ ] After creating a group you land in the Tools tab
- [ ] Reload keeps you logged into the same group (no PIN re-entry)
- [ ] Padlock button in header logs out back to the front page
- [ ] Logging into group A then group B shows two separate tool lists
- [ ] “Who are you?” is remembered per group, not shared between groups
- [ ] Redeploying over an old single-file install: front page appears, old `data.json` is ignored

## Setup
- [ ] Cannot start with fewer than 2 named people
- [ ] Can add extra person rows and remove them
- [ ] Typed PIN survives adding/removing a person row
- [ ] “Back” returns to the front page

## Identity
- [ ] First open forces “Who are you?”
- [ ] Choosing a person sticks on refresh (same browser)
- [ ] “I’m not on the list” can add a new person and select them
- [ ] Chip in header shows correct name + color

## Tools
- [ ] Create tool with name + type + owner
- [ ] Optional photo: select image → preview → save → appears on card
- [ ] Edit tool (name, type, owner, notes, new photo)
- [ ] Delete requires second confirmation tap
- [ ] Search filters by name / type / notes
- [ ] Filters: All, Home, On loan, My loans, per-person owner chip
- [ ] Sticky filter chips stay visible while scrolling

## Loans
- [ ] “Lån ut” opens person picker (excludes current holder)
- [ ] Due date defaults to “Ubestemt tid”; a date is optional
- [ ] After loan, status shows “Hos X · N dager”
- [ ] Borrower in the group can set / change the due date from the card
- [ ] “Lån til meg” asks for a due date (default: no end date)
- [ ] Return sheet: optional note + damage flag; note appears on the tool and in the log
- [ ] Log entries created for loan and return

## People
- [ ] Add / edit person
- [ ] Cannot delete person who still owns or holds tools
- [ ] Counts (owns / has borrowed) are correct
- [ ] First person created is admin; admin badge shows
- [ ] Admin can grant admin on a person, or “make everyone admin”
- [ ] Last admin cannot be removed
- [ ] Admin can add an email on their profile (forgotten PIN)

## Invite, PIN reset, push
- [ ] Profile → invite link copies a URL; opening it on another browser joins without the PIN
- [ ] Front page → Forgot PIN: any email shows the same “queued” message
- [ ] With an admin email saved, a row appears in `/data/mail-queue.json` (no SMTP unless `RESEND_API_KEY` is set)
- [ ] Reset link (`/?reset=…`) sets a new PIN and the old one stops working
- [ ] Profile → turn on notifications: browser permission + subscribe (needs HTTPS / localhost and `pywebpush` in the image)

## Categories & photos
- [ ] Suggested category on a new tool; saving marks it decided
- [ ] Category tidy-up on login only lists tools you have not already judged
- [ ] Skip / keep / apply persists; next login does not re-ask those tools
- [ ] Photo is compressed in the browser and stored as a file (`/data/img/…`), not a data URL in the group JSON
- [ ] 501st new photo is refused (v1 cap 500)

## Log & backup
- [ ] Log shows newest first
- [ ] Download backup produces valid JSON
- [ ] Restore backup asks for confirmation and replaces data
- [ ] Invalid file shows error toast

## Multi-client
- [ ] Two browsers open same instance
- [ ] Loan in A appears in B after refresh / ~25s / visibility change
- [ ] Simultaneous edit: one gets retry / conflict handling (no data loss)

## Accessibility
- [ ] Modal receives focus when opened
- [ ] Tab cycles inside modal (focus trap)
- [ ] Escape closes modal (except forced identity pick)
- [ ] Overlay click closes modal when allowed
- [ ] Toast announces as status for screen readers
- [ ] Buttons show busy state while saving

## PWA / mobile
- [ ] Manifest loads, theme-color correct
- [ ] “Add to Home Screen” works on iOS/Android
- [ ] Safe-area padding on notched phones
- [ ] Dark mode follows system preference
- [ ] Escape closes modal (desktop)
- [ ] Overlay click closes modal

## Ops
- [ ] `/api/health` returns `{"ok": true, ...}`
- [ ] `/api/groups` lists ids and counts only – no names or tools
- [ ] `GET /api/groups/<id>/data` without the right `X-Pin` returns 401
- [ ] A new app version is picked up on reload (service worker is network-first)
- [ ] Docker healthcheck becomes healthy
- [ ] Restart container keeps data (volume)
- [ ] Port mapping 8787 works

## New features
- [ ] Lån til meg when tool is home and you are not holder
- [ ] Multi-select two tools → bulk loan to one person
- [ ] Long-loan tag appears after 14 days (or set since in data)
- [ ] History icon shows per-tool CRM-style log
- [ ] CSV export downloads tools with status
- [ ] CSV import: semicolon file from Excel, Norwegian headers, æøå intact
- [ ] CSV import: re-importing the same file adds nothing (all rows skipped)
- [ ] CSV import: unknown owner is created as a person, unknown type becomes “Annet”
- [ ] Grid shows 2–3 columns on wide screens

## Language & contrast
- [ ] A first-time visitor (cleared storage) gets the browser's language: `nb`/`nn`/`no` → Norwegian, anything else → English
- [ ] Browser preferring `en` before `nb` gets English (order is respected)
- [ ] Detection is never stored – only an explicit NO/EN click is
- [ ] An explicit choice survives a reload even when the browser asks for the other language
- [ ] `CONFIG.autoLang = false` falls back to `CONFIG.defaultLang`
- [ ] NO/EN switch shows both options; the active one is filled in and has `aria-pressed="true"`
- [ ] Switching updates every tab, modal, toast and tool category
- [ ] The choice survives reload, and `<html lang>` follows it
- [ ] Tool categories: a group created before this change still shows the right category, translated
- [ ] Selected filter chip is readable in **both** light and dark mode (dark text on light chip in dark mode)
- [ ] Toast messages are actually visible after saving (loan, return, delete, restore)
- [ ] Toast and the multi-select bar are readable in dark mode

## Due dates, reservations & outside loans
- [ ] Loan sheet has an optional return date; leaving it empty behaves as before
- [ ] Card shows “due in N days” / “due tomorrow” / “N days overdue”
- [ ] Overdue tag uses the warning colour, upcoming uses the accent colour
- [ ] Holder sees the reminder banner when a tool is due within a day or overdue; it filters to “My loans”
- [ ] Returning a tool clears its due date
- [ ] “Reserve” appears only on tools held by someone else; reserving twice does not duplicate
- [ ] Queue is listed on the card in order
- [ ] Returning a reserved tool toasts “Next: <name>”
- [ ] Home tool with a queue shows “Loan to <name>”; receiving it clears that person from the queue
- [ ] Removing a person also removes their reservations
- [ ] “Loan outside the group” records name + note, shows the Neighborhood tag, and appears in log, history and CSV
- [ ] Returning an outside loan clears the external holder
- [ ] CSV export has a `due` column; re-importing keeps the date

## Requests & neighborhood
- [ ] Requests tab shows empty state + “New request” FAB
- [ ] Group-only request: visible to the group, log entry created
- [ ] “Group + neighborhood” reveals radius picker (5/10/25/50 km)
- [ ] Without postal code on your profile you are asked for it; it is saved to the profile after posting
- [ ] With postal code: “calculated from …” line shows address + postal code, not editable in the sheet
- [ ] Unknown postal code is rejected with a toast
- [ ] Second group sees nothing until the neighborhood switch is turned on
- [ ] Second group (member postal code within radius) sees: first name, area, ~distance – never address or group
- [ ] Group outside the radius sees nothing
- [ ] Reply sheet: free-text note, privacy line about what is shared
- [ ] Reply sheet lists only tools that are home right now; picking one shows “Can lend: «…»” to the requester
- [ ] Reply sheet has no tool picker when nothing is home
- [ ] Requester sees the reply with name, area, distance and note; tab badge counts it
- [ ] Replying to your own group’s request is rejected
- [ ] Remove request needs a second tap; disappears from both groups
- [ ] Requests expire from the shared board after 30 days
- [ ] Person sheet has a postal-code field (4 digits, validated)
