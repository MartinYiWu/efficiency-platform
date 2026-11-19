package com.aiep.aihub.memory;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

/** intent原frame刷新后，answer必须沿同一运行使用新授权。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryRefreshIntentHttpIntegrationTest {
    @Test void intentRefreshContinuesOriginalFrameIntoAnswer()throws Exception {
        MemoryRefreshHttpIntegrationTest.runRefreshScenario("intent");
    }
}
