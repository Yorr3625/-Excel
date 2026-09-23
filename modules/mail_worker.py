"""Постоянный процесс проверки почты для серверного развёртывания."""

from __future__ import annotations

import logging
import signal
from threading import Event

from modules.mail_watcher import (
    append_mail_error,
    check_mail_with_retry,
    is_configured,
    load_mail_config,
)


LOGGER = logging.getLogger("dostavo.mail_worker")
DEFAULT_INTERVAL_MINUTES = 10
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 24 * 60
_STOP = Event()


def _interval_minutes(config: dict) -> int:
    try:
        interval = int(config.get("check_interval_minutes", DEFAULT_INTERVAL_MINUTES))
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL_MINUTES
    return min(max(interval, MIN_INTERVAL_MINUTES), MAX_INTERVAL_MINUTES)


def _request_stop(_signum, _frame) -> None:
    _STOP.set()


def run(stop_event: Event | None = None) -> int:
    """Проверяет почту по расписанию до получения сигнала остановки."""

    stop_event = stop_event or _STOP
    LOGGER.info("Почтовый worker запущен")

    while not stop_event.is_set():
        config = load_mail_config()
        interval = _interval_minutes(config)

        if is_configured(config):
            try:
                result = check_mail_with_retry(config)
            except Exception as error:
                try:
                    entry = append_mail_error("Фоновая проверка почты", error, config)
                    LOGGER.error("Проверка почты завершилась ошибкой: %s", entry["error"])
                except Exception:
                    LOGGER.error("Проверка почты завершилась неожиданной ошибкой")
            else:
                if result.get("ok"):
                    LOGGER.info(
                        "Проверка почты завершена, новых элементов: %d",
                        len(result.get("items") or []),
                    )
                else:
                    LOGGER.error(
                        "Проверка почты не выполнена: %s",
                        result.get("error") or "неизвестная ошибка",
                    )
        else:
            LOGGER.info("Почтовый worker ожидает заполнения config/mail.json")

        stop_event.wait(interval * 60)

    LOGGER.info("Почтовый worker остановлен")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
