"""
web_importer.py
Imports a recipe from a URL into a structured dict that matches
the add_recipe_tab / database schema.

Primary strategy:  recipe-scrapers (handles 300+ sites natively)
Fallback strategy: raw HTML + heuristic parsing
"""

from __future__ import annotations
import re
import urllib.request
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RecipeManager/1.0)"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    # Detect encoding from headers or default to utf-8
    content_type = resp.headers.get_content_charset("utf-8")
    return raw.decode(content_type, errors="replace")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ── Ingredient parser ──────────────────────────────────────────────────────────

_UNITS = {
    "teaspoon", "teaspoons", "tsp", "tablespoon", "tablespoons", "tbsp",
    "cup", "cups", "c", "ounce", "ounces", "oz", "pound", "pounds", "lb", "lbs",
    "gram", "grams", "g", "kilogram", "kilograms", "kg",
    "milliliter", "milliliters", "ml", "liter", "liters", "l",
    "pinch", "dash", "handful", "clove", "cloves", "slice", "slices",
    "can", "cans", "package", "packages", "pkg", "pint", "pints", "quart", "quarts",
    "gallon", "gallons", "piece", "pieces", "sprig", "sprigs", "stalk", "stalks",
    "head", "heads", "bunch", "bunches", "strip", "strips",
}

_FRACTION_MAP = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
                 "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}

def _normalize_fractions(text: str) -> str:
    for uf, asc in _FRACTION_MAP.items():
        text = text.replace(uf, asc)
    return text


def parse_ingredient_line(line: str) -> dict:
    """
    Split 'qty unit item' into structured fields.
    Returns {"quantity": str, "unit": str, "item": str}
    """
    line = _normalize_fractions(line.strip())
    tokens = line.split()
    if not tokens:
        return {"quantity": "", "unit": "", "item": line}

    qty_parts = []
    i = 0

    # Collect numeric / fraction tokens
    while i < len(tokens):
        t = tokens[i]
        # Pure number or fraction like "1/2"
        if re.match(r"^[\d/\.]+$", t):
            qty_parts.append(t)
            i += 1
        # "1-1/2" style
        elif re.match(r"^\d+-\d+/\d+$", t):
            qty_parts.append(t.replace("-", " "))
            i += 1
        else:
            break

    quantity = " ".join(qty_parts)

    # Next token might be a unit
    unit = ""
    if i < len(tokens) and tokens[i].lower().rstrip(".") in _UNITS:
        unit = tokens[i]
        i += 1

    item = " ".join(tokens[i:])
    return {"quantity": quantity, "unit": unit, "item": item}


# ── recipe-scrapers strategy ───────────────────────────────────────────────────

def _scrape_with_library(url: str) -> Optional[dict]:
    try:
        from recipe_scrapers import scrape_me
        scraper = scrape_me(url)

        name = scraper.title() or ""
        try:
            ingredients_raw = scraper.ingredients()
        except Exception:
            ingredients_raw = []

        try:
            instructions = scraper.instructions() or ""
        except Exception:
            instructions = ""

        try:
            yields = scraper.yields() or ""
        except Exception:
            yields = ""

        try:
            host = scraper.host() or ""
        except Exception:
            host = url

        notes = f"Yields: {yields}" if yields else ""

        return {
            "name": _clean(name),
            "url": url,
            "source": host,
            "body": instructions,
            "notes": notes,
            "ingredients": [parse_ingredient_line(i) for i in ingredients_raw if i.strip()],
            "tags": [],
        }
    except ImportError:
        return None
    except Exception:
        return None


# ── JSON-LD / schema.org fallback ──────────────────────────────────────────────

def _scrape_jsonld(html: str, url: str) -> Optional[dict]:
    """Extract recipe from schema.org/Recipe JSON-LD blocks."""
    import json

    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE
    )
    for m in pattern.finditer(html):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue

        # Unwrap @graph arrays
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict) and "@graph" in data:
            candidates = data["@graph"]
        else:
            candidates = [data]

        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            rtype = obj.get("@type", "")
            if isinstance(rtype, list):
                is_recipe = any("Recipe" in str(t) for t in rtype)
            else:
                is_recipe = "Recipe" in str(rtype)
            if not is_recipe:
                continue

            name = obj.get("name", "")
            yields = obj.get("recipeYield", "")
            if isinstance(yields, list):
                yields = ", ".join(str(y) for y in yields)

            # Ingredients
            raw_ings = obj.get("recipeIngredient", [])
            ingredients = [parse_ingredient_line(i) for i in raw_ings if i.strip()]

            # Instructions
            inst_raw = obj.get("recipeInstructions", "")
            if isinstance(inst_raw, str):
                instructions = inst_raw
            elif isinstance(inst_raw, list):
                parts = []
                for step in inst_raw:
                    if isinstance(step, str):
                        parts.append(step)
                    elif isinstance(step, dict):
                        parts.append(step.get("text", ""))
                instructions = "\n".join(p for p in parts if p)
            else:
                instructions = ""

            notes_parts = []
            if yields:
                notes_parts.append(f"Yields: {yields}")
            desc = obj.get("description", "")
            if desc:
                notes_parts.append(_clean(desc)[:200])

            return {
                "name": _clean(name),
                "url": url,
                "source": "",
                "body": _clean(instructions),
                "notes": "  |  ".join(notes_parts),
                "ingredients": ingredients,
                "tags": [],
            }
    return None


# ── Heuristic HTML fallback ───────────────────────────────────────────────────

def _strip_tags(html_fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", html_fragment)


def _scrape_heuristic(html: str, url: str) -> dict:
    """Last-resort: grab <li> items from the longest <ul> as ingredients."""
    # Title
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    name = _clean(_strip_tags(title_m.group(1))) if title_m else "Imported Recipe"

    # Find all <ul> blocks and pick the longest one as the ingredient list
    ul_blocks = re.findall(r"<ul[^>]*>(.*?)</ul>", html, re.DOTALL | re.IGNORECASE)
    best_ings: list[str] = []
    for block in ul_blocks:
        items = re.findall(r"<li[^>]*>(.*?)</li>", block, re.DOTALL | re.IGNORECASE)
        cleaned = [_clean(_strip_tags(i)) for i in items if _strip_tags(i).strip()]
        if len(cleaned) > len(best_ings):
            best_ings = cleaned

    ingredients = [parse_ingredient_line(i) for i in best_ings]

    # Instructions: grab longest <ol>
    ol_blocks = re.findall(r"<ol[^>]*>(.*?)</ol>", html, re.DOTALL | re.IGNORECASE)
    steps: list[str] = []
    for block in ol_blocks:
        items = re.findall(r"<li[^>]*>(.*?)</li>", block, re.DOTALL | re.IGNORECASE)
        cleaned = [_clean(_strip_tags(i)) for i in items if _strip_tags(i).strip()]
        if len(cleaned) > len(steps):
            steps = cleaned

    body = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else ""

    return {
        "name": name,
        "url": url,
        "source": "",
        "body": body,
        "notes": "Imported via heuristic parser — please review and edit.",
        "ingredients": ingredients,
        "tags": [],
    }


# ── Public API ────────────────────────────────────────────────────────────────

def import_from_url(url: str) -> dict:
    """
    Import a recipe from a URL.
    Returns a dict with keys: name, url, body, notes, ingredients (list of dicts), tags.
    Raises ValueError with a user-friendly message on failure.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Strategy 1: recipe-scrapers library
    result = _scrape_with_library(url)
    if result and result.get("name"):
        return result

    # Strategy 2: fetch HTML ourselves and try JSON-LD
    try:
        html = _fetch_html(url)
    except Exception as e:
        raise ValueError(f"Could not fetch URL:\n{e}") from e

    result = _scrape_jsonld(html, url)
    if result and result.get("name"):
        return result

    # Strategy 3: heuristic
    result = _scrape_heuristic(html, url)
    return result
