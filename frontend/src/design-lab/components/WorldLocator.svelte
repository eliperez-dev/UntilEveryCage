<script lang="ts">
  import type { Basemap } from "../contract";
  import worldLandUrl from "../assets/world-land.svg";
  import {
    formatCameraCenter,
    projectWorldPosition,
  } from "./worldLocatorProjection";

  let {
    latitude,
    longitude,
    basemap,
    onbasemap,
  }: {
    latitude: number;
    longitude: number;
    basemap: Basemap;
    onbasemap(value: Basemap): void;
  } = $props();

  let expanded = $state(false);

  let position = $derived(projectWorldPosition(latitude, longitude));
  let coordinateLabel = $derived(formatCameraCenter(latitude, longitude));
</script>

<aside class="world-locator" class:expanded aria-label="Map lens">
  <div class="locator-heading">
    <button type="button" class="lens-toggle" aria-expanded={expanded} aria-controls="map-lens-options" onclick={() => expanded = !expanded}>Map lens <span aria-hidden="true">{expanded ? "−" : "+"}</span></button>
    <div class="mode-switch" aria-label="Map dimension">
      <button type="button" class="mode-active" aria-pressed="true">2D</button>
      <button
        type="button"
        disabled
        title="3D view is not available yet"
        aria-label="3D view is not available yet">3D</button
      >
    </div>
  </div>

  <svg
    class="world-map"
    viewBox="0 0 360 180"
    role="img"
    aria-label={`World overview with map camera at ${coordinateLabel}`}
    preserveAspectRatio="xMidYMid meet"
  >
    <image href={worldLandUrl} width="360" height="180" />
    <circle class="camera-ring" cx={position.x} cy={position.y} r="8" />
    <circle class="camera-dot" cx={position.x} cy={position.y} r="4" />
  </svg>

  <p class="camera-coordinate">Camera center <strong>{coordinateLabel}</strong></p>
  <div class="lens-options" id="map-lens-options" hidden={!expanded}>
    <span class="option-label">MAP VIEW</span>
    <div class="view-options" role="group" aria-label="Map view">
      <button type="button" aria-pressed={basemap === "vector"} onclick={() => onbasemap("vector")}>Street</button>
      <button type="button" aria-pressed={basemap === "satellite"} onclick={() => onbasemap("satellite")}>Satellite</button>
      <button type="button" aria-pressed={basemap === "muted"} onclick={() => onbasemap("muted")}>Muted</button>
    </div>
  </div>
</aside>

<style>
  .world-locator {
    box-sizing: border-box;
    width: 12.25rem;
    padding: 0.5rem 0.6rem 0.45rem;
    border: 1px solid #555b58;
    background: #171918eb;
    box-shadow: 0 2px 12px #0004;
    color: #e9eee8;
    font-family: system-ui, sans-serif;
    pointer-events: auto;
  }

  .locator-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    color: #c3c9c5;
    font-size: 0.56rem;
    font-weight: 700;
    letter-spacing: 0.08em;
  }
  .lens-toggle { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:0; border:0; background:none; color:#e9eee8; cursor:pointer; font:700 .66rem system-ui; letter-spacing:.02em; }
  .lens-toggle span { font-size:1rem; font-weight:400; }
  .lens-toggle:focus-visible, .view-options button:focus-visible { outline:2px solid #e9eee8; outline-offset:2px; }
  .lens-options { margin-top:.5rem; padding-top:.5rem; border-top:1px solid #48504b; }
  .lens-options[hidden] { display:none; }
  .option-label { color:#c3c9c5; font-size:.55rem; font-weight:700; letter-spacing:.08em; }
  .view-options { display:grid; grid-template-columns:repeat(3,1fr); gap:.2rem; margin-top:.35rem; }
  .view-options button { min-width:0; padding:.3rem .1rem; border:1px solid #5a625c; background:#202421; color:#e9eee8; cursor:pointer; font:.57rem system-ui; }
  .view-options button[aria-pressed="true"] { background:#e6e8e6; color:#171a18; }

  .mode-switch {
    display: flex;
    align-items: center;
    gap: 0.15rem;
    font-size: 0.62rem;
    letter-spacing: 0;
  }

  .mode-active,
  .mode-switch button {
    min-width: 1.65rem;
    padding: 0.12rem 0.2rem;
    border: 1px solid transparent;
    text-align: center;
  }

  .mode-active {
    border-color: #b6bbb8;
    background: #e6e8e6;
    color: #171a18;
    cursor: default;
  }

  .mode-switch button:disabled {
    background: transparent;
    color: #878e8a;
    cursor: not-allowed;
  }

  .world-map {
    display: block;
    width: 100%;
    aspect-ratio: 2;
    margin: 0.3rem 0 0.2rem;
    border: 1px solid #3e4441;
    background: #171b1ab8;
  }

  .camera-ring {
    fill: #c8dcdab3;
    stroke: #171b1a;
    stroke-width: 0.8;
  }

  .camera-dot {
    fill: #e1f0ee;
    stroke: #171b1a;
    stroke-width: 0.6;
  }

  .camera-coordinate {
    display: flex;
    justify-content: space-between;
    gap: 0.4rem;
    margin: 0;
    color: #c5cbc6;
    font-size: 0.58rem;
    white-space: nowrap;
  }

  .camera-coordinate strong {
    color: #e9eee8;
    font-size: 0.6rem;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }

  @media (max-width: 40rem) {
    .world-locator {
      width: auto;
      min-width: 5.4rem;
      padding: 0.4rem 0.5rem;
    }
    .world-locator:not(.expanded) .mode-switch,
    .world-locator:not(.expanded) .world-map,
    .world-locator:not(.expanded) .camera-coordinate {
      display: none;
    }
    .world-locator.expanded { width: 9.75rem; }
    .world-locator.expanded .camera-coordinate { display: block; }
    .world-locator.expanded .camera-coordinate strong {
      display: block;
      margin-top: 0.1rem;
    }
  }
</style>
