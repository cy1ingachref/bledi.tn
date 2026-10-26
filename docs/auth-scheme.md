# Single auth scheme across the two backends

Status: **design.** Nothing here is implemented yet. The recommended path is
**Option A**: Python becomes a token *consumer* that validates the same HS256
tokens the Rust server issues, using the shared `JWT_SECRET`.

## The problem

There are two backends:

| Backend | Owns | Auth today |
|---|---|---|
| Python FastAPI (`services/transit/`) | all transit routing, the seed data, geometry | none |
| Rust axum (`services/accounts/`) | auth, memories, favorites, location shares | JWT (HS256), bcrypt |

The Rust server signs HS256 tokens with `JWT_SECRET`. The Python server has no
auth at all and does not validate anything, so there is no way for the Python
side to know who the caller is.

Clients already have one base URL: the web image's nginx gateway routes each
path prefix to one service (see [architecture](architecture.md)). The gateway
does not touch auth.

## Options

### Option A — Keep the split, share the JWT (recommended)

Python becomes a token *consumer*, not a token *issuer*. It validates the same
HS256 tokens the Rust server issues, using the same `JWT_SECRET`, and derives the
caller identity from the `sub` claim.

- **One signing key.** Both services read `JWT_SECRET` from the environment. They
  must agree on the algorithm (`HS256`) and on the claim names (`sub`, `email`,
  `exp`, `iat`, already the shape in `services/accounts/bledi-server/src/jwt.rs`).
- **Issuer stays single.** Only the Rust server mints tokens. If Python ever
  needs to mint one (it should not), that is a signal the split is wrong.
- **FastAPI dependency.** A `Depends` that reads the `Authorization` header,
  decodes and verifies the token, and returns a `CurrentUser` (or `None` for
  optional-auth routes). Route handlers that need a user declare it.
- **Public vs private routes.** Routing endpoints stay public. Anything that
  reads or writes user data declares the dependency.

Cost: one new module in Python plus a dependency on a JWT library. Low risk.

Risk to be honest about: **shared-secret HS256 means any service holding the
secret can mint tokens.** With exactly two services that is acceptable. The
moment a third appears, move to RS256/EdDSA — the issuer signs with a private
key, everyone else verifies with a public key. That is a small change if the
verify path is written to take a key type rather than hardcoding HMAC.

### Option B — A gateway in front of both

A reverse proxy terminates auth, validates the token once, and forwards an
internal header (e.g. `X-User-Id`) to whichever backend handles the route. Both
backends stop doing JWT at all and trust the header.

- Requires the backends to be **unreachable except through the gateway**. If a
  backend is also exposed directly, the `X-User-Id` header is trivially forged.
  This is the failure mode that makes gateway auth dangerous: it is secure only
  when the network boundary is airtight.
- Adds a hop and a piece of infrastructure to operate.

Better as a later step, once there is a deployment to put it in.

### Option C — Port routing to Rust

One backend, one auth scheme, no shared-secret problem. This is the cleanest
end state.

It is also the largest job: the routing engine, the road/rail graphs, the OSRM
and Nominatim proxies, the geometry caches and the seed loader all move, and the
150-test Python suite becomes the specification for the Rust implementation.

Feasible — the tests and fixtures exist, which is exactly what makes a port
tractable — but it is a milestone, not a task.

## Recommendation

**Option A now, Option C eventually.**

Option A is a day of work and unblocks the Flutter and web clients immediately:
one base URL, one token, both backends agree on who the caller is. It also does
not foreclose Option C — a Python service that consumes JWTs is easy to delete
once routing lives in Rust.

Do **not** leave it as it is: today there is no way to identify a user on the
half that serves the product.

## Concrete next steps for Option A

1. Add `JWT_SECRET` to the Python service's required environment, and refuse to
   start without it (mirror the Rust server's behaviour).
2. Add a token verifier port in `bledi_transit.application`, an HS256 adapter,
   and a `current_user` FastAPI dependency in `adapters/http` that returns the
   `sub` UUID.
3. Write the verify path so the algorithm and key are configurable
   (`JWT_ALGORITHM`, default `HS256`) to make a later move to RS256 a config
   change rather than a rewrite.
4. Add tests: a valid token yields the right user; an expired token is rejected;
   a token signed with the wrong secret is rejected; a missing header on a
   protected route is a 401.
