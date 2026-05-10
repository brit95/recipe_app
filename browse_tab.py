from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QTextBrowser, QSplitter,
    QScrollArea, QFrame, QMessageBox, QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
import database as db
import webbrowser


class TagFilterBar(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._buttons: dict[str, QPushButton] = {}
        self._selected: set[str] = set()

    def refresh(self, tags: list[str]):
        # Remove old buttons
        for btn in self._buttons.values():
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()
        self._selected.clear()
        for tag in tags:
            btn = QPushButton(tag)
            btn.setCheckable(True)
            btn.setObjectName("tagBtn")
            btn.toggled.connect(lambda checked, t=tag: self._toggle(t, checked))
            self._layout.addWidget(btn)
            self._buttons[tag] = btn
        self._layout.addStretch()

    def _toggle(self, tag: str, checked: bool):
        if checked:
            self._selected.add(tag)
        else:
            self._selected.discard(tag)
        self.changed.emit()

    def selected_tags(self) -> list[str]:
        return list(self._selected)


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


class BrowseTab(QWidget):
    edit_recipe = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────
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
        search_row.addWidget(self.search_box)
        top_layout.addLayout(search_row)

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

        # Recipe list
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

    def _refresh_list(self):
        query = self.search_box.text()
        tags = self.tag_bar.selected_tags()
        recipes = db.search_recipes(query, tags if tags else None)
        self.recipe_list.clear()
        for r in recipes:
            item = QListWidgetItem(r["name"])
            item.setData(Qt.UserRole, r["id"])
            tag_str = "  ".join(f"#{t}" for t in r.get("tags", []))
            item.setToolTip(tag_str)
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
        default_name = suggested_filename(recipe)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Recipe as LaTeX",
            default_name,
            "LaTeX Files (*.tex);;All Files (*)"
        )
        if not path:
            return
        try:
            export_recipe_to_file(recipe, path)
            QMessageBox.information(self, "Exported",
                                    f"Recipe saved to:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))
