package com.aiep.platformai.api.dto;

import java.util.List;
import java.util.Objects;

final class CustomerServiceDtoSupport {
    private CustomerServiceDtoSupport() {
    }

    static String requireText(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " 不能为空");
        }
        return value;
    }

    static String requireContract(String value, String expected) {
        if (!expected.equals(value)) {
            throw new IllegalArgumentException("contract_version 必须为 " + expected);
        }
        return value;
    }

    static <T> List<T> immutableList(List<T> values, String fieldName) {
        Objects.requireNonNull(values, fieldName + " 不能为空");
        return List.copyOf(values);
    }

    static int requireRange(int value, int minimum, int maximum, String fieldName) {
        if (value < minimum || value > maximum) {
            throw new IllegalArgumentException(fieldName + " 必须在 " + minimum + " 到 " + maximum + " 之间");
        }
        return value;
    }
}
