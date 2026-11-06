# Concierge VM test bundle

One folder that starts three things with Docker:

| Service | What it is | Default port |
|---|---|---|
| `site` | the 24-page website (nginx, from `./site`) | 8080 |
| `server` + `worker` + `db` + `redis` | Twenty CRM v2.56.0 | 3010 |
| `bridge` | lead bridge: website form to Twenty (repo code in `../integrations/twenty/bridge`) | 4410 |

## Run it

```bash
cd vm
./run.sh
```

`run.sh` creates `.env` (random database and app secrets, never committed), unzips the site into `./site`
from `./concierge-site.zip` (or `SITE_ZIP=/path/to/zip`), then runs `docker compose up -d`.

Open the site at http://localhost:8080/ and the CRM at http://localhost:3010/.

The site expects the CRM on port 3010 and the bridge on port 4410 of the same host name. If the VM is
reached from outside under another name (for example a forwarded port), use that host name in the browser
and set `TWENTY_PUBLIC_URL=http://<host>:3010` before `./run.sh`.

## Bridge key (never stored in a file here)

A fresh Twenty has no workspace and no API key, so the bridge answers `503 not_configured` and the contact
form falls back to email. After you create a workspace in Twenty and an API key in its settings:

```bash
TWENTY_API_KEY=<the key> ./run.sh
```

## Click-test the site navigation

Needs Node 22+ and Google Chrome on the machine running the test.

```bash
cd vm/nav-test
npm install
node nav-test.mjs http://localhost:8080
```

It checks all 24 pages at desktop (1280px) and mobile (390px) width: the Product dropdown opens on hover and
keyboard focus and stays open while the pointer is inside it, the hamburger menu opens and closes with the right
`aria-expanded` value, menu links navigate, "Log in" links point at port 3010, and the pages log no JavaScript errors.

## Other commands

```bash
./run.sh down     # stop, keep data
./run.sh reset    # stop and delete this bundle's Twenty data (asks first)
```

Extra ports can be changed with `TWENTY_PORT`, `BRIDGE_PORT`, `SITE_PORT`, `BIND_ADDR`. Note that the site's
Log in and form addresses assume 3010 and 4410.

## What this bundle has and has not proven

Verified on the Mac: `docker compose config` passes, all six containers start healthy, the site serves,
the bridge answers (400 for an empty lead), and the navigation test passes.
Not covered: a lead reaching Twenty inside this bundle (needs a workspace and key created in the bundle's
own Twenty), and a run on a real separate VM.
