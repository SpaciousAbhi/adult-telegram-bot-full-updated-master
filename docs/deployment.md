# Deployment Checklist

## 1. Database

Use MongoDB for production. This bot stores registered users, tasks, media fingerprints, force subscription settings, referral links, broadcasts, and admin runtime settings in MongoDB.

Do not replace the old MongoDB database if it already contains registered users. Point `MONGO_URI` to the existing database so broadcasts can still target saved users.

If the old bot used PostgreSQL, set the PostgreSQL URL as `LEGACY_DATABASE_URL` and set a new `MONGO_URI` for this bot. The worker imports old users from common PostgreSQL user tables (`users`, `bot_users`, `registered_users`) into MongoDB without deleting old data.

The app never drops collections during startup.

## 2. Required Config Vars

Set these in Heroku:

```env
BOT_TOKEN=...
ADMIN_ID=...
MONGO_URI=...
```

`ADMIN_ID`, `ADMIN_IDS`, `OWNER_ID`, and `OWNER_IDS` may contain comma-separated numeric Telegram user IDs. All configured IDs can manage the bot.

If you prefer `DATABASE_URL` for the runtime database, it must be a `mongodb://` or `mongodb+srv://` URI. Heroku Postgres URLs start with `postgres://`; keep those as `LEGACY_DATABASE_URL`.

## 3. Userbot Config

Automatic source scanning requires API ID and API Hash. You can add them from `/admin` -> `Userbot Management`, or set fallback vars:

```env
API_ID=...
API_HASH=...
```

Then open `/admin` -> `Userbot Management` and login with API ID -> API Hash -> phone -> code -> 2FA if needed, or paste a Telethon StringSession after API credentials are saved.

The session string is stored in MongoDB, not in the repository.

## 4. Telegram Permissions

The bot needs:

- admin permission in destination channels to publish teaser posts
- admin permission in storage channels to copy or forward stored videos to users
- admin permission in force-subscription channels to check members and create invite links
- admin permission in referral channels to create user-specific invite links

The userbot needs:

- membership/access in source channels
- ability to forward source videos to the task storage channel

## 5. Task Setup

Open `/admin` -> `Task Management`.

For each task:

1. Create task.
2. Add sources.
3. Add destination channels.
4. Set storage channel.
5. Set interval.
6. Set videos per interval.
7. Start task.

Each task runs independently. Pausing a task stops posting only for that task.

## 6. Force Subscription

Open `/admin` -> `Advanced Force Subscription`.

Add channels as:

```text
chat_id | title | join
chat_id | title | request
```

Join mode creates a normal join link. Request mode creates a join-request invite link when the bot has permission.

Users only see channels they have not completed.

## 7. Broadcasting

Open `/admin` -> `Advanced Broadcasting System`.

Start a broadcast and send or forward the message. The bot copies it to saved users from MongoDB and updates the progress message with sent and failed counts.

## 8. Production Notes

- Run one worker dyno for polling. Do not run multiple polling workers with the same bot token.
- Rotate the bot token if it was exposed anywhere outside Heroku Config Vars.
- Keep `.env`, session files, logs, and runtime files untracked.
- If MongoDB startup fails on Heroku, check Atlas Network Access, database username/password, and TLS settings.
