-- The public organization selector now anchors source-asserted legal/operator
-- names through the exact retained-record release binding and artifact. Retire
-- builds made by the prior selector so live views fail closed until v3 is
-- rebuilt with those checks.
UPDATE uec.graph_public_projection_builds
   SET active=false
 WHERE active;

UPDATE uec.graph_projection_generation
   SET generation=generation+1
 WHERE singleton=true;
