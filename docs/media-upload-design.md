# Media upload design

Status: **implemented for images.** A geo-pinned memory now carries a real
photo: the accounts service receives it, checks it, stores it under its own
media root and serves it back. The object-storage pipeline described at the
end of this document is still the target for video, and for images once the
data grows.

## What is implemented

- **The photo travels with the memory.** `POST /api/v1/memories` takes a
  multipart form; the `photo` part is the image. The client never names a file
  and never sends a URL.
- **The type comes from the bytes.** The server reads the magic number and
  accepts only JPEG and PNG (`services/accounts/bledi-http/src/media.rs`). A
  `.jpg` that is really an HTML file is refused.
- **The size is capped at 10 MiB** (`media::MAX_UPLOAD_BYTES`), and the body
  limit on the route leaves room for the multipart overhead.
- **The metadata is dropped.** EXIF and XMP blocks are stripped before the
  photo is stored (`services/accounts/bledi-http/src/exif.rs`). A GPS tag would
  otherwise defeat `unlock_radius_m` outright.
- **The key is the source of truth.** The server names the file `<uuid>.<ext>`
  and stores that key with the memory; `media_url` is derived from it
  (`/api/v1/media/<key>`), so a change of host or path rewrites the URL without
  touching a stored row.
- **The photo is served only to the people who may see the memory.**
  `GET /api/v1/media/:key` resolves the key back to its memory and applies that
  memory's visibility rules, so a private photo is not reachable by guessing a
  URL. The response is `private, max-age=300` and `nosniff`.
- **The browser cannot load it directly.** The endpoint needs the caller's
  token, so the client fetches the bytes and shows them through an object URL
  (`fetchMedia` in `apps/web/src/lib/api.js`).

What is not done: video, object storage and moderation. The JSON create path
still accepts a `media_url` pointing at a third-party host; the multipart path
the app uses ignores it, but the server should refuse it outright.

## Why the third-party URL had to go

A memory used to store an arbitrary string in `media_url`, and the frontend
rendered it directly:

```svelte
<img src={m.media_url} alt="" />
```

That let anyone create a memory pointing at a host they control and log the IP
address, User-Agent and Referer of every viewer who scrolled past it. It also
meant the app could be used to host arbitrary content under a bledi.tn page.

Validation of `media_url` (absolute http/https, max 2048 chars, no `data:` URLs
— see `services/accounts/bledi-domain/src/text.rs`) reduced the blast radius
but did not fix it: a valid https URL on an attacker's server is exactly the
attack.

The fix was to stop accepting third-party URLs for uploaded photos and serve the
media from the accounts service itself.

## The object-storage design (not implemented yet)

The photos now live on the media root of the accounts service, which is a
volume. That is enough for one server, and not enough for more than one. The
target design moves the bytes into object storage and keeps the key as the
only thing the database stores.

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

Steps 1–3 are done today; 4 and 5 are what object storage would add.

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

Done: `memories.media_key` holds the object key and the API computes
`media_url` on read. Keeping a stored absolute URL would mean a bucket migration
or CDN change invalidates every row.

### 6. What this does NOT fix

- **GPS spoofing.** The unlock endpoint checks a *claimed* position. Nothing here
  proves the device is physically present. Do not describe radius-unlock as
  cryptographic proof of presence; it is a product affordance, and the honest
  framing is "the media is only shown to clients that report being within the
  radius."
- **Abuse.** Uploads need moderation, reporting and a takedown path before any
  public launch. Out of scope here.

## Minimum shippable subset

For the image path, the minimum safe version is done:

1. Presigned POST upload with `content-length-range` and a content-type allowlist.
   *Today: a multipart form to the create-memory call, with the same size cap
   and allowlist enforced on the bytes.*
2. Server-side magic-number check + size check on create.
3. Re-encode + EXIF strip for images. *Today: the EXIF strip is done; the
   re-encode is not.*
4. Store `media_key`, sign on read, serve from one first-party host.
5. Reject any client-supplied absolute URL. *Not done on the JSON path yet.*

Steps 1–5 are what make it safe. Video transcoding (step 4 of the processing
list) can follow.
