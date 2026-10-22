package com.aiep.platformfile;

import static org.assertj.core.api.Assertions.assertThat;

import com.aiep.platformfile.config.CosFileProperties;
import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.TestConfiguration;

class CosFilePropertiesBindingTest {
    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(BindingConfiguration.class)
            .withPropertyValues(
                    "file.storage.tencent-cos.secret-id=test-secret-id",
                    "file.storage.tencent-cos.secret-key=test-secret-key",
                    "file.storage.tencent-cos.region=ap-test",
                    "file.storage.tencent-cos.bucket=test-bucket-10001",
                    "file.storage.tencent-cos.domain=https://test-bucket-10001.cos.ap-test.myqcloud.com",
                    "file.storage.tencent-cos.base-path=efficiency-platform",
                    "file.storage.tencent-cos.read-url-ttl=10m");

    @Test
    void bindsJavaOwnedCosConfiguration() {
        contextRunner.run(context -> {
            CosFileProperties properties = context.getBean(CosFileProperties.class);

            assertThat(properties.getSecretId()).isEqualTo("test-secret-id");
            assertThat(properties.getSecretKey()).isEqualTo("test-secret-key");
            assertThat(properties.getRegion()).isEqualTo("ap-test");
            assertThat(properties.getBucket()).isEqualTo("test-bucket-10001");
            assertThat(properties.getDomain())
                    .isEqualTo(URI.create("https://test-bucket-10001.cos.ap-test.myqcloud.com"));
            assertThat(properties.getBasePath()).isEqualTo("efficiency-platform");
            assertThat(properties.getReadUrlTtl()).isEqualTo(Duration.ofMinutes(10));
        });
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CosFileProperties.class)
    static class BindingConfiguration {
    }
}
