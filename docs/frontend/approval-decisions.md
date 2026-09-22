# Decisions requiring maintainer approval

The design can proceed without blocking on aesthetic micro-decisions. These
decisions materially affect product scope or public contract and should be
recorded before implementation is declared complete.

1. **Public graph contract:** approve the narrow one-hop release-scoped graph
   projection and its exact/inferred confidence vocabulary. Confirm that all
   inferred edges remain public but prominently qualified and filterable.
2. **Map engine:** approve MapLibre/WebGL as the preferred candidate after the
   benchmark, or accept Leaflet if it demonstrably meets the same transfer,
   memory, and pan budgets.
3. **Approximate rendering:** approve the area/halo city grammar and defer
   heatmaps unless exact/coarse semantics can remain unmistakable.
4. **Profile exposure:** choose whether official is the only public default at
   launch and whether secondary/community profiles are explicit opt-in routes.
5. **Export scope:** approve bounded server export for MVP and defer bulk release
   snapshots to the named release workflow.
6. **V1 language:** confirm whether de/es/fr remain launch locales or whether
   English-first implementation ships with translation-ready architecture.
7. **Visual identity:** approve the “field notebook” direction, restrained
   palette, and no-shock-imagery stance before visual implementation begins.

## Recommended defaults

Approve all seven recommendations above, with English-first launch only if
translation resources are unavailable. Keep the public graph visible from day
one, but put it below the record's evidence/precision context and use one-hop
rows rather than a graph canvas. Let measured performance choose the map engine.

