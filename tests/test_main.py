import main as console_app


def test_console_cancellation_after_preview_does_not_process(monkeypatch):
    calls = []

    monkeypatch.setattr(console_app, "load_settings", lambda: {})
    monkeypatch.setattr(console_app, "select_order_file", lambda: "заказ.xlsx")
    monkeypatch.setattr(console_app, "load_processed_files", lambda: {})
    monkeypatch.setattr(console_app.paths, "stores_file_for", lambda mode: "stores.json")
    monkeypatch.setattr(console_app, "load_stores", lambda path: {})
    monkeypatch.setattr(console_app, "build_groups", lambda stores, fills: [])
    monkeypatch.setattr(
        console_app,
        "build_order_preview",
        lambda *args: calls.append("preview") or {"warnings": []},
    )
    monkeypatch.setattr(console_app, "format_preview", lambda preview: "просмотр")
    monkeypatch.setattr(
        console_app,
        "process_order",
        lambda *args: calls.append("process"),
    )
    monkeypatch.setattr(
        console_app,
        "record_processing",
        lambda *args: calls.append("history"),
    )
    answers = iter(["2", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    console_app.main()

    assert calls == ["preview"]
