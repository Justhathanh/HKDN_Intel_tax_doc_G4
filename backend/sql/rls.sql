-- Lop cach ly thu hai o PostgreSQL (SEC 01, ARC 01). Ap dung tai Sprint 1.
-- API phai chay bang role khong phai owner va SET LOCAL app.client_ids trong moi transaction.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['batches','documents','submissions','extracted_fields'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format($p$CREATE POLICY client_scope ON %I
      USING (client_id = ANY (string_to_array(current_setting('app.client_ids', true), ',')))
      WITH CHECK (client_id = ANY (string_to_array(current_setting('app.client_ids', true), ',')))$p$, t);
  END LOOP;
END $$;
