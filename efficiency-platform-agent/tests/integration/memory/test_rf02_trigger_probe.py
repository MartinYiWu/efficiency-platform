"""RF02P 本机 Toy 表诊断；不安装任何 RF02 正式 SQL，不连接共享实例。"""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import asyncmy
import pytest

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / ".local-acceptance/agent-memory-implementation"
pytestmark = pytest.mark.skipif(
    os.environ.get("D16RF02P_PROBE_ALLOWED") != "1"
    or os.environ.get("MEMORY_IT_ENABLED") != "1"
    or os.environ.get("MEMORY_IT_LOCAL_MYSQL_ONLY") != "1",
    reason="仅 root 明确授权的 D16RF02P 本机 Toy 诊断",
)
MODES = {"exclusive": "FOR UPDATE", "shared": "LOCK IN SHARE MODE", "plain": ""}


async def _attempt(cursor, statement, params):
    try:
        await cursor.execute(statement, params)
    except asyncmy.errors.Error as error:
        return {"ok": False, "code": error.args[0], "message": str(error.args[1])}
    return {"ok": True}


async def test_native_trigger_lock_read_diagnostic():
    assert os.environ["MEMORY_IT_LOCAL_MYSQL_HOST"] == "127.0.0.1"
    url = urlsplit(os.environ["MEMORY_IT_MYSQL_JDBC_URL"].removeprefix("jdbc:"))
    assert url.hostname == "127.0.0.1"
    schema = url.path.lstrip("/")
    assert re.fullmatch(r"aiep_memory_it_20261117_[0-9a-f]{10}", schema)
    options = {
        "host": "127.0.0.1",
        "port": url.port,
        "user": os.environ["MEMORY_IT_MYSQL_USER"],
        "password": os.environ["MEMORY_IT_MYSQL_PASSWORD"],
        "db": schema,
        "autocommit": True,
        "connect_timeout": 5,
    }
    first = await asyncmy.connect(**options)
    second = await asyncmy.connect(**options)
    report = {
        "task": "D16RF02P",
        "toyOnly": True,
        "paidCalls": 0,
        "sharedBusinessWrites": False,
        "schema": schema,
        "modes": {},
    }
    tables = ["rf02p_parent"] + [f"rf02p_{mode}" for mode in MODES]
    try:
        async with first.cursor() as a, second.cursor() as b:
            for cursor in (a, b):
                await cursor.execute(
                    "SELECT DATABASE(),CONNECTION_ID(),@@version,@@transaction_isolation"
                )
                database, session_id, version, isolation = await cursor.fetchone()
                assert database == schema and version.startswith("8.0.26")
                report.setdefault("sessions", []).append(
                    {"id": session_id, "version": version, "isolation": isolation}
                )
                await cursor.execute("SET SESSION innodb_lock_wait_timeout=3")
                await cursor.execute("SET SESSION lock_wait_timeout=3")
                await cursor.execute(
                    "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ"
                )
            await a.execute(
                "CREATE TABLE rf02p_parent(id INT PRIMARY KEY,value INT NOT NULL) ENGINE=InnoDB"
            )
            for index, (mode, lock) in enumerate(MODES.items(), start=1):
                table = f"rf02p_{mode}"
                await a.execute(
                    f"CREATE TABLE {table}(id INT PRIMARY KEY,owner_id INT NOT NULL,kind VARCHAR(12) NOT NULL,phase VARCHAR(24) NOT NULL,target_revision INT NOT NULL DEFAULT 0,next_wait_id INT,observed_ready INT,observed_max INT) ENGINE=InnoDB"
                )
                await a.execute(f"""CREATE TRIGGER trg_{table}_insert BEFORE INSERT ON {table} FOR EACH ROW
BEGIN
 DECLARE parent_value INT;
 DECLARE matches INT;
 DECLARE highest INT;
 SELECT value INTO parent_value FROM rf02p_parent WHERE id=NEW.owner_id FOR UPDATE;
 IF NEW.kind='REFRESH' THEN
  SELECT COUNT(*) INTO matches FROM {table} WHERE owner_id=NEW.owner_id AND kind='WAIT' AND phase='READY' {lock};
  SELECT COALESCE(MAX(target_revision),0) INTO highest FROM {table} WHERE owner_id=NEW.owner_id AND kind='HISTORY' {lock};
  SET NEW.observed_ready=matches;
  SET NEW.observed_max=highest;
  IF matches<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RF02P_WAIT_NOT_READY'; END IF;
  IF NEW.target_revision<=highest THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RF02P_REVISION_REGRESSION'; END IF;
 END IF;
END""")
                await a.execute(f"""CREATE TRIGGER trg_{table}_update BEFORE UPDATE ON {table} FOR EACH ROW
BEGIN
 DECLARE parent_value INT;
 DECLARE matches INT;
 SELECT value INTO parent_value FROM rf02p_parent WHERE id=NEW.owner_id FOR UPDATE;
 IF OLD.phase='PENDING' AND NEW.phase='APPLIED_EXPIRED' THEN
  SELECT COUNT(*) INTO matches FROM {table} WHERE id=NEW.next_wait_id AND kind='WAIT' AND phase='READY' {lock};
  SET NEW.observed_ready=matches;
  IF matches<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RF02P_NEXT_WAIT_NOT_READY'; END IF;
 END IF;
END""")
                await a.execute("INSERT INTO rf02p_parent VALUES(%s,1)", (index,))
                await a.execute(
                    f"INSERT INTO {table}(id,owner_id,kind,phase,target_revision) VALUES(1,%s,'WAIT','READY',0),(10,%s,'HISTORY','DONE',5),(20,%s,'CANDIDATE','PENDING',8)",
                    (index, index, index),
                )
                result = report["modes"][mode] = {"lockingClause": lock}
                result["basicInsert"] = await _attempt(
                    a,
                    f"INSERT INTO {table}(id,owner_id,kind,phase,target_revision) VALUES(2,%s,'REFRESH','PENDING',8)",
                    (index,),
                )
                if result["basicInsert"]["ok"]:
                    await a.execute(
                        f"SELECT observed_ready,observed_max FROM {table} WHERE id=2"
                    )
                    result["basicInsert"]["observed"] = list(await a.fetchone())
                result["sameTableUpdate"] = await _attempt(
                    a,
                    f"UPDATE {table} SET phase='APPLIED_EXPIRED',next_wait_id=1 WHERE id=20",
                    (),
                )

                # A 已有 RR read view；B 在同一 parent 排他锁下提交 READY 与更高历史。
                await a.execute(f"UPDATE {table} SET phase='BUILDING' WHERE id=1")
                await first.begin()
                await a.execute(
                    f"SELECT COUNT(*),COALESCE(MAX(target_revision),0) FROM {table} WHERE (kind='WAIT' AND phase='READY') OR kind='HISTORY'"
                )
                result["initialReadView"] = list(await a.fetchone())
                await second.begin()
                await b.execute(
                    "SELECT value FROM rf02p_parent WHERE id=%s FOR UPDATE", (index,)
                )
                await b.fetchone()
                await b.execute(f"UPDATE {table} SET phase='READY' WHERE id=1")
                await b.execute(
                    f"INSERT INTO {table}(id,owner_id,kind,phase,target_revision) VALUES(11,%s,'HISTORY','DONE',7)",
                    (index,),
                )
                await second.commit()
                await a.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE kind='WAIT' AND phase='READY'"
                )
                result["ordinarySelectAfterOtherCommit"] = (await a.fetchone())[0]
                result["rrReadyInsert"] = await _attempt(
                    a,
                    f"INSERT INTO {table}(id,owner_id,kind,phase,target_revision) VALUES(3,%s,'REFRESH','PENDING',8)",
                    (index,),
                )
                if result["rrReadyInsert"]["ok"]:
                    await a.execute(
                        f"SELECT observed_ready,observed_max FROM {table} WHERE id=3"
                    )
                    result["rrReadyInsert"]["observed"] = list(await a.fetchone())
                await first.rollback()

                # A 的旧 view 已见 READY；B 再提交 revision9，旧 MAX7 不得准许 revision8。
                await first.begin()
                await a.execute(
                    f"SELECT COALESCE(MAX(target_revision),0) FROM {table} WHERE kind='HISTORY'"
                )
                result["oldMaxReadView"] = (await a.fetchone())[0]
                await second.begin()
                await b.execute(
                    "SELECT value FROM rf02p_parent WHERE id=%s FOR UPDATE", (index,)
                )
                await b.fetchone()
                await b.execute(
                    f"INSERT INTO {table}(id,owner_id,kind,phase,target_revision) VALUES(12,%s,'HISTORY','DONE',9)",
                    (index,),
                )
                await second.commit()
                result["rrRevisionRegression"] = await _attempt(
                    a,
                    f"INSERT INTO {table}(id,owner_id,kind,phase,target_revision) VALUES(4,%s,'REFRESH','PENDING',8)",
                    (index,),
                )
                if result["rrRevisionRegression"]["ok"]:
                    await a.execute(
                        f"SELECT observed_ready,observed_max FROM {table} WHERE id=4"
                    )
                    result["rrRevisionRegression"]["observed"] = list(
                        await a.fetchone()
                    )
                await first.rollback()
            assert report["modes"]["exclusive"]["basicInsert"]["code"] == 1442
            assert report["modes"]["plain"]["basicInsert"]["ok"]
            for mode in MODES:
                assert report["modes"][mode]["ordinarySelectAfterOtherCommit"] == 0
    finally:
        await first.rollback()
        await second.rollback()
        async with first.cursor() as cursor:
            for table in reversed(tables):
                assert re.fullmatch(r"rf02p_[a-z_]+", table)
                await cursor.execute(f"DROP TABLE IF EXISTS {table}")
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'rf02p\\_%'"
            )
            report["toyTablesRemaining"] = (await cursor.fetchone())[0]
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg_rf02p\\_%'"
            )
            report["toyTriggersRemaining"] = (await cursor.fetchone())[0]
        first.close()
        second.close()
        (OUT / "green/D16RF02P-trigger-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    assert report["toyTablesRemaining"] == report["toyTriggersRemaining"] == 0
