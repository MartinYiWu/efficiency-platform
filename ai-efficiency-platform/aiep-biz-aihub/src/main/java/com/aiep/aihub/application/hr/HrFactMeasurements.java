package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.domain.hr.HrMonthIntervalCalculator;
import java.time.*;
import java.util.*;

final class HrFactMeasurements {
  private HrFactMeasurements() {}

  static Integer educationRank(String degree) {
    if (degree == null) return null;
    return switch (degree) {
      case "中专", "高中" -> 1;
      case "大专", "专科" -> 2;
      case "本科", "学士" -> 3;
      case "硕士" -> 4;
      case "博士" -> 5;
      default -> null;
    };
  }

  static StructuredFact education(List<StructuredFact> structured, List<Field> fields) {
    Set<String> confirmed = confirmed(fields);
    return structured.stream()
        .filter(
            f ->
                f.kind().equals("education")
                    && confirmed.contains(f.factId())
                    && educationRank(f.degree()) != null)
        .max(Comparator.comparingInt(f -> educationRank(f.degree())))
        .orElse(null);
  }

  static HrMonthIntervalCalculator.MonthBounds experience(
      List<StructuredFact> structured, List<Field> fields, LocalDate asOfDate) {
    Set<String> confirmed = confirmed(fields);
    List<HrMonthIntervalCalculator.WorkPeriod> periods = new ArrayList<>();
    boolean conflict = false;
    for (StructuredFact fact : structured) {
      if (!fact.kind().equals("employment")) continue;
      if (!confirmed.contains(fact.factId()) || fact.startDate() == null) {
        conflict = true;
        continue;
      }
      try {
        periods.add(
            new HrMonthIntervalCalculator.WorkPeriod(
                range(fact.startDate()),
                fact.endDate() == null ? null : range(fact.endDate()),
                Boolean.TRUE.equals(fact.ongoing()),
                fact.isInternship()));
      } catch (RuntimeException error) {
        conflict = true;
      }
    }
    if (periods.isEmpty()) return null;
    var bounds = new HrMonthIntervalCalculator().calculate(periods, asOfDate);
    return new HrMonthIntervalCalculator.MonthBounds(
        bounds.minMonths(), bounds.maxMonths(), bounds.needsReview() || conflict);
  }

  /** 实际材料的只读展示，不参与权威硬条件判断或评分。 */
  static String actual(com.aiep.aihub.api.hr.HrPositionContracts.HardRule rule,Facts facts,LocalDate asOfDate,String status){
    if("EDUCATION".equals(rule.type())){var degree=education(facts.structuredFacts(),facts.fields());return degree==null?null:degree.degree();}
    if("WORK_EXPERIENCE".equals(rule.type())){var bounds=experience(facts.structuredFacts(),facts.fields(),asOfDate);if(bounds==null)return null;String value=bounds.minMonths()==bounds.maxMonths()?bounds.minMonths()+"个月":bounds.minMonths()+"—"+bounds.maxMonths()+"个月";return bounds.needsReview()?value+"（日期范围需核对）":value;}
    Set<String> confirmed=confirmed(facts.fields());
    if("LANGUAGE".equals(rule.type())&&rule.unit()!=null&&!rule.unit().isBlank()){List<String> quotes=new ArrayList<>();for(var fact:facts.structuredFacts())if("language".equals(fact.kind())&&confirmed.contains(fact.factId())&&fact.evidence()!=null)for(var e:fact.evidence())if(e.quote().toLowerCase(Locale.ROOT).contains(rule.unit().toLowerCase(Locale.ROOT)))quotes.add(e.quote());if(quotes.isEmpty())return null;String actual=String.join("；",quotes.stream().distinct().limit(5).toList());return "NEEDS_REVIEW".equals(status)?actual+"（材料冲突，需核对）":actual;}
    if("PROJECT_SCALE".equals(rule.type())||"TEAM_SIZE".equals(rule.type())){StructuredFact selected=null;java.math.BigDecimal maximum=null;for(var fact:facts.structuredFacts()){var measured=fact.measurement();if(!"project".equals(fact.kind())||!confirmed.contains(fact.factId())||measured==null||!fact.factId().equals(measured.projectId()))continue;java.math.BigDecimal value=null;if("TEAM_SIZE".equals(rule.type())&&measured.managedTeamSize()!=null)value=java.math.BigDecimal.valueOf(measured.managedTeamSize());if("PROJECT_SCALE".equals(rule.type())&&rule.values()!=null&&rule.values().contains(measured.metric())&&Objects.equals(rule.unit(),measured.unit()))value=measured.value();if(value!=null&&(maximum==null||value.compareTo(maximum)>0)){maximum=value;selected=fact;}}if(selected==null)return null;String unit="TEAM_SIZE".equals(rule.type())?"人":Objects.toString(selected.measurement().unit(),"");String actual=maximum.stripTrailingZeros().toPlainString()+unit;return "NEEDS_REVIEW".equals(status)?actual+"（材料冲突，需核对）":actual;}
    return "NEEDS_REVIEW".equals(status)?"材料冲突，需核对":null;
  }

  static HrMonthIntervalCalculator.DateRange range(DateValue date) {
    if (date == null || date.value() == null || date.precision() == null)
      throw new IllegalArgumentException("date required");
    return switch (date.precision()) {
      case "YEAR" -> {
        if (!date.value().matches("[0-9]{4}"))
          throw new IllegalArgumentException("year precision mismatch");
        int year = Integer.parseInt(date.value());
        yield new HrMonthIntervalCalculator.DateRange(
            YearMonth.of(year, 1), YearMonth.of(year, 12));
      }
      case "MONTH", "DAY" -> {
        YearMonth month =
            date.precision().equals("DAY")
                ? YearMonth.from(LocalDate.parse(date.value()))
                : YearMonth.parse(date.value());
        yield new HrMonthIntervalCalculator.DateRange(month, month);
      }
      default -> throw new IllegalArgumentException("unsupported precision");
    };
  }

  private static Set<String> confirmed(List<Field> fields) {
    Set<String> result = new HashSet<>();
    for (Field field : fields) if (field.status().equals("CONFIRMED")) result.add(field.id());
    return result;
  }
}

