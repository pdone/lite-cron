# LiteCron Changelog

[English](./UPDATE_EN.md) | [中文](./UPDATE.md)

This file covers releases from `v1.6.0` onward; for earlier changes, refer to the git history and GitHub Releases.

## v1.7.0

### Added

- New "Settings" modal in the WebUI for editing the shared proxy and notification (Webhook / NTFY) configuration in the browser
- New `GET` / `POST /api/settings` endpoints that read and save the proxy anchor and notify section of `config.yml`
- Webhook now supports `GET` / `POST` / `PUT` / `PATCH` methods, with JSON, form, plain text and Markdown content types
- New three-state theme switch (light / follow system / dark) in the WebUI; defaults to follow system, stored in browser local storage and never written to `config.yml`
- New automatic check-in task for the CarPT site (`tasks/carpt.py`)
- Supports `CARPT_COOKIE` / `CARPT_BASE_URL` / `CARPT_SIGN_QUERY` / `CARPT_PROXY` environment variables, so the site address can be customized

### Changed

- Settings are saved with `ruamel.yaml`, preserving comments, quotes and anchors so hand-maintained config files keep their formatting
- Editing the shared proxy now rewrites every `*proxy` reference, so aliases no longer keep pointing at the old value
- Notification `headers` stay as a YAML block scalar (`|`), so multi-line headers are not escaped into a single line
- Theme colors now live in CSS variables and task log colors are derived from the active theme, so switching themes needs no page re-render
- Declared `color-scheme` so scrollbars and native selects follow the active theme

### Fixed

- Notification header parsing now skips `#` comment and example lines, so sample headers are no longer sent as real ones
- Fixed light-mode contrast for task logs, selected log file, log row hover background and modal overlay

## v1.6.9

### Changed

- NodeSeek now uses `curl_cffi.Session`, with browser fingerprint candidates from newest to oldest (chrome146 / 145 / 142 / 131 / 124 / 120) filtered by `curl_cffi` version
- Adds `Accept`, `Sec-Fetch` and other headers, sends an empty JSON body on POST, and warms up the index page before check-in to obtain `__cf_bm` session cookies
- New optional `NODESEEK_UA` and `NODESEEK_IMPERSONATE` settings

### Fixed

- Fixed NodeSeek receiving a Cloudflare managed challenge (HTTP 403) because the TLS/HTTP2 fingerprint did not match `cf_clearance`
- Upgraded the `curl_cffi` dependency to `>=0.15.0`

## v1.6.8

### Fixed

- PTTime now handles the redesigned check-in page: parses the "7-day" and "previous 30-day" check-in records, and accepts both full-width and half-width colons before the total magic value
- PTTime already-signed detection now recognizes "今天已签到", "今日已签到", "已经签到" and "请勿重复刷新", so it is no longer reported as a failure
- PTTime records the raw page response when parsing fails, making later structure changes easier to diagnose

## v1.6.7

### Added

- New `log_response_detail`: on request or parse failures the raw site response is written to `logs/responses/<date>/`, while the main log only keeps the status code, URL, length and a summary
- All task scripts (iKuuu, Baidu Tieba, NodeSeek, PTTime, SMZDM, Bilibili, FnClub, V2EX, AliyunPan, ZhuTiX) now use the raw-response dump

### Changed

- Task colors are now generated dynamically from a task-name hash plus the golden angle (137.508°), keeping tasks distinguishable well beyond seven tasks
- `manage.py clean` and the WebUI cleanup endpoint now also purge expired `logs/responses` files (older than 7 days) and remove empty directories

## v1.6.6

### Added

- Log lines carry a `[TASK:<name>]` tag, so every line of multi-line output is attributed to the right task
- WebUI log viewer rewritten: logs are grouped and colored by task, with task filtering and collapsing, plus a new system log group

### Changed

- `manage.py`, `task_wrapper.py` and `webapp.py` now inject `LITECRON_TASK_NAME` consistently, so cron, in-container manual runs and local runs all produce the same task attribution
- The log viewer drops the download button in favor of in-page filtering and collapsing

### Fixed

- FnClub now returns a non-zero exit code when check-in fails, so failure notifications are no longer missed

## v1.6.5

### Added

- iKuuu supports a custom site domain via `IKUUU_DOMAIN`, defaulting to `ikuuu.win` when unset

### Fixed

- Fixed the mobile header layout where text overflowed

## v1.6.4

### Added

- New login page and token authentication for the WebUI; unauthorized requests are redirected to `/login`
- The access token can be set with the `WEBUI_TOKEN` environment variable or `webui.token` in `config.yml`
- A successful login stores a session cookie valid for 7 days by default, adjustable via `WEBUI_SESSION_DAYS` or `webui.session_days`
- Scripts can call the API with `Authorization: Bearer <token>`, which is not limited by the session lifetime

### Changed

- The WebUI binds to `127.0.0.1` only by default; setting `WEBUI_HOST=0.0.0.0` without a token refuses to start, preventing unauthorized public access

## v1.6.3

### Added

- Task list headers can be sorted by status, task name, schedule, description and next run time, in ascending, descending or unsorted order
- The sort state is persisted to `localStorage` and survives page reloads

### Changed

- The top toolbar (view logs / reload config / enable all / disable all) moved into the task card header with compact buttons
- Top-level stats became card header badges: enabled count (green pulsing dot) and total tasks
- Simplified the page header styling, made the logo circular and tuned its hover effect

## v1.6.2

### Added

- New "Enable all" / "Disable all" buttons and a `/api/tasks/batch/toggle` endpoint to toggle every scheduled task at once

### Changed

- Batch toggling uses `ruamel.yaml` to edit the `enabled` field in place, preserving anchors, aliases and comments
- WebUI operation logs now carry a `[WebUI]` prefix and cover `.env` generation, reloads after edits and log cleanup
- Centered the confirm icon; the cleanup button turns red on hover and uses a trash icon

### Fixed

- Fixed the refresh button behaving incorrectly because of a stray quote in its `index.html` attributes

## v1.6.1

### Changed

- WebUI toast notifications now use a left border for coloring instead of a pseudo-element, so they no longer overlap the text

### Fixed

- Bilibili: forwards the full cookie (including the `buvid3` / `buvid4` / `b_nutss` device fingerprints) to pass share-endpoint risk control
- V2EX: only "daily login reward already claimed" counts as already signed in, avoiding a false skip
- SMZDM: reworked the check-in return value and reward parsing to handle the already-signed case
- ZhuTiX: handles `dict`-shaped responses (`credit` / `mission`)

## v1.6.0

### Added

- The WebUI can now edit tasks: change the name, schedule, description and task-specific environment variables, and save back to `config.yml`
- New task detail, cron expression validation and script path validation endpoints, so configuration errors surface while editing
- New mobile-friendly layout, modal confirmation dialogs and maximized log viewing

### Changed

- Hardcoded absolute paths were replaced with dynamically resolved current directory, and the log directory falls back gracefully when it is not writable
- The hardcoded `python3` was replaced with `sys.executable` to fit different environments

### Fixed

- Bilibili following-feed videos are now fetched in a single dynamic feed request with better sampling, cutting request count and missed videos
