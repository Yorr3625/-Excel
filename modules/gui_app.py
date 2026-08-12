import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from modules.config import (
    load_settings,
    load_stores,
    save_settings,
    save_stores,
    build_groups,
)
from modules.styles import (
    green_fill,
    yellow_fill,
    blue_fill,
    purple_fill,
    conflict_fill,
)
from modules.history import record_processing
from modules.file_selector import ORDERS_FOLDER
from modules.output_writer import PROCESSED_FOLDER
from modules.logger import LOGS_FOLDER
from modules.pipeline import process_order
from modules.reporter import format_summary


# понятные подписи для известных ключей settings.json
SETTINGS_LABELS = {
    "open_file_after_processing": "Открывать файл после обработки",
    "open_folder_after_processing": "Открывать папку после обработки",
    "create_logs": "Вести лог обработки",
    "save_backup": "Сохранять резервную копию",
    "show_errors": "Показывать ошибки",
}

ROUTE_KEYS = ["route_1", "route_2", "route_3", "route_4"]


def open_in_explorer(path):
    """Открывает файл или папку в проводнике (Windows)."""

    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

    os.startfile(path)


class App:

    def __init__(self, root):

        self.root = root
        self.root.title("Обработка заказов")
        self.root.geometry("1300x900")

        self.result_queue = queue.Queue()
        self.selected_file = tk.StringVar()

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.process_tab = ttk.Frame(notebook)
        self.settings_tab = ttk.Frame(notebook)
        self.routes_tab = ttk.Frame(notebook)

        notebook.add(self.process_tab, text="Обработка")
        notebook.add(self.settings_tab, text="Настройки")
        notebook.add(self.routes_tab, text="Маршруты")

        self._build_process_tab()
        self._build_settings_tab()
        self._build_routes_tab()

        self.refresh_recent_files()

    # ==========================================================
    # ВКЛАДКА "ОБРАБОТКА"
    # ==========================================================

    def _build_process_tab(self):

        top = ttk.Frame(self.process_tab)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Файл заказа:").pack(side="left")

        entry = ttk.Entry(top, textvariable=self.selected_file, state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=8)

        ttk.Button(
            top,
            text="Обзор...",
            command=self.choose_file,
        ).pack(side="left")

        action_bar = ttk.Frame(self.process_tab)
        action_bar.pack(fill="x", padx=10)

        self.process_button = ttk.Button(
            action_bar,
            text="Обработать",
            command=self.start_processing,
        )
        self.process_button.pack(side="left")

        self.progress = ttk.Progressbar(action_bar, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        ttk.Button(
            action_bar,
            text="Открыть папку orders",
            command=lambda: open_in_explorer(ORDERS_FOLDER),
        ).pack(side="left", padx=4)

        ttk.Button(
            action_bar,
            text="Открыть папку logs",
            command=lambda: open_in_explorer(LOGS_FOLDER),
        ).pack(side="left", padx=4)

        body = ttk.Frame(self.process_tab)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- лог / сводка обработки ----
        log_frame = ttk.LabelFrame(body, text="Результат обработки")
        log_frame.pack(side="left", fill="both", expand=True)

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # ---- список последних обработанных файлов ----
        recent_frame = ttk.LabelFrame(body, text="Последние обработанные файлы")
        recent_frame.pack(side="left", fill="y", padx=(10, 0))

        self.recent_list = tk.Listbox(recent_frame, width=45)
        self.recent_list.pack(fill="both", expand=True, padx=4, pady=4)

        recent_buttons = ttk.Frame(recent_frame)
        recent_buttons.pack(fill="x", padx=4, pady=(0, 4))

        ttk.Button(
            recent_buttons,
            text="Обновить",
            command=self.refresh_recent_files,
        ).pack(side="left")

        ttk.Button(
            recent_buttons,
            text="Открыть файл",
            command=self.open_selected_recent,
        ).pack(side="left", padx=4)

        ttk.Button(
            recent_buttons,
            text="Открыть папку",
            command=lambda: open_in_explorer(PROCESSED_FOLDER),
        ).pack(side="left")

    def choose_file(self):

        os.makedirs(ORDERS_FOLDER, exist_ok=True)

        path = filedialog.askopenfilename(
            title="Выберите файл заказа",
            initialdir=ORDERS_FOLDER,
            filetypes=[("Excel файлы", "*.xlsx *.xlsm")],
        )

        if path:
            self.selected_file.set(path)

    def start_processing(self):

        input_file = self.selected_file.get()

        if not input_file:
            messagebox.showwarning(
                "Файл не выбран",
                "Сначала выберите файл заказа.",
            )
            return

        self.process_button.configure(state="disabled")
        self.progress.start(12)
        self._set_log_text("Обработка...")

        thread = threading.Thread(
            target=self._run_processing,
            args=(input_file,),
            daemon=True,
        )
        thread.start()

        self.root.after(100, self._poll_result)

    def _run_processing(self, input_file):

        try:
            settings = load_settings()
            stores = load_stores()
            fills = [green_fill, yellow_fill, blue_fill, purple_fill]
            groups = build_groups(stores, fills)

            output_file, log_file, stats = process_order(
                input_file,
                settings,
                groups,
                conflict_fill,
            )

            record_processing(os.path.basename(input_file), stats)

            summary = format_summary(output_file, stats, log_file)
            self.result_queue.put(("ok", summary))

        except Exception as error:
            self.result_queue.put(("error", str(error)))

    def _poll_result(self):

        try:
            status, message = self.result_queue.get_nowait()

        except queue.Empty:
            self.root.after(100, self._poll_result)
            return

        self.progress.stop()
        self.process_button.configure(state="normal")

        if status == "ok":
            self._set_log_text(message)
            self.refresh_recent_files()

        else:
            self._set_log_text(f"ОШИБКА:\n{message}")
            messagebox.showerror("Ошибка обработки", message)

    def _set_log_text(self, text):

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", text)
        self.log_text.configure(state="disabled")

    def refresh_recent_files(self):

        self.recent_list.delete(0, "end")

        if not os.path.exists(PROCESSED_FOLDER):
            return

        found = []

        for root_dir, _, files in os.walk(PROCESSED_FOLDER):

            for name in files:

                # ~$... — временные файлы блокировки, которые Excel создаёт
                # рядом с открытым документом. Расширение у них тоже .xlsx,
                # поэтому без явной проверки они попадали в список как
                # мусорные строки, которые невозможно открыть.
                if name.startswith("~$"):
                    continue

                if name.endswith((".xlsx", ".xlsm")):

                    full_path = os.path.join(root_dir, name)
                    found.append(full_path)

        found.sort(key=os.path.getmtime, reverse=True)

        self._recent_paths = found

        for path in found:
            self.recent_list.insert("end", os.path.relpath(path, PROCESSED_FOLDER))

    def open_selected_recent(self):

        selection = self.recent_list.curselection()

        if not selection:
            messagebox.showinfo("Ничего не выбрано", "Выберите файл в списке.")
            return

        path = self._recent_paths[selection[0]]
        os.startfile(path)

    # ==========================================================
    # ВКЛАДКА "НАСТРОЙКИ"
    # ==========================================================

    def _build_settings_tab(self):

        container = ttk.Frame(self.settings_tab)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        self.settings_vars = {}
        self.settings_data = load_settings()

        for key, value in self.settings_data.items():

            label = SETTINGS_LABELS.get(key, key)

            if isinstance(value, bool):

                var = tk.BooleanVar(value=value)

                ttk.Checkbutton(
                    container,
                    text=label,
                    variable=var,
                ).pack(anchor="w", pady=4)

                self.settings_vars[key] = ("bool", var)

            else:

                row = ttk.Frame(container)
                row.pack(fill="x", pady=4)

                ttk.Label(row, text=label + ":").pack(side="left")

                var = tk.StringVar(value=str(value))
                ttk.Entry(row, textvariable=var).pack(
                    side="left", fill="x", expand=True, padx=8
                )

                self.settings_vars[key] = ("text", var)

        button_bar = ttk.Frame(container)
        button_bar.pack(fill="x", pady=20)

        ttk.Button(
            button_bar,
            text="Сохранить настройки",
            command=self.save_settings_tab,
        ).pack(side="left")

        ttk.Button(
            button_bar,
            text="Отменить изменения",
            command=self.reload_settings_tab,
        ).pack(side="left", padx=8)

    def save_settings_tab(self):

        data = {}

        for key, (kind, var) in self.settings_vars.items():

            if kind == "bool":
                data[key] = bool(var.get())

            else:
                data[key] = _parse_value(var.get())

        save_settings(data)
        self.settings_data = data

        messagebox.showinfo("Готово", "Настройки сохранены.")

    def reload_settings_tab(self):

        for widget in self.settings_tab.winfo_children():
            widget.destroy()

        self._build_settings_tab()

    # ==========================================================
    # ВКЛАДКА "МАРШРУТЫ"
    # ==========================================================

    def _build_routes_tab(self):

        self.stores_data = load_stores()

        inner_notebook = ttk.Notebook(self.routes_tab)
        inner_notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.route_listboxes = {}

        for index, key in enumerate(ROUTE_KEYS, start=1):

            tab = ttk.Frame(inner_notebook)
            inner_notebook.add(tab, text=f"Маршрут №{index}")

            listbox = tk.Listbox(tab, selectmode="extended")
            listbox.pack(fill="both", expand=True, padx=8, pady=8)

            for name in self.stores_data.get(key, []):
                listbox.insert("end", name)

            self.route_listboxes[key] = listbox

            controls = ttk.Frame(tab)
            controls.pack(fill="x", padx=8, pady=(0, 8))

            new_value = tk.StringVar()
            entry = ttk.Entry(controls, textvariable=new_value)
            entry.pack(side="left", fill="x", expand=True)

            ttk.Button(
                controls,
                text="Добавить",
                command=lambda lb=listbox, v=new_value: self._add_store(lb, v),
            ).pack(side="left", padx=4)

            ttk.Button(
                controls,
                text="Удалить выбранное",
                command=lambda lb=listbox: self._remove_selected_stores(lb),
            ).pack(side="left")

        button_bar = ttk.Frame(self.routes_tab)
        button_bar.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Button(
            button_bar,
            text="Сохранить маршруты",
            command=self.save_routes_tab,
        ).pack(side="left")

        ttk.Button(
            button_bar,
            text="Отменить изменения",
            command=self.reload_routes_tab,
        ).pack(side="left", padx=8)

    def _add_store(self, listbox, value_var):

        value = value_var.get().strip()

        if value:
            listbox.insert("end", value)
            value_var.set("")

    def _remove_selected_stores(self, listbox):

        for index in reversed(listbox.curselection()):
            listbox.delete(index)

    def save_routes_tab(self):

        data = {}

        for key, listbox in self.route_listboxes.items():
            data[key] = list(listbox.get(0, "end"))

        save_stores(data)
        self.stores_data = data

        messagebox.showinfo("Готово", "Маршруты сохранены.")

    def reload_routes_tab(self):

        for widget in self.routes_tab.winfo_children():
            widget.destroy()

        self._build_routes_tab()


def _parse_value(text):
    """Пытается привести текстовое значение настройки к числу, иначе оставляет строкой."""

    for caster in (int, float):

        try:
            return caster(text)

        except ValueError:
            continue

    return text


def run_app():

    root = tk.Tk()
    _apply_dpi_scaling(root)
    App(root)
    root.mainloop()


def _apply_dpi_scaling(root):
    """Подгоняет масштаб tkinter под реальный DPI экрана (актуально для Windows)."""

    try:
        dpi = root.winfo_fpixels("1i")  # физических пикселей на дюйм
        root.tk.call("tk", "scaling", dpi / 72.0)

    except Exception:
        pass
