import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QStatusBar, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

import database as db
from browse_tab import BrowseTab
from add_recipe_tab import AddEditTab
from planner_tab import MealPlannerTab


STYLESHEET = """
/* ── Base ──────────────────────────────────────────────────────── */
QWidget {
    font-family: -apple-system, "Helvetica Neue", "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #1a1a2e;
    background-color: #f5f4f0;
}

QMainWindow {
    background-color: #f5f4f0;
}

/* ── Tab bar ────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: none;
    background: #f5f4f0;
}
QTabBar::tab {
    background: #e8e6e0;
    color: #555;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 500;
    border: none;
    border-bottom: 3px solid transparent;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #f5f4f0;
    color: #c0392b;
    border-bottom: 3px solid #c0392b;
    font-weight: 700;
}
QTabBar::tab:hover:!selected {
    background: #dedad3;
    color: #333;
}

/* ── Top / toolbar bars ─────────────────────────────────────────── */
#topBar {
    background: #ffffff;
    border-bottom: 1px solid #ddd;
}
#btnBar {
    background: #ffffff;
    border-top: 1px solid #e0ddd7;
}
#shopBar {
    background: #ffffff;
    border-top: 1px solid #e0ddd7;
}

/* ── Search box ─────────────────────────────────────────────────── */
#searchBox {
    background: #f0ede8;
    border: 1.5px solid #ddd;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 14px;
}
#searchBox:focus {
    border-color: #c0392b;
    background: #fff;
}

/* ── Tag filter buttons ─────────────────────────────────────────── */
QPushButton#tagBtn {
    background: #e8e6e0;
    color: #555;
    border: 1.5px solid #ccc;
    border-radius: 14px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton#tagBtn:checked {
    background: #c0392b;
    color: #fff;
    border-color: #a93226;
}
QPushButton#tagBtn:hover:!checked {
    background: #d5d2cc;
}
QPushButton#tagBtnOR {
    background: #2471a3;
    color: #fff;
    border: 1.5px solid #1a5276;
    border-radius: 14px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#tagBtnOR:hover { background: #1a5276; }
QPushButton#tagBtnAND {
    background: #1e8449;
    color: #fff;
    border: 1.5px solid #196f3d;
    border-radius: 14px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#tagBtnAND:hover { background: #196f3d; }
QPushButton#tagBtnNOT {
    background: #c0392b;
    color: #fff;
    border: 1.5px solid #a93226;
    border-radius: 14px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
    text-decoration: line-through;
}
QPushButton#tagBtnNOT:hover { background: #a93226; }

/* ── Recipe list ────────────────────────────────────────────────── */
QListWidget#recipeList {
    background: #ffffff;
    border: 1px solid #e0ddd7;
    border-radius: 8px;
    outline: none;
}
QListWidget#recipeList::item {
    padding: 10px 12px;
    border-bottom: 1px solid #f0ede8;
}
QListWidget#recipeList::item:selected {
    background: #fdecea;
    color: #c0392b;
    font-weight: 600;
}
QListWidget#recipeList::item:hover:!selected {
    background: #f8f6f3;
}

/* ── Detail pane labels ─────────────────────────────────────────── */
#recipeTitle {
    font-size: 20px;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 4px;
}
#recipeTags {
    color: #c0392b;
    font-size: 12px;
    font-weight: 500;
    margin-bottom: 8px;
}
#sectionHeader {
    font-size: 12px;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-top: 6px;
}
#notesLabel {
    color: #666;
    font-style: italic;
}
#countLabel {
    color: #888;
    font-size: 12px;
    padding: 4px 2px;
}
#colHeader {
    font-size: 11px;
    font-weight: 700;
    color: #999;
    text-transform: uppercase;
}

/* ── Text browsers ──────────────────────────────────────────────── */
QTextBrowser, QTextEdit {
    background: #fafaf8;
    border: 1px solid #e0ddd7;
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
    line-height: 1.5;
}

/* ── Form inputs ────────────────────────────────────────────────── */
QLineEdit {
    background: #ffffff;
    border: 1.5px solid #ddd;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #c0392b;
}
#hintLabel {
    color: #999;
    font-size: 12px;
}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 13px;
}
#saveBtn {
    background: #c0392b;
    color: #fff;
    font-weight: 700;
    padding: 9px 20px;
    border: none;
}
#saveBtn:hover { background: #a93226; }
#saveBtn:pressed { background: #922b21; }

#clearBtn {
    background: transparent;
    color: #888;
    border: 1.5px solid #ccc;
}
#clearBtn:hover { background: #e8e6e0; }

#actionBtn {
    background: #1a1a2e;
    color: #fff;
    border: none;
}
#actionBtn:hover { background: #2c2c4a; }

#exportBtn {
    background: #2c5f8a;
    color: #fff;
    border: none;
}
#exportBtn:hover { background: #1e4a6e; }

#importTexBtn {
    background: #5c3d8a;
    color: #fff;
    border: none;
    font-weight: 600;
    padding: 8px 16px;
}
#importTexBtn:hover { background: #4a3070; }

    color: #fff;
    border: none;
    font-weight: 600;
    padding: 8px 16px;
}
#importBtn:hover { background: #155230; }

#deleteBtn {
    background: transparent;
    color: #c0392b;
    border: 1.5px solid #c0392b;
}
#deleteBtn:hover { background: #fdecea; }

#urlBtn {
    background: transparent;
    color: #2980b9;
    border: 1.5px solid #2980b9;
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
}
#urlBtn:hover { background: #eaf4fb; }

#smallBtn {
    background: #e8e6e0;
    color: #444;
    border: 1px solid #ccc;
    font-size: 12px;
    padding: 4px 10px;
}
#smallBtn:hover { background: #d5d2cc; }

QPushButton#removeBtn {
    background: transparent;
    color: #aaa;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 11px;
    padding: 0;
}
QPushButton#removeBtn:hover {
    color: #c0392b;
    border-color: #c0392b;
    background: #fdecea;
}

/* ── Nav buttons ─────────────────────────────────────────────────── */
#navBtn {
    background: transparent;
    color: #555;
    border: 1.5px solid #ccc;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
}
#navBtn:hover { background: #e8e6e0; }

#accentBtn {
    background: #c0392b;
    color: #fff;
    border: none;
    font-weight: 600;
    padding: 7px 16px;
}
#accentBtn:hover { background: #a93226; }

#shopBtn {
    background: #1a6b3a;
    color: #fff;
    border: none;
    font-weight: 600;
    padding: 8px 18px;
}
#shopBtn:hover { background: #155230; }

/* ── Week label ──────────────────────────────────────────────────── */
#weekLabel {
    font-size: 15px;
    font-weight: 600;
    color: #1a1a2e;
    margin: 0 12px;
}

/* ── Day headers ─────────────────────────────────────────────────── */
#dayHeader {
    font-size: 13px;
    font-weight: 700;
    color: #555;
    padding: 4px;
}
#dayHeaderToday {
    font-size: 13px;
    font-weight: 700;
    color: #c0392b;
    padding: 4px;
}
#dateSubLabel {
    font-size: 11px;
    color: #999;
}

/* ── Recipe cards ────────────────────────────────────────────────── */
QFrame#recipeCard {
    background: #ffffff;
    border: 1.5px solid #e0ddd7;
    border-radius: 10px;
}
QFrame#recipeCard[filled="true"] {
    border-color: #c0392b;
    background: #fffcfc;
}
QFrame#recipeCardHover {
    background: #fdecea;
    border: 2px dashed #c0392b;
    border-radius: 10px;
}
#cardName {
    font-size: 13px;
    font-weight: 600;
    color: #1a1a2e;
}
QFrame#recipeCard[filled="false"] #cardName {
    color: #bbb;
    font-weight: 400;
    font-style: italic;
}
#cardBtn {
    background: transparent;
    color: #888;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}
#cardBtn:hover {
    background: #f0ede8;
    color: #444;
}
#cardClearBtn {
    background: transparent;
    color: #ccc;
    border: none;
    font-size: 13px;
    padding: 2px 6px;
}
#cardClearBtn:hover {
    color: #c0392b;
}

/* ── Page header ─────────────────────────────────────────────────── */
#pageHeader {
    font-size: 22px;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 8px;
}

/* ── Splitter ────────────────────────────────────────────────────── */
QSplitter::handle {
    background: #e0ddd7;
    width: 1px;
}

/* ── Scroll bars ─────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #ccc;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #ccc;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Recipe Manager")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        # ── Build tabs ────────────────────────────────────────────
        self.browse_tab = BrowseTab()
        self.add_tab = AddEditTab()
        self.planner_tab = MealPlannerTab()

        self.tabs.addTab(self.browse_tab, "📖  Browse Recipes")
        self.tabs.addTab(self.add_tab, "➕  Add Recipe")
        self.tabs.addTab(self.planner_tab, "📅  Meal Planner")

        # ── Cross-tab signals ─────────────────────────────────────
        self.add_tab.recipe_saved.connect(self._on_recipe_saved)
        self.browse_tab.edit_recipe.connect(self._edit_recipe)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # ── Status bar ────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    def _on_recipe_saved(self):
        self.browse_tab.refresh()
        self.tabs.setCurrentWidget(self.browse_tab)
        self.status.showMessage("Recipe saved!", 3000)

    def _edit_recipe(self, recipe_id: int):
        self.add_tab.load_recipe_for_edit(recipe_id)
        self.tabs.setCurrentWidget(self.add_tab)

    def _on_tab_changed(self, index):
        widget = self.tabs.widget(index)
        if widget is self.browse_tab:
            self.browse_tab.refresh()
        elif widget is self.planner_tab:
            self.planner_tab.refresh()


def main():
    db.init_db()
    db.seed_demo_data()

    app = QApplication(sys.argv)
    app.setApplicationName("Recipe Manager")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
