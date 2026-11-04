# Дживс

Telegram-бот для игроков World of Warcraft (чаты гильдий). Переписанная на Python версия старого PHP-бота.

Сейчас умеет: рассылать RSS-новости про WoW в подписанные чаты («Дживс, включи новости» / «Дживс, выключи новости»). Остальной старый функционал возвращаем по [ROADMAP](docs/ROADMAP.md).

## Локальный запуск и тесты

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m pytest
```

Для запуска самого бота скопируйте `.env.example` в `.env` и заполните его; бот работает через webhook, поэтому нужен публичный HTTPS-адрес. Для разработки удобнее опираться на тесты.

## Развёртывание

См. [deploy/DEPLOY.md](deploy/DEPLOY.md): systemd + nginx, без Docker.

## Устройство

- `src/jeeves/router.py` — разбор «Дживс, …» и слэш-команд
- `src/jeeves/handlers.py` — обработчики команд
- `src/jeeves/news.py`, `news_job.py` — получение RSS и рассылка
- `src/jeeves/db.py` — доступ к MariaDB (база `wa`, схема не менялась)
- `src/jeeves/app.py`, `main.py` — webhook и запуск
- `docs/` — дизайн, план, roadmap
