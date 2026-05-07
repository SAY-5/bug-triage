package com.example.calc;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

/**
 * Tiny shunting-yard parser for infix arithmetic expressions over longs.
 * Supports + - * / and parenthesized sub-expressions. Whitespace is ignored.
 */
public final class ExpressionParser {

    private ExpressionParser() {}

    public static double evaluate(String expression) {
        Objects.requireNonNull(expression, "expression");
        if (expression.isBlank()) {
            throw new IllegalArgumentException("empty expression");
        }
        final List<String> tokens = tokenize(expression);
        final List<String> rpn = toRpn(tokens);
        return evalRpn(rpn);
    }

    private static List<String> tokenize(String expression) {
        final List<String> out = new ArrayList<>();
        final StringBuilder num = new StringBuilder();
        for (int i = 0; i < expression.length(); i++) {
            final char c = expression.charAt(i);
            if (Character.isWhitespace(c)) {
                flushNumber(num, out);
                continue;
            }
            if (Character.isDigit(c)) {
                num.append(c);
                continue;
            }
            if (c == '-' && num.isEmpty() && (out.isEmpty() || isOperator(out.get(out.size() - 1)) || "(".equals(out.get(out.size() - 1)))) {
                num.append(c);
                continue;
            }
            flushNumber(num, out);
            if (c == '+' || c == '-' || c == '*' || c == '/' || c == '(' || c == ')') {
                out.add(String.valueOf(c));
            } else {
                throw new IllegalArgumentException("unexpected character: " + c);
            }
        }
        flushNumber(num, out);
        return out;
    }

    private static void flushNumber(StringBuilder num, List<String> out) {
        if (num.isEmpty()) {
            return;
        }
        final String token = num.toString();
        if ("-".equals(token)) {
            throw new IllegalArgumentException("dangling minus sign");
        }
        out.add(token);
        num.setLength(0);
    }

    private static List<String> toRpn(List<String> tokens) {
        final List<String> output = new ArrayList<>();
        final Deque<String> ops = new ArrayDeque<>();
        for (String token : tokens) {
            if (isNumber(token)) {
                output.add(token);
            } else if ("(".equals(token)) {
                ops.push(token);
            } else if (")".equals(token)) {
                while (!ops.isEmpty() && !"(".equals(ops.peek())) {
                    output.add(ops.pop());
                }
                if (ops.isEmpty()) {
                    throw new IllegalArgumentException("unbalanced parentheses");
                }
                ops.pop();
            } else if (isOperator(token)) {
                while (!ops.isEmpty() && isOperator(ops.peek()) && precedence(ops.peek()) >= precedence(token)) {
                    output.add(ops.pop());
                }
                ops.push(token);
            } else {
                throw new IllegalArgumentException("unexpected token: " + token);
            }
        }
        while (!ops.isEmpty()) {
            final String top = ops.pop();
            if ("(".equals(top) || ")".equals(top)) {
                throw new IllegalArgumentException("unbalanced parentheses");
            }
            output.add(top);
        }
        return output;
    }

    private static double evalRpn(List<String> rpn) {
        final Deque<Double> stack = new ArrayDeque<>();
        for (String token : rpn) {
            if (isNumber(token)) {
                stack.push(Double.parseDouble(token));
            } else {
                if (stack.size() < 2) {
                    throw new IllegalArgumentException("malformed expression");
                }
                final double b = stack.pop();
                final double a = stack.pop();
                stack.push(applyOperator(a, b, token));
            }
        }
        if (stack.size() != 1) {
            throw new IllegalArgumentException("malformed expression");
        }
        return stack.pop();
    }

    private static double applyOperator(double a, double b, String op) {
        return switch (op) {
            case "+" -> a + b;
            case "-" -> a - b;
            case "*" -> a * b;
            case "/" -> {
                if (b == 0.0) {
                    throw new ArithmeticException("division by zero");
                }
                yield a / b;
            }
            default -> throw new IllegalArgumentException("unsupported operator: " + op);
        };
    }

    private static boolean isOperator(String token) {
        return "+".equals(token) || "-".equals(token) || "*".equals(token) || "/".equals(token);
    }

    private static int precedence(String token) {
        return switch (token) {
            case "+", "-" -> 1;
            case "*", "/" -> 2;
            default -> 0;
        };
    }

    private static boolean isNumber(String token) {
        if (token.isEmpty()) {
            return false;
        }
        int i = 0;
        if (token.charAt(0) == '-') {
            if (token.length() == 1) {
                return false;
            }
            i = 1;
        }
        for (; i < token.length(); i++) {
            if (!Character.isDigit(token.charAt(i))) {
                return false;
            }
        }
        return true;
    }
}
