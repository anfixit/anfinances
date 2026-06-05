#!/bin/sh
# Bootstrap Let's Encrypt сертификата для nginx.
#
# Запусти ОДИН раз после того, как домен указывает на сервер (A-запись)
# и фронтенд собран (frontend/dist):
#
#   DOMAIN=anfinances.example.com EMAIL=you@example.com ./scripts/init-letsencrypt.sh
#
# Для проверки без расхода лимитов LE — STAGING=1.
set -eu

DOMAIN="${DOMAIN:-your-domain.tld}"
EMAIL="${EMAIL:-you@example.com}"
STAGING="${STAGING:-0}"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
LIVE="/etc/letsencrypt/live/$DOMAIN"

if [ "$DOMAIN" = "your-domain.tld" ]; then
  echo "Укажи DOMAIN и EMAIL: DOMAIN=... EMAIL=... $0" >&2
  exit 1
fi

echo "### Временный self-signed сертификат для $DOMAIN ..."
$COMPOSE run --rm --entrypoint "\
  sh -c 'mkdir -p $LIVE && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout $LIVE/privkey.pem -out $LIVE/fullchain.pem -subj /CN=localhost'" \
  certbot

echo "### Старт nginx ..."
$COMPOSE up -d nginx

echo "### Удаляю временный сертификат ..."
$COMPOSE run --rm --entrypoint "\
  rm -rf /etc/letsencrypt/live/$DOMAIN \
         /etc/letsencrypt/archive/$DOMAIN \
         /etc/letsencrypt/renewal/$DOMAIN.conf" \
  certbot

echo "### Запрашиваю боевой сертификат Let's Encrypt ..."
STAGING_ARG=""
[ "$STAGING" != "0" ] && STAGING_ARG="--staging"
# shellcheck disable=SC2086
$COMPOSE run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot $STAGING_ARG \
    -d $DOMAIN --email $EMAIL --rsa-key-size 4096 \
    --agree-tos --no-eff-email --force-renewal" \
  certbot

echo "### Перезагружаю nginx ..."
$COMPOSE exec nginx nginx -s reload

echo "### Готово. Открой https://$DOMAIN"
