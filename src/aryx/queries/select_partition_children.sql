SELECT inhrelid::regclass::text FROM pg_inherits WHERE inhparent = %(parent)s::regclass
