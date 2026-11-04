# Развёртывание Дживса на сервере

Схема: Telegram → `https://jeeves.perm-bear.ru/webhook` → nginx (443, TLS, существующий vhost) → бот на `127.0.0.1:18090` → MariaDB на `127.0.0.1:3306` (база `wa`). Бот запускается как systemd-сервис. Docker не нужен.

Инструкция проверена на CentOS 7 (glibc 2.17, systemd 219, системный Python 3.6 не трогаем). На более новых системах вместо `uv` можно взять системный Python 3.12.

## 0. Что понадобится

- Сервер с nginx, MariaDB (база `wa`), доступом в интернет и сертификатом для `jeeves.perm-bear.ru`
- Токен бота от @BotFather (см. шаг 7: старый бот или новый)
- Telegram ID администратора (`ADMIN_ID`): туда придут сообщения о сбоях
- Порт для бота, свободный на `127.0.0.1` (здесь `18090`; проверка: `sudo ss -ltnp | grep 18090`)

## 1. Пользователь и каталог

```bash
sudo useradd --system --create-home --home-dir /opt/jeeves --shell /sbin/nologin jeeves
```

## 2. Python 3.12 через uv (для старых систем)

Скачиваем готовый `uv` (без pipe-в-shell) и ставим автономный Python 3.12 в домашний каталог пользователя `jeeves`:

```bash
sudo -u jeeves -H bash -c '
set -e
mkdir -p /opt/jeeves/bin
curl -fsSL -o /tmp/uv.tgz https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz
tar -xzf /tmp/uv.tgz -C /opt/jeeves/bin --strip-components=1
rm /tmp/uv.tgz
cd /opt/jeeves   # иначе uv ищет uv.toml в текущем каталоге вызывающего и падает с Permission denied
bin/uv --version
bin/uv python install 3.12
bin/uv python find 3.12
'
```

## 3. Код и окружение

Код кладём в `/opt/jeeves/src` (способ: `git clone https://github.com/safrashenkov/jeeves.git /opt/jeeves/src` либо копирование архива).

```bash
sudo -u jeeves -H bash -c '
set -e
cd /opt/jeeves
bin/uv venv --python 3.12 .venv
# --only-binary greenlet: на старых системах (glibc 2.17) нет свежего greenlet в бинарном виде,
# а gcc 4.8 его не соберёт; uv подберёт версию с готовым пакетом
bin/uv pip install --python .venv/bin/python --only-binary greenlet /opt/jeeves/src
.venv/bin/python -c "import jeeves, aiogram, greenlet; print(\"ok\", aiogram.__version__, greenlet.__version__)"
'
```

## 4. Пользователь БД (не `root`)

Боту нужны только две таблицы. Выполните от администратора MariaDB:

```sql
CREATE USER 'jeeves'@'localhost'  IDENTIFIED BY '<пароль>';
CREATE USER 'jeeves'@'127.0.0.1' IDENTIFIED BY '<пароль>';
GRANT SELECT, INSERT, UPDATE, DELETE ON wa.t_settings      TO 'jeeves'@'localhost', 'jeeves'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE, DELETE ON wa.t_chat_settings TO 'jeeves'@'localhost', 'jeeves'@'127.0.0.1';
FLUSH PRIVILEGES;
```

Посмотрите, что уже лежит в базе:

```sql
SELECT * FROM wa.t_settings WHERE s_setting = 'newsUpdateTime';
SELECT s_value, COUNT(*) FROM wa.t_chat_settings WHERE s_setting = 'enableNews' GROUP BY s_value;
```

Если `newsUpdateTime` старше суток, при первом запуске бот сам сбросит его на «сейчас» и ничего не разошлёт: старые записи в чаты не придут.

## 5. Конфигурация

```bash
sudo -u jeeves cp /opt/jeeves/src/.env.example /opt/jeeves/.env
sudo chmod 600 /opt/jeeves/.env
sudo -u jeeves vi /opt/jeeves/.env
```

Заполните `BOT_TOKEN`, `BOT_NAME` (имя бота без `@`), `ADMIN_ID`, `WEBHOOK_SECRET` (случайная строка: `openssl rand -hex 24`), `DB_USER=jeeves`, `DB_PASSWORD`. Остальное по умолчанию (`LISTEN_PORT=18090`).

## 6. nginx

Если у `jeeves.perm-bear.ru` уже есть vhost (как на kmb-5, `/etc/nginx/sites-enabled/jeeves.perm-bear.ru`), добавьте в его блок с `listen 443 ssl` два `location` из `deploy/nginx.conf` (вариант А). Затем:

```bash
sudo cp /etc/nginx/sites-enabled/jeeves.perm-bear.ru /root/jeeves.perm-bear.ru.bak   # резервная копия
sudo vi /etc/nginx/sites-enabled/jeeves.perm-bear.ru
sudo nginx -t && sudo systemctl reload nginx
```

PHP-скрипты на этом же vhost продолжают работать: точное совпадение `location = /webhook` приоритетнее regex-локаций.

## 7. Какой токен: старый бот или новый

- **Новый бот:** создайте в @BotFather, впишите токен в `.env`. Старый PHP-бот не затрагивается.
- **Старый бот** (чаты и подписки сохраняются): `setWebhook` перенаправит апдейты на новый адрес, и PHP-версия **перестанет получать сообщения**. Перед запуском остановите отправку новостей PHP-версией. На kmb-5 это строка в crontab пользователя root:

  ```
  */5 * * * * php /var/www/jeeves/w_rcon.php >/dev/null 2>&1
  ```

  Закомментируйте её (`sudo crontab -e`, поставьте `#` в начало строки). Остальные строки (`w_rcon_1.php`, `cron_1.php`) связаны с аукционом, новости они не шлют. Вместе со строкой `w_rcon.php` отключается и старая пересылка сообщений из Discord (внешний сервис, скорее всего, давно мёртв).

Проверить, куда сейчас смотрит бот:

```bash
read -rs TOKEN && curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"; unset TOKEN
```

## 8. Запуск

```bash
sudo cp /opt/jeeves/src/deploy/jeeves.service /etc/systemd/system/jeeves.service
sudo systemctl daemon-reload
sudo systemctl enable --now jeeves
journalctl -u jeeves -f
```

В логе должно появиться «Слушаю 127.0.0.1:18090» и «Вебхук установлен».

## 9. Проверка

1. `curl https://jeeves.perm-bear.ru/healthz` отвечает `ok`.
2. `getWebhookInfo` (команда из шага 7): `url` равен `https://jeeves.perm-bear.ru/webhook`, поля `last_error_message` нет.
3. В личке с ботом напишите «помощь». Должен прийти список команд.
4. В группе напишите «Дживс, включи новости». Бот ответит «Подписка на новости включена».
5. Через 5–10 минут в чат придёт первая свежая новость.

## Обновление и откат

```bash
cd /opt/jeeves/src && sudo -u jeeves git pull
sudo -u jeeves -H bash -c 'cd /opt/jeeves && bin/uv pip install --python .venv/bin/python --only-binary greenlet /opt/jeeves/src'
sudo systemctl restart jeeves
```

Откат: `git checkout <предыдущий коммит>`, затем те же `pip install` и `restart`. Вернуть PHP-версию: `sudo systemctl stop jeeves`, раскомментировать строку в crontab и выставить вебхук PHP-бота обратно (`setWebhook` на его прежний URL).

## Если что-то не так

| Симптом | Что смотреть |
|---|---|
| `healthz` не отвечает | `systemctl status jeeves`, `journalctl -u jeeves -n 50`; `nginx -t`; порт `LISTEN_PORT` совпадает с `proxy_pass` |
| `getWebhookInfo` показывает `SSL error … certificate verify failed` | сертификат vhost просрочен или не тот: `curl -svI https://jeeves.perm-bear.ru/healthz 2>&1 \| grep -iE "subject:\|expire date"`. Путь `ssl_certificate` в vhost должен вести в `/etc/letsencrypt/live/jeeves.perm-bear.ru/` (список: `sudo certbot certificates`). После правки: `nginx -t`, `reload`, затем переустановить вебхук (перезапуск сервиса или `setWebhook`). Накопившиеся апдейты можно сбросить параметром `drop_pending_updates=true`. Не проверяйте сертификат через `openssl s_client` из CentOS 7: старый OpenSSL ненадёжно передаёт SNI, ориентируйтесь на `curl -v` |
| Сервис перезапускается каждые 5 с | в логе причина: чаще всего неверный `BOT_TOKEN` (Unauthorized) или нет доступа к БД |
| `[Errno 98] address already in use` | порт занят: выберите другой `LISTEN_PORT` и поправьте `proxy_pass` |
| Telegram получает 401 от webhook | `WEBHOOK_SECRET` в `.env` менялся после установки вебхука: перезапустите сервис, он поставит вебхук заново |
| Бот молчит в группе | пишите «Дживс, …» или слэш-команду; в группе другие сообщения бот игнорирует |
| Новости не приходят | `SELECT * FROM t_settings WHERE s_setting='newsUpdateTime'` (должна обновляться), `SELECT * FROM t_chat_settings WHERE s_setting='enableNews'`; в логе строки «Лента … недоступна» |
| Чат перестал получать новости | бота удалили или заблокировали: чат автоматически отписывается (`enableNews = 0`), включите заново |
