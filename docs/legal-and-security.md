# Safety boundary

VelaFetch handles anonymously accessible public media in M6. It does not bypass payment,
membership, login, region restrictions, access control, or DRM. User-authorized account access is
reserved for M7 and must be designed so credentials do not enter command history or logs.

Practical safeguards remain small and concrete:

- private media, subtitle, and cover URLs are neither printed nor stored in fixtures;
- external programs receive argument arrays and are never invoked through a shell;
- existing user files are not overwritten without `--overwrite`;
- API, sidecar, and transfer errors expose safe context rather than signed URLs;
- list support is limited to public UGC season/series URLs, not favorites or watch-later data.

The project is private and has no redistribution license yet. Local reference repositories, when
present, are reading material rather than runtime or build dependencies.
