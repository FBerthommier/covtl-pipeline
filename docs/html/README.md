# Interactive HTML demos (repository-only)

Self-contained demo pages (embedded audio + polar trajectories, no
network): `index.html` (hub), `polar_demo_fr.html` (« ba.da.ga »),
`polar_demo_en.html` ("this is easy for us").

* **Never installed**: `pip install covtl-pipeline` ships only the
  `vtl_synth*` packages — this folder is repository-only
  (`pyproject.toml` allowlist + `MANIFEST.in` prunes for both
  `examples/` and `docs/html/`).
* **Regenerate**: `python docs/html/make_html_demos.py` re-synthesizes
  the phrases and rebuilds the pages in place (requires the engine and
  the demo MP4s under `out/html_demos`).
* **Publishing is an explicit copy**: the pages are served by GitHub
  Pages from this `docs/` folder, or copy the folder manually where
  needed. Nothing is deployed automatically by an install.
