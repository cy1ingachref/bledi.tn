"""Export the per-edge way NAMES out of the .npz graphs into a JSON sidecar.

Why this exists
---------------
`ename_raw` is an object-dtype array: a pickle, not a numeric buffer. The Rust
port reads the graphs with a hand-written .npz/.npy reader and deliberately does
not implement pickle -- an unsafe-ish parser for a field that is only ever used
to caption a route ("which road am I on") is a bad trade. So the Python side,
which already owns the pickle, writes the names out once as plain JSON.

The alternative is to ship the names as an empty list and lose `road_names` from
the API, which is user-visible text. One small script is cheaper.

Usage:
    python scripts/export_names.py            # writes data/road_names.json
                                              # + data/rail_names.json

Output: {"names": [["", "", ""], ["name", "from", "ar"], ...]}
Index position matches the `ename` edge-id -> row mapping in the graph, so the
Rust side does a single Vec index and never re-parses anything.
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def export(npz_name: str, out_name: str) -> dict:
    path = os.path.join(ROOT, "data", npz_name)
    if not os.path.exists(path):
        print(f"skip {npz_name}: not built")
        return {}
    with np.load(path, allow_pickle=True) as z:
        if "ename_raw" not in z.files:
            print(f"skip {npz_name}: no ename_raw")
            return {}
        raw = z["ename_raw"].tolist()
        ename = z["ename"]
    names = [[("" if c is None else str(c)) for c in row] for row in raw]
    out_path = os.path.join(ROOT, "data", out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"names": names}, f, ensure_ascii=False)
    nonempty = sum(1 for row in names if row and row[0])
    print(
        f"{out_name}: {len(names)} way names "
        f"({nonempty} with a primary name), max ename id {int(ename.max())}, "
        f"{os.path.getsize(out_path)} bytes"
    )
    return {"n": len(names), "max_id": int(ename.max()), "named": nonempty}


if __name__ == "__main__":
    info = {
        "road": export("road_graph.npz", "road_names.json"),
        "rail": export("rail_graph.npz", "rail_names.json"),
    }
    # If any edge points past the table, a lookup would panic in Rust. Better to
    # fail loudly here, where the fix is obvious.
    for kind, v in info.items():
        if v and v["max_id"] >= v["n"]:
            raise SystemExit(f"{kind}: ename id {v['max_id']} >= {v['n']} names")
    print("ok")