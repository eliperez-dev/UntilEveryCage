<script lang="ts">
  let { mode = "synthetic" }: { mode?: "synthetic" | "real-preview" } =
    $props();
</script>

<div class="precision-legend" aria-label="Map symbol legend">
  <strong>Map symbols</strong><span
    ><i class:coordinate={mode === "real-preview"} class="glyph exact"
    ></i>{mode === "real-preview"
      ? "Numeric source coordinate · review pending"
      : "Exact site"}</span
  ><span><i class="glyph approximate"></i>Approximate source coordinate</span
  ><span><i class="glyph cluster"></i>Parent cluster</span
  >{#if mode === "synthetic"}<span
      ><i class="glyph cluster city"></i>CITY aggregate</span
    ><span><i class="glyph cluster coarse"></i>AREA aggregate</span>{:else}<span
      ><i class="glyph reference city"></i>City reference · approximate, not a
      facility point</span
    ><span
      ><i class="glyph reference coarse"></i>Area reference · no approved map
      geometry</span
    >{/if}<span
    ><i class="glyph unmapped"></i>No mapped location · list only</span
  >{#if mode === "synthetic"}<small
      >Pin color: <b class="poultry"></b>Poultry <b class="pig"></b>Pig
      <b class="dairy"></b>Dairy <b class="processing"></b>Processing
      <b class="laboratory"></b>Lab
      <b class="aquaculture"></b>Aquaculture</small
    >{:else}<small class="preview-disclosure"
      >Private development preview · not publication-approved</small
    >{/if}
</div>

<style>
  .precision-legend {
    position: absolute;
    z-index: 2;
    bottom: 1rem;
    left: 1rem;
    display: grid;
    gap: 0.28rem;
    padding: 0.6rem;
    border: 1px solid #48504b;
    background: #171a18e8;
    color: #f1efe8;
    font: 0.65rem system-ui;
  }
  .precision-legend strong {
    font-size: 0.65rem;
  }
  .precision-legend small {
    display: flex;
    max-width: 15rem;
    flex-wrap: wrap;
    gap: 0.25rem;
    align-items: center;
    color: #c6cbc4;
    font-size: 0.54rem;
  }
  .precision-legend .preview-disclosure {
    display: block;
    max-width: 15rem;
    font-size: 0.58rem;
    line-height: 1.35;
  }
  .precision-legend b {
    width: 0.45rem;
    height: 0.45rem;
    border-radius: 50%;
    background: #c83232;
  }
  .precision-legend .pig {
    background: #8c8c8c;
  }
  .precision-legend .dairy {
    background: #7f5c9c;
  }
  .precision-legend .processing {
    background: #ccb44f;
  }
  .precision-legend .laboratory {
    background: #d47b30;
  }
  .precision-legend .aquaculture {
    background: #39804e;
  }
  .glyph {
    display: inline-block;
    width: 0.72rem;
    height: 0.72rem;
    margin-right: 0.35rem;
    vertical-align: -0.1rem;
  }
  .exact {
    width: 0.52rem;
    height: 0.78rem;
    border: 2px solid #fff;
    border-radius: 55% 55% 55% 0;
    background: #c83232;
    box-shadow: 0 1px 2px #0008;
    transform: rotate(-45deg);
  }
  .exact.coordinate {
    width: 0.72rem;
    height: 0.72rem;
    border: 2px solid #171a18;
    border-radius: 50%;
    background: #d8c99b;
    box-shadow: none;
    transform: none;
  }
  .approximate {
    border: 2px solid #262820;
    border-radius: 50%;
    background: #d8c99b;
  }
  .cluster {
    border-radius: 50%;
    background: #6ecc39;
    box-shadow: 0 0 0 4px #b5e28c;
  }
  .cluster.city {
    outline: 2px solid #315b83;
  }
  .cluster.coarse {
    outline: 2px solid #6b4f2f;
  }
  .reference {
    border-radius: 50%;
    background: #15252c;
    border: 2px solid #86aeca;
  }
  .reference.coarse {
    background: #292117;
    border-color: #c9a36e;
  }
  .unmapped {
    height: 0.35rem;
    border-bottom: 1px solid #e9ebe6;
  }
  @media (max-width: 40rem) {
    .precision-legend {
      bottom: 0.65rem;
      left: 0.65rem;
      font-size: 0.58rem;
    }
  }
</style>
