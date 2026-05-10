import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QPoint, QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QContextMenuEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    import keyboard
except Exception:
    keyboard = None


APP_FOLDER_NAME = "FNaF Timer But Dumb"
SETTINGS_FILE = "settings.json"
INTERVALS_SUBDIR = "intervals"
RECENT_FILE_LIMIT = 8

DEFAULT_KEYBINDS = {
    "main": "r",
    "sub1": "t",
    "sub2": "u",
    "sub3": "i",
    "sub4": "o",
    "interval_prev": "q",
    "interval_next": "e",
}
DEFAULT_ACTIVE_SUBTIMERS = 1
DEFAULT_BLINK_LEAD_SECONDS = 3
DEFAULT_SOUND_LEAD_SECONDS = 3
DEFAULT_INTERVAL_NAME = "Blank"
DEFAULT_INTERVALS = [
    24.0,
    49.5,
    75.1,
    100.6,
    126.2,
    151.7,
    177.3,
    202.8,
    228.4,
    253.9,
    279.5,
    305.0,
    330.6,
    356.1,
]
DEFAULT_INTERVAL_SETS = [{"name": DEFAULT_INTERVAL_NAME, "intervals": list(DEFAULT_INTERVALS)}]


def get_settings_dir() -> str:
    appdata = os.getenv("APPDATA")
    if appdata:
        return os.path.join(appdata, APP_FOLDER_NAME)
    return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", APP_FOLDER_NAME)


def ensure_storage_dirs() -> tuple[str, str, str]:
    settings_dir = get_settings_dir()
    intervals_dir = os.path.join(settings_dir, INTERVALS_SUBDIR)
    os.makedirs(intervals_dir, exist_ok=True)
    settings_path = os.path.join(settings_dir, SETTINGS_FILE)
    return settings_dir, intervals_dir, settings_path


def parse_time_to_seconds(raw: str) -> float:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty time value")

    match = re.search(r"\d+(?::\d+){1,2}(?:\.\d+)?", text)
    if match:
        text = match.group(0)
    else:
        numeric = re.search(r"\d+(?:\.\d+)?", text)
        if numeric:
            text = numeric.group(0)

    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)

    parts = text.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Invalid time format: {raw}")

    try:
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return float(minutes * 60) + seconds

        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    except ValueError as exc:
        raise ValueError(f"Invalid time format: {raw}") from exc

    if len(parts) == 2:
        return float(minutes * 60 + seconds)
    return float(hours * 3600 + minutes * 60 + seconds)


def format_interval_time(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes = total // 60
    secs = total % 60
    return f"{minutes:02d}:{secs:02d}"


def clean_interval_sets(raw_sets: list[dict]) -> list[dict]:
    cleaned = []
    for item in raw_sets:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "") or "").strip() or "Intervals"
        values = item.get("intervals", [])
        if not isinstance(values, list):
            continue

        parsed = []
        for value in values:
            try:
                sec = float(value)
            except (TypeError, ValueError):
                continue
            if sec > 0:
                parsed.append(sec)

        if not parsed:
            continue

        parsed.sort()
        cleaned.append({"name": name, "intervals": parsed})

    return cleaned


def current_next_for_elapsed(
    intervals: list[float], elapsed: float, display_offset: float = 0.0
) -> tuple[str, str, float | None]:
    if not intervals:
        return "--:--", "--:--", None

    current_index = 0
    while current_index < len(intervals) and intervals[current_index] < elapsed:
        current_index += 1

    if current_index >= len(intervals):
        adj_last = max(0.0, intervals[-1] - display_offset)
        return format_interval_time(adj_last), "--:--", None

    current_val = intervals[current_index]
    next_val = intervals[current_index + 1] if (current_index + 1) < len(intervals) else None
    current_txt = format_interval_time(max(0.0, current_val - display_offset))
    next_txt = (
        format_interval_time(max(0.0, next_val - display_offset)) if next_val is not None else "--:--"
    )
    return current_txt, next_txt, current_val


def build_interval_set_line(
    interval_name: str,
    intervals: list[float],
    elapsed: float,
    display_offset: float = 0.0,
) -> tuple[str, float | None]:
    current_txt, next_txt, current_target = current_next_for_elapsed(intervals, elapsed, display_offset)
    return f"{interval_name}: {current_txt} | {next_txt}", current_target


def normalize_key(raw: str) -> str:
    text = (raw or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


@dataclass
class TimerState:
    start_time: float

    def reset(self) -> None:
        self.start_time = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.start_time


class KeybindDialog(QDialog):
    def __init__(self, parent: QWidget, keybinds: dict, active_subtimers: int):
        super().__init__(parent)
        self.setWindowTitle("Keybind Settings")
        self.setModal(True)
        self.resize(420, 260)

        self.result_keybinds = dict(keybinds)

        root = QVBoxLayout(self)

        form_frame = QFrame(self)
        form_layout = QFormLayout(form_frame)

        self.labels = {}
        self.capture_buttons = {}
        labels = [
            ("main", "Main Timer"),
            ("sub1", "Subtimer 1"),
            ("sub2", "Subtimer 2"),
            ("sub3", "Subtimer 3"),
            ("sub4", "Subtimer 4"),
            ("interval_prev", "Interval -1"),
            ("interval_next", "Interval +1"),
        ]

        for key, title in labels:
            row = QHBoxLayout()
            current = QLabel(self.result_keybinds[key], self)
            current.setMinimumWidth(90)
            btn = QPushButton("Change", self)
            btn.clicked.connect(lambda _, key_name=key: self.capture_key(key_name))
            row.addWidget(current)
            row.addWidget(btn)

            row_holder = QWidget(self)
            row_holder.setLayout(row)
            form_layout.addRow(f"{title}:", row_holder)
            self.labels[key] = current
            self.capture_buttons[key] = btn

        self.active_spin = QSpinBox(self)
        self.active_spin.setMinimum(1)
        self.active_spin.setMaximum(4)
        self.active_spin.setValue(active_subtimers)
        form_layout.addRow("Active Subtimers:", self.active_spin)

        root.addWidget(form_frame)

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_btn = QPushButton("Save", self)
        cancel_btn = QPushButton("Cancel", self)
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(save_btn)
        actions.addWidget(cancel_btn)
        root.addLayout(actions)

    def capture_key(self, key_name: str) -> None:
        key, ok = KeyCaptureDialog.get_key(self)
        if not ok:
            return
        self.result_keybinds[key_name] = key
        self.labels[key_name].setText(key)

    def get_result(self) -> tuple[dict, int]:
        return self.result_keybinds, self.active_spin.value()


class KeyCaptureDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("Press a key")
        self.setModal(True)
        self.resize(280, 120)

        layout = QVBoxLayout(self)
        self.info = QLabel("Press a key or key combo (e.g. ctrl+shift+r)", self)
        self.value_label = QLabel("", self)
        self.value_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.info)
        layout.addWidget(self.value_label)

        row = QHBoxLayout()
        row.addStretch(1)
        self.ok_btn = QPushButton("Use This Key", self)
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(self.ok_btn)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

        self.captured = ""

    def keyPressEvent(self, a0: QKeyEvent | None):
        if a0 is None:
            return
        event = a0
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")

        key_text = event.text().strip().lower()
        if not key_text:
            special = {
                Qt.Key.Key_F1: "f1",
                Qt.Key.Key_F2: "f2",
                Qt.Key.Key_F3: "f3",
                Qt.Key.Key_F4: "f4",
                Qt.Key.Key_F5: "f5",
                Qt.Key.Key_F6: "f6",
                Qt.Key.Key_F7: "f7",
                Qt.Key.Key_F8: "f8",
                Qt.Key.Key_F9: "f9",
                Qt.Key.Key_F10: "f10",
                Qt.Key.Key_F11: "f11",
                Qt.Key.Key_F12: "f12",
                Qt.Key.Key_Space: "space",
                Qt.Key.Key_Tab: "tab",
                Qt.Key.Key_Return: "enter",
                Qt.Key.Key_Enter: "enter",
                Qt.Key.Key_Escape: "esc",
            }
            key_text = special.get(Qt.Key(event.key()), "")

        if not key_text:
            return

        self.captured = "+".join(parts + [key_text])
        self.value_label.setText(self.captured)
        self.ok_btn.setEnabled(True)

    @staticmethod
    def get_key(parent: QWidget) -> tuple[str, bool]:
        dlg = KeyCaptureDialog(parent)
        ok = dlg.exec() == QDialog.DialogCode.Accepted
        return dlg.captured, ok and bool(dlg.captured)


class IntervalAlertDialog(QDialog):
    def __init__(self, parent: QWidget, blink_seconds: int, sound_seconds: int):
        super().__init__(parent)
        self.setWindowTitle("Interval Alert Settings")
        self.setModal(True)
        self.resize(320, 180)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.blink_spin = QSpinBox(self)
        self.blink_spin.setMinimum(0)
        self.blink_spin.setMaximum(600)
        self.blink_spin.setValue(blink_seconds)
        form.addRow("Blink before interval (s):", self.blink_spin)

        self.sound_spin = QSpinBox(self)
        self.sound_spin.setMinimum(0)
        self.sound_spin.setMaximum(600)
        self.sound_spin.setValue(sound_seconds)
        form.addRow("Sound before interval (s):", self.sound_spin)

        root.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        ok_btn = QPushButton("Save", self)
        cancel_btn = QPushButton("Cancel", self)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(ok_btn)
        actions.addWidget(cancel_btn)
        root.addLayout(actions)

    def get_result(self) -> tuple[int, int]:
        return self.blink_spin.value(), self.sound_spin.value()


class IntervalsManagerDialog(QDialog):
    def __init__(self, parent: QWidget, interval_sets: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Intervals Manager")
        self.setModal(True)
        self.resize(520, 480)

        self.result_sets = [dict(s) for s in interval_sets] if interval_sets else [{"name": DEFAULT_INTERVAL_NAME, "intervals": []}]
        self.current_set_index = 0
        self.result_intervals = list(self.result_sets[0].get("intervals", []))

        root = QVBoxLayout(self)

        set_row = QHBoxLayout()
        set_row.addWidget(QLabel("Set:", self))
        self.set_combo = QComboBox(self)
        self.set_combo.currentIndexChanged.connect(self.on_set_changed)
        set_row.addWidget(self.set_combo)
        add_set_btn = QPushButton("+ Add Set", self)
        add_set_btn.clicked.connect(self.add_set)
        set_row.addWidget(add_set_btn)
        delete_set_btn = QPushButton("- Delete Set", self)
        delete_set_btn.clicked.connect(self.delete_set)
        set_row.addWidget(delete_set_btn)
        root.addLayout(set_row)

        form = QFormLayout()
        self.interval_text_edit = QLineEdit(self)
        form.addRow("Set Name:", self.interval_text_edit)
        root.addLayout(form)

        self.list_widget = QListWidget(self)
        root.addWidget(self.list_widget)

        buttons_row = QHBoxLayout()
        add_btn = QPushButton("Add", self)
        edit_btn = QPushButton("Edit", self)
        delete_btn = QPushButton("Delete", self)
        up_btn = QPushButton("Up", self)
        down_btn = QPushButton("Down", self)
        sort_btn = QPushButton("Sort", self)

        add_btn.clicked.connect(self.add_interval)
        edit_btn.clicked.connect(self.edit_interval)
        delete_btn.clicked.connect(self.delete_interval)
        up_btn.clicked.connect(self.move_up)
        down_btn.clicked.connect(self.move_down)
        sort_btn.clicked.connect(self.sort_intervals)

        buttons_row.addWidget(add_btn)
        buttons_row.addWidget(edit_btn)
        buttons_row.addWidget(delete_btn)
        buttons_row.addWidget(up_btn)
        buttons_row.addWidget(down_btn)
        buttons_row.addWidget(sort_btn)
        root.addLayout(buttons_row)

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_btn = QPushButton("Save", self)
        cancel_btn = QPushButton("Cancel", self)
        save_btn.clicked.connect(self.accept_with_validation)
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(save_btn)
        actions.addWidget(cancel_btn)
        root.addLayout(actions)

        self.rebuild_set_combo()
        self.on_set_changed(0)

    def rebuild_set_combo(self) -> None:
        self.set_combo.blockSignals(True)
        self.set_combo.clear()
        for i, s in enumerate(self.result_sets):
            name = str(s.get("name", f"Set {i+1}") or f"Set {i+1}")
            self.set_combo.addItem(name, i)
        self.set_combo.setCurrentIndex(self.current_set_index)
        self.set_combo.blockSignals(False)

    def on_set_changed(self, index: int) -> None:
        if index < 0 or index >= len(self.result_sets):
            return
        current_set = self.result_sets[self.current_set_index]
        current_set["name"] = self.interval_text_edit.text().strip() or DEFAULT_INTERVAL_NAME
        current_set["intervals"] = list(self.result_intervals)
        self.current_set_index = index
        self.result_intervals = list(self.result_sets[index].get("intervals", []))
        self.interval_text_edit.setText(str(self.result_sets[index].get("name", DEFAULT_INTERVAL_NAME)))
        self.rebuild_list()

    def rebuild_list(self) -> None:
        self.list_widget.clear()
        for sec in self.result_intervals:
            item = QListWidgetItem(f"{format_interval_time(sec)} ({sec:.1f}s)")
            self.list_widget.addItem(item)

    def selected_index(self) -> int:
        return self.list_widget.currentRow()

    def add_set(self) -> None:
        new_set = {"name": f"Set {len(self.result_sets) + 1}", "intervals": []}
        self.result_sets.append(new_set)
        self.rebuild_set_combo()
        self.set_combo.setCurrentIndex(len(self.result_sets) - 1)

    def delete_set(self) -> None:
        if len(self.result_sets) <= 1:
            QMessageBox.warning(self, "Cannot Delete", "Must have at least one interval set.")
            return
        if self.current_set_index < 0 or self.current_set_index >= len(self.result_sets):
            return
        self.result_sets.pop(self.current_set_index)
        self.current_set_index = min(self.current_set_index, len(self.result_sets) - 1)
        self.rebuild_set_combo()
        self.set_combo.setCurrentIndex(self.current_set_index)

    def add_interval(self) -> None:
        value, ok = QInputDialog.getText(self, "Add Interval", "Enter time (MM:SS, HH:MM:SS, or seconds):")
        if not ok:
            return
        try:
            sec = parse_time_to_seconds(value)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Interval", str(exc))
            return
        if sec <= 0:
            QMessageBox.warning(self, "Invalid Interval", "Interval must be greater than 0 seconds.")
            return
        self.result_intervals.append(sec)
        self.rebuild_list()
        self.list_widget.setCurrentRow(len(self.result_intervals) - 1)

    def edit_interval(self) -> None:
        idx = self.selected_index()
        if idx < 0 or idx >= len(self.result_intervals):
            return
        current = self.result_intervals[idx]
        value, ok = QInputDialog.getText(
            self,
            "Edit Interval",
            "Enter time (MM:SS, HH:MM:SS, or seconds):",
            text=f"{current:.1f}",
        )
        if not ok:
            return
        try:
            sec = parse_time_to_seconds(value)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Interval", str(exc))
            return
        if sec <= 0:
            QMessageBox.warning(self, "Invalid Interval", "Interval must be greater than 0 seconds.")
            return
        self.result_intervals[idx] = sec
        self.rebuild_list()
        self.list_widget.setCurrentRow(idx)

    def delete_interval(self) -> None:
        idx = self.selected_index()
        if idx < 0 or idx >= len(self.result_intervals):
            return
        self.result_intervals.pop(idx)
        self.rebuild_list()
        self.list_widget.setCurrentRow(min(idx, len(self.result_intervals) - 1))

    def move_up(self) -> None:
        idx = self.selected_index()
        if idx <= 0 or idx >= len(self.result_intervals):
            return
        self.result_intervals[idx - 1], self.result_intervals[idx] = self.result_intervals[idx], self.result_intervals[idx - 1]
        self.rebuild_list()
        self.list_widget.setCurrentRow(idx - 1)

    def move_down(self) -> None:
        idx = self.selected_index()
        if idx < 0 or idx >= len(self.result_intervals) - 1:
            return
        self.result_intervals[idx + 1], self.result_intervals[idx] = self.result_intervals[idx], self.result_intervals[idx + 1]
        self.rebuild_list()
        self.list_widget.setCurrentRow(idx + 1)

    def sort_intervals(self) -> None:
        self.result_intervals.sort()
        self.rebuild_list()

    def accept_with_validation(self) -> None:
        current_set = self.result_sets[self.current_set_index]
        current_set["name"] = self.interval_text_edit.text().strip() or DEFAULT_INTERVAL_NAME
        current_set["intervals"] = list(self.result_intervals)
        for s in self.result_sets:
            if not s.get("intervals"):
                QMessageBox.warning(self, "Empty Set", "All interval sets must have at least one interval.")
                return
        self.accept()

    def get_result(self) -> list[dict]:
        return self.result_sets


class TimerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings_dir, self.intervals_dir, self.settings_path = ensure_storage_dirs()

        (
            self.keybinds,
            self.active_subtimers,
            self.blink_lead_seconds,
            self.sound_lead_seconds,
            self.interval_sets,
            self.recent_interval_files,
            self.current_interval_file,
        ) = self.load_settings()

        self.hotkeys = []
        self.drag_active = False
        self.drag_offset = QPoint()
        self.sound_triggered_keys = set()
        self.interval_display_offset_seconds = 0.0

        self.main_timer = TimerState(time.monotonic())
        self.sub_timers = [TimerState(time.monotonic()) for _ in range(4)]

        self.setup_window()
        self.setup_ui()
        self.bind_hotkeys()

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh_labels)
        self.update_timer.start(33)

    def setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(640, 190)
            return

        geo = screen.availableGeometry()
        width = 350
        height = 160
        x = (geo.width() - width) // 2 + geo.x()
        y = geo.y() + 8
        self.setGeometry(x, y, width, height)

    def setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(4)

        font_main = QFont("Tahoma", 36, QFont.Weight.Bold)
        font_sub = QFont("Tahoma", 24, QFont.Weight.Bold)

        self.main_label = QLabel("00:00.00", self)
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_label.setFont(font_main)
        self.main_label.setStyleSheet(
            "color: rgb(64, 255, 96);"
            "background-color: transparent;"
        )
        root.addWidget(self.main_label)

        grid_holder = QWidget(self)
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)

        colors = [
            "rgb(255, 220, 64)",
            "rgb(96, 196, 255)",
            "rgb(255, 128, 96)",
            "rgb(220, 140, 255)",
        ]

        self.sub_labels = []
        for i in range(4):
            label = QLabel("00:00.00", self)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFont(font_sub)
            label.setStyleSheet(
                f"color: {colors[i]};"
                "background-color: transparent;"
            )
            grid.addWidget(label, i // 2, i % 2)
            self.sub_labels.append(label)

        root.addWidget(grid_holder)

        self.interval_scroll = QScrollArea(self)
        self.interval_scroll.setWidgetResizable(True)
        self.interval_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.interval_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.interval_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.interval_scroll.setStyleSheet("background: transparent;")

        self.interval_content = QWidget(self)
        self.interval_layout = QVBoxLayout(self.interval_content)
        self.interval_layout.setContentsMargins(0, 0, 0, 0)
        self.interval_layout.setSpacing(1)
        self.interval_scroll.setWidget(self.interval_content)
        self.interval_scroll.setFixedHeight(58)
        root.addWidget(self.interval_scroll)

        self.interval_labels = []
        self.rebuild_interval_labels()
        self.update_subtimer_visibility()
        self.refresh_labels()

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 51))
        painter.drawRect(self.rect())

    def mousePressEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self.drag_active = True
            self.drag_offset = a0.globalPosition().toPoint() - self.frameGeometry().topLeft()
            a0.accept()
            return
        super().mousePressEvent(a0)

    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if self.drag_active and (a0.buttons() & Qt.MouseButton.LeftButton):
            self.move(a0.globalPosition().toPoint() - self.drag_offset)
            a0.accept()
            return
        super().mouseMoveEvent(a0)

    def mouseReleaseEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        if a0.button() == Qt.MouseButton.LeftButton:
            self.drag_active = False
            a0.accept()
            return
        super().mouseReleaseEvent(a0)

    def contextMenuEvent(self, a0: QContextMenuEvent | None) -> None:
        if a0 is None:
            return
        event = a0
        menu = QMenu(self)
        settings_action = QAction("Keybind Settings", self)
        settings_action.triggered.connect(self.open_keybind_settings)
        menu.addAction(settings_action)

        alert_action = QAction("Interval Alert Settings", self)
        alert_action.triggered.connect(self.open_interval_alert_settings)
        menu.addAction(alert_action)

        menu.addSeparator()
        manage_intervals_action = QAction("Intervals Manager", self)
        manage_intervals_action.triggered.connect(self.open_intervals_manager)
        menu.addAction(manage_intervals_action)

        load_intervals_action = QAction("Load Intervals File", self)
        load_intervals_action.triggered.connect(self.load_intervals_from_dialog)
        menu.addAction(load_intervals_action)

        save_intervals_action = QAction("Save Intervals", self)
        save_intervals_action.triggered.connect(self.save_intervals)
        menu.addAction(save_intervals_action)

        recent_menu = menu.addMenu("Recent Interval Files")
        if recent_menu is not None:
            self.populate_recent_files_menu(recent_menu)

        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if a0 is None:
            return
        event = a0
        self.unbind_hotkeys()
        super().closeEvent(event)

    def load_settings(self) -> tuple[dict, int, int, int, list[dict], list[str], str]:
        if not os.path.exists(self.settings_path):
            return (
                dict(DEFAULT_KEYBINDS),
                DEFAULT_ACTIVE_SUBTIMERS,
                DEFAULT_BLINK_LEAD_SECONDS,
                DEFAULT_SOUND_LEAD_SECONDS,
                clean_interval_sets(DEFAULT_INTERVAL_SETS),
                [],
                "",
            )

        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            keybinds = dict(DEFAULT_KEYBINDS)
            keybinds.update({k: normalize_key(v) for k, v in data.get("keybinds", {}).items() if k in DEFAULT_KEYBINDS})
            active = int(data.get("active_subtimers", DEFAULT_ACTIVE_SUBTIMERS))
            active = max(1, min(4, active))

            blink_lead = int(data.get("blink_lead_seconds", DEFAULT_BLINK_LEAD_SECONDS))
            blink_lead = max(0, min(600, blink_lead))
            sound_lead = int(data.get("sound_lead_seconds", DEFAULT_SOUND_LEAD_SECONDS))
            sound_lead = max(0, min(600, sound_lead))

            interval_sets_raw = data.get("interval_sets", [])
            interval_sets = []
            if isinstance(interval_sets_raw, list):
                interval_sets = clean_interval_sets(interval_sets_raw)

            # Backward compatibility with older settings shape.
            if not interval_sets:
                interval_text = str(data.get("interval_text", DEFAULT_INTERVAL_NAME) or DEFAULT_INTERVAL_NAME)
                intervals_raw = data.get("intervals", [])
                legacy_intervals = []
                if isinstance(intervals_raw, list):
                    for value in intervals_raw:
                        try:
                            sec = float(value)
                        except (TypeError, ValueError):
                            continue
                        if sec > 0:
                            legacy_intervals.append(sec)
                legacy_intervals.sort()
                if legacy_intervals:
                    interval_sets = [{"name": interval_text, "intervals": legacy_intervals}]
                else:
                    interval_sets = clean_interval_sets(DEFAULT_INTERVAL_SETS)

            recent = data.get("recent_interval_files", [])
            if not isinstance(recent, list):
                recent = []
            recent = [str(p) for p in recent if isinstance(p, str)]

            current_interval_file = str(data.get("current_interval_file", "") or "")
            return keybinds, active, blink_lead, sound_lead, interval_sets, recent, current_interval_file
        except Exception:
            return (
                dict(DEFAULT_KEYBINDS),
                DEFAULT_ACTIVE_SUBTIMERS,
                DEFAULT_BLINK_LEAD_SECONDS,
                DEFAULT_SOUND_LEAD_SECONDS,
                clean_interval_sets(DEFAULT_INTERVAL_SETS),
                [],
                "",
            )

    def save_settings(self) -> None:
        payload = {
            "keybinds": self.keybinds,
            "active_subtimers": self.active_subtimers,
            "blink_lead_seconds": self.blink_lead_seconds,
            "sound_lead_seconds": self.sound_lead_seconds,
            "interval_sets": self.interval_sets,
            "recent_interval_files": self.recent_interval_files[:RECENT_FILE_LIMIT],
            "current_interval_file": self.current_interval_file,
        }
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def format_elapsed(self, sec: float) -> str:
        minutes = int(sec // 60)
        seconds = int(sec % 60)
        hundredths = int((sec - int(sec)) * 100)
        return f"{minutes:02d}:{seconds:02d}.{hundredths:02d}"

    def refresh_labels(self) -> None:
        elapsed = self.main_timer.elapsed()
        self.main_label.setText(self.format_elapsed(elapsed))
        for idx, label in enumerate(self.sub_labels):
            label.setText(self.format_elapsed(self.sub_timers[idx].elapsed()))
        self.refresh_interval_text(elapsed)

    def refresh_interval_text(self, elapsed: float) -> None:
        blink_now = (int(time.monotonic() * 4) % 2) == 0

        for idx, interval_set in enumerate(self.interval_sets):
            if idx >= len(self.interval_labels):
                break

            label = self.interval_labels[idx]
            set_name = str(interval_set.get("name", "Intervals") or "Intervals")
            intervals = interval_set.get("intervals", [])
            if not isinstance(intervals, list):
                intervals = []

            line_text, target = build_interval_set_line(
                set_name, intervals, elapsed, self.interval_display_offset_seconds
            )
            label.setText(line_text)
            if target is None:
                label.setStyleSheet("color: rgb(120, 120, 120); background-color: transparent;")
                continue

            adjusted_target = target - self.interval_display_offset_seconds
            remaining = adjusted_target - elapsed
            sound_key = f"{idx}:{adjusted_target:.3f}"

            if 0.0 < remaining <= float(self.sound_lead_seconds) and sound_key not in self.sound_triggered_keys:
                QApplication.beep()
                self.sound_triggered_keys.add(sound_key)

            if 0.0 < remaining <= float(self.blink_lead_seconds):
                if blink_now:
                    label.setStyleSheet("color: rgb(255, 96, 96); background-color: transparent;")
                else:
                    label.setStyleSheet("color: rgb(240, 240, 240); background-color: transparent;")
            elif remaining <= 0.0:
                label.setStyleSheet("color: rgb(120, 120, 120); background-color: transparent;")
            else:
                label.setStyleSheet("color: rgb(240, 240, 240); background-color: transparent;")

    def reset_main(self) -> None:
        self.main_timer.reset()
        for timer in self.sub_timers:
            timer.reset()
        self.sound_triggered_keys.clear()
        self.interval_display_offset_seconds = 0.0
        self.refresh_labels()

    def reset_sub(self, index: int) -> None:
        if index < 0 or index >= self.active_subtimers:
            return
        self.sub_timers[index].reset()
        self.refresh_labels()

    def shift_interval_display(self, direction: int) -> None:
        """Shift interval labels (and alert timing) without moving the main timer. Reset clears offset."""
        if direction == 0:
            return
        self.interval_display_offset_seconds -= float(direction)
        self.refresh_labels()

    def open_keybind_settings(self) -> None:
        dlg = KeybindDialog(self, self.keybinds, self.active_subtimers)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_keybinds, new_count = dlg.get_result()

        normalized = {k: normalize_key(v) for k, v in new_keybinds.items()}
        values = list(normalized.values())
        if any(not v for v in values):
            QMessageBox.warning(self, "Invalid Key", "Every keybind must have a value.")
            return
        if len(set(values)) != len(values):
            QMessageBox.warning(self, "Duplicate Keys", "Each timer must use a unique keybind.")
            return

        self.keybinds = normalized
        self.active_subtimers = max(1, min(4, int(new_count)))
        self.update_subtimer_visibility()
        self.save_settings()
        self.bind_hotkeys()

    def open_interval_alert_settings(self) -> None:
        dlg = IntervalAlertDialog(self, self.blink_lead_seconds, self.sound_lead_seconds)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        blink, sound = dlg.get_result()
        self.blink_lead_seconds = blink
        self.sound_lead_seconds = sound
        self.save_settings()



    def get_primary_interval_set(self) -> dict:
        if not self.interval_sets:
            self.interval_sets = [{"name": DEFAULT_INTERVAL_NAME, "intervals": []}]
        first = self.interval_sets[0]
        if "name" not in first:
            first["name"] = DEFAULT_INTERVAL_NAME
        if "intervals" not in first or not isinstance(first["intervals"], list):
            first["intervals"] = []
        return first

    def open_intervals_manager(self) -> None:
        dlg = IntervalsManagerDialog(self, self.interval_sets)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.interval_sets = dlg.get_result()
        self.rebuild_interval_labels()
        self.sound_triggered_keys.clear()
        self.save_settings()

    def rebuild_interval_labels(self) -> None:
        for label in self.interval_labels:
            self.interval_layout.removeWidget(label)
            label.deleteLater()
        self.interval_labels.clear()

        if not self.interval_sets:
            placeholder = QLabel("Intervals: --:-- | --:--", self.interval_content)
            placeholder.setFont(QFont("Tahoma", 11, QFont.Weight.Bold))
            placeholder.setStyleSheet("color: rgb(180, 180, 180); background-color: transparent;")
            self.interval_layout.addWidget(placeholder)
            self.interval_labels.append(placeholder)
            return

        elapsed = self.main_timer.elapsed()
        for interval_set in self.interval_sets:
            set_name = str(interval_set.get("name", "Intervals") or "Intervals")
            intervals = interval_set.get("intervals", [])
            if not isinstance(intervals, list):
                intervals = []
            line_text, _ = build_interval_set_line(
                set_name, intervals, elapsed, self.interval_display_offset_seconds
            )
            label = QLabel(line_text, self.interval_content)
            label.setFont(QFont("Tahoma", 11, QFont.Weight.Bold))
            label.setStyleSheet("color: rgb(240, 240, 240); background-color: transparent;")
            self.interval_layout.addWidget(label)
            self.interval_labels.append(label)

    def parse_interval_file(self, path: str) -> list[dict]:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        ext = os.path.splitext(path)[1].lower()
        interval_sets: list[dict] = []

        if ext == ".json":
            data = json.loads(content)
            if isinstance(data, dict):
                raw_sets = data.get("interval_sets", [])
                if isinstance(raw_sets, list):
                    interval_sets = clean_interval_sets(raw_sets)

                if not interval_sets:
                    source = data.get("intervals", [])
                    interval_name = str(data.get("interval_text", DEFAULT_INTERVAL_NAME) or DEFAULT_INTERVAL_NAME)
                    items = []
                    if isinstance(source, list):
                        for value in source:
                            try:
                                if isinstance(value, (int, float)):
                                    sec = float(value)
                                else:
                                    sec = parse_time_to_seconds(str(value))
                            except ValueError:
                                continue
                            if sec > 0:
                                items.append(sec)
                    items.sort()
                    if items:
                        interval_sets = [{"name": interval_name, "intervals": items}]
            elif isinstance(data, list):
                items = []
                for value in data:
                    try:
                        if isinstance(value, (int, float)):
                            sec = float(value)
                        else:
                            sec = parse_time_to_seconds(str(value))
                    except ValueError:
                        continue
                    if sec > 0:
                        items.append(sec)
                items.sort()
                if items:
                    interval_sets = [{"name": DEFAULT_INTERVAL_NAME, "intervals": items}]

            if interval_sets:
                return interval_sets
            return clean_interval_sets(DEFAULT_INTERVAL_SETS)

        current_name = ""
        current_items: list[float] = []

        def flush_current() -> None:
            nonlocal current_name, current_items, interval_sets
            if current_items:
                name = current_name or DEFAULT_INTERVAL_NAME
                interval_sets.append({"name": name, "intervals": sorted(current_items)})
                current_items = []

        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            token = re.split(r"[|,;\t]", line)[0].strip()
            if not token:
                continue

            if not re.match(r"^\d", token):
                flush_current()
                current_name = token.split(",")[0].strip() or current_name
                continue

            try:
                sec = parse_time_to_seconds(token)
                if sec > 0:
                    current_items.append(sec)
                continue
            except ValueError:
                pass

            flush_current()
            name_candidate = token.split(",")[0].strip()
            if name_candidate:
                current_name = name_candidate

        flush_current()

        if interval_sets:
            return interval_sets
        return clean_interval_sets(DEFAULT_INTERVAL_SETS)

    def update_recent_files(self, path: str) -> None:
        full = os.path.abspath(path)
        updated = [p for p in self.recent_interval_files if os.path.abspath(p) != full]
        updated.insert(0, full)
        self.recent_interval_files = updated[:RECENT_FILE_LIMIT]

    def load_intervals_from_file(self, path: str) -> None:
        try:
            interval_sets = self.parse_interval_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Failed", f"Could not load intervals file:\n{exc}")
            return

        self.interval_sets = clean_interval_sets(interval_sets)
        if not self.interval_sets:
            self.interval_sets = clean_interval_sets(DEFAULT_INTERVAL_SETS)
        self.current_interval_file = os.path.abspath(path)
        self.update_recent_files(path)
        self.rebuild_interval_labels()
        self.sound_triggered_keys.clear()
        self.save_settings()

    def load_intervals_from_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Intervals File",
            self.intervals_dir,
            "Interval Files (*.json *.txt *.csv);;All Files (*)",
        )
        if not path:
            return
        self.load_intervals_from_file(path)

    def save_intervals_to_file(self, path: str) -> None:
        payload = {
            "interval_sets": self.interval_sets,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def save_intervals(self) -> None:
        default_target = self.current_interval_file or os.path.join(self.intervals_dir, "intervals.json")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Intervals",
            default_target,
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            self.save_intervals_to_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", f"Could not save intervals:\n{exc}")
            return

        self.current_interval_file = os.path.abspath(path)
        self.update_recent_files(path)
        self.save_settings()



    def populate_recent_files_menu(self, recent_menu: QMenu) -> None:
        existing = []
        for path in self.recent_interval_files:
            if os.path.exists(path):
                existing.append(path)

        self.recent_interval_files = existing[:RECENT_FILE_LIMIT]

        if not self.recent_interval_files:
            empty_action = QAction("(No recent files)", self)
            empty_action.setEnabled(False)
            recent_menu.addAction(empty_action)
            return

        for path in self.recent_interval_files:
            action = QAction(path, self)
            action.triggered.connect(lambda _=False, p=path: self.load_intervals_from_file(p))
            recent_menu.addAction(action)

    def update_subtimer_visibility(self) -> None:
        for idx, label in enumerate(self.sub_labels):
            label.setVisible(idx < self.active_subtimers)

    def bind_hotkeys(self) -> None:
        self.unbind_hotkeys()

        if keyboard is None:
            QMessageBox.warning(
                self,
                "Global Hotkeys Unavailable",
                "The 'keyboard' package is not installed.\nInstall with: pip install keyboard",
            )
            return

        try:
            self.hotkeys.append(keyboard.add_hotkey(self.keybinds["main"], self.reset_main, suppress=False, trigger_on_release=False))
            self.hotkeys.append(keyboard.add_hotkey(self.keybinds["sub1"], lambda: self.reset_sub(0), suppress=False, trigger_on_release=False))
            self.hotkeys.append(keyboard.add_hotkey(self.keybinds["sub2"], lambda: self.reset_sub(1), suppress=False, trigger_on_release=False))
            self.hotkeys.append(keyboard.add_hotkey(self.keybinds["sub3"], lambda: self.reset_sub(2), suppress=False, trigger_on_release=False))
            self.hotkeys.append(keyboard.add_hotkey(self.keybinds["sub4"], lambda: self.reset_sub(3), suppress=False, trigger_on_release=False))
            if "interval_prev" in self.keybinds:
                self.hotkeys.append(
                    keyboard.add_hotkey(
                        self.keybinds["interval_prev"],
                        lambda: self.shift_interval_display(-1),
                        suppress=False,
                        trigger_on_release=False,
                    )
                )
            if "interval_next" in self.keybinds:
                self.hotkeys.append(
                    keyboard.add_hotkey(
                        self.keybinds["interval_next"],
                        lambda: self.shift_interval_display(1),
                        suppress=False,
                        trigger_on_release=False,
                    )
                )
        except Exception as exc:
            QMessageBox.warning(self, "Hotkey Error", f"Failed to register global hotkeys:\n{exc}")

    def unbind_hotkeys(self) -> None:
        if keyboard is None:
            return
        for hk in self.hotkeys:
            try:
                keyboard.remove_hotkey(hk)
            except Exception:
                pass
        self.hotkeys.clear()


def main() -> int:
    app = QApplication(sys.argv)
    window = TimerApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
