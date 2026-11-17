"""已审RF02的真实本机结构演练；不连接共享实例，不授予模型或发送权限。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import secrets
import sys
from pathlib import Path

import asyncmy
import pytest
from psycopg import AsyncConnection, Error, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row, tuple_row

from tests.integration.context_control.test_memory_execution_mysql import configured_url

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / ".local-acceptance/agent-memory-implementation"
pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1"
    or os.environ.get("MEMORY_IT_ALLOW_SCHEMA_DDL") != "1",
    reason="须root显式本机双库及已审RF02哈希",
)


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zero_checks(columns, rows) -> int:
    checked = 0
    for row in rows:
        values = row if isinstance(row, dict) else dict(zip(columns, row))
        for name, value in values.items():
            if (
                name.startswith(
                    (
                        "invalid_",
                        "orphaned_",
                        "resurrected_",
                        "mismatched_",
                        "incompatible_",
                        "existing_delta_",
                    )
                )
                or name == "prefixed_indexes"
            ):
                assert value == 0, "RF02结构检查发现异常"
                checked += 1
    return checked


async def _mysql_script(connection, path: Path, parser) -> int:
    checked = 0
    async with connection.cursor() as cursor:
        for statement in parser.statements(path):
            await cursor.execute(statement)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                checked += _zero_checks(columns, await cursor.fetchall())
    return checked


async def _pg_script(connection, path: Path) -> int:
    cursor = await connection.execute(path.read_text(encoding="utf-8"), prepare=False)
    checked = 0
    while True:
        if cursor.description:
            checked += _zero_checks(
                [column.name for column in cursor.description], await cursor.fetchall()
            )
        if not cursor.nextset():
            break
    return checked


async def _mysql_definitions(connection, scripts, parser) -> None:
    expected = {}
    for path in scripts:
        for statement in parser.statements(path):
            match = re.match(r"CREATE TRIGGER (\w+)", statement, re.IGNORECASE)
            if match:
                body = re.search(
                    r"\bBEGIN\b.*\bEND$", statement, re.IGNORECASE | re.DOTALL
                )
                assert body is not None
                expected[match[1]] = body.group(0).strip()
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT trigger_name,action_statement FROM information_schema.triggers WHERE trigger_schema=DATABASE()"
        )
        actual = dict(await cursor.fetchall())
        assert expected and all(
            actual[name].replace("\r\n", "\n").strip() == body
            for name, body in expected.items()
        )
        await cursor.execute(
            "SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND constraint_type='CHECK' AND enforced<>'YES'"
        )
        assert (await cursor.fetchone())[0] == 0


async def _pg_definitions(connection, path: Path, schema: str) -> None:
    expected = {
        name: body.strip()
        for name, body in re.findall(
            r"CREATE FUNCTION (\w+)\(\).*?AS \$\$(.*?)\$\$;",
            path.read_text(encoding="utf-8"),
            re.IGNORECASE | re.DOTALL,
        )
    }
    rows = await connection.execute(
        "SELECT p.proname,p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s",
        (schema,),
    )
    actual = {row["proname"]: row["prosrc"].strip() for row in await rows.fetchall()}
    assert len(expected) == 2 and expected == actual
    result = await connection.execute(
        "SELECT COUNT(*) AS invalid FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=%s AND NOT c.convalidated",
        (schema,),
    )
    assert (await result.fetchone())["invalid"] == 0


async def test_reviewed_refresh_schema_constraints_scrub_and_rollback():
    approval = json.loads(
        (OUT / "green/D16RF02-isolated-sql-approval.json").read_text(encoding="utf-8")
    )
    assert approval["task"] == "D16RF02" and not approval["sharedDdlApproved"]
    for relative, digest in approval["sqlHashes"].items():
        path = (ROOT / relative).resolve()
        assert (
            path.is_relative_to(ROOT)
            and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        )
    fixture = OUT / "D16RF02-schema-cases.py"
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == approval["fixtureHash"]
    frozen = json.loads(
        (OUT / "manifests/D16RF02-after.json").read_text(encoding="utf-8")
    )
    assert approval["fixtureHash"] == frozen[fixture.relative_to(ROOT).as_posix()]
    for name, digest in approval["reviewHashes"].items():
        assert (
            hashlib.sha256((OUT / "reviews" / name).read_bytes()).hexdigest() == digest
        )
    sys.path.insert(0, str(OUT))
    parser = _module("rf02_schema_parser", OUT / "run_memory_schema_it.py")
    cases = _module("rf02_reviewed_cases", fixture)
    url = configured_url()
    mysql = await asyncmy.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        db=url.database,
        autocommit=True,
    )

    async def connect_new():
        return await asyncmy.connect(
            host=url.host,
            port=url.port,
            user=url.username,
            password=url.password,
            db=url.database,
            autocommit=True,
        )

    dsn = os.environ["MEMORY_IT_POSTGRES_DSN"]
    assert conninfo_to_dict(dsn).get("host") in {"127.0.0.1", "localhost", "::1"}
    pg = await AsyncConnection.connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        prepare_threshold=0,
        connect_timeout=5,
    )
    schema = "memory_it_rf02_" + secrets.token_hex(5)
    created = False
    result = {"realProviderCalls": 0, "sharedWrites": False, "assertions": {}}
    java_up = (
        ROOT
        / "ai-efficiency-platform/sql/migration/V1.2.18__memory_context_refresh.sql"
    )
    java_pre = (
        ROOT
        / "ai-efficiency-platform/sql/verification/V1.2.18__precheck_memory_context_refresh.sql"
    )
    java_verify = (
        ROOT
        / "ai-efficiency-platform/sql/verification/V1.2.18__verify_memory_context_refresh.sql"
    )
    java_down = (
        ROOT
        / "ai-efficiency-platform/sql/rollback/R__V1.2.18__memory_context_refresh.sql"
    )
    mysql_dir = (
        ROOT / "efficiency-platform-agent/sql/bootstrap/memory_context_refresh_v1"
    )
    pg_dir = ROOT / "efficiency-platform-agent/sql/bootstrap/memory_thread_refresh_v1"
    try:
        async with mysql.cursor() as cursor:
            await cursor.execute("SELECT DATABASE()")
            assert (await cursor.fetchone())[0] == url.database
        result["assertions"]["initialMySqlVerify"] = await _mysql_script(
            mysql, java_verify, parser
        ) + await _mysql_script(mysql, mysql_dir / "03-verify.sql", parser)
        await _mysql_definitions(mysql, (java_up, mysql_dir / "02-up.sql"), parser)
        await _mysql_script(mysql, java_down, parser)
        await _mysql_script(mysql, mysql_dir / "04-rollback.sql", parser)
        assert await _mysql_script(mysql, java_pre, parser) >= 1
        assert await _mysql_script(mysql, mysql_dir / "01-precheck.sql", parser) >= 2
        for path in (java_up, mysql_dir / "02-up.sql"):
            await _mysql_script(mysql, path, parser)
        await _mysql_definitions(mysql, (java_up, mysql_dir / "02-up.sql"), parser)
        await pg.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        created = True
        await pg.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
        )
        assert (
            await (await pg.execute("SELECT current_schema() AS selected")).fetchone()
        )["selected"] == schema
        for topic in ("memory_thread_v1", "memory_thread_capability_v1"):
            await _pg_script(
                pg,
                ROOT / "efficiency-platform-agent/sql/bootstrap" / topic / "02-up.sql",
            )
        assert await _pg_script(pg, pg_dir / "01-precheck.sql") >= 5
        await _pg_script(pg, pg_dir / "02-up.sql")
        await _pg_definitions(pg, pg_dir / "02-up.sql", schema)
        assert await _pg_script(pg, pg_dir / "03-verify.sql") >= 4
        await _pg_script(pg, pg_dir / "04-rollback.sql")
        assert await _pg_script(pg, pg_dir / "01-precheck.sql") >= 5
        await _pg_script(pg, pg_dir / "02-up.sql")
        await _pg_definitions(pg, pg_dir / "02-up.sql", schema)
        result["mysqlCases"] = await cases.exercise_mysql(mysql)
        result["mysqlExpiryCases"] = await cases.exercise_mysql_expiry(mysql)
        result["mysqlReviewCases"] = await cases.exercise_review_mysql(mysql)
        result["mysqlNativeRrCases"] = await cases.exercise_native_rr_mysql(
            mysql, connect_new
        )
        pg.row_factory = tuple_row
        try:
            result["pgCases"] = await cases.exercise_pg(pg)
            result["pgReviewCases"] = await cases.exercise_review_pg(pg)
        finally:
            pg.row_factory = dict_row
        result["assertions"]["finalMySqlVerify"] = await _mysql_script(
            mysql, java_verify, parser
        ) + await _mysql_script(mysql, mysql_dir / "03-verify.sql", parser)
        result["assertions"]["finalPgVerify"] = await _pg_script(
            pg, pg_dir / "03-verify.sql"
        )
        for path in (java_down, mysql_dir / "04-rollback.sql"):
            with pytest.raises(
                asyncmy.errors.Error, match="MEMORY_REFRESH_ROLLBACK_REQUIRES_UNUSED"
            ):
                await _mysql_script(mysql, path, parser)
        with pytest.raises(Error, match="MEMORY_REFRESH_ROLLBACK_REQUIRES_UNUSED"):
            await _pg_script(pg, pg_dir / "04-rollback.sql")
        await pg.rollback()
        result["assertions"]["protectedAfterRefusedRollback"] = (
            await _mysql_script(mysql, java_verify, parser)
            + await _mysql_script(mysql, mysql_dir / "03-verify.sql", parser)
            + await _pg_script(pg, pg_dir / "03-verify.sql")
        )
        await _mysql_definitions(mysql, (java_up, mysql_dir / "02-up.sql"), parser)
        await _pg_definitions(pg, pg_dir / "02-up.sql", schema)
        result["unusedRollbackReup"] = True
        result["usedRollbackRefused"] = True
    finally:
        mysql.close()
        await pg.rollback()
        if created:
            await pg.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
        await pg.close()
        result["ownedPgSchemaRemoved"] = created
        (OUT / "green/D16RF02-schema-cycle.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
