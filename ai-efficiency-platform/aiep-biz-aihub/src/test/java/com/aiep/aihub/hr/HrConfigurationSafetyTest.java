package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrJdDraftContracts.*;
import com.aiep.aihub.api.hr.HrTemplateContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

class HrConfigurationSafetyTest {
  @Test
  void jd_requires_verbatim_evidence_default_unadopted_and_strips_protected_fields()
      throws Exception {
    var json = JsonMapper.builder().build();
    String text = "具备Java开发能力，负责服务治理。年龄不超过30岁。";
    var output =
        json.readTree(
            "{\"candidates\":[{\"type\":\"SKILL\",\"dimension\":\"SKILL\",\"skill\":{\"name\":\"Java\"},\"criterion\":\"Java开发\",\"source_quote\":\"具备Java开发能力\"},{\"type\":\"SKILL\",\"dimension\":\"SKILL\",\"skill\":{\"name\":\"Java\"},\"criterion\":\"年龄限制\",\"source_quote\":\"年龄不超过30岁\"}]}");
    var result = HrJdDraftService.validate("d", "p", "dept", text, false, output);
    assertEquals(1, result.candidates().size());
    assertTrue(result.adoptedIds().isEmpty());
    assertFalse(result.safetyWarnings().isEmpty());
    var c = result.candidates().getFirst();
    assertEquals(c.originalQuote(), text.substring(c.start(), c.end()));
    assertThrows(
        HrBusinessException.class,
        () ->
            HrJdDraftService.validate(
                "d",
                "p",
                "dept",
                text,
                false,
                json.readTree(
                    "{\"candidates\":[{\"type\":\"SKILL\",\"dimension\":\"SKILL\",\"skill\":{\"name\":\"Java\"},\"criterion\":\"Java\",\"source_quote\":\"不存在\"}]}")));
    assertThrows(
        HrBusinessException.class,
        () ->
            HrJdDraftService.validate(
                "d",
                "p",
                "dept",
                text,
                false,
                json.readTree(
                    "{\"candidates\":[{\"type\":\"SKILL\",\"dimension\":\"SKILL\",\"skill\":{\"name\":\"Java\"},\"criterion\":\"Java\",\"source_quote\":\"具备Java开发能力\",\"default_adopted\":true}]}")));
  }

  @Test
  void short_jd_and_immutable_platform_template_do_not_invoke_external_calls() {
    var positions = mock(HrPositionService.class);
    var gateway = mock(HrSemanticGateway.class);
    var repository = mock(HrSettingsRepository.class);
    var actor =
        new HrActor(
            "t", "1", Set.of("d"), Set.of("hr:position:edit", "hr:config:read", "hr:config:edit"));
    when(positions.get(actor, "p"))
        .thenReturn(
            new HrPositionContracts.Position(
                "p",
                "t",
                "岗位",
                "TECHNOLOGY",
                "d",
                "P6",
                "d-1",
                "DRAFT",
                null,
                "ctx-1",
                "1",
                java.time.Instant.now(),
                1));
    var jd = new HrJdDraftService(positions, gateway, repository, JsonMapper.builder().build());
    assertThrows(HrBusinessException.class, () -> jd.generate(actor, "p", new Generate("太短", 1)));
    verifyNoInteractions(gateway, repository);
    var templates = new HrTemplateService(repository, positions);
    assertThrows(
        HrBusinessException.class,
        () ->
            templates.edit(
                actor, "platform-TECHNOLOGY", new Edit(1, "编辑", Map.of(), List.of(), List.of())));
    verifyNoInteractions(repository);
  }

  @Test
  void csv_roundtrip_and_xlsx_formulas_and_size_limits() throws Exception {
    var csv =
        new MockMultipartFile(
            "file",
            "d.csv",
            "text/csv",
            "id,category,canonical,aliases,contextPattern\r\na,SKILL,Java,JDK|JVM,\r\n"
                .getBytes(StandardCharsets.UTF_8));
    var entries = HrDictionaryFileReader.read(csv);
    assertEquals(List.of("JDK", "JVM"), entries.getFirst().aliases());
    var bad = new MockMultipartFile("file", "d.csv", "text/csv", new byte[10485761]);
    assertThrows(HrBusinessException.class, () -> HrDictionaryFileReader.read(bad));
    byte[] sheet =
        "<worksheet><sheetData><row><c r=\"A1\"><f>HYPERLINK(1)</f><v>id</v></c></row></sheetData></worksheet>"
            .getBytes(StandardCharsets.UTF_8);
    var out = new ByteArrayOutputStream();
    try (var zip = new ZipOutputStream(out)) {
      zip.putNextEntry(new ZipEntry("xl/worksheets/sheet1.xml"));
      zip.write(sheet);
      zip.closeEntry();
    }
    assertThrows(
        HrBusinessException.class,
        () ->
            HrDictionaryFileReader.read(
                new MockMultipartFile(
                    "file", "d.xlsx", "application/octet-stream", out.toByteArray())));
  }

  @Test
  void
      jd_structured_categories_preserve_hard_conditions_experience_and_project_as_unadopted_drafts() {
    var json = JsonMapper.builder().build();
    var output = json.createObjectNode();
    var items = output.putArray("candidates");
    var hard =
        items
            .addObject()
            .put("type", "HARD_CONDITION")
            .put("dimension", "SKILL")
            .put("criterion", "必须掌握Java")
            .put("source_quote", "必须掌握Java");
    hard.putObject("hard_condition")
        .put("type", "REQUIRED_SKILL")
        .put("match_mode", "ALL")
        .putArray("values")
        .add("Java");
    var exp =
        items
            .addObject()
            .put("type", "EXPERIENCE")
            .put("dimension", "EXPERIENCE")
            .put("criterion", "3至5年经验")
            .put("source_quote", "3至5年经验");
    exp.putObject("experience").put("minimum_months", 36).put("maximum_months", 60);
    var project =
        items
            .addObject()
            .put("type", "PROJECT")
            .put("dimension", "PROJECT")
            .put("criterion", "管理10人团队")
            .put("source_quote", "管理10人团队");
    project.putObject("project").put("managed_team_size", 10);
    var result =
        HrJdDraftService.validate("jd", "p", "d", "必须掌握Java；3至5年经验；管理10人团队。", false, output);
    assertTrue(result.adoptedIds().isEmpty());
    assertEquals("REQUIRED_SKILL", result.candidates().get(0).hardRule().type());
    assertFalse(result.candidates().get(0).hardRule().overridable());
    assertEquals("EXPERIENCE", result.candidates().get(1).criterion().dimension());
    assertEquals("EXPERIENCE_MONTHS", result.candidates().get(1).criterion().calculation().type());
    assertEquals("TEAM_SIZE", result.candidates().get(2).criterion().calculation().type());
    assertEquals("", result.candidates().get(1).criterion().matchAnchor());
  }

  @Test
  void configuration_permissions_never_imply_candidate_body_access() {
    var actor =
        new HrActor(
            "t", "1", Set.of("d"), Set.of("hr:config:read", "hr:config:edit", "hr:config:publish"));
    assertThrows(
        HrBusinessException.class, () -> HrAccessPolicy.require(actor, "hr:candidate:read"));
  }
}
