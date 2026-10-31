# UBBC Bot

Telegram bot for group beer purchasing (UBBC). Python 3.14 on AWS Lambda via SAM (eu-north-1),
DynamoDB, S3, SSM Parameter Store. No bot framework: raw Bot API via `requests`; Telethon user
client for messages sent from the admin's own Telegram account.

## Commands
- Setup: `python3 -m venv test_env && source test_env/bin/activate && pip install -r src/requirements.txt -r tests/requirements.txt`
- Tests: `AWS_DEFAULT_REGION=eu-north-1 AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing PYTHONPATH=src pytest`
  (parallel via xdist; single file: add `tests/test_x.py -p no:xdist`). Fake AWS env vars keep tests off real AWS.
- Deploy: `./deploy.sh test`. Production (`./deploy.sh prod`) only after explicit approval.
- There is no local bot runtime; the `test` stack on AWS is the dev environment.

## Architecture
- Entry: `src/handlers/webhook.py` (verifies `X-Telegram-Bot-Api-Secret-Token`) → `services/bot_service.py::process_update`
  - commands → `services/command_router.py` (authorization + admin check, then if/elif dispatch)
  - inline buttons → `services/callback_handler.py`: `_authorize_callback` first, then regex routes in
    `_register_routes`, then prefix fallbacks (`wd_`, `lc_`, `admin`, `cmd`, `page_`)
  - free-text replies → edit contexts (`utils/edit_context.py`, table `edit-contexts`, keyed by chat) → `BotService._handle_edit_reply`
- Handlers: `src/handlers/admin/**`, `src/handlers/customer/**`, all subclass `handlers/base_handler.py`
- Data: `services/database.py` facade → `repositories/*` (one per DynamoDB table); models and status enums in `models/entities.py`
- Async Lambdas: `notification_sender.py` (offer broadcasts), `message_sender.py` (bot or admin account)
- Public read-only API: `handlers/api/offers.py` (`GET /offers`, same API Gateway as the webhook)
- Status flows: Box open→full→ordered→delivered; Order pending→ordered→ready_for_labeling→labeling_completed→awaiting_payment→completed (or cancelled)

## Access control (security boundary)
- Admin = the single Telegram ID in `ADMIN_USER_ID` (`config.py`).
- Callback data is client-supplied. Any new customer-facing callback must be added to
  `CUSTOMER_CALLBACK_PATTERN` in `callback_handler.py`; everything else is admin-only by default.
- Handlers that take only `chat_id` cannot check the caller: never expose them without a gate in front.
- Customers must be `approved` to order; `handle_create_order` enforces this for every entry point.
- Edit contexts are only consumed by the admin's replies.

## Conventions
- All user-facing text via `self._t(key, user_id, **params)`; the key must exist in both
  `src/translations/nl.json` and `en.json`; no duplicate keys; group messages are always nl.
- Changing a command: update command_router, callback_handler/admin panel, help text, translations,
  `setup-commands.sh` and README together.
- Escape user-supplied strings (`_escape_html`) in any `parse_mode="HTML"` message.
- Use `logger`, not `print`. Never log tokens, contact info or free-text user input.
- Resource naming `ubbc-bot-{env}-{type}`; secrets only in SSM under `/ubbc-bot/{env}/`
  (`telegram-bot-token`, `telegram-webhook-secret`, `telegram-api-id`, `telegram-api-hash`, `telegram-session`).
- Conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`). Branch from `main`, PR with green CI.

## Gotchas
- Customer data belongs to real people (GDPR): never export or print real data during development; use the test stack.
- Box quantity and credit updates are read-modify-write without conditional writes; concurrent orders can
  overbook. Use DynamoDB `ConditionExpression`/transactions in new code that touches capacity or credits.
- Prod redirects most group commands to a private chat and blocks non-forced group messages; the test env does not.
- `BotService` is rebuilt per request; only the Telegram token and webhook secret are cached per container.
