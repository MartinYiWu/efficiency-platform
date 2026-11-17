"""锁定官方Saver异步边界；原Saver只交给受信清理适配。"""

import base64
import binascii
import inspect
import json
import math
import uuid
from collections.abc import Mapping
from dataclasses import fields, replace
from importlib.metadata import version
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from efficiency_platform_agent.core.budget import BudgetCharge, BudgetState
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.memory_thread import (
    CheckpointBodyCipher,
    CheckpointCiphertext,
    CheckpointLocation,
    MemoryThreadRegistry,
)
from efficiency_platform_agent.core.run import JsonObject


class CheckpointPayloadSerializer:
    """序列化后加密，拒绝旧明文和位置错配；不依赖官方primitive加密行为。"""

    def __init__(self, cipher: CheckpointBodyCipher):
        self.cipher = cipher

    def _pack(self, value: Any) -> Any:
        if value is None or type(value) in {str, int, bool}:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        if type(value) is JsonObject:
            return [
                "json_object",
                [[key, self._pack(child)] for key, child in value.items],
            ]
        if type(value) in {tuple, list}:
            return [
                "tuple" if type(value) is tuple else "list",
                [self._pack(child) for child in value],
            ]
        if type(value) is dict and all(type(key) is str for key in value):
            return ["dict", [[key, self._pack(child)] for key, child in value.items()]]
        if type(value) in {BudgetCharge, BudgetState}:
            return [
                "budget_charge" if type(value) is BudgetCharge else "budget_state",
                self._pack(
                    {field.name: getattr(value, field.name) for field in fields(value)}
                ),
            ]
        if type(value) is RunStatus:
            return ["run_status", value.value]
        raise TypeError("CHECKPOINT_VALUE_UNSUPPORTED")

    def _unpack(self, value: Any) -> Any:
        if value is None or type(value) in {str, int, bool}:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        if type(value) is not list or len(value) != 2 or type(value[0]) is not str:
            raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
        tag, data = value
        if tag in {"json_object", "dict"}:
            if (
                type(data) is not list
                or any(
                    type(item) is not list or len(item) != 2 or type(item[0]) is not str
                    for item in data
                )
                or len({item[0] for item in data}) != len(data)
            ):
                raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
            pairs = tuple((key, self._unpack(child)) for key, child in data)
            return JsonObject(pairs) if tag == "json_object" else dict(pairs)
        if tag in {"tuple", "list"} and type(data) is list:
            children = [self._unpack(child) for child in data]
            return tuple(children) if tag == "tuple" else children
        if tag in {"budget_charge", "budget_state"}:
            kwargs = self._unpack(data)
            if type(kwargs) is not dict:
                raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
            return (
                BudgetCharge(**kwargs)
                if tag == "budget_charge"
                else BudgetState(**kwargs)
            )
        if tag == "run_status" and type(data) is str:
            return RunStatus(data)
        raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")

    def encode(self, location: CheckpointLocation, value: Any) -> dict[str, str]:
        if not isinstance(location, CheckpointLocation):
            raise TypeError("CHECKPOINT_OWNER_REQUIRED")
        kind = "checkpoint-json/2"
        body = json.dumps(
            self._pack(value),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        sealed = self.cipher.seal(location, kind.encode() + b"\0" + body)
        return {
            "memory_checkpoint_format": "1",
            "key_version": sealed.key_version,
            "nonce": base64.b64encode(sealed.nonce).decode(),
            "ciphertext": base64.b64encode(sealed.ciphertext).decode(),
        }

    def decode(self, location: CheckpointLocation, value: Any) -> Any:
        try:
            if isinstance(value, JsonObject):
                value = dict(value.items)
            if (
                not isinstance(value, dict)
                or set(value)
                != {"memory_checkpoint_format", "key_version", "nonce", "ciphertext"}
                or value["memory_checkpoint_format"] != "1"
            ):
                raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
            sealed = CheckpointCiphertext(
                base64.b64decode(value["ciphertext"], validate=True),
                base64.b64decode(value["nonce"], validate=True),
                value["key_version"],
            )
            kind, body = self.cipher.open(location, sealed).split(b"\0", 1)
            if kind != b"checkpoint-json/2":
                raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
            return self._unpack(json.loads(body))
        except (ValueError, TypeError, KeyError, binascii.Error):
            raise ValueError("CHECKPOINT_BODY_UNAVAILABLE") from None


class FencedCheckpointSaver(BaseCheckpointSaver[Any]):
    memory_fenced = True

    def __init__(
        self,
        saver: Any,
        registry: MemoryThreadRegistry,
        backend_id: str,
        *,
        serializer: CheckpointPayloadSerializer | None = None,
    ):
        super().__init__(serde=saver.serde)
        if (
            getattr(registry, "requires_encrypted_checkpoints", False)
            and serializer is None
        ):
            raise ValueError("CHECKPOINT_ENCRYPTION_REQUIRED")
        self._saver, self._registry, self.backend_id = saver, registry, backend_id
        self.serializer = serializer

    @property
    def config_specs(self):
        return self._saver.config_specs

    def get_next_version(self, current, channel):
        return self._saver.get_next_version(current, channel)

    def _guard(self, config, *, pending_writes=False):
        if config is None:
            raise PermissionError("MEMORY_THREAD_REQUIRED")
        values = config.get("configurable", {})
        thread = values.get("thread_id")
        namespace = values.get("checkpoint_ns", "")
        if not isinstance(thread, str) or not thread or not isinstance(namespace, str):
            raise PermissionError("MEMORY_THREAD_REQUIRED")
        return self._registry.guard(
            thread, self.backend_id, namespace, pending_writes=pending_writes
        )

    async def aget_tuple(self, config):
        async with self._guard(config) as owner:
            value = await self._saver.aget_tuple(config)
            return (
                self._decode_tuple(owner, value)
                if self.serializer is not None and value is not None
                else value
            )

    def _decode_tuple(self, owner, value):
        config = value.config["configurable"]
        owner = replace(
            owner,
            thread_id=config["thread_id"],
            checkpoint_ns=config.get("checkpoint_ns", ""),
        )
        checkpoint_id = config["checkpoint_id"]
        checkpoint = dict(value.checkpoint)
        frame = self.serializer.decode(
            replace(owner, coordinate=("frame", checkpoint_id)),
            checkpoint.pop("_memory_checkpoint_frame", None),
        )
        if checkpoint["id"] != checkpoint_id or frame != {
            key: child for key, child in checkpoint.items() if key != "channel_values"
        }:
            raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
        checkpoint["channel_values"] = {
            channel: self.serializer.decode(
                replace(
                    owner,
                    coordinate=(
                        "channel",
                        channel,
                        str(checkpoint["channel_versions"][channel]),
                    ),
                ),
                child,
            )
            for channel, child in checkpoint["channel_values"].items()
        }
        metadata = self.serializer.decode(
            replace(owner, coordinate=("metadata", checkpoint_id)),
            value.metadata.get("_memory_checkpoint_metadata"),
        )
        writes = [
            (
                task,
                channel,
                self.serializer.decode(
                    replace(owner, coordinate=("write", checkpoint_id, task, channel)),
                    child,
                ),
            )
            for task, channel, child in value.pending_writes or ()
        ]
        return value._replace(
            checkpoint=checkpoint, metadata=metadata, pending_writes=writes
        )

    async def aget(self, config):
        result = await self.aget_tuple(config)
        return result.checkpoint if result else None

    async def alist(self, config, *, filter=None, before=None, limit=None):
        if before is not None and (
            config is None
            or before.get("configurable", {}).get("thread_id")
            != config.get("configurable", {}).get("thread_id")
        ):
            raise PermissionError("MEMORY_THREAD_MISMATCH")
        async with self._guard(config) as owner:
            count = 0
            async for item in self._saver.alist(
                config,
                filter=filter if self.serializer is None else None,
                before=before,
                limit=limit if filter is None else None,
            ):
                if self.serializer is not None:
                    item = self._decode_tuple(owner, item)
                if filter is not None and not all(
                    item.metadata.get(key) == value for key, value in filter.items()
                ):
                    continue
                yield item
                count += 1
                if limit is not None and count >= limit:
                    break

    async def aput(self, config, checkpoint, metadata, new_versions):
        async with self._guard(config) as owner:
            if self.serializer is not None:
                if checkpoint.get("pending_sends") or any(
                    type(value).__name__ == "_DeltaSnapshot"
                    for value in checkpoint["channel_values"].values()
                ):
                    raise PermissionError("MEMORY_DELTA_CHECKPOINT_UNSUPPORTED")
                checkpoint_id = checkpoint["id"]
                frame = {
                    key: value
                    for key, value in checkpoint.items()
                    if key != "channel_values"
                }
                checkpoint = checkpoint | {
                    "_memory_checkpoint_frame": self.serializer.encode(
                        replace(owner, coordinate=("frame", checkpoint_id)), frame
                    ),
                    "channel_values": {
                        channel: self.serializer.encode(
                            replace(
                                owner,
                                coordinate=(
                                    "channel",
                                    channel,
                                    str(checkpoint["channel_versions"][channel]),
                                ),
                            ),
                            value,
                        )
                        for channel, value in checkpoint["channel_values"].items()
                    },
                }
                metadata = {
                    "_memory_checkpoint_metadata": self.serializer.encode(
                        replace(owner, coordinate=("metadata", checkpoint_id)), metadata
                    )
                }
                config = {
                    "configurable": {
                        key: value
                        for key, value in config["configurable"].items()
                        if key in {"thread_id", "checkpoint_ns", "checkpoint_id"}
                    }
                }
            return await self._saver.aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        async with self._guard(config, pending_writes=True) as owner:
            if self.serializer is not None:
                checkpoint_id = config["configurable"]["checkpoint_id"]
                writes = [
                    (
                        channel,
                        self.serializer.encode(
                            replace(
                                owner,
                                coordinate=("write", checkpoint_id, task_id, channel),
                            ),
                            value,
                        ),
                    )
                    for channel, value in writes
                ]
            await self._saver.aput_writes(config, writes, task_id, task_path)

    async def aget_delta_channel_history(self, *, config, channels):
        async with self._guard(config):
            if self.serializer is not None:
                raise PermissionError("MEMORY_DELTA_CHECKPOINT_UNSUPPORTED")
            return await self._saver.aget_delta_channel_history(
                config=config, channels=channels
            )

    async def adelete_thread(self, thread_id):
        raise PermissionError("MEMORY_ERASURE_AUTHORIZATION_REQUIRED")

    def get_tuple(self, *args, **kwargs):
        raise PermissionError("MEMORY_SYNC_CHECKPOINT_DISABLED")

    def list(self, *args, **kwargs):
        raise PermissionError("MEMORY_SYNC_CHECKPOINT_DISABLED")

    def put(self, *args, **kwargs):
        raise PermissionError("MEMORY_SYNC_CHECKPOINT_DISABLED")

    def put_writes(self, *args, **kwargs):
        raise PermissionError("MEMORY_SYNC_CHECKPOINT_DISABLED")

    def delete_thread(self, *args, **kwargs):
        raise PermissionError("MEMORY_SYNC_CHECKPOINT_DISABLED")


class OfficialPostgresInventory:
    """只读取官方三表技术ID，不解密或加载checkpoint正文。"""

    backend_id = "official"

    def __init__(self, saver):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        if (
            type(saver) is not AsyncPostgresSaver
            or version("langgraph-checkpoint-postgres") != "3.1.2"
        ):
            raise ValueError("MEMORY_SAVER_VERSION_UNSUPPORTED")
        self._saver = saver

    async def members(self, root_thread_id: str) -> frozenset[str]:
        return frozenset(thread for thread, _, _ in await self.entries(root_thread_id))

    async def entries(self, root_thread_id: str) -> frozenset[tuple[str, str, bool]]:
        prefix = root_thread_id + ":child:"
        async with self._saver._cursor() as cursor:
            await cursor.execute(
                "SELECT thread_id,checkpoint_ns,false AS pending FROM checkpoints WHERE thread_id=%s OR starts_with(thread_id,%s) "
                "UNION SELECT thread_id,checkpoint_ns,false AS pending FROM checkpoint_blobs WHERE thread_id=%s OR starts_with(thread_id,%s) "
                "UNION SELECT thread_id,checkpoint_ns,true AS pending FROM checkpoint_writes WHERE thread_id=%s OR starts_with(thread_id,%s)",
                (
                    root_thread_id,
                    prefix,
                    root_thread_id,
                    prefix,
                    root_thread_id,
                    prefix,
                ),
            )
            return frozenset(
                (row["thread_id"], row["checkpoint_ns"], row["pending"])
                for row in await cursor.fetchall()
            )


class OwnedPostgresInventory:
    """自有索引独立盘点；不能用它替代官方三表。"""

    def __init__(self, store):
        self._store, self.backend_id = store, store.backend_id

    async def members(self, root_thread_id: str) -> frozenset[str]:
        return frozenset(thread for thread, _, _ in await self.entries(root_thread_id))

    async def entries(self, root_thread_id: str) -> frozenset[tuple[str, str, bool]]:
        from psycopg import sql

        provider = self._store.provider
        result = await provider.connection.execute(
            sql.SQL(
                "SELECT thread_id, checkpoint_ns FROM {} WHERE thread_id=%s OR starts_with(thread_id,%s)"
            ).format(sql.Identifier(provider.schema, "checkpoints")),
            (root_thread_id, root_thread_id + ":child:"),
        )
        return frozenset(
            (row["thread_id"], row["checkpoint_ns"], False)
            for row in await result.fetchall()
        )


class FencedCheckpointStore:
    """GraphRuntime自有索引也经相同门禁，失败路径不得另写裸索引。"""

    def __init__(
        self,
        store,
        registry: MemoryThreadRegistry,
        *,
        serializer: CheckpointPayloadSerializer | None = None,
    ):
        if (
            getattr(registry, "requires_encrypted_checkpoints", False)
            and serializer is None
        ):
            raise ValueError("CHECKPOINT_ENCRYPTION_REQUIRED")
        self._store, self._registry = store, registry
        self.backend_id = store.backend_id
        self.serializer = serializer

    @staticmethod
    def _binding(value) -> JsonObject:
        if isinstance(value, JsonObject):
            return value
        if isinstance(value, Mapping):
            from .postgres_checkpoint import _to_json_value

            normalized = _to_json_value(value)
            if isinstance(normalized, JsonObject):
                return normalized
        raise ValueError("CHECKPOINT_BINDING_INVALID")

    async def save(self, run_id, checkpoint_ns, state, *, tenant_id="", **kwargs):
        async with self._registry.guard(
            run_id, self.backend_id, checkpoint_ns
        ) as owner:
            if owner is not None and owner.scope.conversation.tenant_id != tenant_id:
                raise PermissionError("MEMORY_THREAD_OWNER_MISMATCH")
            if self.serializer is not None:
                if type(state) is not dict:
                    raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
                state = dict(state)
                binding = self._binding(state.get("resume_binding", JsonObject()))
                supplied = kwargs.get("resume_binding")
                if supplied is not None:
                    supplied = self._binding(supplied)
                    if "resume_binding" in state and supplied != binding:
                        raise ValueError("CHECKPOINT_BINDING_MISMATCH")
                    binding = supplied
                    if "resume_binding" not in state and binding.items:
                        state["resume_binding"] = binding
                kwargs["resume_binding"] = binding
                checkpoint_id = kwargs.get("checkpoint_id") or str(uuid.uuid4())
                kwargs["checkpoint_id"] = checkpoint_id
                state = self.serializer.encode(
                    replace(owner, coordinate=("owned", checkpoint_id)), state
                )
            value = self._store.save(
                run_id, checkpoint_ns, state, tenant_id=tenant_id, **kwargs
            )
            return await value if inspect.isawaitable(value) else value

    async def get(self, run_id, checkpoint_ns, tenant_id=""):
        async with self._registry.guard(
            run_id, self.backend_id, checkpoint_ns
        ) as owner:
            if owner is not None and owner.scope.conversation.tenant_id != tenant_id:
                raise PermissionError("MEMORY_THREAD_OWNER_MISMATCH")
            value = self._store.get(run_id, checkpoint_ns, tenant_id)
            value = await value if inspect.isawaitable(value) else value
            if value is not None and self.serializer is not None:
                from .checkpoint import CheckpointRecord

                state = self.serializer.decode(
                    replace(owner, coordinate=("owned", value.view.checkpoint_id)),
                    value.state,
                )
                if type(state) is not dict:
                    raise ValueError("CHECKPOINT_BODY_UNAVAILABLE")
                binding = self._binding(state.get("resume_binding", JsonObject()))
                return CheckpointRecord(
                    replace(value.view, resume_binding=binding), state
                )
            return value
