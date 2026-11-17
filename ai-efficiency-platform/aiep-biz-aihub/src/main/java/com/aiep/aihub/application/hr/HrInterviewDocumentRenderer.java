package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;

/** A4导出仅接收安全Guide，Word使用OOXML，PDF使用Unicode中文字体。 */
public final class HrInterviewDocumentRenderer {
  private HrInterviewDocumentRenderer() {}

  private static List<String> lines(InterviewGuide guide) {
    List<String> lines = new ArrayList<>();
    lines.add(guide.positionName());
    for (Question q : guide.questions()) {
      lines.add("第" + (q.layer() + 1) + "层 · " + q.minutes() + "分钟");
      lines.add(q.title());
      lines.add("目的：" + q.purpose());
      q.answerPoints().forEach(v -> lines.add("回答要点：" + v));
      q.followUps().forEach(v -> lines.add("追问：" + v));
      lines.add("优秀：" + q.references().excellent());
      lines.add("合格：" + q.references().qualified());
      lines.add("需核实：" + q.references().needsVerification());
      lines.add("\f");
      lines.add("面试记录：" + q.title());
      for (int i = 0; i < 32; i++) lines.add("____________________________________");
      lines.add("\f");
    }
    if (guide.resumeSections() != null && !guide.resumeSections().isEmpty()) {
      lines.add("附件：清洗后的可读简历（不含联系方式、评分与禁用属性）");
      for (var section : guide.resumeSections()) {
        lines.add(section.kind());
        lines.add(section.text());
      }
    }
    lines.add(guide.disclaimer());
    return lines;
  }

  public static byte[] word(InterviewGuide guide) {
    return wordLines(lines(guide));
  }

  public static byte[] word(ContactExportModel model) {
    return wordLines(contactLines(model));
  }

  private static List<String> contactLines(ContactExportModel model) {
    List<String> result = new ArrayList<>(lines(model.guide()));
    result.add(1, "联系版 · 仅限招聘负责人，不可转发面试官");
    result.add(
        2,
        "电话："
            + Objects.toString(model.contact().phone(), "未核实")
            + "；邮箱："
            + Objects.toString(model.contact().email(), "未核实"));
    return result;
  }

  private static byte[] wordLines(List<String> documentLines) {
    try {
      var bytes = new ByteArrayOutputStream();
      try (var zip = new ZipOutputStream(bytes, StandardCharsets.UTF_8)) {
        entry(
            zip,
            "[Content_Types].xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Types"
                + " xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default"
                + " Extension=\"rels\""
                + " ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default"
                + " Extension=\"xml\" ContentType=\"application/xml\"/><Override"
                + " PartName=\"/word/document.xml\""
                + " ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/></Types>");
        entry(
            zip,
            "_rels/.rels",
            "<Relationships"
                + " xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship"
                + " Id=\"rId1\""
                + " Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\""
                + " Target=\"word/document.xml\"/></Relationships>");
        StringBuilder body =
            new StringBuilder(
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?><w:document"
                    + " xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>");
        for (String line : documentLines) {
          if ("\f".equals(line)) {
            body.append("<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>");
            continue;
          }
          body.append(
                  "<w:p><w:r><w:rPr><w:rFonts w:eastAsia=\"Microsoft YaHei\"/><w:sz"
                      + " w:val=\"22\"/></w:rPr><w:t xml:space=\"preserve\">")
              .append(escape(line))
              .append("</w:t></w:r></w:p>");
        }
        body.append(
            "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1134\""
                + " w:right=\"1134\" w:bottom=\"1134\""
                + " w:left=\"1134\"/></w:sectPr></w:body></w:document>");
        entry(zip, "word/document.xml", body.toString());
      }
      return bytes.toByteArray();
    } catch (IOException e) {
      throw new IllegalStateException("HR_EXPORT_RENDER_FAILED");
    }
  }

  private static void entry(ZipOutputStream zip, String name, String content) throws IOException {
    zip.putNextEntry(new ZipEntry(name));
    zip.write(content.getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
  }

  private static String escape(String value) {
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
  }

  public static byte[] pdf(InterviewGuide guide) {
    return pdfLines(lines(guide));
  }

  public static byte[] pdf(ContactExportModel model) {
    return pdfLines(contactLines(model));
  }

  private static byte[] pdfLines(List<String> documentLines) {
    try {
      List<String> wrapped = new ArrayList<>();
      for (String line : documentLines) {
        if ("\f".equals(line)) {
          while (wrapped.size() % 44 != 0) wrapped.add("");
          continue;
        }
        int[] points = line.codePoints().toArray();
        if (points.length == 0) wrapped.add("");
        for (int i = 0; i < points.length; i += 42)
          wrapped.add(new String(points, i, Math.min(42, points.length - i)));
      }
      int pages = Math.max(1, (wrapped.size() + 43) / 44);
      List<byte[]> objects = new ArrayList<>();
      objects.add(ascii("<< /Type /Catalog /Pages 2 0 R >>"));
      StringBuilder kids = new StringBuilder();
      for (int p = 0; p < pages; p++) kids.append(5 + p * 2).append(" 0 R ");
      objects.add(ascii("<< /Type /Pages /Count " + pages + " /Kids [" + kids + "] >>"));
      objects.add(
          ascii(
              "<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H"
                  + " /DescendantFonts [4 0 R] >>"));
      objects.add(
          ascii(
              "<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo <<"
                  + " /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> >>"));
      for (int p = 0; p < pages; p++) {
        int contentId = 6 + p * 2;
        objects.add(
            ascii(
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3"
                    + " 0 R >> >> /Contents "
                    + contentId
                    + " 0 R >>"));
        StringBuilder stream = new StringBuilder("BT /F1 11 Tf 50 790 Td 16 TL\n");
        for (int i = p * 44; i < Math.min((p + 1) * 44, wrapped.size()); i++)
          stream
              .append('<')
              .append(HexFormat.of().formatHex(wrapped.get(i).getBytes(StandardCharsets.UTF_16BE)))
              .append("> Tj T*\n");
        stream
            .append("ET\nBT /F1 9 Tf 50 30 Td <")
            .append(
                HexFormat.of()
                    .formatHex(
                        ("AI辅助 · " + (p + 1) + "/" + pages).getBytes(StandardCharsets.UTF_16BE)))
            .append("> Tj ET");
        byte[] contents = ascii(stream.toString());
        var obj = new ByteArrayOutputStream();
        obj.write(ascii("<< /Length " + contents.length + " >>\nstream\n"));
        obj.write(contents);
        obj.write(ascii("\nendstream"));
        objects.add(obj.toByteArray());
      }
      var out = new ByteArrayOutputStream();
      out.write(ascii("%PDF-1.4\n"));
      List<Integer> offsets = new ArrayList<>();
      offsets.add(0);
      for (int i = 0; i < objects.size(); i++) {
        offsets.add(out.size());
        out.write(ascii((i + 1) + " 0 obj\n"));
        out.write(objects.get(i));
        out.write(ascii("\nendobj\n"));
      }
      int start = out.size();
      out.write(ascii("xref\n0 " + offsets.size() + "\n0000000000 65535 f \n"));
      for (int i = 1; i < offsets.size(); i++)
        out.write(ascii(String.format(Locale.ROOT, "%010d 00000 n \n", offsets.get(i))));
      out.write(
          ascii(
              "trailer\n<< /Size "
                  + offsets.size()
                  + " /Root 1 0 R >>\nstartxref\n"
                  + start
                  + "\n%%EOF\n"));
      return out.toByteArray();
    } catch (IOException e) {
      throw new IllegalStateException("HR_EXPORT_RENDER_FAILED");
    }
  }

  private static byte[] ascii(String value) {
    return value.getBytes(StandardCharsets.ISO_8859_1);
  }
}
