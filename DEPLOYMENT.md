# Развёртывание Dostavo

Production запускается через Docker Compose на VPS. Секретные файлы не входят в Git и создаются непосредственно на сервере.

## Сервисы

- `app-blue` и `app-green` — взаимозаменяемые экземпляры Reflex на внутреннем порту `8080`; в обычной работе активен один, второй запускается только на время выпуска;
- `mail-worker` — единственный постоянный IMAP-worker;
- `nginx` — reverse proxy, WebSocket, HTTPS и закрепление сессии за цветом backend;
- `certbot` — получение и обновление сертификата Let's Encrypt по запросу.

`config/` и `data/` монтируются с VPS, поэтому настройки, заказы, вложения, историю и OCR-фотографии не теряются при пересборке образа.

## Почему нужен blue–green

Административные и водительские сессии, а также состояние Reflex WebSocket хранятся в памяти процесса Python. Обычное пересоздание `app` разрывает их, а две одновременно работающие реплики не могут безопасно обслуживать одну сессию.

Nginx выдаёт и обновляет техническую cookie `dostavo_backend`; она не является авторизацией и хранит только цвет процесса. Все HTTP- и WebSocket-запросы посетителя продолжают идти в тот же backend. После переключения новый цвет выдаётся только новым посетителям, а cookie прежнего цвета получает единый абсолютный дедлайн через 12 часов после выпуска. Старый backend нельзя останавливать до истечения этого срока.

Не выполняйте выпуски чаще одного раза в 12 часов. Настоящее горизонтальное масштабирование потребует отдельного общего хранилища сессий и состояния Reflex.

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

Перед первым запуском подготовьте runtime-файл выбора цвета. Он намеренно находится в игнорируемой `.runtime/`, поэтому изменения цвета не загрязняют checkout на VPS:

```bash
mkdir -p .runtime
cp nginx.active-backend.conf.example .runtime/active-backend.conf
```

## Первый запуск HTTPS

Сначала запускается временная HTTP-конфигурация, чтобы certbot мог пройти ACME-проверку:

```bash
docker compose -f compose.yaml -f compose.bootstrap.yaml up -d --build app-blue mail-worker nginx
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
docker compose up -d --no-deps nginx
docker compose exec nginx nginx -t
```

## Первая миграция с прежнего `app`

На уже работающем сервере старый контейнер `app` должен оставаться запущенным. **Не используйте `docker compose down` и `docker compose up --remove-orphans`: они удалят его и завершат действующие сессии.**

После `git pull --ff-only origin main` выполните:

```bash
bash scripts/deploy-blue-green.sh --migrate-from-legacy
```

Команда один раз пересоздаёт Nginx с новой конфигурацией. Открытые WebSocket на этот короткий момент переподключатся, но попадут обратно в старый `app`, где остаются их серверные сессии. Затем она поднимет и проверит `app-blue`, переключит только новых посетителей на него и сохранит старый цвет `legacy` в `.runtime/previous-backend`.

Не останавливайте legacy-контейнер ранее чем через 12 часов после этого запуска. После дренирования проверьте его ID перед остановкой:

```bash
docker ps --filter label=com.docker.compose.service=app
docker stop CONTAINER_ID
```

## Обычное обновление приложения

Каждый последующий выпуск выполняйте только после окончания 12-часового дренирования предыдущего цвета:

```bash
git pull --ff-only origin main
bash scripts/deploy-blue-green.sh
```

Сценарий:

1. определяет активный и неактивный цвета;
2. пересобирает образ и запускает только неактивный `app-blue` или `app-green`;
3. ждёт успешный healthcheck и проверяет HTTP-ответ кандидата;
4. атомарно меняет `.runtime/active-backend.conf`, проверяет Nginx и выполняет graceful reload;
5. проверяет маршрут через Nginx и только затем пересоздаёт единственный `mail-worker`.

При ошибке сборки, healthcheck или проверки активный цвет не меняется. До остановки предыдущего backend откат выполняется повторным запуском сценария: он подготовит другой цвет и переключит новых посетителей обратно. Текущий активный цвет находится в `.runtime/active-backend.conf`, предыдущий и время переключения — в `.runtime/previous-backend`.

После 12 часов остановите именно предыдущий цвет из `.runtime/previous-backend`:

```bash
cat .runtime/previous-backend
# Если указан blue или green:
docker compose stop app-BACKEND
```

Не останавливайте `app-blue` или `app-green`, пока он указан как `default` в `.runtime/active-backend.conf`.

## Обновление сертификата

Периодически выполняйте на VPS:

```bash
docker compose --profile certbot run --rm certbot renew \
  --webroot --webroot-path /var/www/certbot

docker compose exec nginx nginx -s reload
```

Это можно перенести в системный timer VPS после первой успешной выдачи сертификата.

## Проверки после выпуска

```bash
curl -I https://dostavo.online/
curl -I https://dostavo.online/driver
curl -I https://dostavo.online/manifest.webmanifest
curl -I https://dostavo.online/service-worker.js
docker compose ps
docker compose logs --tail=200 mail-worker
```

Дополнительно проверьте в существующем браузерном профиле, что dashboard и `/driver` продолжают работать после переключения, а в новом приватном профиле вход направляется на новый цвет. В worker не включён автоматический цикл dashboard: постоянную проверку выполняет отдельный `mail-worker`, а ручная проверка из интерфейса остаётся доступной.
