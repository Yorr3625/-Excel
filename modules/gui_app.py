import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from modules.backup import (
    BackupError,
    create_backup,
    list_backups,
    load_backup_directory,
    restore_backup,
    save_backup_directory,
)
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
from modules.history import load_processed_files, record_processing, was_processed
from modules.excel_io import excel_glob_pattern, is_excel_file
from modules.file_selector import ORDERS_FOLDER
from modules.output_writer import PROCESSED_FOLDER
from modules.logger import LOGS_FOLDER
from modules.order_preview import PreviewError, build_order_preview
from modules.pipeline import process_order
from modules.reporter import format_preview, format_summary
from modules.weight_log import (
    add_weight_row,
    delete_weight_row,
    last_avg_weight_for,
    load_weight_rows,
    update_weight_row,
)


# понятные подписи для известных ключей settings.json
SETTINGS_LABELS = {
    "open_file_after_processing": "Открывать файл после обработки",
    "open_folder_after_processing": "Открывать папку после обработки",
    "create_logs": "Вести лог обработки",
    "save_backup": "Сохранять резервную копию",
    "show_errors": "Показывать ошибки",
}

ROUTE_KEYS = ["route_1", "route_2", "route_3", "route_4"]

WEIGHT_NO_BINDING = "— не привязано —"
WEIGHT_ROUTES = ["Маршрут №1", "Маршрут №2", "Маршрут №3", "Маршрут №4"]
WEIGHT_ROUTE_OPTIONS = [WEIGHT_NO_BINDING] + WEIGHT_ROUTES
WEIGHT_FILTER_ALL = "Все"
WEIGHT_FILTER_UNBOUND = "Без привязки"
WEIGHT_ROUTE_FILTER_OPTIONS = [WEIGHT_FILTER_ALL, WEIGHT_FILTER_UNBOUND] + WEIGHT_ROUTES


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
        self.weight_tab = ttk.Frame(notebook)
        self.backups_tab = ttk.Frame(notebook)

        notebook.add(self.process_tab, text="Обработка")
        notebook.add(self.settings_tab, text="Настройки")
        notebook.add(self.routes_tab, text="Маршруты")
        notebook.add(self.weight_tab, text="Вес")
        notebook.add(self.backups_tab, text="Резервные копии")

        self._build_process_tab()
        self._build_settings_tab()
        self._build_routes_tab()
        self._build_weight_tab()
        self._build_backups_tab()

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
            filetypes=[("Excel файлы", excel_glob_pattern())],
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
        self._set_log_text("Проверка файла перед обработкой...")

        thread = threading.Thread(
            target=self._run_preview,
            args=(input_file,),
            daemon=True,
        )
        thread.start()

        self.root.after(100, self._poll_result)

    def _build_groups(self):
        settings = load_settings()
        stores = load_stores()
        fills = [green_fill, yellow_fill, blue_fill, purple_fill]
        return settings, build_groups(stores, fills)

    def _run_preview(self, input_file):

        try:
            settings, groups = self._build_groups()
            preview = build_order_preview(input_file, groups, conflict_fill)
            processed_at = was_processed(os.path.basename(input_file))

            if processed_at:
                preview["warnings"].append(
                    "Файл уже обрабатывался "
                    f"{processed_at}. Повторная обработка обновит статистику."
                )

            self.result_queue.put(("preview", (input_file, settings, groups, preview)))

        except PreviewError as error:
            self.result_queue.put(("error", str(error)))
        except Exception as error:
            self.result_queue.put(("error", str(error)))

    def _run_processing(self, input_file, settings=None, groups=None):

        try:
            if settings is None or groups is None:
                settings, groups = self._build_groups()

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

        if status == "preview":
            input_file, settings, groups, preview = message

            if input_file != self.selected_file.get():
                self._set_log_text(
                    "Выбран другой файл. Постройте предварительный просмотр заново."
                )
                return

            self._set_log_text(format_preview(preview))

            if messagebox.askyesno(
                "Подтверждение обработки",
                "Предварительный просмотр готов. Продолжить обработку?",
            ):
                self.process_button.configure(state="disabled")
                self.progress.start(12)
                self._set_log_text("Обработка...")
                thread = threading.Thread(
                    target=self._run_processing,
                    args=(input_file, settings, groups),
                    daemon=True,
                )
                thread.start()
                self.root.after(100, self._poll_result)
            return

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

                if is_excel_file(name):

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

    # ==========================================================
    # ВКЛАДКА "РЕЗЕРВНЫЕ КОПИИ"
    # ==========================================================

    def _build_backups_tab(self):
        container = ttk.Frame(self.backups_tab)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(
            container,
            text=(
                "Сохраняются статистика, история почты, списки маршрутов и настройки. "
                "Рабочие книги, PDF и логи не копируются."
            ),
            wraplength=900,
        ).pack(anchor="w", pady=(0, 10))

        folder_row = ttk.Frame(container)
        folder_row.pack(fill="x", pady=(0, 12))
        ttk.Label(folder_row, text="Папка:").pack(side="left")
        self.backup_directory_var = tk.StringVar(value=str(load_backup_directory()))
        ttk.Entry(folder_row, textvariable=self.backup_directory_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(folder_row, text="Выбрать...", command=self.choose_backup_directory).pack(side="left")
        ttk.Button(
            folder_row,
            text="Сохранить папку",
            command=self.save_backup_directory_tab,
        ).pack(side="left", padx=(6, 0))

        action_row = ttk.Frame(container)
        action_row.pack(fill="x", pady=(0, 8))
        ttk.Button(action_row, text="Создать копию", command=self.create_backup_tab).pack(side="left")
        ttk.Button(
            action_row,
            text="Обновить список",
            command=self.refresh_backup_list,
        ).pack(side="left", padx=8)
        ttk.Button(
            action_row,
            text="Восстановить выбранную",
            command=self.restore_selected_backup,
        ).pack(side="left")

        self.backup_list = tk.Listbox(container, height=14)
        self.backup_list.pack(fill="both", expand=True)
        self.backup_list.bind("<Double-Button-1>", lambda _event: self.restore_selected_backup())
        self.backup_status_var = tk.StringVar()
        ttk.Label(container, textvariable=self.backup_status_var).pack(anchor="w", pady=(8, 0))
        self.refresh_backup_list()

    def choose_backup_directory(self):
        selected = filedialog.askdirectory(
            title="Выберите папку для резервных копий",
            initialdir=self.backup_directory_var.get() or os.getcwd(),
        )
        if selected:
            self.backup_directory_var.set(selected)

    def save_backup_directory_tab(self):
        try:
            directory = save_backup_directory(self.backup_directory_var.get())
            self.backup_directory_var.set(str(directory))
            self.refresh_backup_list()
            self.backup_status_var.set("Папка резервных копий сохранена.")
        except BackupError as error:
            messagebox.showerror("Резервные копии", str(error))

    def refresh_backup_list(self):
        if not hasattr(self, "backup_list"):
            return
        try:
            items = list_backups(self.backup_directory_var.get())
        except BackupError as error:
            self.backup_status_var.set(str(error))
            return

        self._backup_items = items
        self.backup_list.delete(0, "end")
        for item in items:
            if item.valid:
                warning = " · содержит mail.json" if item.contains_secrets else ""
                label = f"{item.name} · {item.file_count} файлов · {item.size_bytes} байт{warning}"
            else:
                label = f"{item.name} · ПОВРЕЖДЕНА: {item.error}"
            self.backup_list.insert("end", label)

    def create_backup_tab(self):
        try:
            info = create_backup(self.backup_directory_var.get(), reason="вручную")
            self.refresh_backup_list()
            self.backup_status_var.set(f"Копия создана: {info.name}")
        except BackupError as error:
            messagebox.showerror("Резервные копии", str(error))

    def restore_selected_backup(self):
        selection = self.backup_list.curselection()
        if not selection:
            messagebox.showinfo("Резервные копии", "Выберите корректную копию.")
            return

        item = self._backup_items[selection[0]]
        if not item.valid:
            messagebox.showerror("Резервные копии", "Выбранная копия повреждена.")
            return

        if not messagebox.askyesno(
            "Подтвердите восстановление",
            (
                "Текущие статистика, история почты, списки маршрутов и настройки "
                "будут заменены. Перед этим создастся страховочная копия. Продолжить?"
            ),
        ):
            return

        try:
            result = restore_backup(item.path)
            safety = f" Страховочная копия: {result.safety_backup.name}." if result.safety_backup else ""
            self.refresh_backup_list()
            self.reload_settings_tab()
            self.reload_routes_tab()
            self.backup_status_var.set(f"Состояние восстановлено.{safety}")
        except BackupError as error:
            messagebox.showerror("Резервные копии", str(error))

    # ==========================================================
    # ВКЛАДКА "ВЕС"
    # ==========================================================

    def _build_weight_tab(self):
        container = ttk.Frame(self.weight_tab)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(
            container,
            text=(
                "Наименование, ящики и средний вес — а для взвешенных позиций впишите "
                "точный вес. При желании привяжите запись к заказу и маршруту."
            ),
            wraplength=1200,
        ).pack(anchor="w", pady=(0, 10))

        form = ttk.LabelFrame(container, text="Новая запись")
        form.pack(fill="x", pady=(0, 12))

        row1 = ttk.Frame(form)
        row1.pack(fill="x", padx=10, pady=(10, 4))

        self.weight_name_var = tk.StringVar()
        self.weight_box_var = tk.StringVar()
        self.weight_avg_var = tk.StringVar()
        self.weight_exact_var = tk.StringVar()

        ttk.Label(row1, text="Наименование:").pack(side="left")
        name_entry = ttk.Entry(row1, textvariable=self.weight_name_var, width=26)
        name_entry.pack(side="left", padx=(4, 14))
        name_entry.bind("<FocusOut>", self._suggest_weight_from_name)

        ttk.Label(row1, text="Кол-во ящиков:").pack(side="left")
        ttk.Entry(row1, textvariable=self.weight_box_var, width=8).pack(side="left", padx=(4, 14))

        ttk.Label(row1, text="Средний вес, кг:").pack(side="left")
        ttk.Entry(row1, textvariable=self.weight_avg_var, width=8).pack(side="left", padx=(4, 14))

        ttk.Label(row1, text="Точный вес, кг:").pack(side="left")
        ttk.Entry(row1, textvariable=self.weight_exact_var, width=8).pack(side="left")

        row2 = ttk.Frame(form)
        row2.pack(fill="x", padx=10, pady=4)

        self.weight_order_var = tk.StringVar(value=WEIGHT_NO_BINDING)
        self.weight_route_var = tk.StringVar(value=WEIGHT_NO_BINDING)

        ttk.Label(row2, text="Заказ:").pack(side="left")
        self.weight_order_combo = ttk.Combobox(
            row2,
            textvariable=self.weight_order_var,
            state="readonly",
            width=32,
            values=[WEIGHT_NO_BINDING],
        )
        self.weight_order_combo.pack(side="left", padx=(4, 14))

        ttk.Label(row2, text="Маршрут:").pack(side="left")
        ttk.Combobox(
            row2,
            textvariable=self.weight_route_var,
            state="readonly",
            width=16,
            values=WEIGHT_ROUTE_OPTIONS,
        ).pack(side="left")

        row3 = ttk.Frame(form)
        row3.pack(fill="x", padx=10, pady=(4, 10))

        self.weight_submit_button = ttk.Button(row3, text="Добавить", command=self.submit_weight_row)
        self.weight_submit_button.pack(side="left")

        # появляется только во время редактирования строки (см. edit_selected_weight_row)
        self.weight_cancel_button = ttk.Button(row3, text="Отмена", command=self.cancel_weight_edit)

        self.weight_status_var = tk.StringVar()
        ttk.Label(row3, textvariable=self.weight_status_var, foreground="#b00020").pack(side="left", padx=12)

        filter_frame = ttk.Frame(container)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="Фильтр по заказу:").pack(side="left")
        self.weight_filter_order_var = tk.StringVar(value=WEIGHT_FILTER_ALL)
        self.weight_filter_order_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.weight_filter_order_var,
            state="readonly",
            width=32,
            values=[WEIGHT_FILTER_ALL, WEIGHT_FILTER_UNBOUND],
        )
        self.weight_filter_order_combo.pack(side="left", padx=(4, 14))
        self.weight_filter_order_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_weight_list())

        ttk.Label(filter_frame, text="Фильтр по маршруту:").pack(side="left")
        self.weight_filter_route_var = tk.StringVar(value=WEIGHT_FILTER_ALL)
        filter_route_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.weight_filter_route_var,
            state="readonly",
            width=16,
            values=WEIGHT_ROUTE_FILTER_OPTIONS,
        )
        filter_route_combo.pack(side="left", padx=(4, 14))
        filter_route_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_weight_list())

        ttk.Button(filter_frame, text="Сбросить фильтр", command=self.reset_weight_filter).pack(side="left")

        list_frame = ttk.LabelFrame(container, text="Записи")
        list_frame.pack(fill="both", expand=True)

        self.weight_list = tk.Listbox(list_frame, height=14)
        self.weight_list.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self.weight_list.bind("<Double-Button-1>", lambda _event: self.edit_selected_weight_row())

        list_scroll = ttk.Scrollbar(list_frame, command=self.weight_list.yview)
        self.weight_list.configure(yscrollcommand=list_scroll.set)
        list_scroll.pack(side="left", fill="y", pady=4)

        list_buttons = ttk.Frame(container)
        list_buttons.pack(fill="x", pady=(6, 0))

        ttk.Button(list_buttons, text="Изменить выбранную", command=self.edit_selected_weight_row).pack(side="left")
        ttk.Button(
            list_buttons,
            text="Удалить выбранную",
            command=self.delete_selected_weight_row,
        ).pack(side="left", padx=8)

        self.weight_total_var = tk.StringVar()
        ttk.Label(
            list_buttons,
            textvariable=self.weight_total_var,
            font=("TkDefaultFont", 10, "bold"),
        ).pack(side="right")

        self._weight_editing_id = None
        self._weight_items = []  # строки, синхронные по порядку с self.weight_list

        self.refresh_weight_list()

    def refresh_weight_list(self):
        rows = load_weight_rows()

        processed = sorted(load_processed_files().items(), key=lambda item: item[1], reverse=True)
        order_names = [name for name, _ in processed]
        self.weight_order_combo.configure(values=[WEIGHT_NO_BINDING] + order_names)
        self.weight_filter_order_combo.configure(
            values=[WEIGHT_FILTER_ALL, WEIGHT_FILTER_UNBOUND] + order_names
        )

        order_filter = self.weight_filter_order_var.get()
        route_filter = self.weight_filter_route_var.get()

        if order_filter == WEIGHT_FILTER_UNBOUND:
            rows = [row for row in rows if not row["order_file"]]
        elif order_filter != WEIGHT_FILTER_ALL:
            rows = [row for row in rows if row["order_file"] == order_filter]

        if route_filter == WEIGHT_FILTER_UNBOUND:
            rows = [row for row in rows if not row["route"]]
        elif route_filter != WEIGHT_FILTER_ALL:
            rows = [row for row in rows if row["route"] == route_filter]

        self.weight_list.delete(0, "end")
        self._weight_items = rows

        for row in rows:
            order_part = f" · Заказ: {row['order_file']}" if row["order_file"] else ""
            route_part = f" · {row['route']}" if row["route"] else ""
            exact_part = f", точный {row['exact_weight']:g} кг" if row["exact_weight"] is not None else ""
            line = (
                f"{row['name']} — {row['box_count']}×{row['avg_weight']:g} кг{exact_part}"
                f" = {row['total']:g} кг{order_part}{route_part}"
            )
            self.weight_list.insert("end", line)

        total = sum(row["total"] for row in rows)
        self.weight_total_var.set(f"Итого по списку: {total:g} кг")

    def reset_weight_filter(self):
        self.weight_filter_order_var.set(WEIGHT_FILTER_ALL)
        self.weight_filter_route_var.set(WEIGHT_FILTER_ALL)
        self.refresh_weight_list()

    def _suggest_weight_from_name(self, _event=None):
        """Подставляет средний вес ящика из последней записи с таким же названием."""

        if self.weight_avg_var.get().strip() or self._weight_editing_id:
            return

        suggestion = last_avg_weight_for(self.weight_name_var.get())
        if suggestion is not None:
            self.weight_avg_var.set(f"{suggestion:g}")

    def _reset_weight_form(self):
        self.weight_name_var.set("")
        self.weight_box_var.set("")
        self.weight_avg_var.set("")
        self.weight_exact_var.set("")
        self.weight_order_var.set(WEIGHT_NO_BINDING)
        self.weight_route_var.set(WEIGHT_NO_BINDING)
        self.weight_status_var.set("")
        self._weight_editing_id = None
        self.weight_submit_button.configure(text="Добавить")
        self.weight_cancel_button.pack_forget()

    def edit_selected_weight_row(self):
        selection = self.weight_list.curselection()
        if not selection:
            messagebox.showinfo("Вес", "Выберите запись в списке.")
            return

        row = self._weight_items[selection[0]]
        self.weight_name_var.set(row["name"])
        self.weight_box_var.set(str(row["box_count"]))
        self.weight_avg_var.set(f"{row['avg_weight']:g}")
        self.weight_exact_var.set("" if row["exact_weight"] is None else f"{row['exact_weight']:g}")
        self.weight_order_var.set(row["order_file"] or WEIGHT_NO_BINDING)
        self.weight_route_var.set(row["route"] or WEIGHT_NO_BINDING)
        self.weight_status_var.set("")
        self._weight_editing_id = row["id"]
        self.weight_submit_button.configure(text="Сохранить изменения")
        self.weight_cancel_button.pack(side="left", padx=(8, 0))

    def cancel_weight_edit(self):
        self._reset_weight_form()

    def submit_weight_row(self):
        name = self.weight_name_var.get().strip()

        if not name:
            self.weight_status_var.set("Укажите наименование")
            return

        try:
            box_count = int(self.weight_box_var.get())
            assert box_count > 0
        except (ValueError, AssertionError):
            self.weight_status_var.set("Количество ящиков должно быть целым числом больше нуля")
            return

        try:
            avg_weight = float(self.weight_avg_var.get().replace(",", "."))
            assert avg_weight >= 0
        except (ValueError, AssertionError):
            self.weight_status_var.set("Средний вес ящика должен быть числом")
            return

        exact_weight = None
        exact_text = self.weight_exact_var.get().strip()
        if exact_text:
            try:
                exact_weight = float(exact_text.replace(",", "."))
                assert exact_weight >= 0
            except (ValueError, AssertionError):
                self.weight_status_var.set("Точный вес должен быть числом")
                return

        order_file = "" if self.weight_order_var.get() == WEIGHT_NO_BINDING else self.weight_order_var.get()
        route = "" if self.weight_route_var.get() == WEIGHT_NO_BINDING else self.weight_route_var.get()

        if self._weight_editing_id:
            update_weight_row(
                self._weight_editing_id, name, box_count, avg_weight, exact_weight, order_file, route
            )
        else:
            add_weight_row(name, box_count, avg_weight, exact_weight, order_file, route)

        self._reset_weight_form()
        self.refresh_weight_list()

    def delete_selected_weight_row(self):
        selection = self.weight_list.curselection()
        if not selection:
            messagebox.showinfo("Вес", "Выберите запись в списке.")
            return

        row = self._weight_items[selection[0]]
        if not messagebox.askyesno("Подтвердите удаление", f"Удалить запись «{row['name']}»?"):
            return

        delete_weight_row(row["id"])
        if self._weight_editing_id == row["id"]:
            self._reset_weight_form()
        self.refresh_weight_list()


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
