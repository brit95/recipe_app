"""
latex_exporter.py
Exports a recipe from the database to a .tex file matching the user's
existing recipe book format.
"""

from __future__ import annotations
import re
import os


# ── LaTeX escaping ─────────────────────────────────────────────────────────────

_LATEX_SPECIAL = {
    "&":  r"\&",
    "%":  r"\%",
    "$":  r"\$",
    "#":  r"\#",
    "_":  r"\_",
    "{":  r"\{",
    "}":  r"\}",
    "~":  r"\textasciitilde{}",
    "^":  r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}

def _escape(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    result = []
    for ch in text:
        result.append(_LATEX_SPECIAL.get(ch, ch))
    return "".join(result)


# ── Label helpers ─────────────────────────────────────────────────────────────

def _make_label(name: str) -> str:
    """Convert a recipe name to a LaTeX label like 'belgian_waffles'."""
    label = name.lower().strip()
    label = re.sub(r"[^a-z0-9\s]", "", label)
    label = re.sub(r"\s+", "_", label)
    return label


def _make_graphicspath(tags: list[str]) -> str:
    """
    Infer a subfolder from tags (breakfast, lunch, dinner, dessert, etc.)
    matching the convention {{category/}} used in the example file.
    """
    categories = {"breakfast", "lunch", "dinner", "dessert", "snack",
                  "appetizer", "soup", "salad", "bread", "drink", "sauce"}
    for tag in tags:
        if tag.lower() in categories:
            return tag.lower()
    return "recipes"


# ── Instruction formatting ────────────────────────────────────────────────────

def _instructions_to_enumerate(body: str) -> str:
    """
    Convert a body string to LaTeX \\enumerate items.
    Handles numbered lists (1. step), bullet lines, or bare paragraphs.
    """
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    items = []
    for line in lines:
        # Strip leading numbering like "1." or "1)"
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        # Strip bullet characters
        line = re.sub(r"^[-•*]\s*", "", line)
        if line:
            items.append(_escape(line))
    if not items:
        return "    \\item (no instructions provided)"
    return "\n".join(f"    \\item {item}" for item in items)


# ── Main exporter ──────────────────────────────────────────────────────────────

def recipe_to_latex(recipe: dict) -> str:
    """
    Convert a recipe dict (from db.get_recipe) to a LaTeX string
    matching the user's existing recipe book format.
    """
    name    = recipe.get("name", "Untitled Recipe")
    url     = recipe.get("url", "")
    body    = recipe.get("body", "")
    notes   = recipe.get("notes", "")
    ings    = recipe.get("ingredients", [])
    tags    = recipe.get("tags", [])

    label        = _make_label(name)
    graphicspath = _make_graphicspath(tags)

    # ── Source line ───────────────────────────────────────────────
    if url:
        # Extract hostname for a clean source string
        host_m = re.search(r"https?://(?:www\.)?([^/]+)", url)
        source_str = host_m.group(1) if host_m else url
        source_line = f"Source: \\url{{{_escape(url)}}}"
    else:
        source_line = "Source: (unknown)"

    # ── Ingredients block ─────────────────────────────────────────
    if ings:
        ing_items = []
        for ing in ings:
            parts = [
                ing.get("quantity", ""),
                ing.get("unit", ""),
                ing.get("item", ""),
            ]
            line = " ".join(p for p in parts if p).strip()
            ing_items.append(f"    \\item {_escape(line)}")
        ingredients_block = "\n".join(ing_items)
    else:
        ingredients_block = "    \\item (no ingredients listed)"

    # ── Instructions block ────────────────────────────────────────
    if body.strip():
        instructions_block = _instructions_to_enumerate(body)
    else:
        instructions_block = "    \\item (see URL above for instructions)"

    # ── Notes block ───────────────────────────────────────────────
    notes_section = ""
    if notes.strip():
        notes_section = f"""
% Optional: Enter notes here
\\subsubsection{{Notes}}
{_escape(notes)}
"""

    # ── Tags as comment ───────────────────────────────────────────
    tags_comment = ""
    if tags:
        tags_comment = f"% Tags: {', '.join(tags)}\n"

    # ── Assemble ──────────────────────────────────────────────────
    tex = f"""{tags_comment}\\subsection{{{_escape(name)}}}
\\label{{sub:{label}}}
\\graphicspath{{{{{graphicspath}/}}}}
{source_line}
% Optional: Include picture here
% \\begin{{figure}}
%     \\centering
%     \\includegraphics{{}}
%     \\caption{{Caption}}
%     \\label{{fig:my_label}}
% \\end{{figure}}
% Enter the ingredients list here
\\subsubsection{{Ingredients}}
\\begin{{itemize}}
{ingredients_block}
\\end{{itemize}}
% Enter instructions here
\\subsubsection{{Instructions}}
\\begin{{enumerate}}
{instructions_block}
\\end{{enumerate}}{notes_section}"""

    return tex


def export_recipe_to_file(recipe: dict, path: str):
    """Write a recipe to a .tex file at the given path."""
    tex = recipe_to_latex(recipe)
    with open(path, "w", encoding="utf-8") as f:
        f.write(tex)


def suggested_filename(recipe: dict) -> str:
    """Return a suggested filename like 'belgian_waffles.tex'."""
    label = _make_label(recipe.get("name", "recipe"))
    return f"{label}.tex"
