"""Supervisor 父子预算账本及不可突破门禁。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from efficiency_platform_agent.core.multi_agent import BudgetUsage
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject

_ID: Final = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_DIMENSIONS: Final = (
    "max_iterations",
    "max_tool_calls",
    "max_input_tokens",
    "max_output_tokens",
    "timeout_ms",
    "max_cost_microunits",
)
_USAGE_FIELDS: Final = (
    "iterations",
    "tool_calls",
    "input_tokens",
    "output_tokens",
    "elapsed_ms",
    "cost_microunits",
)


def _id(value: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("task_id必须是稳定的小写标识")


def _budget_values(budget: ExecutionBudget) -> tuple[int, ...]:
    if not isinstance(budget, ExecutionBudget):
        raise TypeError("预算必须是ExecutionBudget")
    return tuple(getattr(budget, name) for name in _DIMENSIONS)


def _budget(values: tuple[int, ...]) -> ExecutionBudget:
    if len(values) != len(_DIMENSIONS):
        raise ValueError("预算维度数量无效")
    return ExecutionBudget(*values)


def _add(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(a + b for a, b in zip(left, right, strict=True))


def _sub(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
    values = tuple(a - b for a, b in zip(left, right, strict=True))
    if any(value < 0 for value in values):
        raise ValueError("预算守恒被破坏")
    return values


def _min_budget(*budgets: ExecutionBudget) -> ExecutionBudget:
    if not budgets:
        raise ValueError("至少需要一个预算")
    return _budget(
        tuple(
            min(_budget_values(item)[index] for item in budgets) for index in range(6)
        )
    )


def _json_budget(budget: ExecutionBudget) -> JsonObject:
    return JsonObject(tuple((name, getattr(budget, name)) for name in _DIMENSIONS))


def _json_values(values: tuple[int, ...]) -> JsonObject:
    """把允许为零的内部预算向量编码为 JSON 对象。"""
    return JsonObject(
        tuple((name, values[index]) for index, name in enumerate(_DIMENSIONS))
    )


def _read_json_object(value: object, name: str) -> JsonObject:
    if not isinstance(value, JsonObject):
        raise TypeError(f"快照字段{name}必须是JsonObject")
    return value


def _read_int(obj: JsonObject, key: str) -> int:
    values = {name: value for name, value in obj.items}
    value = values.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"快照字段{key}必须是非负整数")
    return value


def _read_budget(obj: JsonObject) -> ExecutionBudget:
    return _budget(tuple(_read_int(obj, name) for name in _DIMENSIONS))


def _read_vector(obj: JsonObject) -> tuple[int, ...]:
    """读取允许迭代或超时为零的内部预算向量。"""
    return tuple(_read_int(obj, name) for name in _DIMENSIONS)


def _usage_values(usage: BudgetUsage) -> tuple[int, ...]:
    if not isinstance(usage, BudgetUsage):
        raise TypeError("usage必须是受信BudgetUsage")
    return tuple(getattr(usage, name) for name in _USAGE_FIELDS)


@dataclass(slots=True)
class BudgetLedger:
    """可恢复的父预算账本，所有核销均按六个维度原子校验。"""

    _parent: ExecutionBudget
    _requests: dict[str, ExecutionBudget]
    _allocations: dict[str, ExecutionBudget]
    _effective: dict[str, ExecutionBudget]
    _consumed: dict[str, tuple[int, ...]]
    _revision_reserved: dict[str, tuple[int, ...]]
    _released: set[str]
    _available_work: tuple[int, ...]
    _revision_remaining: tuple[int, ...]
    _aggregation_reserved: tuple[int, ...]

    @classmethod
    def allocate(
        cls,
        parent: ExecutionBudget,
        requested_budgets: tuple[tuple[str, ExecutionBudget], ...],
    ) -> BudgetLedger:
        """按 70/15/15 整数池为子任务分配预算。"""

        _budget_values(parent)
        if not isinstance(requested_budgets, tuple) or not requested_budgets:
            raise ValueError("requested_budgets必须是非空不可变元组")
        requests: dict[str, ExecutionBudget] = {}
        for task_id, requested in requested_budgets:
            _id(task_id)
            if task_id in requests:
                raise ValueError("task_id不得重复")
            if not isinstance(requested, ExecutionBudget):
                raise TypeError("请求预算必须是ExecutionBudget")
            if requested.max_iterations < 1 or requested.timeout_ms < 1:
                raise ValueError("BUDGET_UNALLOCATABLE")
            requests[task_id] = requested
        parent_values = _budget_values(parent)
        work = tuple(value * 7000 // 10000 for value in parent_values)
        revision = tuple(value * 1500 // 10000 for value in parent_values)
        aggregation = tuple(parent_values[i] - work[i] - revision[i] for i in range(6))
        allocation_values = {task_id: [0] * 6 for task_id in requests}
        for index, name in enumerate(_DIMENSIONS):
            total_requested = sum(
                getattr(requested, name) for requested in requests.values()
            )
            if total_requested <= work[index]:
                for task_id, requested in requests.items():
                    allocation_values[task_id][index] = getattr(requested, name)
                continue
            if index in (0, 4) and work[index] < len(requests):
                raise ValueError("BUDGET_UNALLOCATABLE")
            base: dict[str, int] = {}
            remainders: dict[str, int] = {}
            for task_id, requested in requests.items():
                numerator = work[index] * getattr(requested, name)
                base[task_id] = numerator // total_requested
                remainders[task_id] = numerator % total_requested
            left = work[index] - sum(base.values())
            for task_id in sorted(requests, key=lambda item: (-remainders[item], item))[
                :left
            ]:
                base[task_id] += 1
            for task_id, amount in base.items():
                allocation_values[task_id][index] = amount
            if index in (0, 4) and any(amount < 1 for amount in base.values()):
                raise ValueError("BUDGET_UNALLOCATABLE")
        allocations = {
            task_id: _budget(tuple(values))
            for task_id, values in allocation_values.items()
        }
        allocated_totals = tuple(
            sum(_budget_values(item)[index] for item in allocations.values())
            for index in range(6)
        )
        consumed: dict[str, tuple[int, ...]] = {
            task_id: (0, 0, 0, 0, 0, 0) for task_id in requests
        }
        return cls(
            parent,
            requests,
            allocations,
            {},
            consumed,
            {},
            set(),
            tuple(work[index] - allocated_totals[index] for index in range(6)),
            revision,
            aggregation,
        )

    def pool(self, name: str) -> ExecutionBudget:
        """返回 70/15/15 初始预算池的只读快照。"""

        parent = _budget_values(self._parent)
        work = tuple(value * 7000 // 10000 for value in parent)
        aggregation = tuple(
            parent[i] - work[i] - parent[i] * 1500 // 10000 for i in range(6)
        )
        pools = {
            "work": _budget(work),
            "revision": _budget(tuple(value * 1500 // 10000 for value in parent)),
            "aggregation": _budget(aggregation),
        }
        if name not in pools:
            raise KeyError(name)
        return pools[name]

    def _redistribute(self) -> None:
        if not any(self._available_work):
            return
        eligible = [
            task_id
            for task_id in self._requests
            if task_id not in self._released and task_id not in self._effective
        ]
        if not eligible:
            return
        for index, name in enumerate(_DIMENSIONS):
            available = self._available_work[index]
            if available <= 0:
                continue
            total_requested = sum(
                getattr(self._requests[task_id], name) for task_id in eligible
            )
            if total_requested <= 0:
                continue
            base: dict[str, int] = {}
            remainders: dict[str, int] = {}
            for task_id in eligible:
                numerator = available * getattr(self._requests[task_id], name)
                base[task_id] = numerator // total_requested
                remainders[task_id] = numerator % total_requested
            for task_id in sorted(eligible, key=lambda item: (-remainders[item], item))[
                : available - sum(base.values())
            ]:
                base[task_id] += 1
            for task_id, amount in base.items():
                current = self._effective.get(task_id, self._allocations[task_id])
                values = list(_budget_values(current))
                values[index] += amount
                self._effective[task_id] = _budget(tuple(values))
        self._available_work = (0, 0, 0, 0, 0, 0)

    def budget_for(self, task_id: str, agent_cap: ExecutionBudget) -> ExecutionBudget:
        """返回任务预算与 Agent 上限逐字段最小值。"""

        _id(task_id)
        if task_id not in self._requests or task_id in self._released:
            raise KeyError(task_id)
        if not isinstance(agent_cap, ExecutionBudget):
            raise TypeError("agent_cap必须是ExecutionBudget")
        if agent_cap.max_iterations < 1 or agent_cap.timeout_ms < 1:
            raise ValueError("BUDGET_UNALLOCATABLE")
        if task_id not in self._effective:
            self._redistribute()
            candidate = self._effective.get(task_id, self._allocations[task_id])
            self._effective[task_id] = _min_budget(candidate, agent_cap)
        else:
            candidate = self._effective[task_id]
        effective = _min_budget(candidate, agent_cap)
        if effective.max_iterations < 1 or effective.timeout_ms < 1:
            raise ValueError("BUDGET_UNALLOCATABLE")
        self._effective[task_id] = effective
        return effective

    def consume(self, task_id: str, usage: BudgetUsage) -> None:
        """原子核销受信运行事实，任一维度超限即整体拒绝。"""

        _id(task_id)
        if task_id not in self._requests or task_id in self._released:
            raise KeyError(task_id)
        values = _usage_values(usage)
        budget = self._effective.get(task_id, self._allocations[task_id])
        limits = _budget_values(budget)
        previous = self._consumed[task_id]
        updated = _add(previous, values)
        if any(updated[index] > limits[index] for index in range(6)):
            raise ValueError("BUDGET_EXHAUSTED")
        self._consumed[task_id] = updated

    def reserve_revision(self, task_id: str) -> ExecutionBudget:
        """从 15% 修订保留池原子领取一次修订预算。"""

        _id(task_id)
        if task_id not in self._requests or task_id in self._released:
            raise KeyError(task_id)
        source = self._effective.get(task_id, self._allocations[task_id])
        available = self._revision_remaining
        reserved = tuple(min(_budget_values(source)[i], available[i]) for i in range(6))
        if reserved[0] < 1 or reserved[4] < 1:
            raise ValueError("BUDGET_UNALLOCATABLE")
        self._revision_remaining = _sub(available, reserved)
        self._revision_reserved[task_id] = _add(
            self._revision_reserved.get(task_id, (0, 0, 0, 0, 0, 0)), reserved
        )
        return _budget(reserved)

    def release_unstarted(self, task_id: str) -> None:
        """释放尚未通过 budget_for 或 consume 的任务工作额度。"""

        _id(task_id)
        if task_id not in self._requests:
            raise KeyError(task_id)
        if task_id in self._released:
            return
        if task_id in self._effective or any(self._consumed[task_id]):
            raise ValueError("只能释放未启动任务")
        self._released.add(task_id)
        self._available_work = _add(
            self._available_work, _budget_values(self._allocations[task_id])
        )

    def consumed_total(self) -> BudgetUsage:
        """返回所有任务已核销的可信消耗总量。"""

        total = tuple(
            sum(values[index] for values in self._consumed.values())
            for index in range(6)
        )
        return BudgetUsage(*total)

    def remaining_total(self) -> ExecutionBudget:
        """返回父预算扣除核销后的保守剩余预算。"""

        parent = _budget_values(self._parent)
        consumed = _usage_values(self.consumed_total())
        return _budget(
            tuple(max(0, parent[index] - consumed[index]) for index in range(6))
        )

    def snapshot(self) -> JsonObject:
        """返回可用于 Checkpoint 的不可变 JSON 账本快照。"""

        def entries(mapping: dict[str, ExecutionBudget]) -> tuple[JsonObject, ...]:
            return tuple(
                JsonObject((("task_id", task_id), ("budget", _json_budget(value))))
                for task_id, value in sorted(mapping.items())
            )

        def usage_entries(
            mapping: dict[str, tuple[int, ...]],
        ) -> tuple[JsonObject, ...]:
            return tuple(
                JsonObject(
                    (
                        ("task_id", task_id),
                        (
                            "usage",
                            JsonObject(
                                tuple(
                                    (name, values[index])
                                    for index, name in enumerate(_USAGE_FIELDS)
                                )
                            ),
                        ),
                    )
                )
                for task_id, values in sorted(mapping.items())
            )

        return JsonObject(
            (
                ("contract_version", "budget-ledger/1"),
                ("parent", _json_budget(self._parent)),
                ("requests", entries(self._requests)),
                ("allocations", entries(self._allocations)),
                ("effective", entries(self._effective)),
                ("consumed", usage_entries(self._consumed)),
                ("revision_reserved", usage_entries(self._revision_reserved)),
                ("released", tuple(sorted(self._released))),
                ("available_work", _json_values(self._available_work)),
                ("revision_remaining", _json_values(self._revision_remaining)),
                ("aggregation_reserved", _json_values(self._aggregation_reserved)),
            )
        )

    @classmethod
    def restore(cls, snapshot: JsonObject) -> BudgetLedger:
        """从不可变快照恢复账本并重新执行守恒校验。"""

        if not isinstance(snapshot, JsonObject):
            raise TypeError("snapshot必须是JsonObject")
        values = {name: value for name, value in snapshot.items}
        required_keys = {
            "contract_version",
            "parent",
            "requests",
            "allocations",
            "effective",
            "consumed",
            "revision_reserved",
            "released",
            "available_work",
            "revision_remaining",
            "aggregation_reserved",
        }
        if set(values) != required_keys:
            raise ValueError("账本快照字段不完整或包含未知字段")
        if values.get("contract_version") != "budget-ledger/1":
            raise ValueError("账本快照版本无效")

        def read_entries(value: object) -> dict[str, ExecutionBudget]:
            if not isinstance(value, tuple):
                raise TypeError("预算条目必须是不可变元组")
            result: dict[str, ExecutionBudget] = {}
            for item in value:
                if not isinstance(item, JsonObject):
                    raise TypeError("预算条目格式无效")
                data = {name: inner for name, inner in item.items}
                task_id_value = data.get("task_id")
                if not isinstance(task_id_value, str):
                    raise TypeError("预算条目task_id必须是字符串")
                task_id = task_id_value
                _id(task_id)
                if task_id in result:
                    raise ValueError("task_id不得重复")
                result[task_id] = _read_budget(
                    _read_json_object(data.get("budget"), "budget")
                )
            return result

        def read_usage_entries(value: object) -> dict[str, tuple[int, ...]]:
            if not isinstance(value, tuple):
                raise TypeError("消耗条目必须是不可变元组")
            result: dict[str, tuple[int, ...]] = {}
            for item in value:
                if not isinstance(item, JsonObject):
                    raise TypeError("消耗条目格式无效")
                data = {name: inner for name, inner in item.items}
                task_id_value = data.get("task_id")
                if not isinstance(task_id_value, str):
                    raise TypeError("消耗条目task_id必须是字符串")
                task_id = task_id_value
                _id(task_id)
                result[task_id] = tuple(
                    _read_int(_read_json_object(data.get("usage"), "usage"), name)
                    for name in _USAGE_FIELDS
                )
            return result

        parent = _read_budget(_read_json_object(values.get("parent"), "parent"))
        requests = read_entries(values.get("requests"))
        allocations = read_entries(values.get("allocations"))
        effective = read_entries(values.get("effective"))
        consumed = read_usage_entries(values.get("consumed"))
        revision_reserved = read_usage_entries(values.get("revision_reserved"))
        released_value = values.get("released")
        if not isinstance(released_value, tuple) or any(
            not isinstance(item, str) for item in released_value
        ):
            raise TypeError("released格式无效")
        released_items = tuple(item for item in released_value if isinstance(item, str))
        released: set[str] = set(released_items)
        if set(allocations) != set(requests) or set(consumed) != set(requests):
            raise ValueError("账本任务集合不一致")
        if not released.issubset(requests) or not set(effective).issubset(requests):
            raise ValueError("账本状态引用未知任务")
        if not set(revision_reserved).issubset(requests):
            raise ValueError("修订保留引用未知任务")
        available_work = _read_vector(
            _read_json_object(values.get("available_work"), "available_work")
        )
        revision_remaining = _read_vector(
            _read_json_object(values.get("revision_remaining"), "revision_remaining")
        )
        aggregation_reserved = _read_vector(
            _read_json_object(
                values.get("aggregation_reserved"), "aggregation_reserved"
            )
        )
        ledger = cls(
            parent,
            requests,
            allocations,
            effective,
            consumed,
            revision_reserved,
            released,
            available_work,
            revision_remaining,
            aggregation_reserved,
        )
        ledger._validate_snapshot()
        return ledger

    def _validate_snapshot(self) -> None:
        parent = _budget_values(self._parent)
        consumed = _usage_values(self.consumed_total())
        if any(consumed[index] > parent[index] for index in range(6)):
            raise ValueError("快照消耗超过父预算")
        if any(
            task_id in self._released and task_id in self._effective
            for task_id in self._requests
        ):
            raise ValueError("释放任务不得有有效预算")
        if any(
            value < 0
            for value in self._revision_remaining
            + self._aggregation_reserved
            + self._available_work
        ):
            raise ValueError("快照预算不得为负")
        work_pool = tuple(value * 7000 // 10000 for value in parent)
        active_allocations = tuple(
            sum(
                _budget_values(budget)[index]
                for task_id, budget in self._allocations.items()
                if task_id not in self._released
            )
            for index in range(6)
        )
        if _add(active_allocations, self._available_work) != work_pool:
            raise ValueError("工作池分配守恒被破坏")
        revision_pool = tuple(value * 1500 // 10000 for value in parent)
        reserved_revision = tuple(
            sum(values[index] for values in self._revision_reserved.values())
            for index in range(6)
        )
        if _add(reserved_revision, self._revision_remaining) != revision_pool:
            raise ValueError("修订池分配守恒被破坏")
        aggregation_pool = tuple(
            parent[index] - work_pool[index] - revision_pool[index]
            for index in range(6)
        )
        if self._aggregation_reserved != aggregation_pool:
            raise ValueError("聚合保留池分配守恒被破坏")
        for task_id, values in self._consumed.items():
            limit = _budget_values(
                self._effective.get(task_id, self._allocations[task_id])
            )
            if any(values[index] > limit[index] for index in range(6)):
                raise ValueError("快照任务消耗超过任务预算")


__all__ = ["BudgetLedger", "BudgetUsage"]
