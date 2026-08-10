# Safety boundary

VelaFetch handles public media and media the locally logged-in user is already authorized to play.
It does not bypass payment, membership, region restrictions, access control, or DRM. Authentication
is limited to Bilibili Web QR login or a Cookie entered through a hidden prompt/stdin; no secret is
accepted as a command-line option, environment variable, or general request header.

Practical safeguards remain small and concrete:

- private media, subtitle, and cover URLs are neither printed nor stored in fixtures;
- external programs receive argument arrays and are never invoked through a shell;
- existing user files are not overwritten without `--overwrite`;
- API, sidecar, and transfer errors expose safe context rather than signed URLs;
- Bilibili cookies are sent only to HTTPS `.bilibili.com` hosts, never media CDN or sidecar hosts;
- the cwd-local `.velafetch/credentials.json` is intentionally plaintext, Git-ignored, and removed
  only by `auth logout`; users must protect the directory themselves;
- QR keys, login URLs, refresh tokens, and arbitrary browser cookies are never persisted;
- list support remains limited to UGC season/series URLs, not favorites or watch-later data.

If Bilibili returns a normal, unencrypted DASH response for the current account, VelaFetch can use
it. A missing entitlement, membership/paywall response, region denial, preview-only response, or
DRM marker remains unsupported. There is no automatic Cookie refresh or remote account mutation.

The project is private and has no redistribution license yet. Local reference repositories, when
present, are reading material rather than runtime or build dependencies.
