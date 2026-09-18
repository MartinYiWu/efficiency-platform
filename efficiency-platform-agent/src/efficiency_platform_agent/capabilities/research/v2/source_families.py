"""以可审计线索解析来源家族和独立性。"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.research_evidence_v2 import SourceDocumentV2

FamilyBasis = Literal[
    "ownership_group",
    "publisher",
    "canonical_url",
    "identical_content",
    "primary_origin",
    "unresolved_origin",
]


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceFamilyV2(_FrozenContract):
    family_id: str = Field(min_length=1, max_length=128)
    member_document_ids: tuple[str, ...] = Field(min_length=1, max_length=2_000)
    publisher_ids: tuple[str, ...] = Field(min_length=1, max_length=2_000)
    ownership_groups: tuple[str, ...] = Field(default=(), max_length=2_000)
    basis: tuple[FamilyBasis, ...] = Field(min_length=1, max_length=8)
    independence_status: Literal["confirmed", "unknown"]


class SourceFamiliesV2(_FrozenContract):
    families: tuple[SourceFamilyV2, ...] = Field(default=(), max_length=2_000)
    input_document_count: int = Field(ge=0)
    family_count: int = Field(ge=0)
    confirmed_independent_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conservation(self) -> SourceFamiliesV2:
        members = [
            document_id
            for family in self.families
            for document_id in family.member_document_ids
        ]
        if (
            self.family_count != len(self.families)
            or self.input_document_count != len(members)
            or len(set(members)) != len(members)
            or self.confirmed_independent_count
            != sum(
                family.independence_status == "confirmed"
                for family in self.families
            )
        ):
            raise ValueError("SOURCE_FAMILY_COUNT_INVALID")
        return self


class SourceFamilyResolver:
    def resolve(
        self,
        documents: tuple[SourceDocumentV2, ...],
    ) -> SourceFamiliesV2:
        ordered = tuple(sorted(documents, key=lambda item: item.document_id))
        identifiers = [item.document_id for item in ordered]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("SOURCE_FAMILY_DOCUMENT_DUPLICATED")
        parent = {item.document_id: item.document_id for item in ordered}
        bases: dict[str, set[FamilyBasis]] = {
            item.document_id: set() for item in ordered
        }

        def find(identifier: str) -> str:
            while parent[identifier] != identifier:
                parent[identifier] = parent[parent[identifier]]
                identifier = parent[identifier]
            return identifier

        def union(left: str, right: str, basis: FamilyBasis) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                keep, move = sorted((left_root, right_root))
                parent[move] = keep
                bases[keep].update(bases.pop(move))
                left_root = keep
            bases[left_root].add(basis)

        indexes: tuple[
            tuple[FamilyBasis, Callable[[SourceDocumentV2], str | None]], ...
        ] = (
            ("ownership_group", lambda item: item.ownership_group),
            ("publisher", lambda item: item.publisher_id),
            ("canonical_url", lambda item: item.canonical_url),
            ("identical_content", lambda item: item.content_hash),
        )
        for basis, key_fn in indexes:
            groups: dict[str, list[str]] = defaultdict(list)
            for document in ordered:
                key = key_fn(document)
                if key is not None:
                    groups[str(key)].append(document.document_id)
            for link_ids in groups.values():
                for member in link_ids[1:]:
                    union(link_ids[0], member, basis)

        grouped_documents: dict[str, list[SourceDocumentV2]] = defaultdict(list)
        for document in ordered:
            grouped_documents[find(document.document_id)].append(document)
        families: list[SourceFamilyV2] = []
        for root, family_documents in sorted(grouped_documents.items()):
            member_ids = tuple(item.document_id for item in family_documents)
            family_bases = set(bases[find(root)])
            confirmed = any(
                item.source_role == "primary" for item in family_documents
            ) or any(
                item.ownership_group is not None for item in family_documents
            )
            family_bases.add("primary_origin" if confirmed else "unresolved_origin")
            digest = hashlib.sha256("\x00".join(member_ids).encode("utf-8")).hexdigest()
            families.append(
                SourceFamilyV2(
                    family_id=f"source-family-{digest[:24]}",
                    member_document_ids=member_ids,
                    publisher_ids=tuple(
                        sorted({item.publisher_id for item in family_documents})
                    ),
                    ownership_groups=tuple(
                        sorted(
                            {
                                item.ownership_group
                                for item in family_documents
                                if item.ownership_group is not None
                            }
                        )
                    ),
                    basis=tuple(sorted(family_bases)),
                    independence_status="confirmed" if confirmed else "unknown",
                )
            )
        result = tuple(sorted(families, key=lambda item: item.family_id))
        return SourceFamiliesV2(
            families=result,
            input_document_count=len(ordered),
            family_count=len(result),
            confirmed_independent_count=sum(
                item.independence_status == "confirmed" for item in result
            ),
        )


__all__ = [
    "SourceFamiliesV2",
    "SourceFamilyResolver",
    "SourceFamilyV2",
]
