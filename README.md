# Adult Telegram Bot Full Updated Master

Heroku-ready Telegram bot for admin-controlled adult content delivery workflows:

- admin dashboard with inline buttons
- task-based source to storage to destination posting
- duplicate video blocking through stored media fingerprints
- per-task interval and posts-per-interval controls
- per-task sources, destinations, and storage channel
- optional Telethon userbot for source scanning
- destination teaser posts with `Get This Video` deep links
- force subscription with join mode and request mode
- free daily limits, premium contact flow, and referral rewards
- user-delivered video and destination-post auto-delete
- saved-user broadcasting with progress tracking
- MongoDB-backed settings, users, tasks, media, referrals, and broadcasts

## Important Security Note

Never commit real bot tokens, database URLs, Telegram API credentials, or session strings. Put them in Heroku Config Vars or a local ignored `.env` file.

If a bot token was posted in chat, rotate it in BotFather before production use.

## Required Heroku Config Vars

Minimum:

```env
BOT_TOKEN=123456:replace-me
ADMIN_ID=123456789
MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/adult_telegram_bot
```

Aliases accepted:

- `BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, or `TOKEN`
- `ADMIN_ID`, `ADMIN_IDS`, `OWNER_ID`, `OWNER_IDS`, `BOT_OWNER_ID`, or `BOT_OWNER_IDS`
- `MONGO_URI`, `MONGODB_URI`, `MONGO_URL`, `MONGODB_URL`, `MONGO_DB_URI`, `MONGO_DB_URL`, or `DATABASE_URL`

`DATABASE_URL` is accepted as the runtime database only when it contains a MongoDB URI. If the old bot used PostgreSQL, keep that URL as `LEGACY_DATABASE_URL` and set `MONGO_URI` for the new runtime. On startup, the bot imports old registered users from common PostgreSQL user tables into MongoDB for broadcasting.

Optional userbot fallback vars:

```env
API_ID=12345
API_HASH=abcdef123456
```

You can also add API ID and API Hash from `/admin` -> `Userbot Management`; the login flow asks for API ID, API Hash, phone, login code, and 2FA password when needed.

## Heroku Deploy

The repo uses a worker dyno:

```Procfile
worker: python -m app.main
```

Deployment shape:

1. Create the Heroku app.
2. Add the config vars above.
3. Deploy this repository.
4. Scale the worker dyno to 1.
5. Add the bot as admin in all destination, storage, force-sub, and referral channels where Bot API actions are required.
6. Add the userbot account to source and storage channels when automatic source scanning is needed.

See [docs/deployment.md](docs/deployment.md) for the detailed checklist.

## Admin Flow

Send `/admin` from an admin account.

The panel includes:

- Userbot Management
- Task Management
- Forward Tag On / Off
- Auto Delete Settings
- Advanced Force Subscription
- User Access Settings
- Advanced Broadcasting System

## User Flow

Users start with `/start`.

If force subscription is enabled, the bot only shows unfinished channels. If no force-subscription channels are configured, `/start` continues normally and always sends a fallback message. After `Verify Access`, the bot resumes the interrupted action. If the user came through a `Get This Video` button, the bot checks the daily limit and then forwards or copies the stored video from the storage channel.

## Local Validation

```powershell
python -m compileall app
python -m unittest discover -s tests
```

Live Telegram behavior requires real Telegram credentials, reachable MongoDB, bot admin permissions, and valid channel IDs.
