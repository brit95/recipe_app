from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QScrollArea,
    QDialog, QListWidget, QListWidgetItem, QDialogButtonBox,
    QTextEdit, QSizePolicy, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QDrag, QFont, QPixmap, QPainter, QColor
from datetime import date, timedelta
import database as db


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MIME_TYPE = "application/x-recipe-card"


def monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ── Recipe picker dialog ───────────────────────────────────────────────────────

class RecipePickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick a Recipe")
        self.setMinimumSize(360, 460)
        layout = QVBoxLayout(self)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.lst = QListWidget()
        layout.addWidget(self.lst)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # Add "— none —" option
        none_item = QListWidgetItem("— clear slot —")
        none_item.setData(Qt.UserRole, None)
        self.lst.addItem(none_item)

        self._all_recipes = db.all_recipes_brief()
        self._populate(self._all_recipes)

    def _populate(self, recipes):
        # Keep first (clear) item
        while self.lst.count() > 1:
            self.lst.takeItem(1)
        for r in recipes:
            item = QListWidgetItem(r["name"])
            item.setData(Qt.UserRole, r["id"])
            self.lst.addItem(item)

    def _filter(self, text):
        filtered = [r for r in self._all_recipes if text.lower() in r["name"].lower()]
        self._populate(filtered)

    def selected_recipe(self):
        item = self.lst.currentItem()
        if not item:
            return -1  # nothing chosen
        return item.data(Qt.UserRole)  # None = clear, int = recipe_id


from PySide6.QtWidgets import QLineEdit


# ── Draggable recipe card ──────────────────────────────────────────────────────

class RecipeCard(QFrame):
    """A card showing a recipe name, draggable to another day slot."""
    recipe_changed = Signal()

    def __init__(self, plan_date: str, meal_type: str,
                 recipe: dict | None, parent=None):
        super().__init__(parent)
        self.plan_date = plan_date
        self.meal_type = meal_type
        self.recipe = recipe  # {"id": int, "name": str} or None
        self.setAcceptDrops(True)
        self.setObjectName("recipeCard")
        self.setCursor(Qt.OpenHandCursor)
        self.setMinimumHeight(70)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.name_label = QLabel()
        self.name_label.setWordWrap(True)
        self.name_label.setObjectName("cardName")
        layout.addWidget(self.name_label)

        self.action_row = QHBoxLayout()
        self.change_btn = QPushButton("change")
        self.change_btn.setObjectName("cardBtn")
        self.change_btn.clicked.connect(self._pick_recipe)
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setObjectName("cardClearBtn")
        self.clear_btn.clicked.connect(self._clear)
        self.action_row.addWidget(self.change_btn)
        self.action_row.addWidget(self.clear_btn)
        self.action_row.addStretch()
        layout.addLayout(self.action_row)

        self._refresh_display()

    def _refresh_display(self):
        if self.recipe:
            self.name_label.setText(self.recipe["name"])
            self.setProperty("filled", True)
        else:
            self.name_label.setText("Drop here or click change")
            self.setProperty("filled", False)
        self.style().polish(self)

    def _pick_recipe(self):
        dlg = RecipePickerDialog(self)
        if dlg.exec() == QDialog.Accepted:
            chosen = dlg.selected_recipe()
            if chosen == -1:
                return
            if chosen is None:
                self.recipe = None
            else:
                recipes = db.all_recipes_brief()
                match = next((r for r in recipes if r["id"] == chosen), None)
                self.recipe = match
            db.set_meal(self.plan_date, self.meal_type,
                        self.recipe["id"] if self.recipe else None)
            self._refresh_display()
            self.recipe_changed.emit()

    def _clear(self):
        self.recipe = None
        db.set_meal(self.plan_date, self.meal_type, None)
        self._refresh_display()
        self.recipe_changed.emit()

    # ── Drag ──────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.recipe:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if not self.recipe:
            return
        drag = QDrag(self)
        mime = QMimeData()
        # Encode: source_date|meal_type|recipe_id|recipe_name
        payload = f"{self.plan_date}|{self.meal_type}|{self.recipe['id']}|{self.recipe['name']}"
        mime.setData(MIME_TYPE, payload.encode())
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            event.acceptProposedAction()
            self.setObjectName("recipeCardHover")
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setObjectName("recipeCard")
        self.style().polish(self)

    def dropEvent(self, event):
        self.setObjectName("recipeCard")
        self.style().polish(self)
        raw = event.mimeData().data(MIME_TYPE).toStdString()
        src_date, src_meal, rid, rname = raw.split("|", 3)
        # Swap
        my_recipe = self.recipe
        incoming = {"id": int(rid), "name": rname}

        # Update DB
        db.set_meal(src_date, src_meal, my_recipe["id"] if my_recipe else None)
        db.set_meal(self.plan_date, self.meal_type, incoming["id"])

        # Update source card
        src_card = self._find_card(src_date, src_meal)
        if src_card:
            src_card.recipe = my_recipe
            src_card._refresh_display()

        self.recipe = incoming
        self._refresh_display()
        self.recipe_changed.emit()
        event.acceptProposedAction()

    def _find_card(self, plan_date: str, meal_type: str):
        # Walk up to PlannerTab and search
        w = self.parent()
        while w:
            if hasattr(w, "get_card"):
                return w.get_card(plan_date, meal_type)
            w = w.parent()
        return None


# ── Planner Tab ───────────────────────────────────────────────────────────────

class MealPlannerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._monday = monday_of_week(date.today())
        self._cards: dict[tuple, RecipeCard] = {}  # (date_str, meal_type) -> card
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top toolbar ───────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setObjectName("topBar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 10, 16, 10)

        self.week_label = QLabel()
        self.week_label.setObjectName("weekLabel")
        prev_btn = QPushButton("◀  Prev")
        prev_btn.setObjectName("navBtn")
        prev_btn.clicked.connect(self._prev_week)
        next_btn = QPushButton("Next  ▶")
        next_btn.setObjectName("navBtn")
        next_btn.clicked.connect(self._next_week)
        today_btn = QPushButton("Today")
        today_btn.setObjectName("navBtn")
        today_btn.clicked.connect(self._go_today)
        suggest_btn = QPushButton("✨  Auto-fill Suggestions")
        suggest_btn.setObjectName("accentBtn")
        suggest_btn.clicked.connect(self._auto_suggest)

        tb_layout.addWidget(prev_btn)
        tb_layout.addWidget(today_btn)
        tb_layout.addWidget(next_btn)
        tb_layout.addWidget(self.week_label)
        tb_layout.addStretch()
        tb_layout.addWidget(suggest_btn)
        root.addWidget(toolbar)

        # ── Grid scroll area ──────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(self.grid_widget)

        # ── Shopping list bar ─────────────────────────────────────
        shop_bar = QWidget()
        shop_bar.setObjectName("shopBar")
        shop_layout = QHBoxLayout(shop_bar)
        shop_layout.setContentsMargins(16, 10, 16, 10)
        shop_btn = QPushButton("🛒  Generate Shopping List")
        shop_btn.setObjectName("shopBtn")
        shop_btn.clicked.connect(self._show_shopping_list)
        shop_layout.addWidget(shop_btn)
        shop_layout.addStretch()
        root.addWidget(shop_bar)

        self._refresh_week()

    def _refresh_week(self):
        # Clear grid
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        monday = self._monday
        sunday = monday + timedelta(days=6)
        self.week_label.setText(
            f"Week of  {monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"
        )

        plan = db.get_week_plan(monday)

        for col, (day_name, delta) in enumerate(zip(DAYS, range(7))):
            d = monday + timedelta(days=delta)
            date_str = str(d)
            is_today = (d == date.today())

            # Day header
            day_lbl = QLabel(day_name)
            day_lbl.setObjectName("dayHeaderToday" if is_today else "dayHeader")
            day_lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(day_lbl, 0, col)

            date_lbl = QLabel(d.strftime("%b %d"))
            date_lbl.setObjectName("dateSubLabel")
            date_lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(date_lbl, 1, col)

            # Dinner card (single meal type for now)
            recipe = plan.get(date_str, {}).get("dinner")
            card = RecipeCard(date_str, "dinner", recipe)
            card.recipe_changed.connect(self._on_card_changed)
            self._cards[(date_str, "dinner")] = card
            self.grid_layout.addWidget(card, 2, col)

        # Make columns equal width
        for col in range(7):
            self.grid_layout.setColumnStretch(col, 1)

    def get_card(self, plan_date: str, meal_type: str) -> RecipeCard | None:
        return self._cards.get((plan_date, meal_type))

    def _on_card_changed(self):
        pass  # Could update shopping preview etc.

    def _prev_week(self):
        self._monday -= timedelta(weeks=1)
        self._refresh_week()

    def _next_week(self):
        self._monday += timedelta(weeks=1)
        self._refresh_week()

    def _go_today(self):
        self._monday = monday_of_week(date.today())
        self._refresh_week()

    def _auto_suggest(self):
        existing = db.get_week_plan(self._monday)
        filled_days = sum(
            1 for d_data in existing.values()
            for v in d_data.values() if v
        )
        if filled_days > 0:
            reply = QMessageBox.question(
                self, "Auto-fill",
                "Some days already have meals. Only fill empty days?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                return
            fill_all = (reply == QMessageBox.No)
        else:
            fill_all = True

        suggestions = db.suggest_meals_for_week(self._monday, "dinner")
        for i, suggestion in enumerate(suggestions):
            d = self._monday + timedelta(days=i)
            date_str = str(d)
            existing_meal = existing.get(date_str, {}).get("dinner")
            if existing_meal and not fill_all:
                continue
            if suggestion:
                db.set_meal(date_str, "dinner", suggestion["id"])

        self._refresh_week()

    def _show_shopping_list(self):
        items = db.get_shopping_list(self._monday)
        dlg = ShoppingListDialog(items, self)
        dlg.exec()

    def refresh(self):
        self._refresh_week()


# ── Shopping List Dialog ──────────────────────────────────────────────────────

class ShoppingListDialog(QDialog):
    def __init__(self, items: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shopping List")
        self.setMinimumSize(420, 540)
        layout = QVBoxLayout(self)

        header = QLabel("🛒  Shopping List")
        header.setObjectName("pageHeader")
        layout.addWidget(header)

        if not items:
            layout.addWidget(QLabel("No ingredients found for this week's meals.\nMake sure recipes have ingredients added."))
        else:
            # Group by ingredient name, combine quantities
            grouped: dict[str, list[str]] = {}
            for item in items:
                key = item["item"].lower().strip()
                entry = " ".join(p for p in [item["quantity"], item["unit"]] if p)
                if entry:
                    grouped.setdefault(key, []).append(f"{entry} ({item['recipe_name']})")
                else:
                    grouped.setdefault(key, []).append(f"({item['recipe_name']})")

            text_area = QTextEdit()
            text_area.setReadOnly(False)  # Let user edit/check off
            lines = []
            for ingredient, entries in sorted(grouped.items()):
                detail = ", ".join(entries)
                lines.append(f"☐  {ingredient.title()}  —  {detail}")
            text_area.setPlainText("\n".join(lines))
            layout.addWidget(text_area)

        copy_btn = QPushButton("📋  Copy to Clipboard")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(
            "\n".join(
                f"{item['quantity']} {item['unit']} {item['item']}".strip()
                for item in items
            )
        ))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
