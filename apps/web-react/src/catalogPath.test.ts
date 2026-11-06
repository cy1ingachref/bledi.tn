import { describe, expect, it } from "vitest";
import { linePath, linePathRuns } from "./catalog";
import type { LineDetail, LineGeometrySegment } from "./catalog";

/**
 * Build a LineDetail-shaped object.
 *
 * Two different coordinate conventions live in one payload, and mixing them up
 * mirrors the line across the equator:
 *   - `geometry_segments[].geometry` is already [lat, lon]
 *   - `geometry.coordinates` is GeoJSON [lon, lat]
 * This helper takes [lat, lon] points and stores them accordingly.
 */
function detail(segments: [number, number][][]): LineDetail {
  const geometry_segments: LineGeometrySegment[] = segments.map((pts, i) => ({
    from_stop_id: `a${i}`,
    to_stop_id: `a${i + 1}`,
    from_name: `A${i}`,
    to_name: `A${i + 1}`,
    has_geometry: pts.length >= 2,
    needs_geometry: pts.length < 2,
    gap_m: 100,
    // Segments are already [lat, lon].
    geometry: pts.map((p) => [p[0], p[1]]),
  }));
  const complete = segments.every((p) => p.length >= 2);
  const stitched = segments.filter((p) => p.length >= 2).flat();
  return {
    line: { id: "x", mode: "train", stations: [] },
    stops: [],
    count: 0,
    mode: "train",
    mode_label: "Train",
    // The top-level field is GeoJSON, i.e. [lon, lat].
    geometry:
      complete && stitched.length >= 2
        ? { type: "LineString", coordinates: stitched.map((p) => [p[1], p[0]]) }
        : null,
    geometry_complete: complete,
    geometry_segments,
    gaps: [],
  };
}

describe("linePathRuns", () => {
  it("returns one run for an unbroken line", () => {
    const a = [
      [36.80, 10.19],
      [36.81, 10.20],
      [36.82, 10.21],
    ];
    const b = [
      [36.82, 10.21],
      [36.83, 10.22],
      [36.84, 10.23],
    ];
    const runs = linePathRuns(detail([a, b]));
    expect(runs).toHaveLength(1);
    // The shared endpoint is not duplicated.
    expect(runs[0]).toHaveLength(5);
  });

  it("keeps lat/lon in the right order (no equator mirroring)", () => {
    const runs = linePathRuns(
      detail([
        [
          [36.80, 10.19],
          [36.81, 10.20],
        ],
      ])
    );
    // Leaflet wants [lat, lon]; latitude for Tunis must stay ~36.8.
    expect(runs[0][0][0]).toBeCloseTo(36.80, 5);
    expect(runs[0][0][1]).toBeCloseTo(10.19, 5);
  });

  it("splits into separate runs across a missing segment", () => {
    const a = [
      [36.80, 10.19],
      [36.81, 10.20],
    ];
    const c = [
      [36.90, 10.30],
      [36.91, 10.31],
    ];
    const runs = linePathRuns(detail([a, [], c]));
    expect(runs).toHaveLength(2);
    expect(runs[0]).toHaveLength(2);
    expect(runs[1]).toHaveLength(2);
  });

  it("does not join segments that merely look consecutive", () => {
    // Two segments with no shared endpoint must stay separate runs.
    const a = [
      [36.80, 10.19],
      [36.81, 10.20],
    ];
    const b = [
      [36.82, 10.21],
      [36.83, 10.22],
    ];
    const runs = linePathRuns(detail([a, b]));
    expect(runs).toHaveLength(2);
  });

  it("returns [] when the line has no geometry at all", () => {
    expect(linePathRuns(detail([[], []]))).toEqual([]);
    expect(linePath(detail([[], []]))).toEqual([]);
  });

  it("linePath converts the GeoJSON top-level field to [lat, lon]", () => {
    const d = detail([
      [
        [36.80, 10.19],
        [36.81, 10.20],
      ],
    ]);
    expect(linePath(d)[0]).toEqual([36.8, 10.19]);
  });

  it("linePathRuns still draws both sides of a gapped line", () => {
    // This is the case the old linePath could not serve: the top-level geometry
    // is absent, so only the per-segment runs can show the real track.
    const d = detail([
      [
        [36.80, 10.19],
        [36.81, 10.20],
      ],
      [],
      [
        [36.90, 10.30],
        [36.91, 10.31],
      ],
    ]);
    d.geometry = null;
    expect(linePath(d)).toEqual([]);
    expect(linePathRuns(d)).toHaveLength(2);
  });
});
