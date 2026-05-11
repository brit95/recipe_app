import sqlite3
import os
from datetime import date, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.expanduser("~"), ".recipe_manager.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS recipes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                url         TEXT,
                body        TEXT,
                notes       TEXT,
                created_at  TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS tags (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS recipe_tags (
                recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
                tag_id    INTEGER REFERENCES tags(id)    ON DELETE CASCADE,
                PRIMARY KEY (recipe_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS ingredients (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER REFERENCES recipes(id) ON DELETE CASCADE,
                item      TEXT NOT NULL,
                quantity  TEXT,
                unit      TEXT
            );

            CREATE TABLE IF NOT EXISTS meal_plan (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_date TEXT NOT NULL,
                meal_type TEXT NOT NULL DEFAULT 'dinner',
                recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
                UNIQUE(plan_date, meal_type)
            );
        """)


# ── Tags ──────────────────────────────────────────────────────────────────────

def get_or_create_tag(conn, name: str) -> int:
    name = name.strip().lower()
    row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    return cur.lastrowid


def all_tags():
    with get_connection() as conn:
        return [row["name"] for row in conn.execute("SELECT name FROM tags ORDER BY name")]


# ── Recipes ───────────────────────────────────────────────────────────────────

def add_recipe(name: str, url: str, body: str, notes: str,
               ingredients: list[dict], tags: list[str]) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO recipes (name, url, body, notes) VALUES (?,?,?,?)",
            (name.strip(), url.strip(), body.strip(), notes.strip())
        )
        recipe_id = cur.lastrowid
        for ing in ingredients:
            conn.execute(
                "INSERT INTO ingredients (recipe_id, item, quantity, unit) VALUES (?,?,?,?)",
                (recipe_id, ing.get("item", ""), ing.get("quantity", ""), ing.get("unit", ""))
            )
        for tag in tags:
            if tag.strip():
                tid = get_or_create_tag(conn, tag)
                conn.execute(
                    "INSERT OR IGNORE INTO recipe_tags (recipe_id, tag_id) VALUES (?,?)",
                    (recipe_id, tid)
                )
        return recipe_id


def update_recipe(recipe_id: int, name: str, url: str, body: str, notes: str,
                  ingredients: list[dict], tags: list[str]):
    with get_connection() as conn:
        conn.execute(
            "UPDATE recipes SET name=?, url=?, body=?, notes=? WHERE id=?",
            (name.strip(), url.strip(), body.strip(), notes.strip(), recipe_id)
        )
        conn.execute("DELETE FROM ingredients WHERE recipe_id=?", (recipe_id,))
        for ing in ingredients:
            conn.execute(
                "INSERT INTO ingredients (recipe_id, item, quantity, unit) VALUES (?,?,?,?)",
                (recipe_id, ing.get("item", ""), ing.get("quantity", ""), ing.get("unit", ""))
            )
        conn.execute("DELETE FROM recipe_tags WHERE recipe_id=?", (recipe_id,))
        for tag in tags:
            if tag.strip():
                tid = get_or_create_tag(conn, tag)
                conn.execute(
                    "INSERT OR IGNORE INTO recipe_tags (recipe_id, tag_id) VALUES (?,?)",
                    (recipe_id, tid)
                )


def delete_recipe(recipe_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))


def get_recipe(recipe_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        if not row:
            return None
        recipe = dict(row)
        recipe["ingredients"] = [
            dict(r) for r in conn.execute(
                "SELECT * FROM ingredients WHERE recipe_id=? ORDER BY id", (recipe_id,)
            )
        ]
        recipe["tags"] = [
            r["name"] for r in conn.execute(
                """SELECT t.name FROM tags t
                   JOIN recipe_tags rt ON rt.tag_id=t.id
                   WHERE rt.recipe_id=? ORDER BY t.name""",
                (recipe_id,)
            )
        ]
        return recipe


def search_recipes(query: str = "", tags: list[str] = None,
                   and_tags: list[str] = None,
                   not_tags: list[str] = None) -> list[dict]:
    """
    Search recipes with boolean tag logic.
    tags      = OR  (match any)
    and_tags  = AND (must match all)
    not_tags  = NOT (must not have any)
    """
    with get_connection() as conn:
        # Start with all recipes, filter down
        base = """
            SELECT DISTINCT r.id, r.name, r.url, r.created_at
            FROM recipes r
        """
        conditions = []
        params = []

        # OR tags — recipe must have at least one
        if tags:
            placeholders = ",".join("?" * len(tags))
            base += f"""
                JOIN recipe_tags rt_or ON rt_or.recipe_id = r.id
                JOIN tags t_or ON t_or.id = rt_or.tag_id AND t_or.name IN ({placeholders})
            """
            params.extend(tags)

        # Name search
        if query:
            conditions.append("r.name LIKE ?")
            params.append(f"%{query}%")

        # AND tags — recipe must have every one
        if and_tags:
            for tag in and_tags:
                conditions.append("""
                    EXISTS (
                        SELECT 1 FROM recipe_tags rt_a
                        JOIN tags t_a ON t_a.id = rt_a.tag_id
                        WHERE rt_a.recipe_id = r.id AND t_a.name = ?
                    )
                """)
                params.append(tag)

        # NOT tags — recipe must have none of these
        if not_tags:
            placeholders = ",".join("?" * len(not_tags))
            conditions.append(f"""
                NOT EXISTS (
                    SELECT 1 FROM recipe_tags rt_n
                    JOIN tags t_n ON t_n.id = rt_n.tag_id
                    WHERE rt_n.recipe_id = r.id AND t_n.name IN ({placeholders})
                )
            """)
            params.extend(not_tags)

        if conditions:
            base += " WHERE " + " AND ".join(conditions)
        base += " ORDER BY r.name"

        rows = conn.execute(base, params).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["tags"] = [
                t["name"] for t in conn.execute(
                    """SELECT t.name FROM tags t
                       JOIN recipe_tags rt ON rt.tag_id=t.id
                       WHERE rt.recipe_id=?""",
                    (r["id"],)
                )
            ]
            results.append(r)
        return results


def all_recipes_brief() -> list[dict]:
    return search_recipes()


# ── Meal Plan ─────────────────────────────────────────────────────────────────

def get_week_plan(monday: date) -> dict:
    """Returns {date_str: {meal_type: recipe_dict_or_None}}"""
    week = {str(monday + timedelta(days=i)): {} for i in range(7)}
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT mp.plan_date, mp.meal_type, r.id, r.name
               FROM meal_plan mp
               LEFT JOIN recipes r ON r.id = mp.recipe_id
               WHERE mp.plan_date BETWEEN ? AND ?""",
            (str(monday), str(monday + timedelta(days=6)))
        ).fetchall()
        for row in rows:
            week[row["plan_date"]][row["meal_type"]] = (
                {"id": row["id"], "name": row["name"]} if row["id"] else None
            )
    return week


def set_meal(plan_date: str, meal_type: str, recipe_id: Optional[int]):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO meal_plan (plan_date, meal_type, recipe_id)
               VALUES (?,?,?)
               ON CONFLICT(plan_date, meal_type) DO UPDATE SET recipe_id=excluded.recipe_id""",
            (plan_date, meal_type, recipe_id)
        )


def suggest_meals_for_week(monday: date, meal_type: str = "dinner") -> list[Optional[dict]]:
    """
    For each day, suggest a recipe based on past usage frequency,
    avoiding repeats within the same week.
    """
    with get_connection() as conn:
        # Get frequency of past use, most-used first
        rows = conn.execute(
            """SELECT r.id, r.name, COUNT(mp.id) as freq
               FROM recipes r
               LEFT JOIN meal_plan mp ON mp.recipe_id = r.id AND mp.meal_type=?
               GROUP BY r.id
               ORDER BY freq DESC, RANDOM()""",
            (meal_type,)
        ).fetchall()

    pool = [{"id": r["id"], "name": r["name"]} for r in rows]
    suggestions = []
    used_ids = set()
    for _ in range(7):
        for candidate in pool:
            if candidate["id"] not in used_ids:
                suggestions.append(candidate)
                used_ids.add(candidate["id"])
                break
        else:
            suggestions.append(None)
    return suggestions


# ── Shopping List ─────────────────────────────────────────────────────────────

def get_shopping_list(monday: date) -> list[dict]:
    """Return all ingredients for all recipes in the week's meal plan."""
    end = monday + timedelta(days=6)
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT r.name as recipe_name, i.item, i.quantity, i.unit
               FROM meal_plan mp
               JOIN recipes r ON r.id = mp.recipe_id
               JOIN ingredients i ON i.recipe_id = r.id
               WHERE mp.plan_date BETWEEN ? AND ?
               ORDER BY i.item""",
            (str(monday), str(end))
        ).fetchall()
        return [dict(r) for r in rows]


# ── Seed demo data ────────────────────────────────────────────────────────────

def seed_demo_data():
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    if count > 0:
        return

    recipes = [
        {
            "name": "Slow Cooker Chicken Tacos",
            "url": "https://example.com/chicken-tacos",
            "body": "",
            "notes": "Great for meal prep",
            "ingredients": [
                {"item": "Chicken thighs", "quantity": "2", "unit": "lb"},
                {"item": "Taco seasoning", "quantity": "2", "unit": "tbsp"},
                {"item": "Salsa", "quantity": "1", "unit": "cup"},
                {"item": "Tortillas", "quantity": "8", "unit": ""},
                {"item": "Lime", "quantity": "1", "unit": ""},
            ],
            "tags": ["crockpot", "dinner", "quick", "mexican"],
        },
        {
            "name": "Spaghetti Aglio e Olio",
            "url": "",
            "body": "Boil spaghetti. In a pan, slowly cook sliced garlic in olive oil until golden. Add chili flakes. Toss with pasta and parsley.",
            "notes": "Ready in 20 minutes",
            "ingredients": [
                {"item": "Spaghetti", "quantity": "400", "unit": "g"},
                {"item": "Garlic cloves", "quantity": "6", "unit": ""},
                {"item": "Olive oil", "quantity": "1/3", "unit": "cup"},
                {"item": "Red chili flakes", "quantity": "1", "unit": "tsp"},
                {"item": "Fresh parsley", "quantity": "1/4", "unit": "cup"},
            ],
            "tags": ["dinner", "quick", "one-pot", "vegetarian"],
        },
        {
            "name": "Black Bean Soup",
            "url": "https://example.com/black-bean-soup",
            "body": "",
            "notes": "Freeze leftovers well",
            "ingredients": [
                {"item": "Black beans", "quantity": "2", "unit": "cans"},
                {"item": "Vegetable broth", "quantity": "4", "unit": "cups"},
                {"item": "Onion", "quantity": "1", "unit": ""},
                {"item": "Cumin", "quantity": "1", "unit": "tsp"},
                {"item": "Garlic", "quantity": "3", "unit": "cloves"},
            ],
            "tags": ["dinner", "vegan", "one-pot", "crockpot"],
        },
        {
            "name": "Sheet Pan Salmon & Veggies",
            "url": "https://example.com/sheet-pan-salmon",
            "body": "",
            "notes": "",
            "ingredients": [
                {"item": "Salmon fillets", "quantity": "4", "unit": ""},
                {"item": "Broccoli florets", "quantity": "2", "unit": "cups"},
                {"item": "Cherry tomatoes", "quantity": "1", "unit": "cup"},
                {"item": "Olive oil", "quantity": "2", "unit": "tbsp"},
                {"item": "Lemon", "quantity": "1", "unit": ""},
            ],
            "tags": ["dinner", "quick", "healthy"],
        },
        {
            "name": "Vegetable Stir Fry",
            "url": "",
            "body": "Heat wok with oil. Add vegetables in order of cooking time. Add soy sauce, ginger, garlic. Serve over rice.",
            "notes": "Use any vegetables on hand",
            "ingredients": [
                {"item": "Mixed vegetables", "quantity": "4", "unit": "cups"},
                {"item": "Soy sauce", "quantity": "3", "unit": "tbsp"},
                {"item": "Ginger", "quantity": "1", "unit": "tsp"},
                {"item": "Garlic", "quantity": "2", "unit": "cloves"},
                {"item": "Sesame oil", "quantity": "1", "unit": "tsp"},
                {"item": "Cooked rice", "quantity": "2", "unit": "cups"},
            ],
            "tags": ["dinner", "quick", "vegan", "one-pot"],
        },
    ]

    for r in recipes:
        add_recipe(r["name"], r["url"], r["body"], r["notes"],
                   r["ingredients"], r["tags"])


# ── Tag management ────────────────────────────────────────────────────────────

def delete_tag(tag_name: str):
    """Delete a tag and remove it from all recipes."""
    with get_connection() as conn:
        conn.execute("DELETE FROM tags WHERE name=?", (tag_name,))


def rename_tag(old_name: str, new_name: str):
    """
    Rename a tag. If new_name already exists, merge (reassign all recipes
    from old tag to the existing new tag, then delete old).
    """
    new_name = new_name.strip().lower()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM tags WHERE name=?", (new_name,)
        ).fetchone()
        old_row = conn.execute(
            "SELECT id FROM tags WHERE name=?", (old_name,)
        ).fetchone()
        if not old_row:
            return
        old_id = old_row["id"]

        if existing:
            new_id = existing["id"]
            # Move any recipe_tags from old to new (skip duplicates)
            conn.execute("""
                UPDATE OR IGNORE recipe_tags SET tag_id=? WHERE tag_id=?
            """, (new_id, old_id))
            conn.execute("DELETE FROM recipe_tags WHERE tag_id=?", (old_id,))
            conn.execute("DELETE FROM tags WHERE id=?", (old_id,))
        else:
            conn.execute(
                "UPDATE tags SET name=? WHERE id=?", (new_name, old_id)
            )


def tag_usage_counts() -> list[dict]:
    """Return all tags with how many recipes use each."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT t.name, COUNT(rt.recipe_id) as count
            FROM tags t
            LEFT JOIN recipe_tags rt ON rt.tag_id = t.id
            GROUP BY t.id
            ORDER BY t.name
        """).fetchall()
        return [dict(r) for r in rows]


# ── JSON export / import ──────────────────────────────────────────────────────

import json as _json

def export_to_json(path: str):
    """Export all recipes to a JSON file."""
    recipes = []
    for brief in all_recipes_brief():
        r = get_recipe(brief["id"])
        recipes.append({
            "name":        r["name"],
            "url":         r.get("url", ""),
            "body":        r.get("body", ""),
            "notes":       r.get("notes", ""),
            "tags":        r.get("tags", []),
            "ingredients": r.get("ingredients", []),
            "created_at":  r.get("created_at", ""),
        })
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({"version": 1, "recipes": recipes}, f, indent=2, ensure_ascii=False)


def load_json_recipes(path: str) -> list[dict]:
    """
    Load recipes from a JSON export file.
    Returns a list of recipe dicts ready for the import preview dialog.
    Raises ValueError for unrecognised file formats.
    """
    with open(path, encoding="utf-8") as f:
        data = _json.load(f)

    # Support both {version, recipes:[...]} and bare [...]
    if isinstance(data, list):
        recipes = data
    elif isinstance(data, dict) and "recipes" in data:
        recipes = data["recipes"]
    else:
        raise ValueError("Unrecognised JSON format — expected a list of recipes "
                         "or {\"version\": 1, \"recipes\": [...]}")

    result = []
    for r in recipes:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        # Normalise ingredient dicts
        ings = []
        for ing in r.get("ingredients", []):
            if isinstance(ing, str):
                ings.append({"item": ing, "quantity": "", "unit": ""})
            elif isinstance(ing, dict):
                ings.append({
                    "item":     ing.get("item", ""),
                    "quantity": ing.get("quantity", ""),
                    "unit":     ing.get("unit", ""),
                })
        result.append({
            "name":        r.get("name", "").strip(),
            "url":         r.get("url", ""),
            "body":        r.get("body", ""),
            "notes":       r.get("notes", ""),
            "tags":        r.get("tags", []),
            "ingredients": ings,
            "_source_file": path,
        })
    return result
