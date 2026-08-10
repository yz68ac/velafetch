# Architecture

The command path stays explicit:

```text
Typer command
  -> application service
  -> one curl_cffi session
  -> Bilibili resource inspection
  -> selected playback unit
  -> Rich table or JSON
```

Downloads add enumeration and per-unit work:

```text
inspect source -> enumerate item/page units -> preflight names
               -> for each unit, just in time:
                    load formats -> select tracks -> transfer/resume
                    -> publish or FFmpeg copy mux
                    -> cover / public subtitles / optional danmaku
               -> per-item batch result
```

The important modules are:

- `cli`: Typer commands and human/JSON rendering.
- `application/download.py`: sequential enumeration, stop/continue rules, and item results.
- `application/media_download.py`: one unit's transfer, mux, and media publication.
- `application/transfer.py`: one track's three attempts, backup URLs, Range resume, and length
  validation.
- `application/assets.py`: cover, subtitle conversion, danmaku, and transactional sidecars.
- `application/naming.py`: default names, templates, component limits, and stable partial paths.
- `extractors/bilibili/extractor.py`: source inspection, WBI cache, and just-in-time playback.
- `extractors/bilibili/video.py`, `bangumi.py`, and `collections.py`: resource-specific metadata and
  collection pagination.
- `extractors/bilibili/assets.py`: public sidecar descriptors.
- `domain`: immutable media/resource/selection data.
- `selection`: deterministic quality, codec, dynamic-range, and AAC selection.
- `transport.py`: the shared GET/stream protocol and fixed Chrome `curl_cffi` session.

There is no repository layer, configuration framework, plugin registry, generic task engine, or
parallel scheduler. Retry loops live next to the operations whose rules they implement: API and
small-resource retries are separate from media Range retries.

Partial paths identify the public resource and playback unit without persisting signed URLs:

```text
ordinary video: OUTPUT/.velafetch/<BV>/page-N/<format>.<container>.part
Bangumi:        OUTPUT/.velafetch/<ss>/ep-<id>/<format>.<container>.part
UGC list:       OUTPUT/.velafetch/<list-id>/<BV>/page-N/<format>.<container>.part
```

Private media, subtitle, and cover URLs live in `MediaSource`; its fields are excluded from repr and
serialization. Results contain only public canonical IDs/URLs, safe messages, and final local paths.

The real HTTP session uses one bundled `chrome` profile so TLS and HTTP behavior are internally
consistent. It does not rotate profiles or identities, and environment proxy variables are
disabled; only the explicit CLI proxy is passed through.
