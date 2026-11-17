package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrGrantTupleTest {
  @Test
  void permissions_and_object_grants_cannot_form_a_cross_department_cartesian_product() {
    var actor =
        new HrActor(
            "t",
            "1",
            Set.of("a", "b"),
            Set.of("hr:candidate:read", "hr:config:read"),
            Set.of("*"),
            Set.of("*", "c2"),
            true,
            List.of(
                new HrActor.GrantScope("hr:candidate:read", "a", null, "*"),
                new HrActor.GrantScope("hr:config:read", "b", null, null)));
    assertEquals(Set.of("a"), HrAccessPolicy.departmentsFor(actor, "hr:candidate:read"));
    HrAccessPolicy.requireFor(actor, "hr:candidate:read", "a", "c1", "CANDIDATE");
    assertThrows(
        HrBusinessException.class,
        () -> HrAccessPolicy.requireFor(actor, "hr:candidate:read", "b", "c2", "CANDIDATE"));
    HrAccessPolicy.requireFor(actor, "hr:config:read", "b", null, "CONFIG");
    assertThrows(
        HrBusinessException.class,
        () -> HrAccessPolicy.requireFor(actor, "hr:config:read", "a", null, "CONFIG"));
  }

  @Test
  void per_department_object_sets_do_not_borrow_wildcard_from_other_department() {
    var actor =
        new HrActor(
            "t",
            "1",
            Set.of("a", "b"),
            Set.of("hr:candidate:read"),
            Set.of(),
            Set.of("*", "c2"),
            true,
            List.of(
                new HrActor.GrantScope("hr:candidate:read", "a", null, "*"),
                new HrActor.GrantScope("hr:candidate:read", "b", null, "c2")));
    assertEquals(
        Set.of("c2"), HrAccessPolicy.objectIdsFor(actor, "hr:candidate:read", "b", "CANDIDATE"));
    assertThrows(
        HrBusinessException.class,
        () -> HrAccessPolicy.requireFor(actor, "hr:candidate:read", "b", "c3", "CANDIDATE"));
  }
}
