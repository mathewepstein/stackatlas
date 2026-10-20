from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors import datastore, detect


def refs_for(root: Path):
    return detect("x", root, Config(), [datastore])


def test_fixture_orders_service(acme):
    refs = detect("orders-service", acme / "orders-service", Config(), [datastore])
    got = [(r.path, r.line, r.kind, r.value, r.engine, r.key, r.env, r.edge_type) for r in refs]
    assert got == [
        ("src/main/resources/application-prod.properties", 2, "url",
         "prod-orders-db.acme.internal:5432/orders", "postgres", "spring.datasource.url", "prod",
         "datastore"),
        ("src/main/resources/application.yml", 5, "url", "orders-db:5432/orders", "postgres",
         "spring.datasource.url", None, "datastore"),
    ]
    assert not any("not-a-real-key" in r.snippet or "app@" in r.snippet for r in refs)


def test_url_forms_and_engines(tmp_path):
    (tmp_path / "a.py").write_text(
        'A = "jdbc:mysql://u:p@db1.internal:3306/x?password=zzz"\n'
        'B = "rediss://cache.internal:6380"\n'
        'C = "mongodb+srv://u:p@cluster0.mongodb.net/app"\n'
        'D = "jdbc:oracle:thin:@ora.internal:1521:ORCL"\n'
        'E = "postgres://pg.internal/db"\n'
    )
    refs = refs_for(tmp_path)
    assert [(r.engine, r.value, r.line) for r in refs] == [
        ("mysql", "db1.internal:3306/x", 1),
        ("redis", "cache.internal:6380", 2),
        ("mongo", "cluster0.mongodb.net/app", 3),
        ("oracle", "ora.internal:1521", 4),
        ("postgres", "pg.internal/db", 5),
    ]
    assert not any("zzz" in r.snippet or "u:p@" in r.snippet for r in refs)


def test_datastore_keys_with_hosts_and_placeholders(tmp_path):
    (tmp_path / "application.properties").write_text(
        "spring.redis.host=cache.internal\n"
        "spring.datasource.url=${DB_URL}\n"
        "spring.datasource.password=${DB_PASS}\n"
        "spring.data.mongodb.uri=mongodb://m.internal/app\n"
    )
    (tmp_path / ".env").write_text(
        "DB_URL=jdbc:postgresql://pg.internal/app\nDB_HOST=pg.internal\nAPI_URL=https://x.acme.com\n"
    )
    refs = refs_for(tmp_path)
    assert [(r.kind, r.value, r.engine, r.key, r.edge_type) for r in refs] == [
        ("url", "pg.internal/app", "postgres", "DB_URL", "datastore"),
        ("url", "pg.internal", "db", "DB_HOST", "datastore"),
        ("url", "cache.internal", "redis", "spring.redis.host", "datastore"),
        ("var", "DB_URL", None, "spring.datasource.url", "datastore"),
        ("url", "m.internal/app", "mongo", "spring.data.mongodb.uri", "datastore"),
    ]
