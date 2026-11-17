package com.aiep.aihub.application.hr;

import java.util.*;

/** 冻结的六层题量与时长门禁。 */
public final class HrInterviewRules {
  private HrInterviewRules() {}

  public static int[] preset(int minutes) {
    return switch (minutes) {
      case 30 -> new int[] {2, 2, 1, 2, 1, 1};
      case 45 -> new int[] {3, 2, 2, 3, 2, 1};
      case 60 -> new int[] {4, 3, 2, 4, 3, 1};
      case 90 -> new int[] {6, 5, 3, 6, 4, 2};
      default -> throw invalid();
    };
  }

  public static int estimated(int[] counts, int[] durations) {
    if (counts == null || durations == null || counts.length != 6 || durations.length != 6)
      throw invalid();
    int total = 0, questions = 0;
    for (int i = 0; i < 6; i++) {
      if (counts[i] < 0 || counts[i] > 10 || durations[i] < 1 || durations[i] > 15) throw invalid();
      total += counts[i] * durations[i];
      questions += counts[i];
    }
    if (questions < 1 || questions > 40) throw invalid();
    return total;
  }

  private static HrBusinessException invalid() {
    return new HrBusinessException("HR_INTERVIEW_PLAN_INVALID", "题量或时长不符合六层面试规则", 422);
  }
}
