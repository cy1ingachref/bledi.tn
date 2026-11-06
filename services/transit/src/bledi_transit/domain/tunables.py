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
