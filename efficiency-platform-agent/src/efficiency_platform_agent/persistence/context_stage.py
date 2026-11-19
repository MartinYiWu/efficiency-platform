"""逻辑阶段与三个固定HTTP操作槽的MySQL持久关联。"""

import hmac
import json
from dataclasses import asdict

from sqlalchemy import LargeBinary, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import TextClause

from efficiency_platform_agent.core.context_stage import StageSlot
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    require_count,
    require_id,
)

_KEY = "tenant_id=:tenant_id AND task_id=:task_id AND execution_id=:execution_id AND stage_id=:stage_id"
_TRANSITIONS = frozenset(
    {
        ("CLAIMED", "RETURNED"),
        ("CLAIMED", "UNKNOWN"),
        ("RETURNED", "SUCCEEDED"),
        ("RETURNED", "INVALID"),
    }
)


def _statement(sql: str) -> TextClause:
    return text(sql).bindparams(
        *(
            bindparam(name, type_=LargeBinary(512))
            for name in ("tenant_id", "task_id", "execution_id", "stage_id")
        )
    )


class MySqlContextStageStore:
    def __init__(self, engine: AsyncEngine, hmac_key: bytes):
        if type(hmac_key) is not bytes or len(hmac_key) < 32:
            raise ValueError("CONTEXT_STAGE_HMAC_KEY_INVALID")
        self._engine = engine
        self._key = hmac_key

    def _parameters(self, scope: ExecutionScope, stage_id: str) -> dict[str, object]:
        require_id(stage_id)
        if not isinstance(scope, ExecutionScope):
            raise TypeError("CONTEXT_STAGE_SCOPE_INVALID")
        scope_json = json.dumps(
            asdict(scope), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            "tenant_id": scope.conversation.tenant_id.encode("utf-8"),
            "task_id": scope.task_id.encode("utf-8"),
            "execution_id": scope.execution_id.encode("utf-8"),
            "stage_id": stage_id.encode("utf-8"),
            "scope_hash": hmac.digest(
                self._key, b"scope:" + scope_json, "sha256"
            ).hex(),
        }

    async def claim(
        self, scope: ExecutionScope, stage_id: str, semantic_hash: str, deadline: int
    ) -> StageSlot:
        require_id(semantic_hash)
        require_count(deadline)
        params = self._parameters(scope, stage_id) | {
            "semantic_hash": semantic_hash,
            "deadline": deadline,
        }
        identity = json.dumps(
            {"scope": asdict(scope), "stage_id": stage_id},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        operations = {
            f"operation_id_{slot}": "stage-"
            + hmac.digest(
                self._key, b"operation:" + identity + f":{slot}".encode(), "sha256"
            ).hex()
            for slot in range(1, 4)
        }
        for retry in range(3):
            try:
                async with self._engine.begin() as conn:
                    row = (
                        (
                            await conn.execute(
                                _statement(
                                    "SELECT scope_hash,semantic_hash,deadline,current_slot,status,operation_id_1,operation_id_2,operation_id_3 FROM agent_context_stage WHERE "
                                    + _KEY
                                ),
                                params,
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if row is None:
                        await conn.execute(
                            _statement(
                                "INSERT INTO agent_context_stage (tenant_id,task_id,execution_id,stage_id,scope_hash,semantic_hash,deadline,current_slot,status,operation_id_1,operation_id_2,operation_id_3) VALUES (:tenant_id,:task_id,:execution_id,:stage_id,:scope_hash,:semantic_hash,:deadline,1,'CLAIMED',:operation_id_1,:operation_id_2,:operation_id_3)"
                            ),
                            params | operations,
                        )
                        return StageSlot(1, operations["operation_id_1"])
                    if (row["scope_hash"], row["semantic_hash"], row["deadline"]) != (
                        params["scope_hash"],
                        semantic_hash,
                        deadline,
                    ):
                        raise ValueError("CONTEXT_STAGE_CONFLICT_409")
                    slot = row["current_slot"]
                    if type(slot) is not int or not 1 <= slot <= 3:
                        raise ValueError("CONTEXT_STAGE_STATE_INVALID")
                    if row["status"] == "CLAIMED":
                        return StageSlot(slot, row[f"operation_id_{slot}"])
                    if row["status"] != "INVALID":
                        raise ValueError("CONTEXT_STAGE_BLOCKED")
                    if slot == 3:
                        raise ValueError("CONTEXT_STAGE_ATTEMPTS_EXHAUSTED")
                    result = await conn.execute(
                        _statement(
                            "UPDATE agent_context_stage SET current_slot=:next_slot,status='CLAIMED' WHERE "
                            + _KEY
                            + " AND scope_hash=:scope_hash AND semantic_hash=:semantic_hash AND deadline=:deadline AND current_slot=:previous_slot AND status='INVALID'"
                        ),
                        params | {"next_slot": slot + 1, "previous_slot": slot},
                    )
                    if result.rowcount == 1:
                        return StageSlot(slot + 1, row[f"operation_id_{slot + 1}"])
            except IntegrityError:
                if retry == 2:
                    raise ValueError("CONTEXT_STAGE_CONFLICT_409") from None
        raise ValueError("CONTEXT_STAGE_CONCURRENT_CONFLICT")

    async def is_claimed_operation(
        self, scope: ExecutionScope, stage_id: str, operation_id: str, deadline: int
    ) -> bool:
        require_id(operation_id)
        require_count(deadline)
        params = self._parameters(scope, stage_id)
        async with self._engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        _statement(
                            "SELECT scope_hash,deadline,current_slot,status,operation_id_1,operation_id_2,operation_id_3 FROM agent_context_stage WHERE "
                            + _KEY
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
        return (
            row is not None
            and row["scope_hash"] == params["scope_hash"]
            and row["deadline"] == deadline
            and row["status"] == "CLAIMED"
            and type(row["current_slot"]) is int
            and 1 <= row["current_slot"] <= 3
            and row[f"operation_id_{row['current_slot']}"] == operation_id
        )

    async def transition(
        self,
        scope: ExecutionScope,
        stage_id: str,
        slot: int,
        expected: str,
        status: str,
    ) -> bool:
        if (
            type(slot) is not int
            or not 1 <= slot <= 3
            or (expected, status) not in _TRANSITIONS
        ):
            return False
        params = self._parameters(scope, stage_id) | {
            "slot": slot,
            "expected": expected,
            "status": status,
        }
        async with self._engine.begin() as conn:
            result = await conn.execute(
                _statement(
                    "UPDATE agent_context_stage SET status=:status WHERE "
                    + _KEY
                    + " AND scope_hash=:scope_hash AND current_slot=:slot AND status=:expected"
                ),
                params,
            )
            return result.rowcount == 1
