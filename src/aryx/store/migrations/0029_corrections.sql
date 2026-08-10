-- Human corrections: standing instructions that fix data now and steer
-- every future ingest (replayed into extraction context, applied after
-- relate). Kinds: retype · suppress · alias · pin_link · forbid_link.
CREATE TABLE IF NOT EXISTS aryx_correction (
    id           BIGSERIAL PRIMARY KEY,
    workspace_id INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    subject      TEXT NOT NULL,
    object       TEXT NOT NULL DEFAULT '',
    detail       TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aryx_correction_ws ON aryx_correction (workspace_id);
