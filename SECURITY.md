# Security

NeighborTools is a PIN-shared list for people who already trust each other.
Treat the group PIN like a house key.

## Report a problem

Open a private note via GitHub Security Advisories on this repository, or an issue labelled `bug` if the report cannot leak a PIN or personal data.

Do not paste live PINs, reset tokens or group JSON into a public issue.

## What the server already does

- PINs, invite tokens and recovery tokens are stored hashed
- Group JSON is not readable without the PIN or a valid grant
- Photos are not served without auth
- Failed PIN attempts are delayed

## What it does not do

- It is not a multi-user account system
- A 4-character PIN can be guessed; use 6+ on a public host
- `GET /api/groups` lists group ids and counts (no names)
- There is no built-in abuse dashboard

For a public URL, put Cloudflare Access or similar in front, and take backups of the Docker volume.
