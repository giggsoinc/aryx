-- Neo4j uniqueness constraint template for ontology export (Slice 4).
-- {name} = sanitised label.
{ddl_verb} {name}_id_unique IF NOT EXISTS FOR (n:{name}) REQUIRE n.id IS UNIQUE;
