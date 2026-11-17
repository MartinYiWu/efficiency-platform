package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import com.aiep.aihub.application.hr.HrSensitiveJsonCodec;
import java.util.Base64;
import org.junit.jupiter.api.Test;

class HrSensitiveJsonCodecTest {
    @Test void encrypts_candidate_snapshots_and_authenticates_ciphertext() {
        HrSensitiveJsonCodec codec = new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32]));
        String value = "{\"name\":\"合成候选人\",\"phone\":\"synthetic\"}";
        String first = codec.seal(value); String second = codec.seal(value);
        assertNotEquals(first, second);
        assertFalse(first.contains("合成候选人"));
        assertEquals(value, codec.open(first));
        assertThrows(RuntimeException.class, () -> codec.open(first.substring(0, first.length() - 3) + "abc"));
    }
    @Test void missing_or_short_key_fails_before_saving_sensitive_values() {
        assertThrows(RuntimeException.class, () -> new HrSensitiveJsonCodec("").seal("private"));
        assertThrows(RuntimeException.class, () -> new HrSensitiveJsonCodec("not-a-valid-key").seal("private"));
    }
}
