# Manual E2E test checklist

Run through this before tagging a release or pushing to a public repo.

## Setup
- [ ] Fresh start (no data.json) shows setup screen
- [ ] Cannot start with fewer than 2 named people
- [ ] Can add extra person rows and remove them
- [ ] After start, app shows Tools tab with empty state

## Identity
- [ ] First open forces “Who are you?”
- [ ] Choosing a person sticks on refresh (same browser)
- [ ] “I’m not on the list” can add a new person and select them
- [ ] Switch person from header chip works

## Tools
- [ ] Add tool with name, type, owner, notes
- [ ] Edit tool updates list
- [ ] Loan out moves status to borrower
- [ ] Return brings tool home
- [ ] Borrow myself works when tool is home
- [ ] Multi-select + bulk loan works
- [ ] Filters (all / home / on loan / my loans / by person) work
- [ ] Search finds by name/type/notes
- [ ] Long-loan tag after 14 days
- [ ] History sheet per tool
- [ ] Photo add/remove (if supported)

## People
- [ ] Add / edit person
- [ ] Counts (owns / has borrowed) are correct
- [ ] Cannot remove person who still has tools

## Log & backup
- [ ] Log shows newest first
- [ ] Download backup produces valid JSON
- [ ] Restore backup asks for confirmation and replaces data
- [ ] CSV export downloads

## Multi-client
- [ ] Two browsers open same instance
- [ ] Loan in A appears in B after refresh / ~25s / visibility change
- [ ] Simultaneous edit: conflict handling (no data loss)

## Language & PIN
- [ ] Language toggle NO/EN updates UI
- [ ] Optional PIN at setup → lock screen on next session
- [ ] CONFIG.pin enforces PIN when set

## Ops
- [ ] `/api/health` returns ok
- [ ] Docker healthcheck becomes healthy
- [ ] Restart keeps data (volume)
