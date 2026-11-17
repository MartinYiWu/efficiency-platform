package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.HrSpecialMarksService;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrSpecialMarksTest {
  @Test
  void all_five_marks_are_stored_even_when_hidden() {
    var facts =
        new Facts(
            "c",
            "r",
            "resume",
            1,
            60,
            "NEEDS_REVIEW",
            new Profile("合成", "本科", 24, ""),
            List.of(),
            List.of(),
            List.of(),
            0,
            0,
            1);
    var marks =
        HrSpecialMarksService.basic(
            facts, List.of(), List.of("CRITICAL_REQUIREMENT_UNKNOWN"), "NOT_RECOMMEND", List.of());
    assertEquals(5, marks.size());
    assertTrue(
        marks.stream()
            .filter(m -> m.key().equals("MANUAL_REVIEW"))
            .findFirst()
            .orElseThrow()
            .active());
    assertTrue(marks.stream().noneMatch(SpecialMark::visible));
  }

  @Test
  void keyword_background_is_not_inferred() {
    var facts =
        new Facts(
            "c",
            "r",
            "创业项目",
            1,
            100,
            "READY",
            new Profile("合成", "本科", 24, ""),
            List.of(new Block("b", 1, "喜欢创业跨界", null)),
            List.of(),
            List.of(),
            0,
            0,
            1);
    var marks =
        HrSpecialMarksService.basic(
            facts, List.of(), List.of(), "NOT_RECOMMEND", List.of("SPECIAL_BACKGROUND"));
    assertFalse(
        marks.stream()
            .filter(m -> m.key().equals("SPECIAL_BACKGROUND"))
            .findFirst()
            .orElseThrow()
            .active());
  }

  @Test
  void explicit_sourced_background_only_marks_low_band() {
    var fact =
        new StructuredFact(
            "f",
            "employment",
            "创办订单服务企业",
            List.of(new Evidence("b", 0, 8, "创办订单服务企业")),
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            "ENTREPRENEURSHIP");
    var facts =
        new Facts(
            "c",
            "r",
            "resume",
            1,
            100,
            "READY",
            new Profile("合成", "本科", 24, ""),
            List.of(new Block("b", 1, "创办订单服务企业", null)),
            List.of(),
            List.of(),
            0,
            0,
            1,
            List.of(fact));
    assertTrue(
        HrSpecialMarksService.basic(
                facts, List.of(), List.of(), "NOT_RECOMMEND", List.of("SPECIAL_BACKGROUND"))
            .get(4)
            .active());
    assertFalse(
        HrSpecialMarksService.basic(
                facts, List.of(), List.of(), "RECOMMEND", List.of("SPECIAL_BACKGROUND"))
            .get(4)
            .active());
  }

  @Test
  void borderline_and_observable_reversed_dates_do_not_need_model() {
    var fact =
        new StructuredFact(
            "f",
            "employment",
            "合成经历",
            List.of(),
            null,
            null,
            null,
            null,
            new DateValue("2025-01", "MONTH", ""),
            new DateValue("2024-01", "MONTH", ""),
            false,
            false);
    var facts =
        new Facts(
            "c",
            "r",
            "resume",
            1,
            100,
            "READY",
            new Profile("合成", "本科", 24, ""),
            List.of(),
            List.of(),
            List.of(),
            0,
            0,
            1,
            List.of(fact));
    var marks =
        HrSpecialMarksService.basic(
            facts,
            List.of(new HardConditionView("h", "年限", "BORDERLINE", "", "", true)),
            List.of(),
            "REVIEW",
            List.of("BORDERLINE", "QUALITY_WARNING"));
    assertTrue(marks.get(1).active());
    assertTrue(marks.get(2).active());
  }
}
