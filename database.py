import sqlite3
import os
import sys
import shutil
from datetime import date, timedelta
from typing import Optional

# ── Database location ─────────────────────────────────────────────
# When running from source, use a SQLite file inside the repo (preferring the
# existing `.recipe_manager.db` which has the full recipe history).
#
# When running as a PyInstaller `--onefile` executable, `__file__` points
# inside a temp extraction dir (sys._MEIPASS) that is wiped on exit, so we
# instead place the writable DB next to the .exe and copy a bundled seed DB
# on first launch.
def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _resource_path(name: str) -> str:
    """Resolve a read-only resource path inside the PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base, name)


def _resolve_db_path() -> str:
    if _is_frozen():
        exe_dir = os.path.dirname(sys.executable)
        # Try to keep the DB next to the executable (portable / USB-stick
        # friendly). If that folder isn't writable (e.g. user installed the
        # binary to /usr/local/bin or Program Files), fall back to a
        # per-user data directory.
        target_dir = exe_dir
        if not os.access(exe_dir, os.W_OK):
            if sys.platform.startswith("win"):
                base = os.environ.get("APPDATA") or os.path.expanduser("~")
            elif sys.platform == "darwin":
                base = os.path.expanduser("~/Library/Application Support")
            else:
                base = os.environ.get(
                    "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
                )
            target_dir = os.path.join(base, "RecipeManager")
            os.makedirs(target_dir, exist_ok=True)

        target = os.path.join(target_dir, "recipe_manager.db")
        if not os.path.exists(target):
            # Seed from a DB packaged with the executable, if present.
            for candidate in (".recipe_manager.db", "recipe_manager.db"):
                seed = _resource_path(candidate)
                if os.path.exists(seed):
                    try:
                        shutil.copyfile(seed, target)
                    except OSError:
                        pass
                    break
        return target

    # Running from source: prefer the hidden DB in the repo.
    repo_dir = os.path.dirname(__file__)
    hidden = os.path.join(repo_dir, ".recipe_manager.db")
    default = os.path.join(repo_dir, "recipe_manager.db")
    return hidden if os.path.exists(hidden) else default


DB_PATH = _resolve_db_path()


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


# ── Deduplication ─────────────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Normalize a recipe name for duplicate detection."""
    return " ".join((name or "").strip().lower().split())


def find_duplicate_groups() -> list[dict]:
    """
    Group recipes that share a normalized name. Returns a list of groups, each:
        {
            "name": <display name of first variant>,
            "key":  <normalized name>,
            "recipes": [
                {"id", "name", "url", "created_at",
                 "ingredient_count", "tag_count", "body_len", "notes_len"},
                ...
            ]
        }
    Only groups with 2+ recipes are included. Groups are ordered alphabetically.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT r.id, r.name, r.url, r.created_at,
                   COALESCE(LENGTH(r.body),  0) AS body_len,
                   COALESCE(LENGTH(r.notes), 0) AS notes_len,
                   (SELECT COUNT(*) FROM ingredients i WHERE i.recipe_id = r.id) AS ingredient_count,
                   (SELECT COUNT(*) FROM recipe_tags rt WHERE rt.recipe_id = r.id) AS tag_count
            FROM recipes r
            ORDER BY r.name COLLATE NOCASE, r.id
        """).fetchall()

    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = _normalize_name(row["name"])
        if not key:
            continue
        groups.setdefault(key, []).append(dict(row))

    out = []
    for key, recipes in groups.items():
        if len(recipes) < 2:
            continue
        out.append({
            "name": recipes[0]["name"],
            "key":  key,
            "recipes": recipes,
        })
    out.sort(key=lambda g: g["name"].lower())
    return out


def _pick_keeper(recipes: list[dict]) -> int:
    """
    Pick the 'best' recipe id to keep from a duplicate group.
    Heuristic: most ingredients → most tags → longest body → longest notes
    → has URL → smallest id (oldest).
    """
    def score(r):
        return (
            r.get("ingredient_count", 0),
            r.get("tag_count", 0),
            r.get("body_len", 0),
            r.get("notes_len", 0),
            1 if (r.get("url") or "").strip() else 0,
            -int(r["id"]),  # prefer smaller id as final tiebreak
        )
    return max(recipes, key=score)["id"]


def dedupe_recipes(dry_run: bool = False) -> dict:
    """
    Remove duplicate recipes (grouped by normalized name).

    Strategy per group:
      - Pick a 'keeper' (richest recipe; see _pick_keeper).
      - Reassign meal_plan rows that reference duplicates to the keeper.
      - Merge tags from duplicates onto the keeper.
      - Delete the duplicate recipe rows (ingredients/tags cascade).

    Returns a summary:
        {
            "groups": <int>,            # number of duplicate groups found
            "duplicates_removed": <int>,
            "kept": [<keeper_id>, ...],
            "removed": [<deleted_id>, ...],
            "dry_run": <bool>,
        }
    """
    groups = find_duplicate_groups()
    summary = {
        "groups": len(groups),
        "duplicates_removed": 0,
        "kept": [],
        "removed": [],
        "dry_run": dry_run,
    }
    if not groups:
        return summary

    with get_connection() as conn:
        for grp in groups:
            keeper_id = _pick_keeper(grp["recipes"])
            dup_ids = [r["id"] for r in grp["recipes"] if r["id"] != keeper_id]
            summary["kept"].append(keeper_id)
            summary["removed"].extend(dup_ids)
            summary["duplicates_removed"] += len(dup_ids)

            if dry_run or not dup_ids:
                continue

            placeholders = ",".join("?" * len(dup_ids))

            # Reassign meal-plan references → keeper (ignore conflicts on UNIQUE)
            conn.execute(
                f"""UPDATE OR IGNORE meal_plan
                       SET recipe_id = ?
                     WHERE recipe_id IN ({placeholders})""",
                (keeper_id, *dup_ids),
            )
            # Any meal-plan rows that couldn't be reassigned (UNIQUE conflict)
            # still point at a soon-to-be-deleted recipe. Cascade will set them
            # to NULL via the existing FK (ON DELETE SET NULL).

            # Merge tags from duplicates onto the keeper
            conn.execute(
                f"""INSERT OR IGNORE INTO recipe_tags (recipe_id, tag_id)
                       SELECT ?, tag_id FROM recipe_tags
                        WHERE recipe_id IN ({placeholders})""",
                (keeper_id, *dup_ids),
            )

            # Delete duplicates (ingredients + recipe_tags cascade)
            conn.execute(
                f"DELETE FROM recipes WHERE id IN ({placeholders})",
                dup_ids,
            )

    return summary
