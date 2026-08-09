# Safety boundary

VelaFetch is for public media or content the user is authorized to access. It does not bypass
payment, membership, region restrictions, access control, or DRM.

The learning version keeps three practical safeguards:

- private media URLs and credentials are not printed or stored in fixtures;
- external programs are invoked with argument arrays, never through a shell;
- existing user files are not overwritten without an explicit option.

The project is private and has no redistribution license yet. The local repositories under
`references/` are reading material and are not runtime or build dependencies.
