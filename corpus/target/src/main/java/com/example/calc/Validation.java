package com.example.calc;

import java.util.Objects;

/** Input validation for calculator endpoints. */
public final class Validation {

    private static final long MAX_OPERAND = 1_000_000_000L;

    private Validation() {}

    public static long parseOperand(String name, String raw) {
        Objects.requireNonNull(name, "name");
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("missing operand: " + name);
        }
        final long value;
        try {
            value = Long.parseLong(raw.trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("operand " + name + " is not an integer: " + raw, ex);
        }
        if (value > MAX_OPERAND || value < -MAX_OPERAND) {
            throw new IllegalArgumentException(
                    "operand " + name + " out of range [" + -MAX_OPERAND + ", " + MAX_OPERAND + "]");
        }
        return value;
    }

    public static String requireNonEmpty(String name, String raw) {
        Objects.requireNonNull(name, "name");
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("missing field: " + name);
        }
        return raw;
    }
}
