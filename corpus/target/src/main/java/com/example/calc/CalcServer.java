package com.example.calc;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * Minimal HTTP front-end exposing /add /sub /mul /div and /eval. Used as a
 * realistic target for the bug-triage corpus and as a reference of what
 * "files_changed" entries in resolution exemplars point at.
 */
public final class CalcServer {

    private static final int DEFAULT_PORT = 8080;

    private CalcServer() {}

    public static void main(String[] args) throws IOException {
        final int port = args.length > 0 ? Integer.parseInt(args[0]) : DEFAULT_PORT;
        final HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/add", ex -> binaryOp(ex, "add"));
        server.createContext("/sub", ex -> binaryOp(ex, "sub"));
        server.createContext("/mul", ex -> binaryOp(ex, "mul"));
        server.createContext("/div", ex -> binaryOp(ex, "div"));
        server.createContext("/eval", CalcServer::evaluate);
        server.createContext("/healthz", ex -> respond(ex, 200, "ok"));
        server.start();
        System.out.println("calc-server listening on " + port);
    }

    private static void binaryOp(HttpExchange ex, String op) throws IOException {
        try {
            final Map<String, String> q = parseQuery(ex.getRequestURI().getRawQuery());
            final long a = Validation.parseOperand("a", q.get("a"));
            final long b = Validation.parseOperand("b", q.get("b"));
            final String body = switch (op) {
                case "add" -> Long.toString(Calculator.add(a, b));
                case "sub" -> Long.toString(Calculator.sub(a, b));
                case "mul" -> Long.toString(Calculator.mul(a, b));
                case "div" -> Double.toString(Calculator.div(a, b));
                default -> throw new IllegalArgumentException("unknown op " + op);
            };
            respond(ex, 200, body);
        } catch (IllegalArgumentException iae) {
            respond(ex, 400, iae.getMessage());
        } catch (ArithmeticException ae) {
            respond(ex, 422, ae.getMessage());
        }
    }

    private static void evaluate(HttpExchange ex) throws IOException {
        try {
            final Map<String, String> q = parseQuery(ex.getRequestURI().getRawQuery());
            final String expr = Validation.requireNonEmpty("expr", q.get("expr"));
            final double result = ExpressionParser.evaluate(expr);
            respond(ex, 200, Double.toString(result));
        } catch (IllegalArgumentException iae) {
            respond(ex, 400, iae.getMessage());
        } catch (ArithmeticException ae) {
            respond(ex, 422, ae.getMessage());
        }
    }

    static Map<String, String> parseQuery(String raw) {
        final Map<String, String> out = new HashMap<>();
        if (raw == null || raw.isEmpty()) {
            return out;
        }
        for (String part : raw.split("&")) {
            final int eq = part.indexOf('=');
            if (eq < 0) {
                out.put(part, "");
            } else {
                out.put(part.substring(0, eq), part.substring(eq + 1));
            }
        }
        return out;
    }

    private static void respond(HttpExchange ex, int status, String body) throws IOException {
        final byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(bytes);
        }
    }
}
