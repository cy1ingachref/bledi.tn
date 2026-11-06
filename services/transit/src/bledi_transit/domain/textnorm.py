"""Text folding for place search: accents, case, punctuation, articles, Arabic marks."""
from __future__ import annotations

import re
import unicodedata

# Leading articles / filler that riders type but stop names often omit
# ("la marsa" is the stop "Marsa"; "el mourouj" is "Mourouj").
ARTICLES = frozenset({"la", "le", "les", "el", "al", "l", "de", "du", "des", "d", "ez", "es", "en", "ech"})

_PUNCT = re.compile(r"[\s\-_/.,;:()'\u2019\u2018`\"]+")
_ARABIC_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u0640]")
_ARABIC_MAP = str.maketrans({"\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627", "\u0649": "\u064a", "\u0629": "\u0647"})
_SMALL_WORDS = frozenset({"de", "du", "des", "la", "le", "les", "el", "al", "et", "sur", "en", "d", "l"})


def fold(text: str | None) -> str:
    """Lowercase, accent-free, punctuation-free, single-spaced."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = _ARABIC_MARKS.sub("", t).translate(_ARABIC_MAP)
    return _PUNCT.sub(" ", t).strip()


def tokens(folded: str) -> list[str]:
    return folded.split() if folded else []


def core_tokens(toks: list[str]) -> list[str]:
    """Tokens without articles, unless that would leave nothing."""
    core = [t for t in toks if t not in ARTICLES]
    return core or toks


def pretty(name: str | None) -> str:
    """Title-case an ALL-CAPS stop name ("BIZERTE" -> "Bizerte"); mixed case is left alone."""
    n = (name or "").strip()
    letters = [c for c in n if c.isalpha()]
    if not letters or not all(c.isupper() for c in letters):
        return n
    out = []
    for i, w in enumerate(n.split(" ")):
        if any(ch.isdigit() for ch in w) or (len(w) <= 3 and w.isupper() and w in {"TGM", "RFR", "RR", "RN", "GP"}):
            out.append(w)
        elif i > 0 and w.lower() in _SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append("-".join(p.capitalize() for p in w.split("-")))
    return " ".join(out)
