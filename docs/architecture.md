# Architecture

The current program has one short path:

```text
Typer command -> application service -> httpx -> Bilibili extractor -> media model -> Rich/JSON
```

The important folders are:

- `cli`: command definitions and output.
- `application`: opens an HTTP client for a command and runs the small doctor checks.
- `extractors/bilibili`: input parsing, WBI signing, API reading, and DASH projection.
- `domain`: media data used by the extractor and selector.
- `selection`: quality, codec, and audio selection rules for the future downloader.

There is deliberately no repository layer, configuration framework, plugin system, schema export,
retry framework, or generic process/storage abstraction. New layers should appear only after two
real callers need the same behavior.

Private media URLs live only in `MediaSource`, whose fields are hidden from representation and
serialization. Normal tests use `httpx.MockTransport` and synthetic `.invalid` URLs.
