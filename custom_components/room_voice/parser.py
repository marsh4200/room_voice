"""Sentence matching for Room voice. Pure Python, no Home Assistant imports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Spoken type word -> (entity domains, words that may appear in an item's name)
TYPES = {
    "light": (("light",), ("light", "lamp", "spot", "led")),
    "fan": (("fan",), ("fan",)),
    "plug": (("switch",), ("plug", "socket")),
    "blind": (("cover",), ("blind", "curtain", "shutter", "garage", "gate")),
    "aircon": (("climate",), ("aircon", "air con", "heater", "thermostat")),
}
TYPE_WORDS = {
    "light": "light", "lights": "light", "lamp": "light", "lamps": "light",
    "fan": "fan", "fans": "fan",
    "plug": "plug", "plugs": "plug", "socket": "plug", "sockets": "plug",
    "blind": "blind", "blinds": "blind", "curtain": "blind", "curtains": "blind",
    "shutter": "blind", "shutters": "blind",
    "aircon": "aircon", "aircons": "aircon", "ac": "aircon",
}


@dataclass
class Match:
    """What the sentence asked for."""

    action: str  # on, off, open, close, brightness, temperature
    value: int | None = None
    room: dict | None = None
    items: list[dict] = field(default_factory=list)
    label: str = ""
    ask: str | None = None  # set when we need the room named


def norm(text: str) -> str:
    text = re.sub(r"[^\w\s%°]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _find(name: str, text: str):
    # Ignore spacing and a plural "s", so "Downlights", "down light" and
    # "down lights" are all the same name.
    chars = norm(name).replace(" ", "")
    if len(chars) > 3 and chars.endswith("s"):
        chars = chars[:-1]
    if not chars:
        return None
    pat = r"\b" + r"\s*".join(re.escape(c) for c in chars) + r"s?\b"
    return re.search(pat, text)


# Words that carry no meaning about which item is wanted.
FILLER = set(
    "turn switch put set make off on open close shut the my a an all every everything "
    "in of to at for and please can could would you now me up it its is s room rooms "
    "hey ok okay nabu percent degrees degree".split()
)


def _leftover(rest: str) -> list[str]:
    return [
        w for w in rest.split()
        if w not in FILLER and w not in TYPE_WORDS and not re.fullmatch(r"[\d%°]+", w)
    ]


def _best(names: list[str], text: str):
    """Longest match of any of the names in the text."""
    best = None
    for name in names:
        m = _find(name, text)
        if m and (best is None or len(m.group()) > len(best.group())):
            best = m
    return best


def _names(obj: dict) -> list[str]:
    return [obj.get("name", "")] + list(obj.get("aliases", []))


def _action(text: str):
    m = re.search(r"\b(\d{1,3})\s*(%|percent)", text)
    if m:
        return "brightness", max(0, min(100, int(m.group(1))))
    m = re.search(r"\b(\d{1,2})\s*(degrees|degree|°)", text)
    if m:
        return "temperature", int(m.group(1))
    for action, pat in (
        ("off", r"\boff\b"),
        ("on", r"\bon\b"),
        ("close", r"\b(close|shut)\b"),
        ("open", r"\bopen\b"),
    ):
        if re.search(pat, text):
            return action, None
    return None, None


def is_type(item: dict, kind: str) -> bool:
    domains, words = TYPES[kind]
    if item.get("entity_id", "").split(".")[0] in domains:
        return True
    name = " ".join(_names(item)).lower()
    return any(w in name for w in words)


def parse(text: str, rooms: list[dict]) -> Match | None:
    """Return a Match, or None when the sentence isn't about a known room or item."""
    text = norm(text)
    action, value = _action(text)
    if action is None:
        return None

    room, room_m = None, None
    for r in rooms:
        m = _best(_names(r), text)
        if m and (room_m is None or len(m.group()) > len(room_m.group())):
            room, room_m = r, m

    # Look for item names outside the words that named the room.
    rest = text if room_m is None else text[: room_m.start()] + " " + text[room_m.end():]
    found = []
    for r in [room] if room else rooms:
        for it in r.get("items", []):
            names = _names(it)
            # "Kitchen Pendant" should also answer to plain "pendant".
            for rn in _names(r):
                for n in _names(it):
                    short = re.sub(r"^\s*" + re.escape(rn) + r"\s+", "", n, flags=re.I)
                    if short and short != n:
                        names.append(short)
            m = _best(names, rest) or (_best(names, text) if room else None)
            if m:
                found.append((len(m.group()), r, it))

    if found:
        top = max(f[0] for f in found)
        best = [f for f in found if f[0] == top]
        best_rooms = {id(f[1]) for f in best}
        if len(best_rooms) > 1:
            names = ", ".join(sorted({f[1]["name"] for f in best}))
            return Match(action, value, ask=f"Which room? I have that in {names}.")
        r = best[0][1]
        items = [f[2] for f in best]
        iname = items[0]["name"]
        label = iname if iname.lower().startswith(r["name"].lower()) else f"{r['name']} {iname}"
        return Match(action, value, r, items, label)

    if room is None:
        return None

    # A word we don't know ("turn off the kitchen pendant") means a specific
    # item was asked for. Never fall back to switching the whole room.
    extra = _leftover(rest)
    if extra:
        return Match(action, value, ask=f"I don't have {' '.join(extra)} set up in {room['name']}.")

    kind = next((TYPE_WORDS[w] for w in rest.split() if w in TYPE_WORDS), None)
    items = list(room.get("items", []))
    label = room["name"]
    if kind:
        items = [it for it in items if is_type(it, kind)]
        label = f"{room['name']} {kind}s"
    elif action == "on":
        # "Turn on the playroom" only switches lights, never plugs or aircons.
        items = [it for it in items if is_type(it, "light")]
        label = f"{room['name']} lights"
    return Match(action, value, room, items, label)
