package com.aiep.aihub.application.hr;

import java.util.List;

/** 招聘评分永久禁用的个人属性；职业中的系统稳定性不等于人员稳定性预测。 */
public final class HrProtectedAttributes {
  private HrProtectedAttributes() {}

  public static final List<String> FIELDS =
      List.of(
          "性别", "年龄", "出生日期", "婚姻状况", "生育状况", "民族", "籍贯", "户籍", "照片", "政治面貌", "健康状况", "宗教信仰", "血型",
          "星座", "身高", "体重");
  private static final List<String> ALIASES =
      List.of(
          "婚育", "婚姻", "生育", "出生", "生日", "宗教", "身份证", "银行卡", "社保号", "性取向", "残疾", "性格", "忠诚度", "离职风险",
          "候选人稳定性", "院校声望");
  private static final java.util.regex.Pattern ENGLISH =
      java.util.regex.Pattern.compile(
          "\\b(?:gender|sex|age|birth(?:date)?|marital|pregnan\\w*|ethnicity|race|religion|blood\\s*type|zodiac|height|weight|political\\s+affiliation|health\\s+status)\\b",
          java.util.regex.Pattern.CASE_INSENSITIVE);

  public static void validateRule(String... values) {
    for (var value : values)
      if (value != null
          && (FIELDS.stream().anyMatch(value::contains)
              || ALIASES.stream().anyMatch(value::contains)
              || ENGLISH.matcher(value).find()))
        throw new HrBusinessException("HR_PROTECTED_ATTRIBUTE_FORBIDDEN", "评分规则不能包含永久禁用的个人属性", 422);
  }
}
