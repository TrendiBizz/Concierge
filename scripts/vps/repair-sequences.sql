-- Run after restoring a legacy Concierge dump, before starting API writers.
-- Some imported rows had IDs beyond their sequence. Never move a sequence back.
DO $$
DECLARE r record; seq text; maximum bigint; previous bigint;
BEGIN
 FOR r IN SELECT table_schema,table_name,column_name FROM information_schema.columns
          WHERE table_schema='public' AND column_default LIKE 'nextval(%'
 LOOP
  seq := pg_get_serial_sequence(format('%I.%I',r.table_schema,r.table_name),r.column_name);
  IF seq IS NOT NULL THEN
   EXECUTE format('SELECT max(%I) FROM %I.%I',r.column_name,r.table_schema,r.table_name) INTO maximum;
   EXECUTE format('SELECT last_value FROM %s',seq) INTO previous;
   IF maximum IS NOT NULL AND maximum >= previous THEN
    PERFORM setval(seq::regclass,maximum,true);
   END IF;
  END IF;
 END LOOP;
END $$;
