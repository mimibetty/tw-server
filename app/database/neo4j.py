from neo4j import GraphDatabase

from app.environments import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER


class Neo4jConnection:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            uri=NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )

    def close(self):
        if self.driver is not None:
            self.driver.close()

    def query(self, query, parameters=None):
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters)
                return [record for record in result]
        except Exception as e:
            raise e
