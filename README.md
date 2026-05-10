# Recipe Manager

A personal recipe organizer and weekly meal planner built with PySide6 and SQLite.

## Setup

### 1. Install Python 3.11+
Download from https://python.org if you don't already have it.

### 2. Create a virtual environment (recommended)
```bash
cd recipe_app
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
python main.py
```

The database is stored at `~/.recipe_manager.db` (your home folder),
so it persists between runs and won't be lost if you move the app folder.

---

## Features

### 📥 Import from LaTeX
In the **Add Recipe** tab, two new buttons let you pull in your existing recipe book:

- **Import .tex File…** — pick a single `.tex` file. If it contains one recipe you'll be offered the choice to preview it in the form first, or save directly. Multi-recipe files go straight to the preview dialog.
- **Import .tex Folder…** — pick a folder (searched recursively). Every `.tex` file is parsed and shown in a batch preview.

The batch preview dialog lets you:
- See every parsed recipe with its ingredient count
- Edit tags inline before importing (inferred from folder name and `\graphicspath`)
- Check/uncheck individual recipes to skip any you don't want
- Import all selected in one click

The parser handles your exact format: `\subsection`, `\subsubsection{Ingredients}` itemize, `\subsubsection{Instructions}` enumerate, `\subsubsection{Notes}`, and `\graphicspath` for category tags.


In the **Add Recipe** tab, paste any recipe URL into the URL field and click **Import Recipe from URL**. The app will:
- Automatically fill in the name, ingredients, instructions, and notes
- Use the [recipe-scrapers](https://github.com/hhursev/recipe-scrapers) library for 300+ supported sites (AllRecipes, Food Network, NYT Cooking, Epicurious, Serious Eats, etc.)
- Fall back to JSON-LD / schema.org parsing for other sites
- Fall back to heuristic HTML parsing as a last resort
- Always let you review and edit before saving

### 📄 Export to LaTeX
Select any recipe in the **Browse** tab and click **Export LaTeX**. The file is saved in your existing recipe book format:
- `\subsection{Name}` with `\label` and `\graphicspath`
- `\subsubsection{Ingredients}` as an `\itemize` list
- `\subsubsection{Instructions}` as an `\enumerate` list
- `\subsubsection{Notes}` if notes are present
- Category subfolder inferred from tags (breakfast, dinner, dessert, etc.)
- All special LaTeX characters properly escaped
- Suggested filename like `belgian_waffles.tex`


- Search recipes by name
- Filter by one or more tags (click to toggle)
- View full details: ingredients, instructions, URL link, notes
- Edit or delete any recipe

### ➕ Add / Edit Recipe
- Add a name, URL or full recipe text, notes
- Add ingredients with quantity, unit, and name
- Comma-separated tags (e.g. `dinner, quick, vegan, crockpot`)
- Edit existing recipes from the Browse tab

### 📅 Meal Planner
- Weekly 7-day grid view
- Navigate between weeks with Prev / Next
- **Auto-fill suggestions** — fills empty days with recipes based on past usage frequency, avoiding duplicates within the same week
- **Drag and drop** recipe cards between days to swap meals
- Click **change** on any card to pick a recipe manually
- **Generate Shopping List** — combines all ingredients from the week's recipes, grouped alphabetically, with source recipe noted
- Copy shopping list to clipboard

---

## Project Structure

```
recipe_app/
├── main.py                 # App entry point, main window, stylesheet
├── database.py             # SQLite schema, all data access functions
├── browse_tab.py           # Browse & Search tab (+ LaTeX export)
├── add_recipe_tab.py       # Add / Edit Recipe tab (+ URL & LaTeX import)
├── planner_tab.py          # Meal Planner tab + Shopping List dialog
├── web_importer.py         # URL recipe importer (recipe-scrapers + fallbacks)
├── latex_exporter.py       # LaTeX .tex file exporter
├── latex_importer.py       # LaTeX .tex file parser (single + batch)
├── latex_import_dialog.py  # Batch import preview/edit dialog
├── requirements.txt
└── README.md
```

---

## Tips

- **Tags** are auto-created as you type them — no setup needed
- The first launch seeds 5 demo recipes so the app isn't empty
- The database lives at `~/.recipe_manager.db` — back it up anytime
- Recipes with a URL but no body text will show "use URL above" in the instructions pane
