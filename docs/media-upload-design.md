# Media upload design (not yet implemented)

Status: **design only.** No upload endpoint exists. This document specifies what
must be built before geo-pinned memories can store real photos and videos.

## Why this must come before the memories API is exposed

Today a memory stores an arbitrary string in `media_url`, and the frontend
renders it directly:

```svelte
<img src={m.media_url} alt="" />
```

That means anyone can create a memory pointing at a host they control and log the
IP address, User-Agent and Referer of every viewer who scrolls past it. It also
means the app can be used to host arbitrary content under a bledi.tn page.

Validation of `media_url` (absolute http/https, max 2048 chars, no `data:` URLs —
see `services/accounts/bledi-server/src/validate.rs`) reduces the blast radius but does not fix
it: a valid https URL on an attacker's server is exactly the attack.

The fix is to stop accepting third-party URLs entirely and serve media from a
first-party host that we control.

## Target design

```
client ──1. POST /api/v1/uploads ─────────────► bledi-server
              (declares content_type + size)
         ◄─2. { upload_url, object_key, expires_at }
              upload_url = presigned PUT, first-party bucket
client ──3. PUT <upload_url> (the bytes) ─────► object storage
client ──4. POST /api/v1/memories ────────────► bledi-server
              { object_key, ... }   (NOT a url)
         ◄─5. memory with media_url = our CDN host
```

### 1. Object storage

S3-compatible. Use **Cloudflare R2** or **MinIO** — both speak the S3 API, so the
same code works for local development (MinIO in `docker-compose.yml`) and
production (R2). Do not write an abstraction layer for other providers; one
S3 client is enough.

Bucket layout, so that access policy can be applied per prefix:

```
memories/<user_id>/<uuid>.<ext>      # user content
tmp/<user_id>/<uuid>                 # staging, before re-encode
```

### 2. Presigned upload

`POST /api/v1/uploads` takes `{"content_type": "image/jpeg", "size_bytes": 812345}`
and returns a presigned `PUT` URL valid for 10 minutes plus the `object_key`.

Constraints enforced **server-side at signing time**, before the URL is issued:

| Constraint | Value |
|---|---|
| Allowed image types | `image/jpeg`, `image/png`, `image/webp`, `image/heic` |
| Allowed video types | `video/mp4`, `video/quicktime` |
| Max image size | 10 MiB |
| Max video size | 100 MiB |
| Presign TTL | 10 minutes |
| Uploads per user per hour | 30 |

The presigned URL must bind `Content-Type` and (via a POST-policy form if the
client cannot be trusted with the size) `content-length-range`. A presigned PUT
alone does not cap size, so either use a presigned **POST** policy with
`content-length-range`, or verify the object size after upload and reject. The
simplest correct option is the presigned POST policy.

### 3. Post-upload verification and processing

A worker (or a synchronous step on the create-memory call) must, before the media
is ever served:

1. **Confirm the object exists and its real size is within the limit.** Do not
   trust the client's declared `size_bytes`.
2. **Confirm the bytes match the declared type.** Read the magic number; do not
   trust `Content-Type`. Reject a `.jpg` that is actually an HTML file.
3. **Re-encode images** (e.g. to WebP or JPEG) and **strip all EXIF** — including
   GPS tags, which would otherwise leak the exact location of a memory that is
   supposed to be radius-locked. This is a correctness requirement, not just a
   privacy nicety: an EXIF GPS tag defeats `unlock_radius_m` entirely.
4. **Transcode / probe video** to a known-good container and cap duration.
5. Write the final object to `memories/<user_id>/<uuid>.<ext>` and delete the
   staging object.

### 4. Serving

Serve only from a first-party host, e.g. `https://media.bledi.tn`, either via the
CDN in front of the bucket or via a signed-redirect endpoint. Two options:

- **Public CDN, unguessable keys.** Fine for `visibility = public` memories.
  The key is a UUID, so it is not enumerable.
- **Signed URLs for `friends` / `private` memories.** Generate a short-lived
  (e.g. 5 minute) signed GET at the moment the memory is unlocked. A public CDN
  URL would let anyone who ever saw it keep fetching the media after the memory
  was made private or deleted.

**Do not** store a permanent public URL for a non-public memory. Store the
`object_key` and sign on read.

### 5. Data model change

`memories.media_url` should become `memories.media_key` (the object key), and the
API should compute `media_url` on read. Keeping a stored absolute URL means a
bucket migration or CDN change invalidates every row. If a stored URL must be
kept for compatibility, store the key as the source of truth and treat the URL as
derived.

### 6. What this does NOT fix

- **GPS spoofing.** The unlock endpoint checks a *claimed* position. Nothing here
  proves the device is physically present. Do not describe radius-unlock as
  cryptographic proof of presence; it is a product affordance, and the honest
  framing is "the media is only shown to clients that report being within the
  radius."
- **Abuse.** Uploads need moderation, reporting and a takedown path before any
  public launch. Out of scope here.

## Minimum shippable subset

If a full pipeline is too large for the next milestone, the minimum safe version
is:

1. Presigned POST upload with `content-length-range` and a content-type allowlist.
2. Server-side magic-number check + size check on create.
3. Re-encode + EXIF strip for images.
4. Store `media_key`, sign on read, serve from one first-party host.
5. Reject any client-supplied absolute URL.

Steps 1–5 are what make it safe. Video transcoding (step 4 of the processing
list) can follow.
