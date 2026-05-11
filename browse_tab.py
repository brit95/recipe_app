from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QTextBrowser, QSplitter,
    QScrollArea, QFrame, QMessageBox, QSizePolicy, QFileDialog,
    QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
import database as db
import webbrowser

# Tag operator cycle: unselected → OR → AND → NOT → unselected
_OP_CYCLE  = [None, "OR", "AND", "NOT"]
_OP_LABELS = {"OR": "OR", "AND": "AND", "NOT": "NOT"}
_OP_STYLES = {
    None:  "tagBtn",
    "OR":  "tagBtnOR",
    "AND": "tagBtnAND",
    "NOT": "tagBtnNOT",
}


class TagFilterBar(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._buttons: dict[str, QPushButton] = {}
        self._ops: dict[str, str | None] = {}   # tag → None|"OR"|"AND"|"NOT"

    def refresh(self, tags: list[str]):
        for btn in self._buttons.values():
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()
        self._ops.clear()
        for tag in tags:
            btn = QPushButton(tag)
            btn.setCheckable(False)
            btn.setObjectName("tagBtn")
            btn.clicked.connect(lambda _, t=tag: self._cycle(t))
            self._layout.addWidget(btn)
            self._buttons[tag] = btn
            self._ops[tag] = None
        self._layout.addStretch()

    def _cycle(self, tag: str):
        current = self._ops.get(tag)
        idx = _OP_CYCLE.index(current)
        next_op = _OP_CYCLE[(idx + 1) % len(_OP_CYCLE)]
        self._ops[tag] = next_op
        btn = self._buttons[tag]
        btn.setObjectName(_OP_STYLES[next_op])
        if next_op:
            btn.setText(f"{_OP_LABELS[next_op]}: {tag}")
        else:
            btn.setText(tag)
        btn.style().polish(btn)
        self.changed.emit()

    def get_tag_groups(self) -> dict:
        """Return {"OR": [...], "AND": [...], "NOT": [...]}"""
        groups: dict[str, list] = {"OR": [], "AND": [], "NOT": []}
        for tag, op in self._ops.items():
            if op:
                groups[op].append(tag)
        return groups

    def selected_tags(self) -> list[str]:
        """Legacy: returns OR tags for backward compat."""
        return self.get_tag_groups()["OR"]

    def clear_all(self):
        for tag in list(self._ops.keys()):
            if self._ops[tag] is not None:
                self._ops[tag] = None
                btn = self._buttons[tag]
                btn.setText(tag)
                btn.setObjectName("tagBtn")
                btn.style().polish(btn)
        self.changed.emit()


# ── Tag Manager Dialog ────────────────────────────────────────────────────────

class TagManagerDialog(QDialog):
    tags_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Tags")
        self.setMinimumSize(420, 480)
        layout = QVBoxLayout(self)

        header = QLabel("Tags")
        header.setObjectName("pageHeader")
        layout.addWidget(header)

        hint = QLabel("Click a tag to rename it. Select and press Delete to remove it.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Tag", "Recipes"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._rename_tag)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        rename_btn = QPushButton("✏️  Rename / Merge")
        rename_btn.setObjectName("actionBtn")
        rename_btn.clicked.connect(lambda: self._rename_tag(None))
        delete_btn = QPushButton("🗑  Delete Tag")
        delete_btn.setObjectName("deleteBtn")
        delete_btn.clicked.connect(self._delete_tag)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("clearBtn")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(rename_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._load()

    def _load(self):
        self.table.setRowCount(0)
        for row in db.tag_usage_counts():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(row["name"])
            count_item = QTableWidgetItem(str(row["count"]))
            count_item.setTextAlignment(Qt.AlignCenter)
            if row["count"] == 0:
                name_item.setForeground(QColor("#aaa"))
                count_item.setForeground(QColor("#aaa"))
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, count_item)

    def _selected_tag(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).text()

    def _rename_tag(self, _item):
        tag = self._selected_tag()
        if not tag:
            QMessageBox.information(self, "No Selection", "Select a tag first.")
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename Tag",
            f"Rename \"{tag}\" to:\n(If the new name already exists, the tags will be merged.)",
            text=tag
        )
        if not ok or not new_name.strip() or new_name.strip().lower() == tag:
            return
        db.rename_tag(tag, new_name.strip())
        self._load()
        self.tags_changed.emit()

    def _delete_tag(self):
        tag = self._selected_tag()
        if not tag:
            QMessageBox.information(self, "No Selection", "Select a tag to delete.")
            return
        reply = QMessageBox.question(
            self, "Delete Tag",
            f"Delete tag \"{tag}\"?\nIt will be removed from all recipes.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            db.delete_tag(tag)
            self._load()
            self.tags_changed.emit()


class RecipeDetailPane(QWidget):
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    export_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recipe_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.title_label = QLabel()
        self.title_label.setObjectName("recipeTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.tags_label = QLabel()
        self.tags_label.setObjectName("recipeTags")
        self.tags_label.setWordWrap(True)
        layout.addWidget(self.tags_label)

        self.url_btn = QPushButton("🔗 Open URL")
        self.url_btn.setObjectName("urlBtn")
        self.url_btn.hide()
        self.url_btn.clicked.connect(self._open_url)
        layout.addWidget(self.url_btn)

        ing_label = QLabel("Ingredients")
        ing_label.setObjectName("sectionHeader")
        layout.addWidget(ing_label)
        self.ing_browser = QTextBrowser()
        self.ing_browser.setMaximumHeight(160)
        layout.addWidget(self.ing_browser)

        body_label = QLabel("Instructions")
        body_label.setObjectName("sectionHeader")
        layout.addWidget(body_label)
        self.body_browser = QTextBrowser()
        layout.addWidget(self.body_browser)

        self.notes_label = QLabel()
        self.notes_label.setObjectName("notesLabel")
        self.notes_label.setWordWrap(True)
        layout.addWidget(self.notes_label)

        btn_row = QHBoxLayout()
        self.edit_btn = QPushButton("✏️  Edit Recipe")
        self.edit_btn.setObjectName("actionBtn")
        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setObjectName("deleteBtn")
        self.export_btn = QPushButton("📄  Export LaTeX")
        self.export_btn.setObjectName("exportBtn")
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._recipe_id))
        self.delete_btn.clicked.connect(self._confirm_delete)
        self.export_btn.clicked.connect(lambda: self.export_requested.emit(self._recipe_id))
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._url = ""
        self._set_empty()

    def _set_empty(self):
        self.title_label.setText("Select a recipe →")
        self.tags_label.setText("")
        self.url_btn.hide()
        self.ing_browser.setPlainText("")
        self.body_browser.setPlainText("")
        self.notes_label.setText("")
        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.export_btn.setEnabled(False)

    def show_recipe(self, recipe_id: int):
        r = db.get_recipe(recipe_id)
        if not r:
            return
        self._recipe_id = recipe_id
        self.title_label.setText(r["name"])
        self.tags_label.setText("  ".join(f"#{t}" for t in r["tags"]))
        self._url = r.get("url", "")
        self.url_btn.show() if self._url else self.url_btn.hide()
        ing_lines = []
        for ing in r["ingredients"]:
            parts = [ing["quantity"], ing["unit"], ing["item"]]
            ing_lines.append(" ".join(p for p in parts if p))
        self.ing_browser.setPlainText("\n".join(ing_lines) if ing_lines else "(none)")
        self.body_browser.setPlainText(r.get("body", "") or "(no instructions — use URL above)")
        notes = r.get("notes", "")
        self.notes_label.setText(f"📝 {notes}" if notes else "")
        self.edit_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

    def _open_url(self):
        if self._url:
            webbrowser.open(self._url)

    def _confirm_delete(self):
        reply = QMessageBox.question(
            self, "Delete Recipe",
            "Are you sure you want to delete this recipe?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(self._recipe_id)


class DedupeDialog(QDialog):
    """Find duplicate recipes (grouped by name) and let the user remove them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find Duplicate Recipes")
        self.resize(720, 520)

        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        hint = QLabel(
            "Recipes are grouped by name (case-insensitive). The 'keeper' is "
            "chosen automatically based on richest content (most ingredients, "
            "tags, then body length). Duplicates' tags and meal-plan entries "
            "are merged into the keeper before deletion."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Recipe", "ID", "Ingredients", "Tags", "Action"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄  Re-scan")
        self.refresh_btn.setObjectName("smallBtn")
        self.refresh_btn.clicked.connect(self._populate)

        self.delete_btn = QPushButton("🗑  Remove duplicates")
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.clicked.connect(self._run_dedupe)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("smallBtn")
        close_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._populate()

    def _populate(self):
        try:
            preview = db.dedupe_recipes(dry_run=True)
            groups = db.find_duplicate_groups()
        except Exception as e:
            QMessageBox.warning(self, "Dedupe failed", str(e))
            return

        self.summary_label.setText(
            f"<b>{preview['groups']}</b> duplicate group(s) found · "
            f"<b>{preview['duplicates_removed']}</b> recipe(s) would be removed."
        )
        self.delete_btn.setEnabled(preview["duplicates_removed"] > 0)

        keep_ids = set(preview["kept"])
        self.table.setRowCount(0)
        for grp in groups:
            row = self.table.rowCount()
            self.table.insertRow(row)
            header = QTableWidgetItem(f"▸ {grp['name']}  ({len(grp['recipes'])})")
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            header.setBackground(QColor("#f0ede8"))
            self.table.setItem(row, 0, header)
            for c in range(1, 5):
                cell = QTableWidgetItem("")
                cell.setBackground(QColor("#f0ede8"))
                self.table.setItem(row, c, cell)
            self.table.setSpan(row, 0, 1, 5)

            for r in grp["recipes"]:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem("   " + r["name"]))
                self.table.setItem(row, 1, QTableWidgetItem(str(r["id"])))
                self.table.setItem(row, 2, QTableWidgetItem(str(r["ingredient_count"])))
                self.table.setItem(row, 3, QTableWidgetItem(str(r["tag_count"])))
                action = "KEEP" if r["id"] in keep_ids else "remove"
                action_item = QTableWidgetItem(action)
                if action == "KEEP":
                    action_item.setForeground(QColor("#1a6b3a"))
                    f = action_item.font(); f.setBold(True); action_item.setFont(f)
                else:
                    action_item.setForeground(QColor("#c0392b"))
                self.table.setItem(row, 4, action_item)

    def _run_dedupe(self):
        preview = db.dedupe_recipes(dry_run=True)
        n = preview["duplicates_removed"]
        if n == 0:
            QMessageBox.information(self, "Dedupe", "No duplicates to remove.")
            return
        reply = QMessageBox.question(
            self, "Remove duplicates",
            f"Remove {n} duplicate recipe(s)?\n\n"
            "Their tags and meal-plan entries will be merged into the kept "
            "recipe. This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            result = db.dedupe_recipes(dry_run=False)
        except Exception as e:
            QMessageBox.warning(self, "Dedupe failed", str(e))
            return
        QMessageBox.information(
            self, "Dedupe complete",
            f"Removed {result['duplicates_removed']} duplicate recipe(s) "
            f"across {result['groups']} group(s)."
        )
        self.accept()
class BrowseTab(QWidget):
    edit_recipe = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        # Populate recipe list and tag filter immediately on construction
        # so the Browse tab shows data without needing a tab switch.
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────
        top = QWidget()
        top.setObjectName("topBar")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(8)

        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search recipes by name…")
        self.search_box.setObjectName("searchBox")
        self.search_box.textChanged.connect(self._refresh_list)

        clear_btn = QPushButton("Clear filters")
        clear_btn.setObjectName("smallBtn")
        clear_btn.clicked.connect(self._clear_filters)

        tag_mgr_btn = QPushButton("🏷  Manage Tags")
        tag_mgr_btn.setObjectName("smallBtn")
        tag_mgr_btn.clicked.connect(self._open_tag_manager)

        export_json_btn = QPushButton("⬆  Export JSON")
        export_json_btn.setObjectName("smallBtn")
        export_json_btn.clicked.connect(self._export_json)

        dedupe_btn = QPushButton("🧹  Dedupe")
        dedupe_btn.setObjectName("smallBtn")
        dedupe_btn.setToolTip("Find and remove duplicate recipes (grouped by name)")
        dedupe_btn.clicked.connect(self._open_dedupe)

        search_row.addWidget(self.search_box)
        search_row.addWidget(clear_btn)
        search_row.addWidget(tag_mgr_btn)
        search_row.addWidget(export_json_btn)
        search_row.addWidget(dedupe_btn)
        top_layout.addLayout(search_row)

        # Tag legend
        legend = QLabel("Click tags to cycle:  unselected → OR → AND → NOT")
        legend.setObjectName("hintLabel")
        top_layout.addWidget(legend)

        tag_scroll = QScrollArea()
        tag_scroll.setWidgetResizable(True)
        tag_scroll.setFixedHeight(46)
        tag_scroll.setFrameShape(QFrame.NoFrame)
        tag_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tag_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tag_bar = TagFilterBar()
        self.tag_bar.changed.connect(self._refresh_list)
        tag_scroll.setWidget(self.tag_bar)
        top_layout.addWidget(tag_scroll)

        root.addWidget(top)

        # ── Splitter ──────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("mainSplitter")

        list_pane = QWidget()
        list_layout = QVBoxLayout(list_pane)
        list_layout.setContentsMargins(8, 8, 0, 8)
        self.count_label = QLabel()
        self.count_label.setObjectName("countLabel")
        list_layout.addWidget(self.count_label)
        self.recipe_list = QListWidget()
        self.recipe_list.setObjectName("recipeList")
        self.recipe_list.currentItemChanged.connect(self._on_select)
        list_layout.addWidget(self.recipe_list)

        self.detail_pane = RecipeDetailPane()
        self.detail_pane.edit_requested.connect(self.edit_recipe.emit)
        self.detail_pane.delete_requested.connect(self._on_delete)
        self.detail_pane.export_requested.connect(self._on_export)

        splitter.addWidget(list_pane)
        splitter.addWidget(self.detail_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter)

    def refresh(self):
        self.tag_bar.refresh(db.all_tags())
        self._refresh_list()

    def _clear_filters(self):
        self.search_box.clear()
        self.tag_bar.clear_all()

    def _refresh_list(self):
        query = self.search_box.text()
        groups = self.tag_bar.get_tag_groups()
        recipes = db.search_recipes(
            query=query,
            tags=groups["OR"] or None,
            and_tags=groups["AND"] or None,
            not_tags=groups["NOT"] or None,
        )
        self.recipe_list.clear()
        for r in recipes:
            item = QListWidgetItem(r["name"])
            item.setData(Qt.UserRole, r["id"])
            item.setToolTip("  ".join(f"#{t}" for t in r.get("tags", [])))
            self.recipe_list.addItem(item)
        self.count_label.setText(f"{len(recipes)} recipe{'s' if len(recipes) != 1 else ''}")

    def _on_select(self, current, _previous):
        if current:
            self.detail_pane.show_recipe(current.data(Qt.UserRole))

    def _on_delete(self, recipe_id: int):
        db.delete_recipe(recipe_id)
        self.refresh()

    def _on_export(self, recipe_id: int):
        from latex_exporter import export_recipe_to_file, suggested_filename
        recipe = db.get_recipe(recipe_id)
        if not recipe:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Recipe as LaTeX",
            suggested_filename(recipe),
            "LaTeX Files (*.tex);;All Files (*)"
        )
        if not path:
            return
        try:
            export_recipe_to_file(recipe, path)
            QMessageBox.information(self, "Exported", f"Recipe saved to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _open_tag_manager(self):
        dlg = TagManagerDialog(self)
        dlg.tags_changed.connect(self.refresh)
        dlg.exec()

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Recipes as JSON", "recipes.json",
            "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            db.export_to_json(path)
            count = len(db.all_recipes_brief())
            QMessageBox.information(self, "Exported",
                                    f"Exported {count} recipes to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _open_dedupe(self):
        dlg = DedupeDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()



class RecipeDetailPane(QWidget):
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    export_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recipe_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.title_label = QLabel()
        self.title_label.setObjectName("recipeTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.tags_label = QLabel()
        self.tags_label.setObjectName("recipeTags")
        self.tags_label.setWordWrap(True)
        layout.addWidget(self.tags_label)

        self.url_btn = QPushButton("🔗 Open URL")
        self.url_btn.setObjectName("urlBtn")
        self.url_btn.hide()
        self.url_btn.clicked.connect(self._open_url)
        layout.addWidget(self.url_btn)

        # Ingredients
        ing_label = QLabel("Ingredients")
        ing_label.setObjectName("sectionHeader")
        layout.addWidget(ing_label)
        self.ing_browser = QTextBrowser()
        self.ing_browser.setMaximumHeight(160)
        layout.addWidget(self.ing_browser)

        # Instructions / Body
        body_label = QLabel("Instructions")
        body_label.setObjectName("sectionHeader")
        layout.addWidget(body_label)
        self.body_browser = QTextBrowser()
        layout.addWidget(self.body_browser)

        # Notes
        self.notes_label = QLabel()
        self.notes_label.setObjectName("notesLabel")
        self.notes_label.setWordWrap(True)
        layout.addWidget(self.notes_label)

        # Actions
        btn_row = QHBoxLayout()
        self.edit_btn = QPushButton("✏️  Edit Recipe")
        self.edit_btn.setObjectName("actionBtn")
        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setObjectName("deleteBtn")
        self.export_btn = QPushButton("📄  Export LaTeX")
        self.export_btn.setObjectName("exportBtn")
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._recipe_id))
        self.delete_btn.clicked.connect(self._confirm_delete)
        self.export_btn.clicked.connect(lambda: self.export_requested.emit(self._recipe_id))
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.export_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._url = ""
        self._set_empty()

    def _set_empty(self):
        self.title_label.setText("Select a recipe →")
        self.tags_label.setText("")
        self.url_btn.hide()
        self.ing_browser.setPlainText("")
        self.body_browser.setPlainText("")
        self.notes_label.setText("")
        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.export_btn.setEnabled(False)

    def show_recipe(self, recipe_id: int):
        r = db.get_recipe(recipe_id)
        if not r:
            return
        self._recipe_id = recipe_id
        self.title_label.setText(r["name"])
        self.tags_label.setText("  ".join(f"#{t}" for t in r["tags"]))
        self._url = r.get("url", "")
        if self._url:
            self.url_btn.show()
        else:
            self.url_btn.hide()

        ing_lines = []
        for ing in r["ingredients"]:
            parts = [ing["quantity"], ing["unit"], ing["item"]]
            ing_lines.append(" ".join(p for p in parts if p))
        self.ing_browser.setPlainText("\n".join(ing_lines) if ing_lines else "(none)")
        self.body_browser.setPlainText(r.get("body", "") or "(no instructions — use URL above)")
        notes = r.get("notes", "")
        self.notes_label.setText(f"📝 {notes}" if notes else "")
        self.edit_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

    def _open_url(self):
        if self._url:
            webbrowser.open(self._url)

    def _confirm_delete(self):
        reply = QMessageBox.question(
            self, "Delete Recipe",
            "Are you sure you want to delete this recipe?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(self._recipe_id)

