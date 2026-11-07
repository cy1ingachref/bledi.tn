"""Routing cost model constants. One place, no environment overrides."""

WALK_SPEED_KMH = 4.5
WALK_SPEED_MS = WALK_SPEED_KMH / 3.6

# Per-mode average speeds (km/h) used for both routing cost and displayed time,
# so the cheapest path is also the physically fastest one.
SPEED_BY_MODE: dict[str, float] = {
    "train": 60.0,
    "rail": 55.0,
    "metro": 30.0,
    "bus": 22.0,
    "rfr": 22.0,
    "tram": 22.0,
    "rural": 22.0,
    "louage": 100.0,
    "louaj": 100.0,
    "taxi": 45.0,
    "walk": WALK_SPEED_KMH,
    "unknown": 22.0,
}

TAXI_SPEED_KMH = SPEED_BY_MODE["taxi"]
TAXI_SPEED_MS = TAXI_SPEED_KMH / 3.6

# Lines with only a couple of departures a day produce multi-hour median
# headways; cap the boarding wait so sparse lines do not dominate long corridors.
BOARDING_WAIT_CAP = 20 * 60

# Per-mode boarding-wait cap (s): metro runs every few minutes, so a
# multi-hour headway estimate is never credible there; every other mode
# keeps the flat 1200 s cap. Mirrored in Rust WAIT_CAP_S_BY_MODE and
# data/shared_tunables.json boarding_wait_cap_s_by_mode.
BOARDING_WAIT_CAP_BY_MODE: dict[str, float] = {
    "metro": 420.0,
    "train": 1200.0,
    "rail": 1200.0,
    "bus": 1200.0,
    "rfr": 1200.0,
    "tram": 1200.0,
    "rural": 1200.0,
    "louage": 1200.0,
    "louaj": 1200.0,
    "taxi": 1200.0,
    "walk": 1200.0,
    "unknown": 1200.0,
}

# Distance-based bus-family speed (km/h): a short urban hop averages
# 22 km/h (stops, lights), a long intercity hop 45 km/h, linearly
# interpolated between the two thresholds. SPEED_BY_MODE[bus-family]
# stays the urban base so shared_tunables.json speed_kmh_by_mode
# (bus = 22) remains the comparable single number.
BUS_SPEED_URBAN_KMH = 22.0
BUS_SPEED_INTERCITY_KMH = 45.0
BUS_SPEED_URBAN_MAX_M = 2000.0
BUS_SPEED_INTERCITY_MIN_M = 5000.0
BUS_FAMILY_MODES = ("bus", "rfr", "tram", "rural")


def bus_speed_kmh(distance_m: float) -> float:
    """Bus-family speed for one hop of `distance_m` metres."""
    if distance_m <= BUS_SPEED_URBAN_MAX_M:
        return BUS_SPEED_URBAN_KMH
    if distance_m >= BUS_SPEED_INTERCITY_MIN_M:
        return BUS_SPEED_INTERCITY_KMH
    frac = (distance_m - BUS_SPEED_URBAN_MAX_M) / (
        BUS_SPEED_INTERCITY_MIN_M - BUS_SPEED_URBAN_MAX_M
    )
    return BUS_SPEED_URBAN_KMH + frac * (BUS_SPEED_INTERCITY_KMH - BUS_SPEED_URBAN_KMH)


def speed_kmh_for_distance(mode: str, distance_m: float) -> float:
    """Per-mode speed honouring the distance-based bus family."""
    if mode in BUS_FAMILY_MODES:
        return bus_speed_kmh(distance_m)
    return SPEED_BY_MODE.get(mode, SPEED_BY_MODE["bus"])


def boarding_wait_cap_for_mode(mode: str) -> float:
    """Boarding-wait cap (s) for a mode (metro 420, others 1200)."""
    return BOARDING_WAIT_CAP_BY_MODE.get(mode, BOARDING_WAIT_CAP)

# Expected wait when departures exist is this fraction of the median headway.
WAIT_HEADWAY_FACTOR = 0.5

# Per-mode wait (seconds) when a line publishes no departures.
DEFAULT_WAIT_BY_MODE: dict[str, float] = {
    "train": 600.0,
    "rail": 600.0,
    "metro": 300.0,
    "bus": 600.0,
    "rfr": 600.0,
    "tram": 600.0,
    "rural": 600.0,
    "louage": 600.0,
    "louaj": 600.0,
    "taxi": 0.0,
    "walk": 0.0,
    "unknown": 600.0,
}

# Departures spanning more than this wrap past midnight: the gap to the next
# day's first departure counts as a headway too, so a 06:05/23:55 pair is not
# only one 18 h headway.
MAX_HEADWAY_SEC = 12 * 3600

TRANSFER_PENALTY_SEC = 180.0
# Large enough that the fewest_transfers strategy genuinely prefers a direct
# bus over a faster two-leg train and bus.
FEWEST_TRANSFERS_PENALTY_SEC = 5400.0

MAX_START_WALK_METERS = 2000
MAX_END_WALK_METERS = 2000

# Walk edges between stops: the pedestrian network inside the graph. Without
# them a stop no line calls at is unreachable. 900 m is a realistic
# walk-to-bus distance.
MAX_WALK_EDGE_METERS = 900

# Radius used to find a drop-off stop when the destination has none nearby.
# Measured on the seed: the nearest served station is 44.3 km from Kairouan and
# 90.8 km from Mahdia, so the radius covers that worst case. The final gap is
# then priced at taxi speed and labelled as a local hop, never as a walk.
DROPOFF_SEARCH_METERS = 100000

# How many served drop-off stops to consider, nearest first. Measured: widening
# to 6 made Mahdia worse (98.3 km hop, 414 min instead of 90.8 km, 443 min)
# because a longer ride undercuts a shorter one plus a long taxi hop.
DROP_OFF_CANDIDATES = 1

# A direct taxi is not offered for trips shorter than this.
TAXI_MIN_DISTANCE_M = 3000
# A taxi ride is offered up to this distance. Beyond it nobody hires a taxi for the trip, and
# louage only runs on its own corridors, so the option is simply not offered.
MAX_DIRECT_TAXI_M = 150_000
# Walking straight to the destination is only offered for a plausible walk.
# The product limit is 1 km: longer gaps are access/egress details around a
# ride, or the trip needs a vehicle; they are never a whole itinerary.
MAX_DIRECT_WALK_M = 1000

# A pure-walk itinerary (no ride leg) longer than this is only offered when no
# transit candidate exists. See data/shared_tunables.json "pure_walk_rule".
MAX_PURE_WALK_MIN = 120.0

# Below this length a straight line is indistinguishable from a real path, so a
# missing polyline is harmless. Above it the client must not draw one.
GEOMETRY_REQUIRED_M = 300.0

# Inter-governorate rule (wily): when start and end sit in different
# governorates (nearest_city differs and both != "Other"), the main ride must
# be a scheduled / louage / rail public mode. walk and taxi as a whole
# itinerary are forbidden; walk only as access/egress (<=2000 m) is allowed.
# See data/shared_tunables.json "inter_governorate_modes".
INTER_GOVERNORATE_MODES = ("louage", "louaj", "bus", "rfr", "tram", "rural", "train", "rail", "metro")
