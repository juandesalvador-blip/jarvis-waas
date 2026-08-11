// =============================================================================
// JARVIS – Inicialización del Knowledge Graph en Neo4j
// Ejecutar manualmente (o vía `python scripts/jarvis_manager.py init-db`) con:
//   cypher-shell -u neo4j -p $NEO4J_PASSWORD -f config/neo4j/init.cypher
// =============================================================================

// Constraints de unicidad
CREATE CONSTRAINT persona_id IF NOT EXISTS FOR (p:Persona) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT conocimiento_nombre IF NOT EXISTS FOR (c:Conocimiento) REQUIRE c.nombre IS UNIQUE;
CREATE CONSTRAINT actividad_nombre IF NOT EXISTS FOR (a:Actividad) REQUIRE a.nombre IS UNIQUE;

// Datos de ejemplo (relación Persona -> Conocimiento)
MERGE (angel:Persona {id: 'angel-001', nombre: 'Ángel'})
MERGE (astro:Conocimiento {nombre: 'astronomía'})
MERGE (angel)-[:ESTUDIA]->(astro);

MERGE (act:Actividad {nombre: 'tutoria-semanal'})
MERGE (angel)-[:DESARROLLA_HABILIDAD]->(act);
