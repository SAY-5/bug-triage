package com.example.calc;

import java.util.concurrent.atomic.AtomicLong;

/**
 * Core arithmetic. Each operation returns a long; division returns a double.
 * The class also keeps a process-wide invocation counter so the server can
 * report how many requests it has handled.
 */
public final class Calculator {

    private static final AtomicLong INVOCATIONS = new AtomicLong();

    private Calculator() {}

    public static long add(long a, long b) {
        INVOCATIONS.incrementAndGet();
        return Math.addExact(a, b);
    }

    public static long sub(long a, long b) {
        INVOCATIONS.incrementAndGet();
        return Math.subtractExact(a, b);
    }

    public static long mul(long a, long b) {
        INVOCATIONS.incrementAndGet();
        return Math.multiplyExact(a, b);
    }

    public static double div(long a, long b) {
        INVOCATIONS.incrementAndGet();
        if (b == 0L) {
            throw new ArithmeticException("division by zero");
        }
        return (double) a / (double) b;
    }

    public static long invocations() {
        return INVOCATIONS.get();
    }

    static void resetForTests() {
        INVOCATIONS.set(0L);
    }
}
