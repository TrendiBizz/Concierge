# SocialSync for Pukeko Construction

Plan, check and schedule social media posts for LinkedIn, Facebook, Instagram and X.

SocialSync does **not publish by itself**. When a post is due, you copy it into the platform (the iPhone app has a Share button for this) and tap **Mark as posted**. Direct publishing can be added later; see "Next steps".

## What is in the box

| Folder | What it is |
| --- | --- |
| `server/` | The backend: JSON API, photo storage, guardrails, and it also serves the web dashboard. Node only, no npm packages. |
| `web/` | The web dashboard (Compose, Calendar, Posts, Photos). Works on a computer or a phone browser. |
| `ios/` | The native iPhone and iPad app (SwiftUI, iOS 17+). |
| `tools/` | `import-site.mjs` (copies the website's pictures into the photo library) and `ui-smoke.mjs` (a browser test that drives the dashboard in headless Chrome and takes screenshots). |
| `import/` | A local copy of what was imported from the website. |

## Features

- Compose once, preview per platform, with live character counts (X counts any link as 23 characters).
- Platform rules: Instagram needs a photo or video, Instagram allows at most 30 hashtags, per-platform media limits.
- **Pukeko guardrails** (`server/rules.json`):
  - *Blocks* scheduling if a post contradicts a verified fact (for example "25 years of experience" when the owner verified "more than 10 years") or uses a forbidden phrase ("Auckland's best", "100% guaranteed", ...).
  - *Warns* about claims still waiting on the owner: Nu-Wall "preferred/certified installer" wording, warranty and guarantee claims, product lifespan figures, LBP numbers, memberships, prices, timelines, superlatives.
  - *Warns* on phone call-to-actions, because Conrad is Deaf and leads come by text, email or the quote form.
- Saved drafts, scheduling, month calendar, post history, "Due now" list.
- Photo library for job photos with project names and captions, reusable across posts.
- Sign-in with a passcode. The phone app keeps its session token in the iOS Keychain.

## Pukeko branding, pictures and social pages

- **Colours.** Taken from pukekoconstruction.co.nz: green `#75BA53`, navy `#112337` (the logo lettering), black text and white. Text on green uses a very dark green for readable contrast, and links use a darker green `#3F7A24`. The logo is in the dashboard header, the sign-in screens and the app icon.
- **Pictures from the website.** `node tools/import-site.mjs` reads the website's WordPress media library and adds its photos to the Photos library, grouped by project ("Pukeko projects (website)", "Pukeko services (website)", "Pukeko website gallery", "Pukeko brand"). It skips placeholders and tiny icons, converts AVIF to JPEG, and is safe to run again: pictures already in the library are skipped. Run it with `--dry-run` first to see what it would add. A copy of everything imported is kept in `import/site/images/`.
- **Social pages.** The **Pages** tab (web) and **Settings > Social pages** (iPhone) hold every page Pukeko uses, in one list you can open, edit and add to. It starts with the pages the website links to: Facebook (`facebook.com/pukekoconstruction`), Instagram (`instagram.com/pukekoconstruction`) and the website. The website does not link to a LinkedIn page, X or YouTube, so add those yourself.
- **Post now.** On any post that is not yet posted, **Post now** copies the text and opens the platform. LinkedIn and X open with the text already filled in. Facebook and Instagram open the page, and you paste the text (Instagram posts are made in the Instagram app). The post's photos have download links on the web dashboard. When it is live, tap **Mark as posted**.

## 1. Run the server

Requires Node 22.5 or newer (built-in SQLite). From the `server` folder:

```bash
cd ~/Pukeko/SocialSync/server
npm start
```

On the first run it prints a passcode and saves it in `data/config.json`. Open http://127.0.0.1:4377 in a browser and sign in.

To use it from a phone on the same Wi-Fi, let the server listen on the network:

```bash
HOST=0.0.0.0 npm start
```

Then use the computer's address from the phone, for example `http://192.168.1.20:4377`. (On a Mac: System Settings > Network shows the address.)

Settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `4377` | Port to listen on |
| `HOST` | `127.0.0.1` | `0.0.0.0` lets other devices on the network connect |
| `DATA_DIR` | `SocialSync/data` | Where the database, photos and passcode live. **Back this folder up.** |
| `SOCIALSYNC_PASSCODE` | from `data/config.json` | Overrides the saved passcode |
| `TRUTH_JSON` | none | Path to Trendi's `truth.json`; its verified facts and forbidden phrases are merged into the guardrails automatically |

Example using the owner-verified facts from Trendi:

```bash
TRUTH_JSON=~/Trendi/clients/pukeko/truth.json HOST=0.0.0.0 npm start
```

**Security note.** The server speaks plain HTTP and is meant for your own network. Do not expose it to the internet as it is. To reach it from outside, put it behind HTTPS (for example a Cloudflare Tunnel or Tailscale) first.

### Keep it running

The server stops when its Terminal closes. To have macOS start it at login and restart it if it stops, save the file below as `~/Library/LaunchAgents/nz.co.pukekoconstruction.socialsync.plist`, then run
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/nz.co.pukekoconstruction.socialsync.plist`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>nz.co.pukekoconstruction.socialsync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/node</string>
        <string>/Users/jo/Pukeko/SocialSync/server/server.js</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOST</key>
        <string>0.0.0.0</string>
        <key>TRUTH_JSON</key>
        <string>/Users/jo/Trendi/clients/pukeko/truth.json</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>15</integer>
    <key>StandardOutPath</key>
    <string>/Users/jo/Library/Logs/socialsync.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/jo/Library/Logs/socialsync.log</string>
</dict>
</plist>
```

## 2. Build the iPhone app

Requires Xcode 16 or newer and [XcodeGen](https://github.com/yonaskolb/XcodeGen) (`brew install xcodegen`).

```bash
cd ~/Pukeko/SocialSync/ios
xcodegen generate
open SocialSync.xcodeproj
```

In Xcode:

1. Select the **SocialSync** target, then **Signing & Capabilities**.
2. Choose your **Team**. If the bundle identifier `nz.co.pukekoconstruction.socialsync` is taken, change it (also in `ios/project.yml`).
3. Pick your iPhone (or a simulator) and press Run.

On first launch, enter the server address and passcode. iOS will ask for permission to use the local network: allow it.

If you change `ios/project.yml`, run `xcodegen generate` again. The `.xcodeproj` is generated, so do not hand-edit it.

## 3. Tests

```bash
cd ~/Pukeko/SocialSync/server && npm test      # 19 API, guardrail and social-page tests
cd ~/Pukeko/SocialSync && node tools/ui-smoke.mjs   # 23 browser checks, needs Google Chrome
```

## Editing the guardrails

Open `server/rules.json`. It reloads automatically (no restart needed).

- `facts` and `forbidden_phrases` are **errors**: they block scheduling.
- `warnings` are shown but do not block. Move a warning's claim into `facts` once the owner has verified it.
- When the owner answers the open questions in `questions.md` (LBP number, memberships, warranty wording, prices, timelines), update the matching rules.

## Next steps (not built yet)

- **Direct publishing.** Needs an approved developer app per platform (Meta for Facebook and Instagram, LinkedIn, X) or a posting service such as Ayrshare or Buffer. The server's `scheduled` posts and the "Due now" list are where a publisher would plug in.
- **Push reminders** when a post becomes due.
- **Multiple users** with separate logins (today there is one shared passcode).
- **HTTPS** and an internet-reachable deployment.

## Known limits

- Photos up to 50 MB each; JPEG, PNG, GIF, WebP, HEIC, MP4, MOV. The iPhone app converts HEIC photos to JPEG before uploading.
- The calendar uses each device's own time zone.
- Editing a post that is already marked as posted is blocked on purpose; use Duplicate.
