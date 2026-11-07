#!/usr/bin/env python3
"""Audit Python tunables/fares vs Rust graph.rs/router.rs against data/shared_tunables.json.

Parses the Python dicts with ast (no import side effects), parses the Rust
const tables with regex, compares every key against the shared source, and
writes data/tunables_reconcile.json. Exit 0 always (audit report); the
'status' field is 'aligned' only when there are zero mismatches.
"""
from __future__ import annotations
import ast, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = json.loads((ROOT / "data/shared_tunables.json").read_text())
PY_TUN = ROOT / "services/transit/src/bledi_transit/domain/tunables.py"
PY_FARE = ROOT / "services/transit/src/bledi_transit/domain/fares.py"
RS_GRAPH = ROOT / "services/routing/src/graph.rs"
RS_ROUTER = ROOT / "services/routing/src/router.rs"


def _eval(node, env):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.Dict):
        return {_eval(k, env): _eval(v, env) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Tuple) or isinstance(node, ast.List):
        return tuple(_eval(e, env) for e in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, env)
    if isinstance(node, ast.BinOp):
        l, r = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Mult): return l * r
        if isinstance(node.op, ast.Add): return l + r
        if isinstance(node.op, ast.Div): return l / r
    raise ValueError("unsupported node")


def py_dicts(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    out = {}
    for node in tree.body:
        target = value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        if target and value is not None:
            try:
                out[target] = _eval(value, out)
            except Exception:
                pass
    return out


def rust_tuples(text: str, const: str):
    m = re.search(rf"{const}[^=]*=\s*&\[(.*?)\];", text, re.S)
    if not m:
        return {}
    out = {}
    for mode, a, b in re.findall(r'\(\s*"([^"]+)"\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?', m.group(1)):
        out[mode] = (float(a), float(b)) if b else float(a)
    return out


def rust_const(text: str, name: str):
    m = re.search(rf"{name}\s*:\s*f64\s*=\s*([\d.]+)|{name}\s*=\s*([\d.]+)", text)
    return float(m.group(1) or m.group(2)) if m else None


def main():
    tun, far = py_dicts(PY_TUN), py_dicts(PY_FARE)
    rs_g = RS_GRAPH.read_text()
    rs_r = RS_ROUTER.read_text()
    mismatches, notes = [], []

    def cmp(kind, key, want, got):
        if want != got:
            mismatches.append({"kind": kind, "key": key, "shared": want, "actual": got})

    # speeds
    rs_speed = rust_tuples(rs_g, "SPEED_KMH")
    py_speed = dict(tun.get("SPEED_BY_MODE", {}))
    for mode, v in SHARED["speed_kmh_by_mode"].items():
        cmp("speed_kmh", mode, v, py_speed.get(mode))
        cmp("speed_kmh", mode, v, rs_speed.get(mode))
    for mode in py_speed:
        if mode not in SHARED["speed_kmh_by_mode"]:
            notes.append(f"python SPEED_BY_MODE extra mode {mode}={py_speed[mode]} (not in shared)")
    for mode in rs_speed:
        if mode not in SHARED["speed_kmh_by_mode"]:
            notes.append(f"rust SPEED_KMH extra mode {mode}={rs_speed[mode]} (not in shared)")

    # waits
    rs_wait = rust_tuples(rs_g, "WAIT_S_BY_MODE")
    py_wait = dict(tun.get("DEFAULT_WAIT_BY_MODE", {}))
    for mode, v in SHARED["default_wait_s_by_mode"].items():
        cmp("default_wait_s", mode, v, py_wait.get(mode))
        cmp("default_wait_s", mode, v, rs_wait.get(mode))
    if "300.0" in rs_r and "wait_by_mode" not in rs_r:
        mismatches.append({"kind": "boarding_wait", "key": "router.rs hardcoded 300s",
                           "shared": "per-mode table", "actual": "300.0 flat"})

    # per-mode boarding-wait caps (metro 420 s, others 1200 s)
    rs_wcap = rust_tuples(rs_g, "WAIT_CAP_S_BY_MODE")
    py_wcap = dict(tun.get("BOARDING_WAIT_CAP_BY_MODE", {}))
    for mode, v in SHARED.get("boarding_wait_cap_s_by_mode", {}).items():
        cmp("boarding_wait_cap_s", mode, v, py_wcap.get(mode))
        cmp("boarding_wait_cap_s", mode, v, rs_wcap.get(mode))
    # distance-based bus speed scalars
    cmp("scalar", "BUS_SPEED_URBAN_KMH (python)", SHARED.get("bus_speed_kmh_urban"), tun.get("BUS_SPEED_URBAN_KMH"))
    cmp("scalar", "BUS_SPEED_INTERCITY_KMH (python)", SHARED.get("bus_speed_kmh_intercity"), tun.get("BUS_SPEED_INTERCITY_KMH"))
    cmp("scalar", "BUS_SPEED_URBAN_KMH (rust)", SHARED.get("bus_speed_kmh_urban"), rust_const(rs_g, "BUS_SPEED_URBAN_KMH"))
    cmp("scalar", "BUS_SPEED_INTERCITY_KMH (rust)", SHARED.get("bus_speed_kmh_intercity"), rust_const(rs_g, "BUS_SPEED_INTERCITY_KMH"))

    # fares
    rs_fare = rust_tuples(rs_g, "FARE")
    py_fare = {k: tuple(v) for k, v in far.get("FARE_DINARS", {}).items()}
    py_caps = far.get("FARE_CAPS_DT", {})
    rs_caps = rust_tuples(rs_g, "FARE_CAP_DT")
    for mode, spec in SHARED["fare_by_mode"].items():
        if mode in ("walk",):
            continue
        want = (spec["base_dt"], spec["per_km_dt"])
        if mode in py_fare:
            cmp("fare_base_per_km", mode, want, py_fare[mode])
        if mode in rs_fare:
            cmp("fare_base_per_km", mode, want, rs_fare[mode])
        if spec["cap_dt"] is not None:
            # Python keys caps by canonical mode (rail->train, louage->louaj)
            canon = {"rail": "train", "louage": "louaj"}.get(mode, mode)
            cmp("fare_cap_dt", mode, spec["cap_dt"], py_caps.get(canon))
            cmp("fare_cap_dt", mode, spec["cap_dt"], rs_caps.get(mode))
    # scalar constants both sides
    scalars = [
        ("TRANSFER_PENALTY_SEC", "transfer_penalty_s"), ("FEWEST_TRANSFERS_PENALTY_SEC", "fewest_transfers_penalty_s"),
        ("BOARDING_WAIT_CAP", "boarding_wait_cap_s"), ("MAX_WALK_EDGE_METERS", "max_walk_edge_m"),
        ("MAX_START_WALK_METERS", "max_start_walk_m"), ("MAX_END_WALK_METERS", "max_end_walk_m"),
        ("MAX_DIRECT_WALK_M", "max_direct_walk_m"),
    ]
    for pyname, shkey in scalars:
        cmp("scalar", pyname, SHARED[shkey], tun.get(pyname))
    cmp("scalar", "MAX_WALK_EDGE_M (rust)", SHARED["max_walk_edge_m"], rust_const(rs_g, "MAX_WALK_EDGE_M"))
    cmp("scalar", "TRANSFER_PENALTY_SEC (rust)", SHARED["transfer_penalty_s"], rust_const(rs_g, "TRANSFER_PENALTY_SEC"))
    cmp("scalar", "MAX_DIRECT_WALK_M (rust)", SHARED["max_direct_walk_m"], rust_const(rs_g, "MAX_DIRECT_WALK_M"))
    cmp("scalar", "MAX_PURE_WALK_SEC (rust)", SHARED["max_pure_walk_min"] * 60, rust_const(rs_g, "MAX_PURE_WALK_SEC"))
    cmp("scalar", "MAX_PURE_WALK_MIN (python)", SHARED["max_pure_walk_min"], tun.get("MAX_PURE_WALK_MIN"))

    report = {
        "generated_by": "scripts/reconcile_tunables.py",
        "shared_source": "data/shared_tunables.json",
        "status": "aligned" if not mismatches else "mismatches_found",
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "notes": notes,
        "python_speed_by_mode": py_speed, "rust_speed_kmh": rs_speed,
        "python_default_wait_by_mode": py_wait, "rust_wait_s_by_mode": rs_wait,
        "python_boarding_wait_cap_by_mode": py_wcap, "rust_wait_cap_s_by_mode": rs_wcap,
        "python_fare_dinars": {k: list(v) for k, v in py_fare.items()},
        "rust_fare": {k: list(v) for k, v in rs_fare.items()},
        "python_fare_caps_dt": py_caps, "rust_fare_cap_dt": rs_caps,
    }
    dest = ROOT / "data/tunables_reconcile.json"
    dest.write_text(json.dumps(report, indent=2))
    print(f"status={report['status']} mismatches={len(mismatches)} -> {dest}")
    for m in mismatches:
        print(" ", m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
