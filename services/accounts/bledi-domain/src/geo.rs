use crate::{Invalid, ValidationError};

pub const EARTH_RADIUS_M: f64 = 6_371_000.0;

pub const LAT_MIN: f64 = 30.0;
pub const LAT_MAX: f64 = 37.5;
pub const LON_MIN: f64 = 7.5;
pub const LON_MAX: f64 = 12.0;

pub const UNLOCK_RADIUS_MIN_M: f64 = 50.0;
pub const UNLOCK_RADIUS_MAX_M: f64 = 1000.0;

/// A cap, not a clamp: a wider search is rejected so the caller never gets a narrower answer than it asked for.
pub const SEARCH_RADIUS_MAX_M: f64 = 5_000.0;

pub fn haversine_m(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let d_lat = (lat2 - lat1).to_radians();
    let d_lon = (lon2 - lon1).to_radians();
    let a = (d_lat / 2.0).sin().powi(2)
        + lat1.to_radians().cos() * lat2.to_radians().cos() * (d_lon / 2.0).sin().powi(2);
    2.0 * EARTH_RADIUS_M * a.sqrt().atan2((1.0 - a).sqrt())
}

// NaN fails every comparison, so a plain range check would let it through.
pub(crate) fn finite_in_range(
    value: f64,
    min: f64,
    max: f64,
    field: &str,
    kind: Invalid,
) -> Result<f64, ValidationError> {
    if !value.is_finite() {
        return Err(ValidationError::new(
            kind,
            format!("{field} must be a finite number"),
        ));
    }
    if value < min || value > max {
        return Err(ValidationError::new(
            kind,
            format!("{field} must be between {min} and {max}"),
        ));
    }
    Ok(value)
}

/// A point inside Tunisia's bounding box.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Coordinates {
    lat: f64,
    lon: f64,
}

impl Coordinates {
    pub fn in_tunisia(lat: f64, lon: f64) -> Result<Self, ValidationError> {
        Ok(Self {
            lat: finite_in_range(lat, LAT_MIN, LAT_MAX, "lat", Invalid::Coordinates)?,
            lon: finite_in_range(lon, LON_MIN, LON_MAX, "lon", Invalid::Coordinates)?,
        })
    }

    pub fn lat(self) -> f64 {
        self.lat
    }

    pub fn lon(self) -> f64 {
        self.lon
    }

    pub fn distance_m(self, lat: f64, lon: f64) -> f64 {
        haversine_m(self.lat, self.lon, lat, lon)
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct UnlockRadius(f64);

impl UnlockRadius {
    pub fn new(metres: f64) -> Result<Self, ValidationError> {
        finite_in_range(
            metres,
            UNLOCK_RADIUS_MIN_M,
            UNLOCK_RADIUS_MAX_M,
            "unlock_radius_m",
            Invalid::Radius,
        )
        .map(Self)
    }

    pub fn metres(self) -> f64 {
        self.0
    }
}

/// The latitude and longitude ranges that contain a search circle, for an index scan before the exact distance check.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Bounds {
    pub lat_min: f64,
    pub lat_max: f64,
    pub lon_min: f64,
    pub lon_max: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SearchArea {
    pub center: Coordinates,
    pub radius_m: f64,
}

impl SearchArea {
    pub fn new(center: Coordinates, radius_m: Option<f64>) -> Result<Self, ValidationError> {
        let radius_m = match radius_m {
            None => SEARCH_RADIUS_MAX_M,
            Some(r) if !r.is_finite() => {
                return Err(ValidationError::new(
                    Invalid::Radius,
                    "radius_m must be a finite number",
                ))
            }
            Some(r) if r <= 0.0 => {
                return Err(ValidationError::new(
                    Invalid::Radius,
                    "radius_m must be greater than 0",
                ))
            }
            Some(r) if r > SEARCH_RADIUS_MAX_M => {
                return Err(ValidationError::new(
                    Invalid::Radius,
                    format!("radius_m must be <= {SEARCH_RADIUS_MAX_M}"),
                ))
            }
            Some(r) => r,
        };
        Ok(Self { center, radius_m })
    }

    /// The distance from the centre when the point is inside the circle.
    pub fn distance_to(&self, lat: f64, lon: f64) -> Option<f64> {
        let d = self.center.distance_m(lat, lon);
        (d <= self.radius_m).then_some(d)
    }

    pub fn bounds(&self) -> Bounds {
        let angle = self.radius_m / EARTH_RADIUS_M;
        let d_lat = angle.to_degrees();
        let d_lon = (angle.sin() / self.center.lat.to_radians().cos())
            .min(1.0)
            .asin()
            .to_degrees();
        Bounds {
            lat_min: self.center.lat - d_lat,
            lat_max: self.center.lat + d_lat,
            lon_min: self.center.lon - d_lon,
            lon_max: self.center.lon + d_lon,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tunis() -> Coordinates {
        Coordinates::in_tunisia(36.8065, 10.1815).unwrap()
    }

    #[test]
    fn coordinates_outside_tunisia_or_not_finite_are_rejected() {
        assert!(Coordinates::in_tunisia(36.8, 10.18).is_ok());
        assert!(Coordinates::in_tunisia(LAT_MIN, LON_MAX).is_ok());
        let paris = Coordinates::in_tunisia(48.8566, 2.3522).unwrap_err();
        assert_eq!(paris.kind, Invalid::Coordinates);
        assert!(paris.message.contains("lat"));
        assert!(Coordinates::in_tunisia(36.8, 2.35)
            .unwrap_err()
            .message
            .contains("lon"));
        assert!(Coordinates::in_tunisia(f64::NAN, 10.0).is_err());
        assert!(Coordinates::in_tunisia(36.8, f64::INFINITY).is_err());
    }

    #[test]
    fn unlock_radius_is_bounded_not_clamped() {
        assert_eq!(UnlockRadius::new(200.0).unwrap().metres(), 200.0);
        assert!(UnlockRadius::new(UNLOCK_RADIUS_MIN_M).is_ok());
        assert!(UnlockRadius::new(UNLOCK_RADIUS_MAX_M).is_ok());
        for bad in [-5.0, 0.0, 49.9, 1000.1, 1e9, f64::NAN] {
            assert_eq!(UnlockRadius::new(bad).unwrap_err().kind, Invalid::Radius);
        }
    }

    #[test]
    fn search_radius_defaults_to_the_cap_and_rejects_above_it() {
        assert_eq!(
            SearchArea::new(tunis(), None).unwrap().radius_m,
            SEARCH_RADIUS_MAX_M
        );
        assert_eq!(
            SearchArea::new(tunis(), Some(1000.0)).unwrap().radius_m,
            1000.0
        );
        for bad in [999_999.0, 0.0, -5.0, f64::NAN] {
            assert_eq!(
                SearchArea::new(tunis(), Some(bad)).unwrap_err().kind,
                Invalid::Radius
            );
        }
    }

    #[test]
    fn haversine_matches_a_known_long_distance() {
        let tunis_to_sfax = haversine_m(36.8065, 10.1815, 34.7406, 10.7603);
        assert!(
            (tunis_to_sfax - 238_000.0).abs() < 5_000.0,
            "{tunis_to_sfax}"
        );
    }

    #[test]
    fn bounds_contain_every_point_of_the_circle() {
        let area =
            SearchArea::new(Coordinates::in_tunisia(37.4, 9.9).unwrap(), Some(5000.0)).unwrap();
        let b = area.bounds();
        for step in 0..360 {
            let bearing = f64::from(step).to_radians();
            let angle = area.radius_m * 0.999 / EARTH_RADIUS_M;
            let (lat1, lon1) = (37.4_f64.to_radians(), 9.9_f64.to_radians());
            let lat2 = (lat1.sin() * angle.cos() + lat1.cos() * angle.sin() * bearing.cos()).asin();
            let lon2 = lon1
                + (bearing.sin() * angle.sin() * lat1.cos())
                    .atan2(angle.cos() - lat1.sin() * lat2.sin());
            let (lat, lon) = (lat2.to_degrees(), lon2.to_degrees());
            assert!(area.distance_to(lat, lon).is_some());
            assert!(
                (b.lat_min..=b.lat_max).contains(&lat),
                "lat {lat} at {step}"
            );
            assert!(
                (b.lon_min..=b.lon_max).contains(&lon),
                "lon {lon} at {step}"
            );
        }
    }
}
