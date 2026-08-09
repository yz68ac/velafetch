# Upstream reference repositories

The repositories below are optional, local reading material. The complete `references/` tree is
Git-ignored and excluded from type checking, tests, builds, coverage, and releases.

## BBDown

- Upstream: <https://github.com/nilaoda/BBDown.git>
- Local path: `references/legacy/BBDown`
- Pinned reference commit: `259a5558cee0a349a7ebb60bd31e40c88e5bc1ed`
- License: MIT, copyright 2020 nilaoda
- Purpose: historical Bilibili feature inventory, API modes, authentication flows, naming behavior,
  and regression scenarios.
- Restrictions: do not build it as part of VelaFetch, reference its assemblies, promise CLI
  compatibility, or translate it line by line.

Recreate the local reference:

```powershell
git clone https://github.com/nilaoda/BBDown.git references/legacy/BBDown
git -C references/legacy/BBDown checkout 259a5558cee0a349a7ebb60bd31e40c88e5bc1ed
```

## N_m3u8DL-RE

- Upstream: <https://github.com/nilaoda/N_m3u8DL-RE.git>
- Local path: `references/upstream/N_m3u8DL-RE`
- Pinned reference commit: `e113dee70c924ee08dae5460624909b04d84cb76`
- License: MIT, copyright 2022 nilaoda
- Purpose: manifest modeling, bounded fragment downloads, integrity tests, merge behavior, and
  live-stream state-machine ideas.
- Restrictions: do not introduce a .NET runtime dependency or copy the C# implementation.

Recreate the local reference:

```powershell
git clone https://github.com/nilaoda/N_m3u8DL-RE.git references/upstream/N_m3u8DL-RE
git -C references/upstream/N_m3u8DL-RE checkout e113dee70c924ee08dae5460624909b04d84cb76
```

If implementation code is ever copied or substantially adapted, record the exact source file,
commit, copyright notice, and license in a tracked attribution document.

These repositories are examples to study, not compatibility targets for VelaFetch.
