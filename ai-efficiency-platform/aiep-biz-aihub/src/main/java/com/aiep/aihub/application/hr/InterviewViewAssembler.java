package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import org.springframework.stereotype.Component;

/** 预览、PDF及Word共用的物理白名单，不装载匹配分数或联系信息。 */
@Component
public class InterviewViewAssembler {
  public java.util.List<ResumeSection> resume(
      com.aiep.aihub.api.hr.HrCandidateContracts.Facts facts) {
    return facts.structuredFacts().stream()
        .filter(
            f ->
                java.util.Set.of(
                        "employment", "project", "education", "skill", "language", "certificate")
                    .contains(f.kind()))
        .map(
            f ->
                new ResumeSection(
                    f.kind(),
                    java.util.stream.Stream.of(
                            f.organization(), f.title(), f.degree(), f.major(), f.value())
                        .filter(java.util.Objects::nonNull)
                        .distinct()
                        .collect(java.util.stream.Collectors.joining(" · "))))
        .filter(s -> safe(s.text()))
        .toList();
  }

  private boolean safe(String text) {
    if (text.isBlank() || text.length() > 5000) return false;
    if (text.matches("(?s).*1[3-9][0-9]{9}.*")
        || text.matches("(?s).*[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}.*")) return false;
    if (text.matches(
        "(?is).*(?:\\b(?:strong|weak|partial|strength|rank|score)\\b|(?:^|[ ·：:])(?:强|中|弱)(?:$|["
            + " ·，,])).*")) return false;
    return java.util.List.of(
            "婚姻", "婚育", "生育", "怀孕", "民族", "宗教", "政治面貌", "身份证", "性取向", "健康状况", "年龄", "性别", "户籍",
            "照片", "残疾", "评分", "排名", "评级", "联系方式")
        .stream()
        .noneMatch(text::contains);
  }

  public InterviewGuide assemble(InterviewSet set, String positionName) {
    return new InterviewGuide(
        set.id(),
        set.version(),
        positionName,
        set.questions(),
        "AI辅助生成，仅供面试准备，最终判断由招聘人员负责。",
        set.resumeSections() == null ? java.util.List.of() : set.resumeSections());
  }
}
