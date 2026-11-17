package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTemplateContracts.*;
import com.aiep.aihub.api.hr.HrTrialContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrTemplateVerificationTest {
  @Test
  void verification_requires_same_frozen_rules_and_records_evidence_without_candidate_body() {
    var repository = mock(HrSettingsRepository.class);
    var trials = mock(HrTrialService.class);
    var actor =
        new HrActor(
            "t", "1", Set.of("d"), Set.of("hr:config:read", "hr:config:publish", "hr:config:edit"));
    var draft = new HrMatchingLifecycleTest().config().snapshot();
    Map<String, Integer> weights = new HashMap<>();
    draft.scoring().weights().forEach((k, v) -> weights.put(k.name(), v));
    var template =
        new Template(
            "template",
            "d",
            "模板",
            "TECHNOLOGY",
            false,
            "PUBLISHED",
            weights,
            draft.hardConditions(),
            draft.criteria(),
            1,
            null,
            null,
            draft.scoring().requirements());
    when(repository.get(actor, "TEMPLATE", "template", Template.class)).thenReturn(template);
    List<TrialResult> results = new ArrayList<>();
    List<Label> labels = new ArrayList<>();
    for (int i = 0; i < 10; i++) {
      results.add(
          new TrialResult(
              "c" + i,
              "SUCCEEDED",
              "RECOMMENDED",
              BigDecimal.valueOf(75),
              BigDecimal.valueOf(100),
              List.of(),
              "s",
              null));
      labels.add(new Label("c" + i, "RECOMMENDED", "SKILL", ""));
    }
    var trial =
        new Trial(
            "trial",
            "p",
            "d",
            10,
            10,
            1,
            "hash",
            3,
            "COMPLETED",
            results,
            labels,
            "SCORING_TOO_LENIENT",
            BigDecimal.valueOf(100),
            true,
            draft,
            LocalDate.now());
    when(trials.get(actor, "trial")).thenReturn(trial);
    var service = new HrTemplateService(repository, mock(HrPositionService.class), trials);
    var verified = service.validateTrial(actor, "template", new Validate(1, "trial"));
    assertNotNull(verified.verification());
    assertEquals(10, verified.verification().sampleSize());
    assertEquals("trial", verified.verification().trialId());
    assertEquals(2, verified.version());
    when(repository.get(actor, "TEMPLATE", "template", Template.class)).thenReturn(verified);
    var edited =
        service.edit(
            actor,
            "template",
            new Edit(
                2,
                "新模板",
                weights,
                draft.hardConditions(),
                draft.criteria(),
                draft.scoring().requirements()));
    assertNull(edited.verification());
  }

  @Test
  void unrelated_trial_cannot_certify_a_template() {
    var repository = mock(HrSettingsRepository.class);
    var trials = mock(HrTrialService.class);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:config:read", "hr:config:publish"));
    var template = HrTemplateService.platformTemplates().getFirst();
    var organization =
        new Template(
            "template",
            "d",
            "空模板",
            template.family(),
            false,
            "DRAFT",
            template.weights(),
            List.of(),
            List.of(),
            1,
            null,
            null);
    when(repository.get(actor, "TEMPLATE", "template", Template.class)).thenReturn(organization);
    when(trials.get(actor, "trial"))
        .thenReturn(
            new Trial(
                "trial",
                "p",
                "d",
                10,
                10,
                1,
                "hash",
                3,
                "COMPLETED",
                List.of(),
                List.of(),
                "BALANCED",
                BigDecimal.valueOf(100),
                true,
                new HrMatchingLifecycleTest().config().snapshot(),
                LocalDate.now()));
    var service = new HrTemplateService(repository, mock(HrPositionService.class), trials);
    assertThrows(
        HrBusinessException.class,
        () -> service.validateTrial(actor, "template", new Validate(1, "trial")));
    verify(repository, never())
        .save(
            any(), anyString(), anyString(), anyString(), anyLong(), anyLong(), any(), anyString());
  }
}
