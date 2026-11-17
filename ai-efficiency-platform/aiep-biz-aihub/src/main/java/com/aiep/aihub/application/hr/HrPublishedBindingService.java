package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrDictionaryContracts.Dictionary;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import org.springframework.stereotype.Service;

/** 发布门禁的词典部分；模型/Prompt必须由平台只读readiness另行核验。 */
@Service
public class HrPublishedBindingService {
  private final HrSettingsRepository repository;

  public HrPublishedBindingService(HrSettingsRepository repository) {
    this.repository = repository;
  }

  public long validateDictionary(HrActor actor, String department) {
    HrAccessPolicy.department(actor, department);
    if (!repository.exists(actor, "DICTIONARY", department)) throw missing();
    return repository
        .publicationHistory(
            actor, "DICTIONARY", department, Dictionary.class, "hr:position:publish", "POSITION")
        .stream()
        .filter(d -> "PUBLISHED".equals(d.status()))
        .mapToLong(Dictionary::version)
        .findFirst()
        .orElseThrow(HrPublishedBindingService::missing);
  }

  private static HrBusinessException missing() {
    return new HrBusinessException("HR_DICTIONARY_NOT_PUBLISHED", "请先发布组织词典版本", 409);
  }
}
