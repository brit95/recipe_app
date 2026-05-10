"""
latex_importer.py
Parses .tex recipe files in the user's existing format and returns
structured recipe dicts compatible with the database schema.

Handles both single-file and batch (folder) imports.
"""

from __future__ import annotations
import os
import re
from pathlib import Path


# ── LaTeX unescape ─────────────────────────────────────────────────────────────

_UNESCAPE = [
    # Special characters
    (r"\\&",                        "&"),
    (r"\\%",                        "%"),
    (r"\\\$",                       "$"),
    (r"\\#",                        "#"),
    (r"\\_",                        "_"),
    (r"\\{",                        "{"),
    (r"\\}",                        "}"),
    (r"\\textasciitilde\{\}",       "~"),
    (r"\\textasciicircum\{\}",      "^"),
    (r"\\textbackslash\{\}",        "\\"),
    # Degree symbols
    (r"\\degree\b",                 "°"),
    (r"\\textdegree\b",             "°"),
    (r"\^\\circ\b",                 "°"),
    # Fractions — \frac{n}{d} → n/d
    (r"\\frac\{(\d+)\}\{(\d+)\}",  r"\1/\2"),
    # Math mode — strip $ delimiters, keep content
    (r"\$([^$]+)\$",               r"\1"),
    # Text commands
    (r"\\url\{([^}]+)\}",          r"\1"),
    (r"\\emph\{([^}]+)\}",         r"\1"),
    (r"\\textbf\{([^}]+)\}",       r"\1"),
    (r"\\textit\{([^}]+)\}",       r"\1"),
    (r"\\textonehalf\b",            "1/2"),
    (r"\\textonequarter\b",         "1/4"),
    (r"\\textthreequarters\b",      "3/4"),
    # Dashes
    (r"---",                        "—"),
    (r"--",                         "–"),
    # Quotes
    (r"``",                         "\u201c"),
    (r"''",                         "\u201d"),
    (r"`",                          "\u2018"),
    (r"'(?=[^s ])",                 "\u2019"),
    # Spaces / misc
    (r"\\,",                        " "),
    (r"~",                          " "),
    (r"\\ ",                        " "),
]

def _unescape(text: str) -> str:
    for pattern, repl in _UNESCAPE:
        try:
            text = re.sub(pattern, repl, text)
        except re.error:
            pass
    return text.strip()


def _strip_comments(text: str) -> str:
    """Remove LaTeX % comments (but not escaped backslash-percent)."""
    lines = []
    for line in text.splitlines():
        result = []
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == chr(92) and i + 1 < len(line):
                result.append(ch)
                result.append(line[i + 1])
                i += 2
            elif ch == '%':
                break
            else:
                result.append(ch)
                i += 1
        lines.append("".join(result))
    return "\n".join(lines)


def _clean(text: str) -> str:
    # Insert space between a digit and an immediately following $\frac
    # e.g. 1$\frac{1}{3}$ -> 1 $\frac{1}{3}$
    text = re.sub(r"(\d)\s*\$\s*\\frac\b", r"\1 $\\frac", text)
    return re.sub(r"\s+", " ", _unescape(text)).strip()


# ── List extractors ────────────────────────────────────────────────────────────

def _extract_list_items(block: str) -> list[str]:
    """Extract \\item contents from an itemize or enumerate block."""
    # Split on \item, skip the first empty chunk
    parts = re.split(r"\\item\b", block)
    items = []
    for part in parts[1:]:
        # Trim to end of this item (stop before next \item or \end)
        item_text = re.split(r"\\item\b|\\end\b", part)[0]
        cleaned = _clean(item_text)
        if cleaned:
            items.append(cleaned)
    return items


# ── Ingredient line parser (reuse logic from web_importer) ────────────────────

_UNITS = {
    "teaspoon", "teaspoons", "tsp", "tablespoon", "tablespoons", "tbsp",
    "cup", "cups", "ounce", "ounces", "oz", "pound", "pounds", "lb", "lbs",
    "gram", "grams", "g", "kilogram", "kilograms", "kg",
    "milliliter", "milliliters", "ml", "liter", "liters", "l",
    "pinch", "dash", "handful", "clove", "cloves", "slice", "slices",
    "can", "cans", "package", "packages", "pkg", "pint", "pints",
    "quart", "quarts", "gallon", "gallons", "piece", "pieces",
    "sprig", "sprigs", "stalk", "stalks", "head", "heads",
    "bunch", "bunches", "strip", "strips",
}

_FRACTION_MAP = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4",
                 "¾": "3/4", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}

def _norm_fractions(text: str) -> str:
    for uf, asc in _FRACTION_MAP.items():
        text = text.replace(uf, asc)
    return text

def _parse_ingredient(line: str) -> dict:
    line = _norm_fractions(line.strip())
    tokens = line.split()
    if not tokens:
        return {"quantity": "", "unit": "", "item": line}
    qty_parts, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[\d/\.]+$", t) or re.match(r"^\d+-\d+/\d+$", t):
            qty_parts.append(t.replace("-", " "))
            i += 1
        else:
            break
    quantity = " ".join(qty_parts)
    unit = ""
    if i < len(tokens) and tokens[i].lower().rstrip(".") in _UNITS:
        unit = tokens[i]
        i += 1
    item = " ".join(tokens[i:])
    return {"quantity": quantity, "unit": unit, "item": item}


# ── Core parser ────────────────────────────────────────────────────────────────

def parse_tex_recipe(tex: str, source_path: str = "") -> dict:
    """
    Parse a single .tex recipe snippet or full file.
    Returns a recipe dict with keys: name, url, body, notes, ingredients, tags.
    """
    # Strip comments for parsing (keep original for fallback)
    text = _strip_comments(tex)

    # ── Name ──────────────────────────────────────────────────────
    name = ""
    m = re.search(r"\\subsection\{([^}]+)\}", text)
    if m:
        name = _clean(m.group(1))

    # ── Source / URL ──────────────────────────────────────────────
    url = ""
    # Look for \url{...} or "Source: ..." line
    url_m = re.search(r"\\url\{([^}]+)\}", tex)
    if url_m:
        url = url_m.group(1).strip()
    elif re.search(r"Source:\s*(https?://\S+)", tex):
        url = re.search(r"Source:\s*(https?://\S+)", tex).group(1).strip()

    # ── graphicspath → category tag ───────────────────────────────
    gp_tag = ""
    gp_m = re.search(r"\\graphicspath\{\{([^/}]+)/?", text)
    if gp_m:
        gp_tag = gp_m.group(1).strip().lower()

    # ── Ingredients ───────────────────────────────────────────────
    ingredients: list[dict] = []
    ing_block_m = re.search(
        r"\\subsubsection\{Ingredients?\}(.*?)(?=\\subsubsection|\\subsection|$)",
        text, re.DOTALL | re.IGNORECASE
    )
    if ing_block_m:
        itemize_m = re.search(
            r"\\begin\{itemize\}(.*?)\\end\{itemize\}",
            ing_block_m.group(1), re.DOTALL
        )
        if itemize_m:
            for item_text in _extract_list_items(itemize_m.group(1)):
                ingredients.append(_parse_ingredient(item_text))

    # ── Instructions ──────────────────────────────────────────────
    body = ""
    inst_block_m = re.search(
        r"\\subsubsection\{Instructions?\}(.*?)(?=\\subsubsection|\\subsection|$)",
        text, re.DOTALL | re.IGNORECASE
    )
    if inst_block_m:
        enum_m = re.search(
            r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}",
            inst_block_m.group(1), re.DOTALL
        )
        if enum_m:
            steps = _extract_list_items(enum_m.group(1))
            body = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))

    # ── Notes ─────────────────────────────────────────────────────
    notes = ""
    notes_block_m = re.search(
        r"\\subsubsection\{Notes?\}(.*?)(?=\\subsubsection|\\subsection|$)",
        text, re.DOTALL | re.IGNORECASE
    )
    if notes_block_m:
        raw_notes = notes_block_m.group(1).strip()
        # Strip environment wrappers
        raw_notes = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", "", raw_notes)
        # If notes contain \item entries, format as bullet lines
        if r"\item" in raw_notes:
            parts = re.split(r"\\item\b", raw_notes)
            note_lines = [_clean(p) for p in parts if _clean(p)]
            notes = "\n".join(f"• {line}" for line in note_lines)
        else:
            notes = _clean(raw_notes)

    # ── Tags ──────────────────────────────────────────────────────
    tags = []
    if gp_tag and gp_tag not in ("recipes", "images", "figures"):
        tags.append(gp_tag)

    # Also check for % Tags: comment in original tex
    tag_comment_m = re.search(r"%\s*[Tt]ags?:\s*(.+)", tex)
    if tag_comment_m:
        extra = [t.strip() for t in tag_comment_m.group(1).split(",") if t.strip()]
        for t in extra:
            if t not in tags:
                tags.append(t)

    return {
        "name": name or (Path(source_path).stem.replace("_", " ").title() if source_path else "Imported Recipe"),
        "url": url,
        "body": body,
        "notes": notes,
        "ingredients": ingredients,
        "tags": tags,
        "_source_file": os.path.basename(source_path) if source_path else "",
    }


# ── Multi-recipe file support ─────────────────────────────────────────────────

def parse_tex_file(path: str) -> list[dict]:
    """
    Parse a .tex file. If it contains multiple \\subsection blocks,
    returns one recipe dict per subsection. Otherwise returns one dict.
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Split on \subsection to handle multi-recipe files
    parts = re.split(r"(?=\\subsection\{)", content)
    results = []
    for part in parts:
        part = part.strip()
        if not part or "\\subsection" not in part:
            continue
        recipe = parse_tex_recipe(part, source_path=path)
        if recipe["name"]:
            # Infer extra tag from parent folder name
            folder = os.path.basename(os.path.dirname(os.path.abspath(path))).lower()
            if folder and folder not in ("recipes", "tex", "latex", "src", "."):
                if folder not in recipe["tags"]:
                    recipe["tags"].insert(0, folder)
            results.append(recipe)

    if not results:
        # No \subsection found — try parsing the whole file as one recipe
        recipe = parse_tex_recipe(content, source_path=path)
        folder = os.path.basename(os.path.dirname(os.path.abspath(path))).lower()
        if folder and folder not in ("recipes", "tex", "latex", "src", "."):
            if folder not in recipe["tags"]:
                recipe["tags"].insert(0, folder)
        results.append(recipe)

    return results


def parse_tex_folder(folder_path: str) -> list[dict]:
    """
    Recursively find all .tex files under folder_path and parse them.
    Returns a flat list of recipe dicts, each with '_source_file' set.
    """
    all_recipes = []
    for root, _dirs, files in os.walk(folder_path):
        for fname in sorted(files):
            if fname.lower().endswith(".tex"):
                full_path = os.path.join(root, fname)
                try:
                    recipes = parse_tex_file(full_path)
                    # Tag with relative subfolder name too
                    rel_dir = os.path.relpath(root, folder_path).lower()
                    for r in recipes:
                        if rel_dir not in (".", "") and rel_dir not in r["tags"]:
                            r["tags"].insert(0, rel_dir)
                    all_recipes.extend(recipes)
                except Exception as e:
                    all_recipes.append({
                        "name": f"⚠ Parse error: {fname}",
                        "url": "", "body": "", "notes": str(e),
                        "ingredients": [], "tags": [],
                        "_source_file": fname,
                        "_error": True,
                    })
    return all_recipes
