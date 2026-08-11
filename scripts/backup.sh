#!/usr/bin/env bash
#
# Бэкап anfinances: дамп базы → проверка восстановлением → шифрование
# → отправка в телеграм.
#
# Проверка восстановлением здесь не для галочки. Бэкап, который ни
# разу не разворачивали, — это не бэкап, а надежда: битый дамп
# выглядит как обычный файл и обнаруживается ровно в тот день, когда
# он нужен. Поэтому каждый дамп разворачивается в отдельную базу и
# сверяется по числу операций с живой. Не сошлось — файл не уходит,
# а в чат падает тревога.
#
# Запускается systemd-таймером, конфигурация в /opt/anfinances/backup.env.

set -euo pipefail

readonly ROOT="${BACKUP_ROOT:-/opt/anfinances}"
readonly STORE="${ROOT}/backups"
readonly KEEP_DAYS=7
readonly PG=anfinances-postgres
readonly SCRATCH=anfinances_restore_check

stamp="$(date +%Y-%m-%d_%H%M)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# shellcheck source=/dev/null
source "${ROOT}/backup.env"

: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE не задан в backup.env}"
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN не задан в backup.env}"
: "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID не задан в backup.env}"

readonly PG_USER="${POSTGRES_USER:-anfinances}"
readonly PG_DB="${POSTGRES_DB:-anfinances}"

notify() {
    curl -sS --max-time 30 \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$1" >/dev/null || true
}

fail() {
    notify "🔴 Бэкап anfinances не сделан: $1"$'\n\n'"Сервер: $(hostname)"
    exit 1
}
trap 'fail "строка $LINENO"' ERR

psql_live() {
    docker exec "$PG" psql -U "$PG_USER" -d "$PG_DB" -tAc "$1"
}

# --- 1. Дамп -----------------------------------------------------

dump="${work}/anfinances_${stamp}.dump"
docker exec "$PG" pg_dump -U "$PG_USER" -d "$PG_DB" -Fc > "$dump"
[ -s "$dump" ] || fail "дамп пустой"

# --- 2. Проверка восстановлением ---------------------------------

live_rows="$(psql_live 'SELECT count(*) FROM transactions')"

docker exec "$PG" psql -U "$PG_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS ${SCRATCH}" >/dev/null
docker exec "$PG" psql -U "$PG_USER" -d postgres \
    -c "CREATE DATABASE ${SCRATCH}" >/dev/null

# pg_restore пишет предупреждения про владельца ролей — они безвредны,
# поэтому смотрим не на его код возврата, а на то, что получилось.
docker exec -i "$PG" pg_restore -U "$PG_USER" -d "$SCRATCH" --no-owner \
    < "$dump" >/dev/null 2>&1 || true

restored_rows="$(docker exec "$PG" psql -U "$PG_USER" -d "$SCRATCH" \
    -tAc 'SELECT count(*) FROM transactions' 2>/dev/null || echo 0)"

docker exec "$PG" psql -U "$PG_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS ${SCRATCH}" >/dev/null

if [ "$restored_rows" != "$live_rows" ]; then
    fail "дамп не разворачивается: операций в базе ${live_rows}, восстановилось ${restored_rows}"
fi

# --- 3. Шифрование -----------------------------------------------

archive="${work}/anfinances_${stamp}.dump.gpg"
printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --quiet --yes \
    --symmetric --cipher-algo AES256 \
    --passphrase-fd 0 --pinentry-mode loopback \
    --output "$archive" "$dump"
[ -s "$archive" ] || fail "шифрование не дало файла"

# --- 4. Отправка -------------------------------------------------

size="$(du -h "$archive" | cut -f1)"
caption="🗄 Бэкап anfinances от ${stamp}
Операций: ${live_rows} · размер: ${size}
Дамп проверен восстановлением.
Расшифровать: gpg --output db.dump --decrypt файл.gpg"

http_code="$(curl -sS --max-time 300 -o /dev/null -w '%{http_code}' \
    -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
    -F "chat_id=${TELEGRAM_CHAT_ID}" \
    -F "document=@${archive}" \
    -F "caption=${caption}")"

[ "$http_code" = "200" ] || fail "телеграм ответил ${http_code}"

# --- 5. Локальная копия и ротация --------------------------------

mkdir -p "$STORE"
cp "$archive" "$STORE/"
find "$STORE" -name 'anfinances_*.dump.gpg' -mtime "+${KEEP_DAYS}" -delete

echo "Бэкап ${stamp} отправлен: ${live_rows} операций, ${size}"
