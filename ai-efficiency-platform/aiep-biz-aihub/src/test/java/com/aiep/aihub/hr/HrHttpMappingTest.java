package com.aiep.aihub.hr;

import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.core.type.filter.AnnotationTypeFilter;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

class HrHttpMappingTest {
  @Test
  void all_hr_controllers_register_without_ambiguous_http_routes() throws Exception {
    var scanner = new ClassPathScanningCandidateComponentProvider(false);
    scanner.addIncludeFilter(new AnnotationTypeFilter(RestController.class));
    var registry = new RequestMappingHandlerMapping();
    for (var definition : scanner.findCandidateComponents("com.aiep.aihub.web.hr")) {
      Class<?> type = Class.forName(definition.getBeanClassName());
      Object controller = mock(type);
      var base = AnnotatedElementUtils.findMergedAnnotation(type, RequestMapping.class);
      String prefix = base == null ? "" : base.value()[0];
      for (var method : type.getDeclaredMethods()) {
        var route = AnnotatedElementUtils.findMergedAnnotation(method, RequestMapping.class);
        if (route == null) continue;
        var paths =
            java.util.Arrays.stream(route.value().length == 0 ? new String[] {""} : route.value())
                .map(p -> prefix + p)
                .toArray(String[]::new);
        registry.registerMapping(
            RequestMappingInfo.paths(paths)
                .methods(route.method())
                .params(route.params())
                .consumes(route.consumes())
                .produces(route.produces())
                .build(),
            controller,
            method);
      }
    }
  }
}
