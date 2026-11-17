package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTrialContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrTrialBlindLabelTest {
  @Test
  void blind_submission_hides_all_scores_then_counts_only_successfully_double_labeled() {
    var repository = mock(HrSettingsRepository.class);
    var positions = mock(HrPositionService.class);
    var candidates = mock(HrCandidateService.class);
    var evaluator = mock(HrTrialEvaluator.class);
    var actor =
        new HrActor(
            "t", "1", Set.of("d"), Set.of("hr:trial:read", "hr:trial:label", "hr:candidate:read"));
    List<TrialResult> results = new ArrayList<>();
    for (int i = 0; i < 10; i++)
      results.add(
          new TrialResult(
              "c" + i,
              "SUCCEEDED",
              "RECOMMENDED",
              new BigDecimal("75"),
              new BigDecimal("100"),
              List.of(),
              "s" + i,
              null));
    results.add(
        new TrialResult(
            "blocked",
            "BLOCKED_NEEDS_EVALUATION",
            null,
            null,
            null,
            List.of(),
            "s11",
            "HR_TRIAL_BUDGET_REQUIRED"));
    var trial =
        new Trial(
            "trial",
            "p",
            "d",
            20,
            11,
            7,
            "hash",
            1,
            "BLOCKED_NEEDS_EVALUATION",
            results,
            List.of(),
            null,
            null,
            false,
            null,
            LocalDate.now());
    when(repository.get(actor, "TRIAL", "trial", Trial.class)).thenReturn(trial);
    var service = new HrTrialService(repository, positions, candidates, evaluator);
    var blind = service.get(actor, "trial");
    assertTrue(blind.results().stream().allMatch(r -> r.label() == null && r.score() == null));
    assertNull(blind.diagnosis());
    List<Label> labels = new ArrayList<>();
    for (int i = 0; i < 10; i++) labels.add(new Label("c" + i, "RECOMMENDED", "SKILL", "独立标注"));
    labels.add(new Label("blocked", "FILTERED", "HARD_CONDITION", ""));
    var compared = service.label(actor, "trial", new Labels(1, labels));
    assertEquals(new BigDecimal("100.0"), compared.agreement());
    assertTrue(compared.verified());
    assertEquals("SCORING_TOO_LENIENT", compared.diagnosis());
    assertNull(compared.results().get(10).label());
    verifyNoInteractions(evaluator);
  }

  @Test
  void per_condition_diagnosis_excludes_system_failures() {
    var r =
        List.of(
            new TrialResult("a", "SUCCEEDED", "FILTERED", null, null, List.of("hard"), "s", null),
            new TrialResult("b", "SUCCEEDED", "REVIEW_REQUIRED", null, null, List.of(), "s", null),
            new TrialResult(
                "c", "BLOCKED_NEEDS_EVALUATION", null, null, null, List.of("hard"), "s", "budget"));
    assertEquals(new BigDecimal("50.0"), HrTrialService.failureRates(r).get("hard"));
  }

  @Test
  void labels_cannot_be_revised_after_system_answers_revealed() {
    var repository = mock(HrSettingsRepository.class);
    var actor =
        new HrActor(
            "t", "1", Set.of("d"), Set.of("hr:trial:read", "hr:trial:label", "hr:candidate:read"));
    var label = new Label("c", "FILTERED", "HARD_CONDITION", "");
    var trial =
        new Trial(
            "trial",
            "p",
            "d",
            10,
            1,
            7,
            "hash",
            2,
            "COMPLETED",
            List.of(
                new TrialResult("c", "SUCCEEDED", "FILTERED", null, null, List.of(), "s", null)),
            List.of(label),
            null,
            null,
            false,
            null,
            LocalDate.now());
    when(repository.get(actor, "TRIAL", "trial", Trial.class)).thenReturn(trial);
    var service =
        new HrTrialService(
            repository,
            mock(HrPositionService.class),
            mock(HrCandidateService.class),
            mock(HrTrialEvaluator.class));
    assertThrows(
        HrBusinessException.class,
        () ->
            service.label(
                actor,
                "trial",
                new Labels(2, List.of(new Label("c", "RECOMMENDED", "SKILL", "")))));
    verify(repository, never())
        .save(
            any(), anyString(), anyString(), anyString(), anyLong(), anyLong(), any(), anyString());
  }
}
