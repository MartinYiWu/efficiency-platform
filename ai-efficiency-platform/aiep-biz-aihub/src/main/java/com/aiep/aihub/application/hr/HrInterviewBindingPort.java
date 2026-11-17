package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;

/** 平台已发布生成绑定版本；只读解析，不触发模型或续预算。 */
public interface HrInterviewBindingPort {
  record Binding(String promptVersion, String modelRouteVersion) {}

  Binding resolve(HrActor actor);
}
