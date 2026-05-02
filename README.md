# tg-accounts-shop

Telegram-бот для продажи зарегистрированных аккаунтов (cookies / login:pass) с оплатой через [CryptoBot](https://t.me/CryptoBot).

## Возможности

- Каталог с иерархией **Категория → Товар → Вариант**, каждый вариант имеет свою цену и сток.
- Три режима заливки стока (на товаре): **ZIP с файлами**, **по строкам**, **несколько документов одним сообщением**. JSON-cookies сохраняются как есть, многострочно.
- Покупка с резервированием стока, лимит **до 10 шт. за заказ** (настраивается).
- Баланс в рублях, пополнение через **CryptoBot** (USDT/TON/BTC/LTC) и **Lolzteam Market** (карты/СБП/Steam/Binance — RUB). Курс CryptoBot берётся автоматически, для Lolzteam применяется настраиваемая наценка (по умолчанию +6%). Округление в пользу сервиса.
- **Реферальная программа**: 5% от пополнений приглашённого, навсегда, на баланс. Процент настраивается.
- **Промокоды**: процентная скидка, фиксированная скидка, бонус на баланс. Лимиты, срок, scope (категория/товар/вариант), мин. заказ.
- **История покупок** с повторным скачиванием файлов.
- **Подписка на пополнение стока** — уведомление, когда вариант снова в наличии.
- **Возвраты** через админа: вернуть деньги + товар, только деньги, или просто заменить.
- **Админка целиком в Telegram**: категории/товары/варианты, заливка стока с превью и откатом партий, пользователи, покупки, промокоды, статистика по дням и категориям, рассылки, настройки на лету (без рестарта).
- **Уведомления админу**: новые юзеры, пополнения, покупки, низкий сток, возвраты, ошибки в debug-режиме.
- **Ежедневные бэкапы SQLite** с ротацией 14 дней (настраивается).

## Установка одной командой (Ubuntu 22.04+)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Lastveunderpass/tg-accounts-shop/main/install.sh)
```

Скрипт:

1. Установит Docker, если его нет.
2. Клонирует репозиторий в `/opt/tg-shop` (можно изменить через `INSTALL_DIR=...`).
3. Спросит обязательные переменные (`BOT_TOKEN`, `ADMIN_ID`, `SUPPORT_USERNAME`, `CRYPTOBOT_TOKEN`), сгенерирует `CRYPTOBOT_WEBHOOK_SECRET`.
4. Поднимет docker compose и накатит миграции.

Повторный запуск = безопасный апдейт (`git pull` + rebuild + `alembic upgrade`).

Управление сервисом:

```bash
cd /opt/tg-shop
docker compose logs -f      # логи
docker compose restart app  # рестарт
docker compose down         # остановить
docker compose up -d --build # обновить и поднять
```

## Конфигурация

Все секреты и настройки — в `.env`. Полный список — в `.env.example`. Ключевые:

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `ADMIN_ID` | Telegram ID единственного админа |
| `SUPPORT_USERNAME` | Юзернейм саппорта (тоже админа) |
| `CRYPTOBOT_TOKEN` | Crypto Pay App token |
| `CRYPTOBOT_POLLING` | `true` — опрос инвойсов (без домена), `false` — webhook (нужен HTTPS-домен) |
| `CRYPTOBOT_BASE_URL` | Публичный HTTPS URL — нужен только при `CRYPTOBOT_POLLING=false` или для Lolzteam-callback'а |
| `LOLZTEAM_TOKEN` | API-токен Lolzteam Market (lolz.live → Account upgrades → API, scope `payments`). Опционально |
| `LOLZTEAM_MERCHANT_ID` | ID мерчанта (lzt.market → Settings → Payments → Merchants). Опционально |
| `LOLZTEAM_POLLING` | `true` — опрос статусов (без домена), `false` — только webhook |
| `LOLZTEAM_INVOICE_LIFETIME` | Время жизни инвойса в секундах (300..43200, дефолт 3600) |
| `DEBUG_MODE` | На время тестов = `true` (ошибки шлются админу в личку) |

Параметры **referral_percent / min_topup_rub / stock_low_threshold / max_qty_per_order / debug_mode / уведомления / cryptobot_enabled / lolzteam_enabled / lolzteam_surcharge_percent** меняются прямо в админке (раздел «⚙️ Настройки») без рестарта.

### Подключение Lolzteam Market

1. На lolz.live → Account upgrades → API создать токен со scope `payments`.
2. На lzt.market → Settings → Payments → Merchants создать мерчанта (получишь `merchant_id`).
3. В `.env` прописать `LOLZTEAM_TOKEN` и `LOLZTEAM_MERCHANT_ID`, перезапустить контейнер.
4. В админке бота включить «Оплата через Lolzteam» и при необходимости задать наценку.

Если у тебя есть HTTPS-домен — пропиши его в `CRYPTOBOT_BASE_URL`, бот выставит callback `https://<домен>/lolzteam/webhook` для мгновенного зачисления; polling остаётся как страховка.

## Архитектура

- Python 3.12 + aiogram 3 (бот, long polling)
- FastAPI (для healthcheck и опционального webhook CryptoBot)
- SQLAlchemy 2 + aiosqlite + Alembic
- aiocryptopay (Crypto Pay API)
- APScheduler (ежедневные бэкапы)
- Один контейнер, один процесс. Volume `./data` хранит БД, бэкапы и логи.

См. также `PLAN.md` (если присутствует) для подробного описания дизайна.

## Заливка стока (для админа)

Каждому товару можно задать один из трёх режимов:

- **ZIP с файлами** — заливаешь архив, каждый файл внутри = 1 аккаунт. Для cookies-JSON — самый удобный режим, JSON может быть многострочным, сохраняется как есть. Превью первых 3 файлов перед сохранением.
- **По строкам** — `.txt`-файл (или текст в чат), каждая непустая строка = 1 аккаунт. Для login:pass валидируется формат `login:pass[:что-то]`.
- **Несколько документов** — отправляешь несколько документов одним сообщением (Telegram media group), каждый = 1 аккаунт.

Каждая заливка создаёт **партию (StockBatch)** — можно удалить непроданные позиции этой партии через раздел «📦 Сток».

## Безопасность

- Все секреты только в `.env` (в `.gitignore`).
- Cookies хранятся в БД в открытом виде; доступ ограничен правами файла volume.
- Логи пишутся без payload'ов, только id и суммы.

## Бэкапы

Ежедневный `sqlite3 .backup` в `data/backups/db-YYYY-MM-DD_HH-MM-SS.sqlite3`, ротация по `BACKUP_RETENTION_DAYS` (по умолчанию 14).

Ручной бэкап:

```bash
docker compose exec app bash scripts/backup.sh
```

Восстановление:

```bash
docker compose exec app bash scripts/restore.sh data/backups/db-2026-05-02_04-00-00.sqlite3
docker compose restart app
```

## Дисклеймер

Это легальный товар: продавец сам регистрирует аккаунты и сдаёт их в аренду через cookies/credentials. Использование по назначению лежит на пользователе.
