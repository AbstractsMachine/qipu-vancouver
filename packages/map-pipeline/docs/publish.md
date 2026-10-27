# publish

`qipu-map publish --release r20261026` writes the release's `manifest.json` and `ground.json`, then copies the release
to its bucket or to a folder. The format is [tiles-format.md](../../../docs/tiles-format.md).

## Inputs and outputs

| reads | writes |
|---|---|
| `tiles/today/`, `tiles/years/<year>/`, `tiles/switch/<a>-<b>/` (each with its `pyramid.json`) | `tiles/manifest.json` |
| `render/<today>/frames.json` (the canvas: left, top, width, height, metres per pixel) | `tiles/ground.json` |
| `scene/<today>/terrain.npz` (optional) | `<bucket_url>/<release>/...` |
| the city file: camera, projection, eras, attribution, `[publish]` | |

`--to` sends the release somewhere other than the city's `publish.bucket_url`: `s3://bucket/prefix`, `file:///path` or
a plain folder. `--dry-run` writes the two JSON files locally, prints one line per object that would be uploaded, and
uploads nothing. `--threads` sets the upload pool (16 by default).

## The manifest

Built from what is on disk, so it cannot name a tile that was not written:

- `canvas` comes from the render's `frames.json`; `zmax` is recomputed from its size and must match today's pyramid.
- `world_to_px` is `geo.camera.Canvas.affine()` for that canvas: the same two lines of arithmetic every stage uses to
  put things on the picture, rounded to a millionth of a pixel.
- Each layer's `have` comes from its `pyramid.json`; `v` is the first 8 hex digits of a SHA-256 over the layer's tile
  paths and MD5s. It changes when any tile of the layer changes and only then.
- `years` are the era years that have a pyramid, sorted. `switch` must hold one date map for each consecutive pair, the
  last ending at today; publish refuses a release where one is missing or extra, since the viewer would play a segment
  with no date map.
- `ground` is set when the scene has a terrain grid: the terrain averaged into 25 m cells, in whole decimetres. It is
  a few kilobytes for a district.

The output is deterministic: the same tiles and inputs give the same manifest, byte for byte, and no timestamps.

## Uploading

The release goes under `<bucket_url>/<release>/`: the tiles that the manifest names, `ground.json`, then
`manifest.json`. The rules, and why:

- Skip what is already there. One listing of the release prefix gives every object's ETag; an object whose ETag
  equals the local MD5 is not sent again. A re-run after fixing one tile writes that tile and the
  manifest (whose `v` for that layer changed), nothing else. Writes are billed per operation on R2, so this keeps a
  re-run cheap.
- Threads in one process. Parallel `gsutil -m` processes crashed Python on macOS; threads moved about 2,000 tiles a
  minute (measured) where a single-threaded copy moved 170. boto3 clients are safe to share between threads.
- Tiles first, manifest last, and only if every tile made it. If any upload fails, publish stops before the manifest
  and says so: viewers keep reading the previous manifest, whose tiles are all still there.
- Never delete. A viewer that loaded the previous manifest a minute ago can still fetch every tile it names.
- `Content-Type` per file (`image/webp`, `image/png`, `application/json`), `Content-MD5` so the store checks each body,
  and `Cache-Control` from the city file: `publish.cache_control` (default `public, max-age=300`) for the tiles and
  `ground.json`, `publish.manifest_cache_control` (default `public, max-age=60`) for the manifest.

### Caching tiles for longer

Five minutes is the safe default: a re-published tile keeps its URL, so a long cache would keep serving the old one.
A viewer that adds the layer's `v` to every tile URL (`?v=3f9a1c2e`), as the qipu viewer does, asks for a
new URL whenever a layer changes. Its tiles can then be cached for a year:

```toml
[publish]
cache_control = "public, max-age=31536000, immutable"
```

The setting also covers `ground.json`, whose URL carries no `v`. It only changes when the terrain does; if it does,
publish under a new release name rather than over the old one. The manifest keeps its own short setting.

Credentials come only from the standard `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` variables. The endpoint comes from
the variable named by `publish.endpoint_env` (`QIPU_MAP_S3_ENDPOINT` by default), which is how Cloudflare R2 is reached;
with an endpoint and no region set, the region is `auto`, as R2 expects. boto3 is the optional `publish` extra
(`pip install 'qipu-map[publish]'`); publishing to a folder needs nothing extra.

A folder target ignores content types and cache headers: they belong to whatever web server serves it.

## Limits

- Files are read whole into memory for upload; tiles are tens of kilobytes, so this is fine.
- Objects uploaded in several parts by another tool have ETags that are not MD5s; publish uploads those again once.
- The qipu.org site reads an older index (`render/index.json`, `render-years.json`) with several areas over a whole-city
  layer. This stage writes `qipu-tiles/1`, one area per release; it does not write the old index.
