# Jeeves Stage 0–1 (каркас, развёртывание, RSS-новости) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python-бот Дживс на webhook, который по таблицам старой БД `wa` рассылает RSS-новости подписанным чатам, принимает «Дживс, включи/выключи новости» и разворачивается на сервере по инструкции.

**Architecture:** Один процесс: aiohttp-приложение (webhook aiogram, `/healthz`) и фоновая asyncio-задача новостей раз в 5 минут. Чистые функции (разбор команд, разбор RSS, выбор новых записей) отделены от I/O (БД, Telegram, HTTP), I/O передаётся в логику как зависимости, чтобы тестировать без сети.

**Tech Stack:** Python ≥3.12, aiogram 3.x, aiohttp, SQLAlchemy 2 (Core, async) + aiomysql, feedparser, pydantic-settings, pytest, pytest-asyncio, aiosqlite (только в тестах).

**Spec:** `docs/superpowers/specs/2026-11-04-jeeves-python-rewrite-design.md` (roadmap: `docs/ROADMAP.md`)

## Global Constraints

- **Не выполнять `git add` / `git commit`**, пока пользователь явно не попросит (его глобальное правило). Каждая задача заканчивается зелёным `python -m pytest`, а не коммитом.
- Схему БД `wa` не менять. Используются только `t_settings(s_setting varchar(20) PK, s_val varchar(20))` и `t_chat_settings(n_chat_id bigint, s_setting varchar(20), s_value varchar(1000), PK(n_chat_id, s_setting))`.
- Ключи: `newsUpdateTime` (unix-секунды, в `t_settings`), `enableNews` со значениями `'1'`/`'0'` (в `t_chat_settings`).
- Все SQL-запросы параметризованные, строки не склеиваются.
- Секреты только в `.env`; в репозиторий попадает `.env.example` без значений.
- Бот слушает `127.0.0.1`, наружу его публикует nginx на 443; домен `jeeves.perm-bear.ru`; Docker не используется.
- Ответы бота на русском; в группе реагирует только на сообщения, начинающиеся с «Дживс», либо на слэш-команды без чужого `@имя`; в личке на любое сообщение.
- Включать и выключать новости может любой участник чата.
- Защита от лавины: если `newsUpdateTime` старше 24 часов (или отсутствует), он сбрасывается на «сейчас» и в этот цикл ничего не рассылается.
- Источники: noob-club, MMO-Champion, YouTube `UC7Oo1q9m4vf7XrlZgOR95WA` и `UCbLj9QP9FAaHs_647QckGtg`, Wowhead news, Raider.IO. Twitter (twitrss.me) не используется.

## Review Focus

1. **Дата записи в будущем.** Лента отдаёт `pubDate` на год вперёд; `newsUpdateTime` не должен уехать вперёд «сейчас», иначе новости встанут. → тест в Task 5.
2. **Лента недоступна или отдаёт мусор.** Остальные ленты обрабатываются, цикл не падает. → тест в Task 4.
3. **Нет подписанных чатов.** `newsUpdateTime` всё равно продвигается, иначе при первой подписке придёт лавина. → тест в Task 5.
4. **Один чат заблокировал бота / удалён.** Он отписывается (`enableNews='0'`), остальные получают новость, цикл не падает. → тест в Task 5.
5. **Сообщение без текста** (стикер, фото, пересланный пост): `message.text is None` не должен ронять обработчик. → тест в Task 3.

---

## File Structure

```
pyproject.toml                  # зависимости, pytest config
.env.example
src/jeeves/__init__.py
src/jeeves/config.py            # Settings
src/jeeves/db.py                # Database + таблицы Core
src/jeeves/router.py            # parse_command
src/jeeves/handlers.py          # тексты и обработчики команд -> str
src/jeeves/news.py              # NewsItem, parse_feed, fetch_all, select_new, format_item
src/jeeves/news_job.py          # run_news_cycle, news_loop
src/jeeves/alerts.py            # AdminNotifier
src/jeeves/app.py               # build_dispatcher, create_app
src/jeeves/main.py              # запуск
tests/...                       # по файлу на модуль
deploy/jeeves.service, deploy/nginx.conf, deploy/DEPLOY.md
```

---

### Task 1: Каркас проекта и конфиг

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/jeeves/__init__.py`, `src/jeeves/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `class Settings(BaseSettings)` в `jeeves.config` с полями `bot_token: str`, `bot_name: str`, `admin_id: int`, `webhook_base_url: str`, `webhook_path: str = "/webhook"`, `webhook_secret: str`, `listen_host: str = "127.0.0.1"`, `listen_port: int = 8080`, `db_host: str = "127.0.0.1"`, `db_port: int = 3306`, `db_user: str`, `db_password: str`, `db_name: str = "wa"`, `news_interval_seconds: int = 300`; свойства `webhook_url -> str` (`base + path`) и `db_url -> str` (`mysql+aiomysql://…?charset=utf8mb4`, пароль URL-кодируется). Переменные окружения называются в верхнем регистре (`BOT_TOKEN`, …). Функция `get_settings() -> Settings`.

- [ ] **Step 1: Написать падающий тест** `tests/test_config.py::test_urls_built_from_env`: через `monkeypatch.setenv` задать минимальный набор (`BOT_TOKEN=1:a`, `BOT_NAME=jeeves_bot`, `ADMIN_ID=5`, `WEBHOOK_BASE_URL=https://jeeves.perm-bear.ru`, `WEBHOOK_SECRET=s`, `DB_USER=u`, `DB_PASSWORD=p@ss/word`); ожидать `webhook_url == "https://jeeves.perm-bear.ru/webhook"` и что `db_url` содержит `p%40ss%2Fword`, начинается с `mysql+aiomysql://u:` и заканчивается `/wa?charset=utf8mb4`.
- [ ] **Step 2:** Запустить `python -m pytest tests/test_config.py -v`; ожидать FAIL (нет модуля).
- [ ] **Step 3:** Создать `pyproject.toml` (setuptools, src-layout, `requires-python >=3.12`, dependencies по списку Tech Stack, extra `dev` = pytest, pytest-asyncio, aiosqlite; `[tool.pytest.ini_options]` с `asyncio_mode = "auto"` и `pythonpath = ["src"]`), `.env.example` со всеми переменными без значений секретов, пакет и `config.py`. Установить: `python -m venv .venv && .venv\Scripts\pip install -e ".[dev]"`.
- [ ] **Step 4:** `python -m pytest tests/test_config.py -v`; ожидать PASS.

---

### Task 2: Доступ к БД

**Files:**
- Create: `src/jeeves/db.py`, `tests/test_db.py`

**Interfaces:**
- Consumes: `Settings.db_url` (Task 1).
- Produces: `class Database` в `jeeves.db`:
  - `__init__(self, url: str)` — создаёт `AsyncEngine` (`pool_pre_ping=True`).
  - `async create_all(self) -> None` — только для тестов (создаёт две таблицы на SQLite).
  - `async get_setting(self, name: str) -> str | None`
  - `async set_setting(self, name: str, value: str) -> None` — upsert
  - `async set_chat_setting(self, chat_id: int, name: str, value: str) -> None` — upsert
  - `async get_chat_ids_with_setting(self, name: str, value: str) -> list[int]`
  - `async migrate_chat(self, old_id: int, new_id: int) -> None` — переносит все строки `t_chat_settings` со старого ID на новый (если у нового уже есть ключ, значение нового сохраняется)
  - `async close(self) -> None`
  - модуль-уровневые `metadata`, `t_settings`, `t_chat_settings` (SQLAlchemy `Table`, типы и длины как в схеме).

Upsert реализуется переносимо: `UPDATE`, и при `rowcount == 0` `INSERT`, в одной транзакции (работает и на MariaDB, и на SQLite в тестах).

- [ ] **Step 1: Написать падающие тесты** (фикстура: `Database("sqlite+aiosqlite:///:memory:")` + `create_all`): `test_setting_roundtrip` (нет → `None`; после `set_setting("newsUpdateTime","100")` → `"100"`; повторный set перезаписывает), `test_chat_setting_upsert_and_filter` (чаты 1 и 2 с `enableNews='1'`, чат 3 с `'0'` → список `[1, 2]`; повторный set для чата 1 в `'0'` убирает его из выборки), `test_migrate_chat_moves_rows_and_keeps_existing_target_value`.
- [ ] **Step 2:** `python -m pytest tests/test_db.py -v`; ожидать FAIL.
- [ ] **Step 3:** Реализовать `Database` по сигнатурам выше. Для `:memory:` SQLite использовать `StaticPool`, чтобы все соединения видели одну БД.
- [ ] **Step 4:** `python -m pytest tests/test_db.py -v`; ожидать PASS.

---

### Task 3: Разбор команд и обработчики

**Files:**
- Create: `src/jeeves/router.py`, `src/jeeves/handlers.py`, `tests/test_router.py`, `tests/test_handlers.py`

**Interfaces:**
- Consumes: `Database` (Task 2).
- Produces:
  - `jeeves.router.parse_command(text: str | None, chat_id: int, bot_name: str) -> str | None` — `None`, если сообщение боту не адресовано; иначе ключ команды: `"news_on"`, `"news_off"`, `"help"` или `"unknown"`.
  - `jeeves.handlers.HANDLERS: dict[str, Callable[[int, Database], Awaitable[str]]]` с ключами `news_on`, `news_off`, `help`, `unknown`; каждый обработчик принимает `chat_id` и `db` и возвращает текст ответа.
  - Тексты ответов: `"Подписка на новости включена"`, `"Подписка на новости отключена"`; `unknown` → `"Простите, не понял. Список команд: /help"`; `help` — список живых команд («Дживс, включи новости», «Дживс, выключи новости», «Дживс, помощь»).

Правила `parse_command`: приведение к нижнему регистру; в тексте убираются `, ? .`. Слэш-команды: `/start`, `/help` → `help`; `/news_on`, `/news_off`; суффикс `@<bot_name>` допустим, чужой `@другойбот` — `None`. Фразы (подстрока): «включи новости» → `news_on`; «выключи новости» и «отключи новости» → `news_off`; «помощь», «help» → `help`. В группе (`chat_id < 0`) без слэша нужно начало «дживс»; в личке (`chat_id > 0`) подходит любое непустое сообщение. Адресованное, но нераспознанное → `"unknown"`.

- [ ] **Step 1: Написать падающие тесты** `test_router.py`: личка «включи новости» → `news_on`; группа «Дживс, включи новости!» → `news_on`; группа «Дживс, отключи новости» → `news_off`; группа «включи новости» (без обращения) → `None`; `/news_on@jeeves_bot` в группе → `news_on`; `/news_on@other_bot` → `None`; `/start` → `help`; группа «Дживс, расскажи анекдот» → `unknown`; **`parse_command(None, -100, "jeeves_bot") is None`** и то же для пустой строки (Review Focus 5). `test_handlers.py`: `HANDLERS["news_on"](chat, db)` записывает `enableNews='1'` и возвращает точный текст; `news_off` пишет `'0'`; `help` упоминает «включи новости».
- [ ] **Step 2:** `python -m pytest tests/test_router.py tests/test_handlers.py -v`; ожидать FAIL.
- [ ] **Step 3:** Реализовать `parse_command` и `HANDLERS` (команды зарегистрированы таблицей «фраза → ключ», чтобы будущие модули добавляли строки).
- [ ] **Step 4:** Те же тесты; ожидать PASS.

---

### Task 4: RSS-сервис

**Files:**
- Create: `src/jeeves/news.py`, `tests/test_news.py`

**Interfaces:**
- Produces в `jeeves.news`:
  - `@dataclass(frozen=True) class NewsItem: title: str; link: str; published: int` (unix-секунды UTC)
  - `FEEDS: list[str]` — URL источников из Global Constraints (при реализации проверить каждый запросом; недоступные оставить в списке с комментарием)
  - `parse_feed(data: bytes) -> list[NewsItem]` — RSS и Atom; записи без даты или без ссылки пропускаются; мусор вместо XML → `[]`
  - `async fetch_all(session: aiohttp.ClientSession, urls: list[str]) -> list[NewsItem]` — параллельно, таймаут 15 с на ленту; исключение одной ленты логируется и не влияет на остальные
  - `select_new(items: list[NewsItem], since: int) -> list[NewsItem]` — записи с `published > since`, без дублей по `link`, по возрастанию `published`
  - `format_item(item: NewsItem) -> str` — `"<экранированный заголовок>\n<ссылка>"`; заголовок обрезается так, чтобы весь текст ≤ 4096 символов; HTML-спецсимволы (`<`, `&`) экранируются

- [ ] **Step 1: Написать падающие тесты** с фикстурами-строками (мини-RSS и мини-Atom с известными датами): `test_parse_rss_and_atom` (поля и unix-время), `test_parse_skips_items_without_date`, `test_parse_garbage_returns_empty`, `test_select_new_filters_dedups_and_sorts` (две записи с одной ссылкой из разных лент → одна), `test_format_item_escapes_and_truncates` (`"A & <b>"` → `"A &amp; &lt;b&gt;\nhttp://x"`; заголовок 5000 символов → результат ≤ 4096), `test_fetch_all_survives_failing_feed` (фейковая session: одна лента бросает исключение, вторая отдаёт RSS → возвращаются записи второй; Review Focus 2).
- [ ] **Step 2:** `python -m pytest tests/test_news.py -v`; ожидать FAIL.
- [ ] **Step 3:** Реализовать (разбор через `feedparser.parse`, время `calendar.timegm(entry.published_parsed or entry.updated_parsed)`).
- [ ] **Step 4:** `python -m pytest tests/test_news.py -v`; ожидать PASS.

---

### Task 5: Цикл рассылки и оповещение админа

**Files:**
- Create: `src/jeeves/news_job.py`, `src/jeeves/alerts.py`, `tests/test_news_job.py`, `tests/test_alerts.py`

**Interfaces:**
- Consumes: `Database` (Task 2), `NewsItem`, `select_new`, `format_item` (Task 4).
- Produces:
  - `jeeves.alerts.AdminNotifier(send: Callable[[str], Awaitable[None]], interval: float = 3600, clock: Callable[[], float] = time.monotonic)` с `async notify(self, text: str) -> bool` — отправляет не чаще раза в `interval`; возвращает, отправлено ли.
  - `jeeves.news_job.run_news_cycle(db: Database, fetch: Callable[[], Awaitable[list[NewsItem]]], send: Callable[[int, str], Awaitable[None]], now: int, pause: float = 0.05) -> int` — возвращает число разосланных записей. Алгоритм: прочитать `newsUpdateTime`; если нет или `< now - 86400` → записать `now`, вернуть 0 (защита от лавины); иначе `fetch()`, у каждой записи `published = min(published, now)` (Review Focus 1), `select_new`, чаты `enableNews='1'`; рассылка от старых к новым, пауза `pause` между отправками; обработка ошибок отправки: `TelegramForbiddenError` и `TelegramBadRequest` с «chat not found» → `enableNews='0'` для чата; `TelegramMigrateToChat` → `migrate_chat(old, e.migrate_to_chat_id)` и повтор в новый ID; `TelegramRetryAfter` → `asyncio.sleep(e.retry_after)` и один повтор; любые другие ошибки одного чата логируются и не прерывают рассылку. В конце `newsUpdateTime = max(published)` по отправленным/отобранным записям, при их отсутствии остаётся прежним (но см. «нет чатов» ниже).
  - `jeeves.news_job.news_loop(run_once: Callable[[], Awaitable[object]], interval: int, on_error: Callable[[str], Awaitable[None]]) -> None` — бесконечный цикл: `run_once()`, при исключении логирует и вызывает `on_error`, затем `asyncio.sleep(interval)`; `CancelledError` не глотается.

- [ ] **Step 1: Написать падающие тесты** `test_news_job.py` (БД SQLite, `fetch` и `send` — фейки, `now` фиксирован): `test_first_run_resets_stale_timestamp_and_sends_nothing` (нет ключа → записан `now`, 0 отправок); `test_stale_over_24h_resets`; `test_sends_new_items_oldest_first_to_subscribed_chats_only` (записи старше `since` не рассылаются, чат с `'0'` не получает); `test_future_pubdate_does_not_advance_beyond_now` (запись с датой `now + 10**7` → `newsUpdateTime <= now`); `test_no_subscribed_chats_still_advances_timestamp` (Review Focus 3); `test_blocked_chat_is_disabled_and_others_still_receive` (send бросает `TelegramForbiddenError` для чата 1 → в БД `enableNews='0'`, чат 2 получил; Review Focus 4); `test_migrate_to_chat_retargets_and_retries`; `test_retry_after_retried_once`; `test_news_loop_survives_exception_and_reports` (`run_once` бросает → `on_error` вызван, цикл продолжается; завершить отменой задачи). `test_alerts.py`: второй вызов в пределах `interval` возвращает `False` и не шлёт; после `interval` — снова шлёт (фейковые часы).
- [ ] **Step 2:** `python -m pytest tests/test_news_job.py tests/test_alerts.py -v`; ожидать FAIL.
- [ ] **Step 3:** Реализовать по контракту выше.
- [ ] **Step 4:** Те же тесты; ожидать PASS.

---

### Task 6: Приложение, webhook и запуск

**Files:**
- Create: `src/jeeves/app.py`, `src/jeeves/main.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `Settings`, `Database`, `parse_command`, `HANDLERS`, `run_news_cycle`, `news_loop`, `fetch_all`, `FEEDS`, `AdminNotifier`.
- Produces:
  - `jeeves.app.build_dispatcher(db: Database, bot_name: str) -> Dispatcher` — один `message`-хендлер: `key = parse_command(message.text, message.chat.id, bot_name)`; `None` → ничего; иначе `reply = await HANDLERS[key](message.chat.id, db)` и `message.reply(reply)`.
  - `jeeves.app.create_app(settings: Settings, db: Database, bot: Bot) -> aiohttp.web.Application` — маршруты: `settings.webhook_path` (aiogram `SimpleRequestHandler` с `secret_token=settings.webhook_secret`) и `GET /healthz` → `200 "ok"`.
  - `jeeves.main.run() -> None` и `if __name__ == "__main__"`: собирает всё, на старте `bot.set_webhook(settings.webhook_url, secret_token=..., drop_pending_updates=False)`, запускает `news_loop` фоновой задачей (с `AdminNotifier`, шлющим админу `admin_id` через `bot.send_message`), слушает `listen_host:listen_port`; при остановке отменяет задачу и закрывает `db`, `bot.session`. Логирование: `logging.basicConfig(level=INFO)` в stdout.

- [ ] **Step 1: Написать падающие тесты** `tests/test_app.py` (aiohttp `TestClient`/`TestServer`, `Bot("123:abc")` без сети, SQLite): `test_healthz_ok`; `test_webhook_rejects_missing_secret` (POST `/webhook` без заголовка `X-Telegram-Bot-Api-Secret-Token` → 403); `test_dispatcher_replies_to_news_on` (вызов `dp.feed_update` с `Update`, содержащим сообщение «Дживс, включи новости» из группы, с `Bot`, у которого метод отправки подменён на запись вызовов → в БД `enableNews='1'`, зафиксирован ответ «Подписка на новости включена»); `test_dispatcher_ignores_unaddressed_group_message` (ответов нет).
- [ ] **Step 2:** `python -m pytest tests/test_app.py -v`; ожидать FAIL.
- [ ] **Step 3:** Реализовать `app.py` и `main.py`.
- [ ] **Step 4:** `python -m pytest -v` (весь набор); ожидать PASS, ноль warnings про незакрытые ресурсы.
- [ ] **Step 5:** Локальная проверка запуска: в `.env` фиктивные значения, `python -m jeeves.main`, в другом окне `curl http://127.0.0.1:8080/healthz` → `ok` (с реальным токеном `set_webhook` пройдёт, с фиктивным — залогирует ошибку; убедиться, что процесс при этом не падает молча, а сообщает причину).

---

### Task 7: Файлы развёртывания и инструкция

**Files:**
- Create: `deploy/jeeves.service`, `deploy/nginx.conf`, `deploy/DEPLOY.md`, `README.md`

**Interfaces:**
- Consumes: запуск `python -m jeeves.main` (Task 6) и переменные `.env` (Task 1).

- [ ] **Step 1:** `deploy/jeeves.service`: unit для пользователя `jeeves`, `WorkingDirectory=/opt/jeeves`, `EnvironmentFile=/opt/jeeves/.env`, `ExecStart=/opt/jeeves/.venv/bin/python -m jeeves.main`, `Restart=always`, `RestartSec=5`, `After=network-online.target mariadb.service`.
- [ ] **Step 2:** `deploy/nginx.conf`: серверный блок `jeeves.perm-bear.ru`, TLS (пути сертификатов — плейсхолдеры с пометкой заменить), `location /webhook` и `location /healthz` → `proxy_pass http://127.0.0.1:8080`, остальное `404`.
- [ ] **Step 3:** `deploy/DEPLOY.md` (по шагам, с командами): требования (Python 3.12, nginx, MariaDB на `127.0.0.1`); пользователь и каталог `/opt/jeeves`; копирование кода; venv и `pip install .`; создание **отдельного пользователя БД** с правами `SELECT, INSERT, UPDATE, DELETE` только на `t_settings` и `t_chat_settings` (а `t_chat_history` — позже, на этапе 3), а не `root`; заполнение `.env`; подключение nginx (`nginx -t && systemctl reload nginx`); запуск (`systemctl enable --now jeeves`); проверка (`curl https://jeeves.perm-bear.ru/healthz` → `ok`, `getWebhookInfo` без `last_error_message`, тестовое «Дживс, включи новости» в чате, `journalctl -u jeeves -f`); **переключение с PHP-бота**: токен — старый или новый (оба варианта; при старом сначала остановить PHP-обработчик, т.к. `setWebhook` его отключит), заметка про `drop_pending_updates`; обновление (`git pull`/копирование, `pip install .`, `systemctl restart jeeves`) и откат; типовые проблемы (403 на webhook — не совпал секрет; нет новостей — смотреть `newsUpdateTime` и `enableNews` в БД).
- [ ] **Step 4:** `README.md`: что это, как запустить локально и прогнать тесты, ссылки на ROADMAP и DEPLOY.
- [ ] **Step 5:** Проверка: `python -m pytest -v` зелёный; на сервере (при развёртывании пользователем) — шаги проверки из DEPLOY.md проходят. Ни один файл не содержит реальных токенов/паролей: `grep -rniE "token|password|secret" deploy README.md` показывает только плейсхолдеры.

---

## Self-Review

- **Spec coverage:** команды и текст ответов (Task 3), источники/формат/защита от лавины/`newsUpdateTime` только после рассылки/авто-отписка/миграция чата/пауза/лимиты Telegram (Tasks 4–5), `/healthz` и `secret_token` (Task 6), алерты админу не чаще раза в час (Task 5, подключено в Task 6), логи в stdout (Task 6), структура и развёртывание (Task 7). «Лог ошибок в чат админа» из спека реализован через `AdminNotifier`. Таблица ошибок в БД спеком отложена и не планируется.
- **Типы:** `Database` методы, `NewsItem(title, link, published)`, `parse_command → str | None`, `HANDLERS[key](chat_id, db)`, `run_news_cycle(db, fetch, send, now, pause)` одинаково названы везде, где используются.
- **Отложено осознанно:** авторизация Battle.net, аукцион и прочие функции — этапы 2–5 ROADMAP.
- **Допущение, требующее внимания при реализации:** конкретные имена исключений и атрибутов aiogram (`TelegramMigrateToChat.migrate_to_chat_id`, `TelegramRetryAfter.retry_after`) проверить по установленной версии.
