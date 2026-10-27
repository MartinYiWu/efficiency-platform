package com.aiep.aihub.application.customer;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class CustomerServiceHelpfulProgressTest {
    @Test void preservesOnlyApprovedAnswerProgress() {
        assertThat(CustomerServiceEventProjector.publicStageSummary("answer", "STARTED", "公司资料存在缺口，正在整理通用建议"))
                .isEqualTo("公司资料存在缺口，正在整理通用建议");
        assertThat(CustomerServiceEventProjector.publicStageSummary("answer", "STARTED", "正在整理已有公司依据与通用建议"))
                .isEqualTo("正在整理已有公司依据与通用建议");
        assertThat(CustomerServiceEventProjector.publicStageSummary("answer", "STARTED", "不可信自由文本"))
                .isEqualTo("正在撰写回答");
        assertThat(CustomerServiceEventProjector.publicStageSummary("retrieval", "STARTED", "公司资料存在缺口，正在整理通用建议"))
                .isEqualTo("正在查找公司资料");
    }
}
