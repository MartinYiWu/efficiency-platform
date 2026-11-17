package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrSoftRuleDraftServiceTest {
  @Test
  void unknown_condition_cannot_be_converted() {
    var positions = mock(HrPositionService.class);
    var matching = mock(HrMatchingService.class);
    var service = new HrSoftRuleDraftService(positions, matching, mock(HrAuditService.class));
    var actor = new HrActor("t", "u", Set.of("d"), Set.of("hr:position:edit"));
    var result = mock(Matching.class);
    when(matching.get(actor, "r")).thenReturn(result);
    when(result.hardConditions())
        .thenReturn(List.of(new HardConditionView("h", "条件", "UNKNOWN", "", "", false)));
    assertThrows(
        HrBusinessException.class,
        () -> service.create(actor, "r", new HrSoftRuleDraftService.Request("h", 1, "调整招聘标准")));
    verify(positions, never()).save(any(), any(), any());
  }

  @Test
  void explicit_fail_copies_frozen_anchors_to_unpublished_draft_and_keeps_existing_changes() {
    var positions = mock(HrPositionService.class);
    var matching = mock(HrMatchingService.class);
    var audit = mock(HrAuditService.class);
    var service = new HrSoftRuleDraftService(positions, matching, audit);
    var actor = new HrActor("t", "u", Set.of("d"), Set.of("hr:position:edit"));
    var result = mock(Matching.class);
    when(matching.get(actor, "r")).thenReturn(result);
    when(result.positionId()).thenReturn("p");
    when(result.configVersion()).thenReturn("v1");
    when(result.hardConditions())
        .thenReturn(List.of(new HardConditionView("h", "Java", "FAIL", "", "", true)));
    var position =
        new Position(
            "p",
            "t",
            "岗位",
            "TECHNOLOGY",
            "d",
            "P3",
            "code",
            "ACTIVE",
            "v2",
            "ctx",
            "u",
            Instant.now(),
            3);
    when(positions.get(actor, "p")).thenReturn(position);
    var hard =
        new HardRule(
            "h", "REQUIRED_SKILL", "Java", "Java", null, null, null, true, List.of("Java"), "ALL");
    var anchor =
        new SemanticCriterion(
            "h", "Java", "SKILL", "明确Java工作证据", "强原锚点", "合格原锚点", "部分原锚点", "不足原锚点", true);
    var frozen =
        new Draft(
            "p",
            "岗位",
            "TECHNOLOGY",
            "d",
            "P3",
            "原JD",
            "HARD_CONDITIONS",
            null,
            List.of(hard),
            List.of(anchor),
            1);
    when(positions.config(actor, "p", "v1"))
        .thenReturn(new ConfigVersion("cfg", "p", "v1", "ctx", frozen, "hash", "u", Instant.now()));
    var draft =
        new Draft(
            "p",
            "岗位新草稿",
            "TECHNOLOGY",
            "d",
            "P3",
            "未发布的JD改动",
            "WEIGHTS",
            null,
            List.of(hard),
            List.of(anchor),
            3);
    when(positions.draft(actor, "p")).thenReturn(draft);
    when(positions.save(eq(actor), eq("p"), any())).thenAnswer(i -> i.getArgument(2));
    var saved = service.create(actor, "r", new HrSoftRuleDraftService.Request("h", 3, "调整招聘标准"));
    assertEquals("未发布的JD改动", saved.jdText());
    assertTrue(saved.hardConditions().isEmpty());
    assertEquals("SOFT_REQUIREMENTS", saved.lastStep());
    assertEquals("强原锚点", saved.criteria().getFirst().strongAnchor());
    assertEquals(1, saved.draftScoring().requirements().size());
    assertNull(saved.scoring());
    verify(audit).append(actor, "HARD_CONDITION_TO_SOFT_DRAFT", "r", "d");
    verify(positions, never()).publish(any(), any(), anyLong());
  }
}
