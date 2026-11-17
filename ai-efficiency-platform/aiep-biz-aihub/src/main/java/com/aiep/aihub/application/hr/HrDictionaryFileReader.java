package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrDictionaryContracts.Entry;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.springframework.web.multipart.MultipartFile;
import org.w3c.dom.*;

/** 限量本地CSV/XLSX解析，不执行公式、宏或外部实体。 */
public final class HrDictionaryFileReader {
  private HrDictionaryFileReader() {}

  public static List<Entry> read(MultipartFile file) {
    if (file.isEmpty() || file.getSize() > 10485760)
      throw HrPositionService.invalid("导入文件须为1字节至10MiB");
    try {
      String name =
          Optional.ofNullable(file.getOriginalFilename()).orElse("").toLowerCase(Locale.ROOT);
      List<List<String>> rows;
      if (name.endsWith(".csv")) rows = csv(new String(file.getBytes(), StandardCharsets.UTF_8));
      else if (name.endsWith(".xlsx")) rows = xlsx(file.getBytes());
      else throw HrPositionService.invalid("仅支持CSV/XLSX");
      if (rows.isEmpty() || rows.size() > 10001) throw HrPositionService.invalid("导入最多10000行");
      if (!rows.getFirst()
          .equals(List.of("id", "category", "canonical", "aliases", "contextPattern")))
        throw HrPositionService.invalid("表头须为id,category,canonical,aliases,contextPattern");
      List<Entry> result = new ArrayList<>();
      for (var row : rows.subList(1, rows.size())) {
        if (row.stream().allMatch(String::isBlank)) continue;
        if (row.size() != 5) throw HrPositionService.invalid("每行须5列");
        result.add(
            new Entry(
                row.get(0),
                row.get(1),
                row.get(2),
                row.get(3).isBlank() ? List.of() : List.of(row.get(3).split("\\|", -1)),
                row.get(4)));
      }
      return result;
    } catch (IOException e) {
      throw HrPositionService.invalid("导入文件无法读取");
    }
  }

  public static List<List<String>> csv(String text) {
    text = text.replaceFirst("^\uFEFF", "");
    List<List<String>> rows = new ArrayList<>();
    List<String> row = new ArrayList<>();
    StringBuilder cell = new StringBuilder();
    boolean quoted = false;
    for (int i = 0; i < text.length(); i++) {
      char c = text.charAt(i);
      if (c == '"') {
        if (quoted && i + 1 < text.length() && text.charAt(i + 1) == '"') {
          cell.append('"');
          i++;
        } else quoted = !quoted;
      } else if (!quoted && c == ',') {
        row.add(cell.toString());
        cell.setLength(0);
      } else if (!quoted && (c == '\r' || c == '\n')) {
        if (c == '\r' && i + 1 < text.length() && text.charAt(i + 1) == '\n') i++;
        row.add(cell.toString());
        rows.add(List.copyOf(row));
        row.clear();
        cell.setLength(0);
        if (rows.size() > 10001) throw HrPositionService.invalid("导入超过10000行");
      } else cell.append(c);
    }
    if (quoted) throw HrPositionService.invalid("CSV引号不完整");
    if (!cell.isEmpty() || !row.isEmpty()) {
      row.add(cell.toString());
      rows.add(row);
    }
    return rows;
  }

  private static Document xml(byte[] bytes) throws Exception {
    var f = DocumentBuilderFactory.newInstance();
    f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    f.setFeature("http://xml.org/sax/features/external-general-entities", false);
    f.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
    f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
    f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
    return f.newDocumentBuilder().parse(new ByteArrayInputStream(bytes));
  }

  private static List<List<String>> xlsx(byte[] bytes) {
    try {
      Map<String, byte[]> parts = new HashMap<>();
      long total = 0;
      try (var zip = new ZipInputStream(new ByteArrayInputStream(bytes))) {
        ZipEntry entry;
        int count = 0;
        while ((entry = zip.getNextEntry()) != null) {
          if (++count > 200) throw HrPositionService.invalid("XLSX条目过多");
          var out = new ByteArrayOutputStream();
          byte[] buffer = new byte[8192];
          int n;
          while ((n = zip.read(buffer)) != -1) {
            total += n;
            if (total > 52428800) throw HrPositionService.invalid("XLSX展开超限");
            out.write(buffer, 0, n);
          }
          if (Set.of("xl/sharedStrings.xml", "xl/worksheets/sheet1.xml").contains(entry.getName()))
            parts.put(entry.getName(), out.toByteArray());
        }
      }
      List<String> shared = new ArrayList<>();
      if (parts.containsKey("xl/sharedStrings.xml")) {
        var strings = xml(parts.get("xl/sharedStrings.xml")).getElementsByTagName("si");
        for (int i = 0; i < strings.getLength(); i++) shared.add(strings.item(i).getTextContent());
      }
      if (!parts.containsKey("xl/worksheets/sheet1.xml"))
        throw HrPositionService.invalid("缺少首张工作表");
      var nodes = xml(parts.get("xl/worksheets/sheet1.xml")).getElementsByTagName("row");
      if (nodes.getLength() > 10001) throw HrPositionService.invalid("导入超过10000行");
      List<List<String>> rows = new ArrayList<>();
      for (int i = 0; i < nodes.getLength(); i++) {
        var cells = ((Element) nodes.item(i)).getElementsByTagName("c");
        List<String> row = new ArrayList<>(Collections.nCopies(5, ""));
        for (int j = 0; j < cells.getLength(); j++) {
          Element c = (Element) cells.item(j);
          if (c.getElementsByTagName("f").getLength() > 0)
            throw HrPositionService.invalid("导入禁止公式");
          int column = 0;
          for (char letter : c.getAttribute("r").toCharArray()) {
            if (!Character.isLetter(letter)) break;
            column = column * 26 + letter - 'A' + 1;
          }
          if (column < 1 || column > 5) throw HrPositionService.invalid("导入仅5列");
          String value = c.getTextContent();
          if ("s".equals(c.getAttribute("t"))) value = shared.get(Integer.parseInt(value));
          row.set(column - 1, value);
        }
        rows.add(row);
      }
      return rows;
    } catch (HrBusinessException e) {
      throw e;
    } catch (Exception e) {
      throw HrPositionService.invalid("XLSX格式无效");
    }
  }
}
