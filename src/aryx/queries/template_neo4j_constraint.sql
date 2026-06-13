{ddl_verb} {name}_id_unique IF NOT EXISTS FOR (n:{name}) REQUIRE n.id IS UNIQUE;
