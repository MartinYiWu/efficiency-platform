package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.application.hr.HrTalentDedup;
import com.aiep.aihub.application.hr.HrTalentDedup.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrTalentIdentityRulesTest {
  private ContactSignal signal(String kind, String value, int quality) {
    return new ContactSignal(kind, value, quality, false, false);
  }

  @Test
  void a_matching_phone_does_not_override_conflicting_email() {
    assertEquals(
        IdentityDecision.MANUAL_REVIEW,
        HrTalentDedup.identity(
            List.of(
                signal("PHONE", "+86 13900000000", 100), signal("EMAIL", "a@example.test", 100)),
            List.of(
                signal("PHONE", "+8613900000000", 100), signal("EMAIL", "b@example.test", 100))));
  }

  @Test
  void normalized_high_quality_single_signal_can_auto_link() {
    assertEquals(
        IdentityDecision.AUTO_LINK,
        HrTalentDedup.identity(
            List.of(signal("PHONE", "+86 13900000000", 100)),
            List.of(signal("PHONE", "+8613900000000", 100))));
  }

  @Test
  void low_quality_shared_and_conflicted_signals_never_auto_link() {
    var trusted = List.of(signal("EMAIL", "a@example.test", 100));
    for (var untrusted :
        List.of(
            signal("EMAIL", "a@example.test", 60),
            new ContactSignal("EMAIL", "a@example.test", 100, true, false),
            new ContactSignal("EMAIL", "a@example.test", 100, false, true)))
      assertNotEquals(
          IdentityDecision.AUTO_LINK, HrTalentDedup.identity(List.of(untrusted), trusted));
  }

  @Test
  void missing_contacts_never_link() {
    assertEquals(IdentityDecision.UNRELATED, HrTalentDedup.identity(List.of(), List.of()));
  }
}
