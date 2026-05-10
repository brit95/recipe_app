"""
latex_import_dialog.py
Dialog for previewing and confirming LaTeX recipe imports (single or batch).
Shows each parsed recipe with name, ingredient count, tags editable inline.
User can deselect recipes to skip, edit tags, then import all selected.
"""

from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QLineEdit, QWidget, QMessageBox, QSizePolicy,
    QScrollArea, QFrame, QSplitter, QTextBrowser
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
import database as db


class RecipePreviewRow(QWidget):
    """A single row in the preview list — checkbox, name, tag editor, ingredient count."""

    def __init__(self, recipe: dict, parent=None):
        super().__init__(parent)
        self.recipe = recipe
        self._build(recipe)

    def _build(self, r: dict):
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(10)

        self.check = QCheckBox()
        self.check.setChecked(not r.get("_error", False))
        self.check.setFixedWidth(24)
        row.addWidget(self.check)

        # Name
        name = r.get("name", "?")
        if r.get("_error"):
            name = f"⚠  {name}"
        self.name_label = QLabel(name)
        self.name_label.setObjectName("previewName")
        self.name_label.setFixedWidth(220)
        self.name_label.setToolTip(r.get("_source_file", ""))
        row.addWidget(self.name_label)

        # Ingredient count
        ing_count = len(r.get("ingredients", []))
        count_lbl = QLabel(f"{ing_count} ing.")
        count_lbl.setObjectName("previewMeta")
        count_lbl.setFixedWidth(55)
        row.addWidget(count_lbl)

        # Tags (editable)
        self.tags_edit = QLineEdit(", ".join(r.get("tags", [])))
        self.tags_edit.setPlaceholderText("tags…")
        self.tags_edit.setObjectName("previewTags")
        row.addWidget(self.tags_edit)

    def is_selected(self) -> bool:
        return self.check.isChecked() and not self.recipe.get("_error")

    def get_tags(self) -> list[str]:
        return [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]


class LatexImportDialog(QDialog):
    recipes_imported = Signal(int)  # emits count of imported recipes

    def __init__(self, recipes: list[dict], source_label: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import LaTeX Recipes")
        self.setMinimumSize(760, 560)
        self._recipes = recipes
        self._rows: list[RecipePreviewRow] = []
        self._build_ui(source_label)

    def _build_ui(self, source_label: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────
        header_widget = QWidget()
        header_widget.setObjectName("topBar")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 14, 20, 14)

        title = QLabel("Import LaTeX Recipes")
        title.setObjectName("pageHeader")
        header_layout.addWidget(title)

        if source_label:
            src_lbl = QLabel(f"From: {source_label}")
            src_lbl.setObjectName("hintLabel")
            header_layout.addWidget(src_lbl)

        total = len(self._recipes)
        errors = sum(1 for r in self._recipes if r.get("_error"))
        summary = f"Found {total} recipe{'s' if total != 1 else ''}"
        if errors:
            summary += f"  ({errors} could not be parsed)"
        summary_lbl = QLabel(summary)
        summary_lbl.setObjectName("hintLabel")
        header_layout.addWidget(summary_lbl)

        root.addWidget(header_widget)

        # ── Select all / none toolbar ─────────────────────────────
        sel_bar = QWidget()
        sel_bar.setObjectName("shopBar")
        sel_layout = QHBoxLayout(sel_bar)
        sel_layout.setContentsMargins(16, 6, 16, 6)
        sel_layout.setSpacing(8)

        all_btn = QPushButton("Select All")
        all_btn.setObjectName("smallBtn")
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton("Select None")
        none_btn.setObjectName("smallBtn")
        none_btn.clicked.connect(lambda: self._set_all(False))

        col_name = QLabel("Recipe Name")
        col_name.setObjectName("colHeader")
        col_name.setFixedWidth(244)
        col_ing = QLabel("Ings.")
        col_ing.setObjectName("colHeader")
        col_ing.setFixedWidth(55)
        col_tags = QLabel("Tags (editable)")
        col_tags.setObjectName("colHeader")

        sel_layout.addWidget(all_btn)
        sel_layout.addWidget(none_btn)
        sel_layout.addSpacing(10)
        sel_layout.addWidget(col_name)
        sel_layout.addWidget(col_ing)
        sel_layout.addWidget(col_tags)
        sel_layout.addStretch()
        root.addWidget(sel_bar)

        # ── Scrollable recipe list ────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        list_container = QWidget()
        self._list_layout = QVBoxLayout(list_container)
        self._list_layout.setContentsMargins(8, 4, 8, 4)
        self._list_layout.setSpacing(0)

        for recipe in self._recipes:
            row_widget = RecipePreviewRow(recipe)
            row_widget.check.stateChanged.connect(self._update_import_btn)
            if recipe.get("_error"):
                row_widget.setStyleSheet("background: #fff8f0;")
            self._rows.append(row_widget)
            self._list_layout.addWidget(row_widget)

            # Separator
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("color: #f0ede8;")
            self._list_layout.addWidget(sep)

        self._list_layout.addStretch()
        scroll.setWidget(list_container)
        root.addWidget(scroll)

        # ── Bottom button bar ─────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setObjectName("btnBar")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(20, 12, 20, 12)

        self._import_btn = QPushButton("💾  Import Selected")
        self._import_btn.setObjectName("saveBtn")
        self._import_btn.clicked.connect(self._do_import)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("clearBtn")
        cancel_btn.clicked.connect(self.reject)

        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("hintLabel")

        btn_layout.addWidget(self._import_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addSpacing(16)
        btn_layout.addWidget(self._status_lbl)
        btn_layout.addStretch()
        root.addWidget(btn_bar)

        self._update_import_btn()

    def _set_all(self, checked: bool):
        for row in self._rows:
            if not row.recipe.get("_error"):
                row.check.setChecked(checked)

    def _update_import_btn(self):
        count = sum(1 for r in self._rows if r.is_selected())
        self._import_btn.setText(f"💾  Import {count} Recipe{'s' if count != 1 else ''}")
        self._import_btn.setEnabled(count > 0)

    def _do_import(self):
        selected = [(row.recipe, row.get_tags())
                    for row in self._rows if row.is_selected()]
        if not selected:
            return

        imported = 0
        skipped = 0
        for recipe, tags in selected:
            name = recipe.get("name", "").strip()
            if not name:
                skipped += 1
                continue
            try:
                db.add_recipe(
                    name=name,
                    url=recipe.get("url", ""),
                    body=recipe.get("body", ""),
                    notes=recipe.get("notes", ""),
                    ingredients=recipe.get("ingredients", []),
                    tags=tags,
                )
                imported += 1
            except Exception:
                skipped += 1

        self.recipes_imported.emit(imported)

        msg = f"✓ Imported {imported} recipe{'s' if imported != 1 else ''}."
        if skipped:
            msg += f"  ({skipped} skipped due to errors)"
        self._status_lbl.setText(msg)
        self._import_btn.setEnabled(False)
        self._set_all(False)
