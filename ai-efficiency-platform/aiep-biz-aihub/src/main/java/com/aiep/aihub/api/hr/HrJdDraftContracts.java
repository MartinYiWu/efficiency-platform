package com.aiep.aihub.api.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.*;
import java.util.List;

/** JD候选只作未采用草案，原句使用UTF-16起止偏移定位。 */
public final class HrJdDraftContracts {
  private HrJdDraftContracts() {}

  public record Generate(String text, long expectedPositionVersion) {}

  public record SkillProposal(String name, Integer expectedLevel, int importance) {}

  public record ExperienceProposal(
      Integer minimumMonths, Integer maximumMonths, String industry, String function) {}

  public record ProjectProposal(
      String metric,
      String unit,
      java.math.BigDecimal expectedScale,
      Integer expectedRole,
      Integer managedTeamSize) {}

  public record Candidate(
      String id,
      String type,
      String label,
      String originalQuote,
      int start,
      int end,
      HardRule hardRule,
      SemanticCriterion criterion,
      SkillProposal skill,
      ExperienceProposal experience,
      ProjectProposal project) {}

  public record JdDraft(
      String id,
      String positionId,
      String departmentId,
      String sourceText,
      boolean truncated,
      List<Candidate> candidates,
      List<String> safetyWarnings,
      long version,
      List<String> adoptedIds) {
    public JdDraft {
      candidates = List.copyOf(candidates);
      safetyWarnings = List.copyOf(safetyWarnings);
      adoptedIds = List.copyOf(adoptedIds);
    }
  }

  public record Adopt(
      long expectedVersion, long expectedPositionVersion, List<String> candidateIds) {}
}
