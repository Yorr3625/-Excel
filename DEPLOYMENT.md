# Развёртывание Dostavo

Production запускается через Docker Compose на VPS. Секретные файлы не входят в Git и должны быть созданы непосредственно на сервере.

## Сервисы

- `app` — Reflex в single-port режиме на внутреннем порту `8080`;
- `mail-worker` — постоянная проверка IMAP независимо от открытого dashboard;
- `nginx` — reverse proxy, WebSocket и HTTPS;
- `certbot` — получение и обновление сертификата Let's Encrypt по запросу.

`config/` и `data/` монтируются с VPS, поэтому настройки, заказы, вложения, историю и OCR-фотографии не теряются при пересборке образа.

## Подготовка конфигурации

На сервере из корня проекта:

```bash
cp config/mail.example.json config/mail.json
chmod 600 config/mail.json
nano config/mail.json
```

В `config/mail.json` заполните IMAP-сервер, адрес, app password, `sources` и оставьте `enabled: true`. App password вводится только в терминале VPS, не в Git и не в чат.

`config/ai.json` создаётся приложением через раздел настроек. Для Yandex Vision в нём должны быть:

- `yandex_vision_api_key`;
- `yandex_vision_folder_id`.

Эти значения также не должны попадать в Git или Docker image.

## Первый запуск HTTPS

Сначала запускается временная HTTP-конфигурация, чтобы certbot мог пройти ACME-проверку:

```bash
docker compose -f compose.yaml -f compose.bootstrap.yaml up -d --build app mail-worker nginx
```

Получите сертификат, указав реальный email администратора:

```bash
docker compose --profile certbot run --rm certbot certonly \
  --webroot --webroot-path /var/www/certbot \
  --email YOUR_EMAIL \
  --agree-tos --no-eff-email \
  -d dostavo.online
```

После успешного получения сертификата переключите nginx на HTTPS-конфигурацию:

```bash
docker compose -f compose.yaml up -d nginx
```

Проверка конфигурации nginx выполняется перед переключением:

```bash
docker compose exec nginx nginx -t
```

## Обновление сертификата

Периодически выполняйте на VPS:

```bash
docker compose --profile certbot run --rm certbot renew \
  --webroot --webroot-path /var/www/certbot

docker compose exec nginx nginx -s reload
```

Это можно перенести в системный timer VPS после первой успешной выдачи сертификата.

## Обновление приложения

```bash
git pull --ff-only origin main
docker compose build app mail-worker
docker compose up -d app mail-worker nginx
```

Перед обновлением не удаляйте `config/` и `data/`. При ошибке запуска сначала смотрите полный вывод:

```bash
docker compose logs --tail=200 app mail-worker nginx
```

## Проверки после запуска

```bash
curl -I https://dostavo.online/
curl -I https://dostavo.online/driver
curl -I https://dostavo.online/manifest.webmanifest
curl -I https://dostavo.online/service-worker.js
docker compose ps
docker compose logs --tail=200 mail-worker
```

В worker не включён автоматический цикл dashboard: постоянную проверку выполняет отдельный `mail-worker`, а ручная проверка из интерфейса остаётся доступной.
