# Integrated sprint review — 2026-09-18

This private engineering review covers the integrated APHIS completeness
accounting, FSIS stale-handoff guard, FSIS recall evidence parser, Brazil
source documentation, and the shared country/source platform. No data was
published or promoted.

## Fixes applied

- APHIS completeness now remains `incomplete` when duplicate export-page rows
  are present, even if the inflated input count reaches the operator-supplied
  displayed-row count. Duplicate observations remain quarantined.
- FSIS recall establishment inference now requires an explicit `EST` marker
  in free text. Digits in firm names or reasons cannot create a source-local
  facility join.

## Validation

The focused package-qualified suite passed: 15 tests covering FSIS refresh,
FSIS recall parsing, APHIS Wave 2 accounting, and the US refresh/rehearsal
contracts. A direct `unittest discover -s pipeline/sources/us` invocation also
ran 62 tests successfully but reported two loader errors for relative-import
tests (`test_refresh` and `test_real_rehearsal`); running those modules with
package-qualified names passed them. This is an invocation portability issue,
not a product-test failure.

## Residual risks

The APHIS proof remains a bounded operator-saved subset, not a national
completeness or currentness claim. FSIS recalls remain private, review-required
evidence and source-local candidate edges; a recall is not itself a finding of
wrongdoing. Registry coverage, source terms, privacy review, factual review,
project approval, and publication remain separate gates. No public release or
promotion was performed.
