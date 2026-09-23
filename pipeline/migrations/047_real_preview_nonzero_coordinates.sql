-- Candidate points at (0,0) are unusable. NOT VALID preserves immutable
-- historical evidence while enforcing the rule for every subsequent insert.
ALTER TABLE real_preview.candidates
    ADD CONSTRAINT real_preview_candidates_nonzero_point
    CHECK (latitude IS NULL OR latitude <> 0 OR longitude <> 0) NOT VALID;
