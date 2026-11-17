package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.application.hr.HrProtectedAttributes;
import org.junit.jupiter.api.Test;

class HrProtectedAttributesTest {
  @Test
  void all_sixteen_protected_attributes_are_server_side_rejected() {
    assertEquals(16, HrProtectedAttributes.FIELDS.size());
    for (var name : HrProtectedAttributes.FIELDS)
      assertThrows(RuntimeException.class, () -> HrProtectedAttributes.validateRule(name + "必须符合"));
  }

  @Test
  void professional_system_stability_is_allowed_but_personal_loyalty_is_not() {
    assertDoesNotThrow(() -> HrProtectedAttributes.validateRule("Java系统稳定性与性能优化"));
    assertThrows(RuntimeException.class, () -> HrProtectedAttributes.validateRule("候选人忠诚度高"));
  }

  @Test
  void english_fields_do_not_bypass_the_same_rule() {
    assertThrows(RuntimeException.class, () -> HrProtectedAttributes.validateRule("Gender: male"));
    assertDoesNotThrow(
        () -> HrProtectedAttributes.validateRule("distributed storage architecture"));
  }
}
