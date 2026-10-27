# map-preview

A small static page that puts the decisions in `decisions.geojson` on a map and lists them beside it, with a year slider and
a link from each decision to its page in the archive.org viewer. It is the quickest way to look at what `qipu-records` made.
It is not the product's map: that is [`packages/viewer`](../../viewer). There is no build step; the page is plain HTML, CSS
and JavaScript, and loads MapLibre GL JS and the OpenFreeMap basemap from the network. The browser test
`tests/e2e/test_demo_map.py` drives it.

To open it, from `packages/records`:

```sh
make demo     # writes build/demo/decisions.geojson
make serve    # then open http://localhost:8000/map-preview/
```

To show another file, add `?data=<url>` to the address. Only links to archive.org pages are made clickable.
