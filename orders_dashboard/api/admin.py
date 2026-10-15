"""Administrative authentication and file downloads."""
from modules.auth import (
    AuthConfigurationError,
    verify_credentials,
)
from starlette.responses import (
    FileResponse,
    JSONResponse,
)
from modules.mail_watcher import (
    MailDownloadError,
    resolve_linked_invoice_for_download,
    resolve_order_for_download,
)
from modules.processed_files import (
    ProcessedFileError,
    consume_download_ticket,
)
from starlette.requests import Request
from orders_dashboard.api.common import (
    _dashboard_download_authorized,
    _excel_media_type,
    _json_payload,
)
from modules import dashboard_sessions


async def admin_login(request: Request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return JSONResponse(
            {"ok": False, "error": "Некорректный запрос"}, status_code=400
        )
    payload = await _json_payload(request)
    if payload is None:
        return JSONResponse({"ok": False, "error": "Некорректный запрос"}, status_code=400)
    try:
        authenticated = verify_credentials(
            str(payload.get("username", "")), str(payload.get("password", ""))
        )
    except AuthConfigurationError:
        return JSONResponse({"ok": False, "error": "Вход временно недоступен."}, status_code=503)
    if not authenticated:
        return JSONResponse({"ok": False, "error": "Неверное имя пользователя или пароль."}, status_code=401)

    previous = request.cookies.get(dashboard_sessions.SESSION_COOKIE)
    dashboard_sessions.destroy_session(previous)
    token = dashboard_sessions.create_session()
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        dashboard_sessions.SESSION_COOKIE,
        token,
        max_age=dashboard_sessions.SESSION_TTL_SECONDS,
        httponly=True,
        secure=(
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        ),
        samesite="strict",
        path="/",
    )
    return response

async def admin_logout(request: Request):
    if request.headers.get("x-dashboard-request") != "1":
        return JSONResponse({"ok": False, "error": "Недействительный запрос"}, status_code=403)
    dashboard_sessions.destroy_session(request.cookies.get(dashboard_sessions.SESSION_COOKIE))
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(dashboard_sessions.SESSION_COOKIE, path="/")
    return response

async def download_processed_file(request: Request):
    try:
        path = consume_download_ticket(request.path_params["ticket"])
    except ProcessedFileError:
        return JSONResponse({"ok": False, "error": "Файл недоступен"}, status_code=404)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Cache-Control": "no-store"},
    )

async def download_order_source_file(request: Request):
    if not _dashboard_download_authorized(request):
        return JSONResponse({"ok": False, "error": "Требуется вход"}, status_code=401)
    try:
        path = resolve_order_for_download(request.path_params["filename"])
    except MailDownloadError:
        return JSONResponse({"ok": False, "error": "Файл недоступен"}, status_code=404)
    return FileResponse(
        path,
        filename=path.name,
        media_type=_excel_media_type(path),
        headers={"Cache-Control": "no-store"},
    )

async def download_linked_invoice_file(request: Request):
    if not _dashboard_download_authorized(request):
        return JSONResponse({"ok": False, "error": "Требуется вход"}, status_code=401)
    try:
        path = resolve_linked_invoice_for_download(
            request.path_params["order_file"],
            request.path_params["filename"],
        )
    except MailDownloadError:
        return JSONResponse({"ok": False, "error": "Файл недоступен"}, status_code=404)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )
