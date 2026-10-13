"""Transport mode taxonomy: seed modes, user-facing modes and their labels."""
from __future__ import annotations

# User-facing mode -> seed line.mode values that map onto it. The
# louage_red|blue|green tags come from the secondary louage seed, which
# classifies shared taxis by route colour; they must not fall through to the
# "unknown -> bus" default and be labelled as scheduled buses.
MODE_ALIASES: dict[str, frozenset[str]] = {
    "bus": frozenset({"bus", "rfr"}),
    "tram": frozenset({"tram"}),
    "metro": frozenset({"metro"}),
    "train": frozenset({"train", "rail"}),
    "louaj": frozenset({
        "louaj", "louage", "louage_red", "louage_blue", "louage_green",
    }),
    "taxi": frozenset({"taxi"}),
    "walk": frozenset({"walk"}),
}

# Display order used by labels and by the station and line listings.
USER_MODES: tuple[str, ...] = (
    "bus",
    "tram",
    "metro",
    "train",
    "louaj",
    "taxi",
    "walk",
)

MODE_LABELS_FR: dict[str, str] = {
    "bus": "Bus",
    "tram": "Tramway",
    "metro": "Metro",
    "train": "Train",
    # Taxi and louage are one rider-facing category (road for hire).
    "louaj": "Taxi / Louage",
    "taxi": "Taxi / Louage",
    "walk": "Marche",
    # Station-only tag for a geocoded stop whose export carried no mode. It is
    # not routable, so it is absent from USER_MODES.
    "unclassified": "Non classé",
}

BUS_MODES: frozenset[str] = frozenset({"bus", "rfr", "tram"})
RAIL_MODES: frozenset[str] = frozenset({"train", "rail", "metro"})
TAXI_MODES: frozenset[str] = frozenset({"taxi", "louaj"})


def canonical_mode(raw: str | None) -> str:
    """Map a seed line.mode onto one of USER_MODES.

    Unknown modes fall back to bus: a scheduled line with an unrecognised tag
    is still a scheduled line, and dropping it would delete a real service.
    """
    if not raw:
        return "bus"
    r = str(raw).strip().lower()
    for mode, aliases in MODE_ALIASES.items():
        if r in aliases:
            return mode
    return "bus"


def resolve_allowed_modes(
    include: list[str] | set[str] | tuple[str, ...] | None,
    exclude: list[str] | set[str] | tuple[str, ...] | None,
) -> frozenset[str] | None:
    """Raw edge-mode set for an include/exclude request.

    None means no restriction. Raises ValueError when the request can never be
    satisfied (unknown mode, or include minus exclude is empty) so the API can
    answer 400 instead of "no route".

    The result holds RAW seed modes because that is what an edge carries;
    exclusion goes through MODE_ALIASES, so excluding "train" also removes
    "rail" and excluding "bus" also removes "rfr".
    """
    known_raw: set[str] = set()
    for aliases in MODE_ALIASES.values():
        known_raw |= set(aliases)

    def expand(names: set[str], what: str) -> set[str]:
        out: set[str] = set()
        unknown: set[str] = set()
        for n in names:
            key = str(n).strip().lower()
            if not key:
                continue
            if key in MODE_ALIASES:
                out |= set(MODE_ALIASES[key])
            elif key in known_raw:
                out.add(key)
            else:
                unknown.add(key)
        if unknown:
            raise ValueError(
                f"unknown {what}: {sorted(unknown)}; available: {list(USER_MODES)}"
            )
        return out

    inc = expand(set(include or ()), "modes_include")
    exc = expand(set(exclude or ()), "modes_exclude")
    if inc:
        allowed = inc - exc
        if not allowed:
            raise ValueError(
                "modes_exclude removed every requested mode; "
                f"available: {list(USER_MODES)}"
            )
        return frozenset(allowed)
    if exc:
        # Walk stays in: never a selectable transport, always needed for access.
        allowed = known_raw - exc
        if not allowed:
            raise ValueError(
                "modes_exclude removed every available mode; "
                f"available: {list(USER_MODES)}"
            )
        return frozenset(allowed | {"walk"})
    return None


def mode_label_fr(mode: str) -> str:
    """French label for one mode.

    The raw value is looked up before canonicalisation, otherwise a
    station-only tag such as `unclassified` would be absorbed by the
    "unknown -> bus" fallback and labelled as a scheduled bus.
    """
    raw = str(mode or "").strip().lower()
    if raw in MODE_LABELS_FR:
        return MODE_LABELS_FR[raw]
    return MODE_LABELS_FR.get(canonical_mode(mode), mode)


def label_modes_fr(modes: object) -> str:
    """'Bus + Metro' style label for an iterable of modes, in USER_MODES order."""
    seen: set[str] = set()
    if isinstance(modes, str):
        modes = [modes]
    for m in modes or ():
        seen.add(canonical_mode(m))
    return " + ".join(MODE_LABELS_FR[m] for m in USER_MODES if m in seen)
