package com.example.calc;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {

    @BeforeEach
    void resetCounter() {
        Calculator.resetForTests();
    }

    @Test
    void addsTwoNumbers() {
        assertEquals(7L, Calculator.add(3L, 4L));
        assertEquals(1L, Calculator.invocations());
    }

    @Test
    void rejectsDivisionByZero() {
        assertThrows(ArithmeticException.class, () -> Calculator.div(1L, 0L));
    }

    @Test
    void evaluatesParenthesizedExpression() {
        assertEquals(14.0, ExpressionParser.evaluate("2 * (3 + 4)"));
    }

    @Test
    void rejectsBlankOperand() {
        assertThrows(IllegalArgumentException.class, () -> Validation.parseOperand("a", "  "));
    }
}
