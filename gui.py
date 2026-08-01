import sys

from modules.gui_app import run_app


def _enable_dpi_awareness():
    """На Windows отключает системное масштабирование картинки tkinter,
    чтобы интерфейс не выглядел размытым при масштабе экрана 125%/150%/200%."""

    if sys.platform != "win32":
        return

    try:
        import ctypes
        # Per-Monitor v2 DPI awareness (Windows 10+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)

    except Exception:

        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()

        except Exception:
            pass


if __name__ == "__main__":
    _enable_dpi_awareness()
    run_app()
