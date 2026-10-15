package com.aiep.aihub.application.operation;

import org.springframework.web.util.HtmlUtils;

final class SafeMarkdownRenderer {
    private SafeMarkdownRenderer() {
    }

    static String render(String markdown) {
        StringBuilder html = new StringBuilder();
        boolean listOpen = false;
        for (String rawLine : markdown.replace("\r\n", "\n").split("\n", -1)) {
            String line = rawLine.stripTrailing();
            boolean listLine = line.startsWith("- ") || line.startsWith("* ");
            if (!listLine && listOpen) {
                html.append("</ul>");
                listOpen = false;
            }
            if (line.isBlank()) {
                continue;
            }
            if (line.startsWith("### ")) {
                html.append("<h3>").append(escape(line.substring(4))).append("</h3>");
            } else if (line.startsWith("## ")) {
                html.append("<h2>").append(escape(line.substring(3))).append("</h2>");
            } else if (line.startsWith("# ")) {
                html.append("<h1>").append(escape(line.substring(2))).append("</h1>");
            } else if (listLine) {
                if (!listOpen) {
                    html.append("<ul>");
                    listOpen = true;
                }
                html.append("<li>").append(escape(line.substring(2))).append("</li>");
            } else {
                html.append("<p>").append(escape(line)).append("</p>");
            }
        }
        if (listOpen) {
            html.append("</ul>");
        }
        return html.toString();
    }

    private static String escape(String value) {
        return HtmlUtils.htmlEscape(value);
    }
}
