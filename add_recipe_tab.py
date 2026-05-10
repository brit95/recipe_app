from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPushButton, QLabel,
    QScrollArea, QFrame, QSizePolicy, QMessageBox,
    QProgressDialog, QApplication, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
import database as db


class IngredientRow(QWidget):
    remove_requested = Signal(object)

    def __init__(self, item="", qty="", unit="", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.qty = QLineEdit(qty)
        self.qty.setPlaceholderText("Qty")
        self.qty.setFixedWidth(60)

        self.unit = QLineEdit(unit)
        self.unit.setPlaceholderText("Unit")
        self.unit.setFixedWidth(70)

        self.item = QLineEdit(item)
        self.item.setPlaceholderText("Ingredient name")

        remove_btn = QPushButton("✕")
        remove_btn.setObjectName("removeBtn")
        remove_btn.setFixedSize(28, 28)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))

        row.addWidget(self.qty)
        row.addWidget(self.unit)
        row.addWidget(self.item)
        row.addWidget(remove_btn)

    def data(self) -> dict:
        return {
            "item": self.item.text().strip(),
            "quantity": self.qty.text().strip(),
            "unit": self.unit.text().strip(),
        }


class ImportWorker(QObject):
    """Runs web import in a background thread to keep the UI responsive."""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            from web_importer import import_from_url
            result = import_from_url(self.url)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class AddEditTab(QWidget):
    recipe_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editing_id = None
        self._ingredient_rows: list[IngredientRow] = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Scrollable form area ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        self.header_label = QLabel("Add New Recipe")
        self.header_label.setObjectName("pageHeader")
        layout.addWidget(self.header_label)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Recipe name")
        form.addRow("Name *", self.name_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://...")
        form.addRow("URL", self.url_edit)

        layout.addLayout(form)

        # Import buttons row
        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        self.import_btn = QPushButton("🌐  Import from URL")
        self.import_btn.setObjectName("importBtn")
        self.import_btn.setToolTip("Fetch and auto-fill this form from the recipe URL above")
        self.import_btn.clicked.connect(self._import_from_url)
        self.import_tex_btn = QPushButton("📄  Import .tex File…")
        self.import_tex_btn.setObjectName("importTexBtn")
        self.import_tex_btn.setToolTip("Import a single LaTeX recipe file")
        self.import_tex_btn.clicked.connect(self._import_single_tex)
        self.import_folder_btn = QPushButton("📁  Import .tex Folder…")
        self.import_folder_btn.setObjectName("importTexBtn")
        self.import_folder_btn.setToolTip("Batch import all .tex files in a folder")
        self.import_folder_btn.clicked.connect(self._import_tex_folder)
        import_row.addWidget(self.import_btn)
        import_row.addWidget(self.import_tex_btn)
        import_row.addWidget(self.import_folder_btn)
        import_row.addStretch()
        layout.addLayout(import_row)

        # Instructions body
        body_label = QLabel("Instructions / Recipe Text")
        body_label.setObjectName("sectionHeader")
        layout.addWidget(body_label)
        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("Paste or type the recipe instructions here (optional if URL is provided)…")
        self.body_edit.setMinimumHeight(120)
        layout.addWidget(self.body_edit)

        # Notes
        notes_label = QLabel("Notes")
        notes_label.setObjectName("sectionHeader")
        layout.addWidget(notes_label)
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("e.g. Great for meal prep, freezes well…")
        layout.addWidget(self.notes_edit)

        # Tags
        tags_label = QLabel("Tags")
        tags_label.setObjectName("sectionHeader")
        layout.addWidget(tags_label)
        tags_hint = QLabel("Comma-separated — e.g.  dinner, crockpot, quick, vegan")
        tags_hint.setObjectName("hintLabel")
        layout.addWidget(tags_hint)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("dinner, quick, vegan…")
        layout.addWidget(self.tags_edit)

        # Ingredients
        ing_header_row = QHBoxLayout()
        ing_label = QLabel("Ingredients")
        ing_label.setObjectName("sectionHeader")
        add_ing_btn = QPushButton("+ Add Ingredient")
        add_ing_btn.setObjectName("smallBtn")
        add_ing_btn.clicked.connect(lambda: self._add_ingredient_row())
        ing_header_row.addWidget(ing_label)
        ing_header_row.addStretch()
        ing_header_row.addWidget(add_ing_btn)
        layout.addLayout(ing_header_row)

        # Column headers
        col_header = QHBoxLayout()
        col_header.setSpacing(6)
        for text, w in [("Qty", 60), ("Unit", 70), ("Ingredient", None)]:
            lbl = QLabel(text)
            lbl.setObjectName("colHeader")
            if w:
                lbl.setFixedWidth(w)
            col_header.addWidget(lbl)
        col_header.addSpacing(34)
        layout.addLayout(col_header)

        # Ingredient rows container — must be a QWidget so new rows
        # trigger a proper resize on the parent scroll area
        self.ing_container_widget = QWidget()
        self.ing_container = QVBoxLayout(self.ing_container_widget)
        self.ing_container.setSpacing(4)
        self.ing_container.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ing_container_widget)

        # Spacer
        layout.addStretch()

        # ── Save / Cancel bar ─────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setObjectName("btnBar")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(24, 12, 24, 12)
        self.save_btn = QPushButton("💾  Save Recipe")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._save)
        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.clicked.connect(self.clear_form)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        outer.addWidget(btn_bar)

    def _add_ingredient_row(self, item="", qty="", unit=""):
        row = IngredientRow(item, qty, unit)
        row.remove_requested.connect(self._remove_ingredient_row)
        self._ingredient_rows.append(row)
        self.ing_container.addWidget(row)
        self.ing_container_widget.adjustSize()

    def _remove_ingredient_row(self, row: IngredientRow):
        self.ing_container.removeWidget(row)
        self._ingredient_rows.remove(row)
        row.deleteLater()
        self.ing_container_widget.adjustSize()

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a recipe name.")
            return

        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        ingredients = [r.data() for r in self._ingredient_rows if r.data()["item"]]

        if self._editing_id:
            db.update_recipe(
                self._editing_id,
                name, self.url_edit.text(), self.body_edit.toPlainText(),
                self.notes_edit.text(), ingredients, tags
            )
        else:
            db.add_recipe(
                name, self.url_edit.text(), self.body_edit.toPlainText(),
                self.notes_edit.text(), ingredients, tags
            )

        self.recipe_saved.emit()
        self.clear_form()

    def _import_from_url(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.information(self, "No URL", "Enter a URL in the URL field first.")
            return

        self._progress = QProgressDialog("Fetching recipe…", "Cancel", 0, 0, self)
        self._progress.setWindowTitle("Importing")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)
        self._progress.show()
        QApplication.processEvents()

        self._thread = QThread()
        self._worker = ImportWorker(url)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_import_done)
        self._worker.error.connect(self._on_import_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._progress.canceled.connect(self._thread.quit)
        self._thread.start()

    def _on_import_done(self, result: dict):
        self._progress.close()
        self.populate_from_import(result)

    def _on_import_error(self, msg: str):
        self._progress.close()
        QMessageBox.warning(self, "Import Failed",
                            f"Could not import recipe:\n\n{msg}\n\n"
                            "You can still fill in the form manually.")

    def populate_from_import(self, data: dict):
        """Fill the form from an imported recipe dict."""
        if data.get("name"):
            self.name_edit.setText(data["name"])
        if data.get("url"):
            self.url_edit.setText(data["url"])
        if data.get("body"):
            self.body_edit.setPlainText(data["body"])
        if data.get("notes"):
            self.notes_edit.setText(data["notes"])
        # Clear existing ingredient rows and repopulate
        for row in list(self._ingredient_rows):
            self._remove_ingredient_row(row)
        for ing in data.get("ingredients", []):
            self._add_ingredient_row(ing.get("item", ""),
                                     ing.get("quantity", ""),
                                     ing.get("unit", ""))

    def _import_single_tex(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open LaTeX Recipe File", "",
            "LaTeX Files (*.tex);;All Files (*)"
        )
        if not path:
            return
        try:
            from latex_importer import parse_tex_file
            from latex_import_dialog import LatexImportDialog
            recipes = parse_tex_file(path)
            if not recipes:
                QMessageBox.information(self, "No Recipes Found",
                                        "No recipe content could be parsed from that file.")
                return
            # Single recipe — if just one, offer to fill the form directly
            if len(recipes) == 1 and not recipes[0].get("_error"):
                r = recipes[0]
                reply = QMessageBox.question(
                    self, "Import Recipe",
                    f"Found: \"{r['name']}\"\n\nFill the form for review, or save directly to database?",
                    QMessageBox.Save | QMessageBox.Open | QMessageBox.Cancel
                )
                if reply == QMessageBox.Open:
                    self.populate_from_import(r)
                    return
                elif reply == QMessageBox.Cancel:
                    return
            # Multiple recipes or user chose Save — show preview dialog
            dlg = LatexImportDialog(recipes, source_label=path, parent=self)
            dlg.recipes_imported.connect(self._on_tex_imported)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Import Error", str(e))

    def _import_tex_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select LaTeX Recipe Folder", ""
        )
        if not folder:
            return
        try:
            from latex_importer import parse_tex_folder
            from latex_import_dialog import LatexImportDialog
            recipes = parse_tex_folder(folder)
            if not recipes:
                QMessageBox.information(self, "No Recipes Found",
                                        "No .tex files with recipe content found in that folder.")
                return
            dlg = LatexImportDialog(recipes, source_label=folder, parent=self)
            dlg.recipes_imported.connect(self._on_tex_imported)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Import Error", str(e))

    def _on_tex_imported(self, count: int):
        if count > 0:
            self.recipe_saved.emit()  # triggers browse tab refresh

    def clear_form(self):
        self._editing_id = None
        self.header_label.setText("Add New Recipe")
        self.name_edit.clear()
        self.url_edit.clear()
        self.body_edit.clear()
        self.notes_edit.clear()
        self.tags_edit.clear()
        for row in list(self._ingredient_rows):
            self._remove_ingredient_row(row)

    def load_recipe_for_edit(self, recipe_id: int):
        r = db.get_recipe(recipe_id)
        if not r:
            return
        self.clear_form()
        self._editing_id = recipe_id
        self.header_label.setText("Edit Recipe")
        self.name_edit.setText(r["name"])
        self.url_edit.setText(r.get("url", ""))
        self.body_edit.setPlainText(r.get("body", ""))
        self.notes_edit.setText(r.get("notes", ""))
        self.tags_edit.setText(", ".join(r.get("tags", [])))
        for ing in r.get("ingredients", []):
            self._add_ingredient_row(ing["item"], ing["quantity"], ing["unit"])
