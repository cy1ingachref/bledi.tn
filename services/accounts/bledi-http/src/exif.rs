//! EXIF removal, done by reading the container structure rather than by re-encoding.
//!
//! An EXIF GPS tag defeats the radius lock of a memory outright, so the metadata has to
//! go before the photo is ever served. Re-encoding would need an image codec; the metadata
//! blocks are self-describing, so dropping them by hand is enough and leaves the pixels
//! untouched.

const PNG_SIGNATURE: &[u8] = &[0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A];

pub fn is_jpeg(bytes: &[u8]) -> bool {
    bytes.len() > 3 && bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF
}

pub fn is_png(bytes: &[u8]) -> bool {
    bytes.len() > PNG_SIGNATURE.len() && &bytes[..PNG_SIGNATURE.len()] == PNG_SIGNATURE
}

/// Removes the metadata blocks that carry the camera's location.
///
/// A JPEG keeps EXIF and XMP in APP1 segments; a PNG keeps it in an `eXIf` chunk. Both are
/// dropped. Anything that is not a JPEG or a PNG is returned unchanged: the caller has
/// already refused it.
pub fn strip_exif(bytes: &[u8]) -> Vec<u8> {
    if is_jpeg(bytes) {
        strip_jpeg_app1(bytes)
    } else if is_png(bytes) {
        strip_png_chunk(bytes, b"eXIf")
    } else {
        bytes.to_vec()
    }
}

/// Drops every APP1 segment. EXIF and XMP both live there, and neither is worth keeping.
fn strip_jpeg_app1(bytes: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bytes.len());
    out.extend_from_slice(&bytes[..2]);
    let mut i = 2;
    while i + 1 < bytes.len() {
        if bytes[i] != 0xFF {
            return bytes.to_vec();
        }
        let marker = bytes[i + 1];
        if marker == 0xFF {
            i += 1;
            continue;
        }
        // Standalone markers carry no payload.
        if marker == 0x01 || marker == 0xD8 || marker == 0xD9 || (0xD0..=0xD7).contains(&marker) {
            out.extend_from_slice(&bytes[i..i + 2]);
            i += 2;
            continue;
        }
        // Start of scan: everything after it is entropy-coded image data.
        if marker == 0xDA {
            out.extend_from_slice(&bytes[i..]);
            return out;
        }
        if i + 4 > bytes.len() {
            return bytes.to_vec();
        }
        let len = u16::from_be_bytes([bytes[i + 2], bytes[i + 3]]) as usize;
        if len < 2 || i + 2 + len > bytes.len() {
            return bytes.to_vec();
        }
        if marker != 0xE1 {
            out.extend_from_slice(&bytes[i..i + 2 + len]);
        }
        i += 2 + len;
    }
    out
}

/// Drops one PNG chunk. PNG chunks are length-prefixed, so removing a whole chunk keeps
/// the file valid without touching a single byte of the image data.
fn strip_png_chunk(bytes: &[u8], kind: &[u8; 4]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bytes.len());
    out.extend_from_slice(&bytes[..8]);
    let mut i = 8;
    while i + 8 <= bytes.len() {
        let len = u32::from_be_bytes([bytes[i], bytes[i + 1], bytes[i + 2], bytes[i + 3]]) as usize;
        let total = 12 + len;
        if total < 12 || i + total > bytes.len() {
            break;
        }
        if &bytes[i + 4..i + 8] != kind {
            out.extend_from_slice(&bytes[i..i + total]);
        }
        i += total;
    }
    if i < bytes.len() {
        out.extend_from_slice(&bytes[i..]);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn jpeg_with_app1() -> Vec<u8> {
        let mut bytes = vec![0xFF, 0xD8];
        // APP1 / EXIF: marker, length, "Exif\0\0", then some payload.
        let payload = b"Exif\0\0GPS-LATITUDE-36.8";
        let len = (payload.len() + 2) as u16;
        bytes.extend_from_slice(&[0xFF, 0xE1]);
        bytes.extend_from_slice(&len.to_be_bytes());
        bytes.extend_from_slice(payload);
        // APP0 / JFIF: kept.
        bytes.extend_from_slice(&[0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00]);
        // Start of scan, then the image data.
        bytes.extend_from_slice(&[0xFF, 0xDA, 0x00, 0x02]);
        bytes.extend_from_slice(&[0xAA, 0xBB, 0xCC]);
        bytes.extend_from_slice(&[0xFF, 0xD9]);
        bytes
    }

    fn png_with_exif() -> Vec<u8> {
        let mut bytes = PNG_SIGNATURE.to_vec();
        // An IHDR chunk: length 13, then width, height, bit depth, colour type,
        // compression, filter and interlace.
        bytes.extend_from_slice(&[0x00, 0x00, 0x00, 0x0D, b'I', b'H', b'D', b'R']);
        bytes.extend_from_slice(&[
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x00, 0x00, 0x00, 0x00,
        ]);
        bytes.extend_from_slice(&[0xDE, 0xAD, 0xBE, 0xEF]);
        // An eXIf chunk, then an IDAT chunk.
        bytes.extend_from_slice(&[0x00, 0x00, 0x00, 0x04, b'e', b'X', b'I', b'f']);
        bytes.extend_from_slice(b"GPS!");
        bytes.extend_from_slice(&[0xDE, 0xAD, 0xBE, 0xEF]);
        bytes.extend_from_slice(&[0x00, 0x00, 0x00, 0x01, b'I', b'D', b'A', b'T']);
        bytes.extend_from_slice(&[0x00]);
        bytes.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);
        bytes
    }

    #[test]
    fn the_jpeg_app1_segment_is_removed_and_the_rest_kept() {
        let stripped = strip_exif(&jpeg_with_app1());
        assert!(!stripped.windows(5).any(|w| w == b"Exif\0"));
        assert!(!stripped.windows(4).any(|w| w == b"GPS-"));
        // The JFIF segment and the image data survive.
        assert!(stripped.windows(2).any(|w| w == [0xFF, 0xE0]));
        assert!(stripped.ends_with(&[0xAA, 0xBB, 0xCC, 0xFF, 0xD9]));
        assert!(is_jpeg(&stripped));
    }

    #[test]
    fn the_png_exif_chunk_is_removed_and_the_others_kept() {
        let stripped = strip_exif(&png_with_exif());
        assert!(!stripped.windows(4).any(|w| w == b"eXIf"));
        assert!(!stripped.windows(3).any(|w| w == b"GPS"));
        assert!(stripped.windows(4).any(|w| w == b"IHDR"));
        assert!(stripped.windows(4).any(|w| w == b"IDAT"));
        assert!(is_png(&stripped));
    }

    #[test]
    fn a_photo_without_metadata_is_left_alone() {
        let plain = vec![0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00, 0xFF, 0xD9];
        assert_eq!(strip_exif(&plain), plain);
    }

    #[test]
    fn a_truncated_file_is_returned_unchanged() {
        let truncated = vec![0xFF, 0xD8, 0xFF, 0xE1, 0x00];
        assert_eq!(strip_exif(&truncated), truncated);
    }
}
