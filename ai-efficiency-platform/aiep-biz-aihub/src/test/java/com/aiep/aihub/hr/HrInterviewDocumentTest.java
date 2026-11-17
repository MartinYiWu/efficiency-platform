package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrInterviewDocumentTest {
  @Test
  void word_and_pdf_are_real_documents_from_safe_guide() throws Exception {
    var type = Class.forName("com.aiep.aihub.application.hr.HrInterviewDocumentRenderer");
    var guide =
        new InterviewGuide(
            "s",
            1,
            "工程师面试指南",
            List.of(
                new Question(
                    "q",
                    0,
                    "请介绍你负责的系统模块，并说明关键技术选择。",
                    "核实项目职责与技术取舍",
                    List.of("个人职责边界", "方案选择依据", "结果核验方法"),
                    List.of("有哪些可验证的成果？", "遇到瓶颈如何定位？"),
                    new Reference("清晰说明证据与取舍", "能说明职责与基本方案", "需进一步核实具体职责"),
                    "RESUME_VERIFY",
                    List.of("fact1"),
                    3,
                    "项目经验")),
            "AI辅助，仅供面试准备，最终判断由招聘人员负责。");
    byte[] word = (byte[]) type.getMethod("word", InterviewGuide.class).invoke(null, guide);
    assertEquals('P', word[0]);
    assertEquals('K', word[1]);
    byte[] pdf = (byte[]) type.getMethod("pdf", InterviewGuide.class).invoke(null, guide);
    assertTrue(
        new String(pdf, java.nio.charset.StandardCharsets.ISO_8859_1).startsWith("%PDF-1.4"));
    var dir = java.nio.file.Path.of("../../.local-acceptance/hr-completion-20261111/talent-export");
    java.nio.file.Files.createDirectories(dir);
    java.nio.file.Files.write(dir.resolve("interview-guide.pdf"), pdf);
    java.nio.file.Files.write(dir.resolve("interview-guide.docx"), word);
  }
}
