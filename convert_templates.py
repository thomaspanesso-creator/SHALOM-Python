"""One-off Thymeleaf -> Jinja2 converter for the SHALOM templates.

It is intentionally tailored to the expression/attribute subset used by the
original Spring Boot templates. Anything it cannot translate safely is left
alone (and reported) so it can be fixed by hand.
"""

from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shalom", "templates")

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

# Python attribute names are snake_case.
NAME_MAP = {
    "productName": "product_name",
    "minStock": "min_stock",
    "stockAfter": "stock_after",
    "stockBefore": "stock_before",
    "createdAt": "created_at",
    "lastName": "last_name",
    "availableRewards": "available_rewards",
    "photoUrl": "photo_url",
}

TIME_TOKENS = ("HH", "H", "hh", "h", "mm", "m", "ss", "a")


class Scanner(HTMLParser):
    def __init__(self, src: str):
        super().__init__(convert_charrefs=False)
        self.src = src
        self.line_starts = [0]
        for line in src.splitlines(keepends=True):
            self.line_starts.append(self.line_starts[-1] + len(line))
        self.nodes = []
        self.stack = []

    def _abs(self):
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def _start(self, tag, attrs, selfclosing):
        start = self._abs()
        raw = self.get_starttag_text()
        node = {
            "tag": tag,
            "start": start,
            "tag_end": start + len(raw),
            "raw": raw,
            "attrs": dict(attrs),
            "void": tag in VOID or selfclosing,
            "inner_start": start + len(raw),
            "inner_end": start + len(raw),
            "end": start + len(raw),
            "closed": False,
        }
        self.nodes.append(node)
        if node["void"]:
            node["closed"] = True
        else:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                while len(self.stack) > index:
                    node = self.stack.pop()
                    if node["tag"] == tag:
                        node["inner_end"] = self._abs()
                        node["end_start"] = self._abs()
                        node["end"] = self._abs() + len(tag) + 3
                        node["closed"] = True
                        break
                return


def _split_top(text: str, separator: str):
    """Split on a separator that is not inside quotes or parentheses."""
    parts = []
    depth = 0
    quote = None
    current = []
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            current.append(ch)
            if ch == quote and not (quote == "'" and i + 1 < len(text) and text[i + 1] == "'"):
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if depth == 0 and text.startswith(separator, i):
            parts.append("".join(current))
            current = []
            i += len(separator)
            continue
        current.append(ch)
        i += 1
    parts.append("".join(current))
    return parts


def _find_top(text: str, needle: str):
    depth = 0
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(needle, i):
            return i
        i += 1
    return -1


def _replace_calls(text: str, name: str, render) -> str:
    """Replace name(arg, arg) calls (balanced parentheses) through render(args)."""
    marker = name + "("
    start = 0
    while True:
        index = text.find(marker, start)
        if index == -1:
            return text
        depth = 0
        quote = None
        end = -1
        i = index + len(marker)
        while i < len(text):
            ch = text[i]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    end = i
                    break
                depth -= 1
            i += 1
        if end == -1:
            return text
        args = _split_top(text[index + len(marker):end], ",")
        replacement = render([a.strip() for a in args])
        text = text[:index] + replacement + text[end + 1:]
        start = index + len(replacement)


def _question_index(text: str):
    quote = None
    for index, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "?" and not text.startswith("?:", index) and not text.startswith("??", index):
            return index
    return None


def _convert_ternaries(text: str) -> str:
    """Convert Thymeleaf `cond ? a : b` (including nested/parenthesised ones)."""
    while True:
        qi = _question_index(text)
        if qi is None:
            return text

        # Start of the condition segment.
        depth = 0
        start = 0
        for k in range(qi - 1, -1, -1):
            ch = text[k]
            if ch == ")":
                depth += 1
            elif ch == "(":
                if depth == 0:
                    start = k + 1
                    break
                depth -= 1
            elif depth == 0 and ch in ",+":
                start = k + 1
                break

        # Matching colon (skip nested ternaries at the same depth).
        depth = 0
        quote = None
        pending = 0
        colon = -1
        end = len(text)
        for k in range(qi + 1, len(text)):
            ch = text[k]
            if quote:
                if ch == quote:
                    quote = None
                continue
            if ch in "'\"":
                quote = ch
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    end = k
                    break
                depth -= 1
            elif ch == "?" and depth == 0:
                pending += 1
            elif ch == ":" and depth == 0:
                if pending:
                    pending -= 1
                else:
                    colon = k
                    break
        if colon == -1:
            return text

        # End of the false branch.
        depth = 0
        quote = None
        for k in range(colon + 1, len(text)):
            ch = text[k]
            if quote:
                if ch == quote:
                    quote = None
                continue
            if ch in "'\"":
                quote = ch
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    end = k
                    break
                depth -= 1
            elif depth == 0 and ch == ",":
                end = k
                break

        condition = _convert_ternaries(text[start:qi].strip())
        when_true = _convert_ternaries(text[qi + 1:colon].strip())
        when_false = _convert_ternaries(text[colon + 1:end].strip())
        replacement = f"(({when_true}) if ({condition}) else ({when_false}))"
        text = text[:start] + replacement + text[end:]


def _pattern_literal(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1]
    return raw.replace("''", "'")


def _translate_text(text: str) -> str:
    """Translate a Thymeleaf expression body into Jinja2."""
    # Built-in objects ------------------------------------------------
    text = text.replace("#temporals.createNow()", "now")
    text = text.replace("#authentication.name", "current_user.email")

    text = _replace_calls(text, "#temporals.format", lambda a: (
        f"({a[0]}|temporal({_pattern_literal(a[1])!r}))" if len(a) >= 2 else a[0]
    ))
    text = _replace_calls(text, "#numbers.formatDecimal", lambda a: f"(({a[0]})|number)")
    text = _replace_calls(text, "#numbers.sequence", lambda a: (
        f"range({a[0]}, {int(a[1]) + 1})" if len(a) >= 2 and a[1].lstrip("-").isdigit() else a[0]
    ))
    text = _replace_calls(text, "#lists.size", lambda a: f"(({a[0]})|length)")
    text = _replace_calls(text, "#strings.substring", lambda a: (
        f"(({a[0]}) or '')[{a[1]}:{a[2]}]" if len(a) >= 3 else a[0]
    ))
    text = _replace_calls(text, "#strings.toUpperCase", lambda a: f"(({a[0]}) or '')|upper")
    text = _replace_calls(text, "#strings.capitalize", lambda a: f"(({a[0]}) or '')|capitalize")
    text = _replace_calls(text, "#strings.equalsIgnoreCase", lambda a: (
        f"((({a[0]}) or '')|lower == {a[1]})" if len(a) >= 2 else a[0]
    ))

    # Emptiness helpers (negated forms first so they collapse cleanly).
    text = re.sub(r"(?:not\s+|!\s*)#lists\.isEmpty\(([^()]*)\)", r"(\1)", text)
    text = re.sub(r"(?:not\s+|!\s*)#strings\.isEmpty\(([^()]*)\)", r"(\1)", text)
    text = re.sub(r"#lists\.isEmpty\(([^()]*)\)", r"(not \1)", text)
    text = re.sub(r"#strings\.isEmpty\(([^()]*)\)", r"(not \1)", text)

    text = re.sub(r"#maps\.isEmpty\(([^()]*)\)", r"(not \1)", text)

    # Loop status variables.
    text = re.sub(r"\bst\.index\b", "loop.index0", text)
    text = re.sub(r"\bst\.count\b", "loop.index", text)
    text = re.sub(r"\bst\.(first|last|even|odd)\b", r"loop.\1", text)

    # Java -> Python literals / keywords.
    text = re.sub(r"\.name\(\)", "", text)
    text = re.sub(r"\bnull\b", "none", text)
    text = re.sub(r"!\s*(?=[A-Za-z_#(])", "not ", text)

    # Elvis operator.
    while True:
        index = _find_top(text, "?:")
        if index == -1:
            break
        left = text[:index].strip()
        right = text[index + 2:].strip()
        text = f"({left} or {right})"

    text = _convert_ternaries(text)

    # Numbers concatenated with strings need an explicit cast.
    text = re.sub(r"(\b[A-Za-z_][\w.\[\]]*)\s*\+\s*(?=')", r"\1|string + ", text)
    text = re.sub(r"\)\s*\+\s*(?=')", ")|string + ", text)

    # Snake-case the model attributes.
    def rename(match):
        word = match.group(0)
        return NAME_MAP.get(word, word)

    if NAME_MAP:
        pattern = r"\b(" + "|".join(re.escape(k) for k in NAME_MAP) + r")\b"
        text = re.sub(pattern, rename, text)

    return text.strip()


def translate(expr: str) -> str:
    """Translate a complete Thymeleaf attribute value into a Jinja expression."""
    expr = expr.strip()

    # |literal ${x} literal|
    if expr.startswith("|") and expr.endswith("|"):
        body = expr[1:-1]
        return _convert_ternaries(_translate_interpolated(body))

    return _convert_ternaries(_translate_interpolated(expr))


def _translate_interpolated(expr: str) -> str:
    out = []
    i = 0
    while i < len(expr):
        if expr.startswith("${", i) or expr.startswith("*{", i):
            depth = 0
            j = i + 1
            while j < len(expr):
                if expr[j] == "{":
                    depth += 1
                elif expr[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            body = expr[i + 2:j]
            out.append("(" + _translate_text(body) + ")")
            i = j + 1
            continue
        out.append(expr[i])
        i += 1
    return "".join(out)


def jinja_expr(expr: str) -> str:
    value = translate(expr)
    # Strip redundant outer parentheses for readability.
    while value.startswith("(") and value.endswith(")") and _balanced(value[1:-1]):
        value = value[1:-1].strip()
    return value


def _balanced(text: str) -> bool:
    depth = 0
    quote = None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def convert_at(inner: str) -> str:
    """Translate an @{...} link into a Jinja string expression."""
    inner = inner.strip()
    if not inner.startswith("/"):
        return repr(inner)
    path = inner
    args = {}
    if "(" in inner:
        path, rest = inner.split("(", 1)
        rest = rest.rstrip(")")
        for chunk in _split_top(rest, ","):
            if "=" in chunk:
                key, value = chunk.split("=", 1)
                args[key.strip()] = value.strip()

    used = set(re.findall(r"\{([^}]+)\}", path))
    extras = [(key, value) for key, value in args.items() if key not in used]

    pieces = re.split(r"(\{[^}]+\})", path)
    parts = []
    for piece in pieces:
        if not piece:
            continue
        if piece.startswith("{") and piece.endswith("}") and piece[1:-1] in args:
            parts.append("(" + jinja_expr(args[piece[1:-1]]) + ")")
        else:
            parts.append(repr(piece))

    if extras:
        query = "?" + "&".join(f"{key}=" for key, _ in extras)
        parts.append(repr(query))
        for index, (key, value) in enumerate(extras):
            parts.append("(" + jinja_expr(value) + ")")
            if index < len(extras) - 1:
                parts.append("'&" + extras[index + 1][0] + "='")

    if len(parts) == 1 and parts[0].startswith(("'", '"')):
        return parts[0]
    return " ~ ".join(parts)


def _link_expr(expr: str) -> str:
    expr = expr.strip()
    if expr.startswith("@{") and expr.endswith("}"):
        return convert_at(expr[2:-1])
    if expr.startswith("${") and expr.endswith("}"):
        return jinja_expr(expr)
    return repr(expr)


def _whole_interpolation(expr: str) -> bool:
    if not (expr.startswith("${") or expr.startswith("*{")):
        return False
    depth = 0
    for k in range(1, len(expr)):
        if expr[k] == "{":
            depth += 1
        elif expr[k] == "}":
            depth -= 1
            if depth == 0:
                return k == len(expr) - 1
    return False


def link_attr(expr: str) -> str:
    """Return the literal value for href/src/action attributes."""
    expr = expr.strip()
    if _whole_interpolation(expr):
        return "{{ " + jinja_expr(expr) + " }}"
    if "@{" in expr:
        index = _question_index(expr)
        if index is not None:
            depth = 0
            quote = None
            i = index + 1
            colon = -1
            while i < len(expr):
                ch = expr[i]
                if quote:
                    if ch == quote:
                        quote = None
                elif ch in "'\"":
                    quote = ch
                elif ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth -= 1
                elif ch == ":" and depth == 0:
                    colon = i
                    break
                i += 1
            condition = jinja_expr(expr[:index])
            when_true = _link_expr(expr[index + 1:colon])
            when_false = _link_expr(expr[colon + 1:])
            return "{{ (" + when_true + ") if (" + condition + ") else (" + when_false + ") }}"
        return "{{ " + _link_expr(expr) + " }}"
    return expr


def attr_insertions(node, raw_start: str, directives: dict):
    """Return the rewritten start tag and the list of Jinja insertions in the tag."""
    th = {}
    for name, value in re.findall(r'\s+th:([A-Za-z-]+)="([^"]*)"', raw_start):
        th[name] = value

    new_raw = raw_start
    for name in th:
        new_raw = re.sub(r'\s+th:' + re.escape(name) + r'="[^"]*"', "", new_raw)

    if "href" in th:
        new_raw = re.sub(r'\shref="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'href="{link_attr(th["href"]).replace(chr(34), "&quot;")}"')
    if "src" in th:
        new_raw = re.sub(r'\ssrc="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'src="{link_attr(th["src"]).replace(chr(34), "&quot;")}"')
    if "action" in th:
        new_raw = re.sub(r'\saction="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'action="{link_attr(th["action"]).replace(chr(34), "&quot;")}"')
    if "value" in th:
        value = jinja_expr(th["value"]).replace('"', "&quot;")
        new_raw = re.sub(r'\svalue="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'value="{{{{ {value} }}}}"')
    if "alt" in th:
        value = jinja_expr(th["alt"]).replace('"', "&quot;")
        new_raw = re.sub(r'\salt="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'alt="{{{{ {value} }}}}"')
    if "style" in th:
        value = jinja_expr(th["style"]).replace('"', "&quot;")
        new_raw = re.sub(r'\sstyle="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'style="{{{{ {value} }}}}"')
    if "classappend" in th:
        value = jinja_expr(th["classappend"]).replace('"', "&quot;")
        if re.search(r'\sclass="[^"]*"', new_raw):
            new_raw = re.sub(r'(\sclass="[^"]*)"', r'\1 {{ ' + value.replace("\\", "\\\\") + r' }}"', new_raw, count=1)
        else:
            new_raw = _add_attr(new_raw, f'class="{{{{ {value} }}}}"')
    if "class" in th and "classappend" not in th:
        value = jinja_expr(th["class"]).replace('"', "&quot;")
        new_raw = re.sub(r'\sclass="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'class="{value}"')

    if "selected" in th:
        value = jinja_expr(th["selected"])
        new_raw = _add_attr(new_raw, "{{ 'selected' if " + value + " else '' }}")
    if "checked" in th:
        value = jinja_expr(th["checked"])
        new_raw = _add_attr(new_raw, "{{ 'checked' if " + value + " else '' }}")
    if "disabled" in th:
        value = jinja_expr(th["disabled"])
        new_raw = _add_attr(new_raw, "{{ 'disabled' if " + value + " else '' }}")
    for extra in re.findall(r'\sth:(data-[A-Za-z-]+)="([^"]*)"', raw_start):
        new_raw = re.sub(r'\s+th:' + re.escape(extra[0]) + r'="[^"]*"', "", new_raw)
        new_raw = _add_attr(new_raw, f'{extra[0]}="{{{{ {jinja_expr(extra[1])} }}}}"')

    if "attr" in th:
        body = th["attr"].strip()
        for pair in re.findall(r"([A-Za-z-]+)\s*=\s*(\$\{[^}]*\})", body):
            new_raw = _add_attr(new_raw, f'{pair[0]}="{{{{ {jinja_expr(pair[1])} }}}}"')

    # th:field style attributes that we could not translate are reported later.
    return new_raw, th


def _add_attr(raw_start: str, text: str) -> str:
    stripped = raw_start.rstrip()
    if stripped.endswith("/>"):
        stripped = stripped[:-2].rstrip()
    elif stripped.endswith(">"):
        stripped = stripped[:-1].rstrip()
    return stripped + " " + text + ">"


RE_INCLUDE = re.compile(r'th:replace="~\{([^}]*)\}"')


def include_for(spec: str) -> str:
    spec = spec.strip()
    fragment = ""
    if "::" in spec:
        spec, fragment = spec.split("::", 1)
        spec = spec.strip()
        fragment = fragment.strip()
    path = spec.strip()
    if not path.endswith(".html"):
        path += ".html"
    if "clientNavbar" in fragment:
        arg = re.search(r"\(\s*'([^']*)'\s*\)", fragment)
        active = arg.group(1) if arg else ""
        return "{% with active = '" + active + "' %}{% include '" + path + "' %}{% endwith %}"
    return "{% include '" + path + "' %}"


def convert_source(src: str):
    scanner = Scanner(src)
    scanner.feed(src)
    scanner.close()
    scanner.stack.clear()

    replacements = []  # (start, end, text)
    insertions = []    # (pos, order, text)

    # --- th:replace ---------------------------------------------------
    skip_nodes = set()
    for node in scanner.nodes:
        match = RE_INCLUDE.search(node["raw"])
        if not match:
            continue
        replacements.append((node["start"], node["end"], include_for(match.group(1))))
        # everything inside this node is irrelevant
        for other in scanner.nodes:
            if other is not node and node["start"] <= other["start"] < node["end"]:
                skip_nodes.add(id(other))

    for node in scanner.nodes:
        if id(node) in skip_nodes:
            continue
        if not node["closed"]:
            continue
        raw = node["raw"]
        th = dict(re.findall(r'\s+th:([A-Za-z-]+)="([^"]*)"', raw))
        if not th:
            continue

        opens = []
        closes = []

        if "each" in th:
            match = re.match(r"\s*([A-Za-z0-9_, ]+?)\s*:\s*(.+?)\s*$", th["each"], re.S)
            if match:
                variables = [v.strip() for v in match.group(1).split(",")]
                iterable = jinja_expr(match.group(2))
                loop_var = variables[0]
                opens.append("{% for " + loop_var + " in " + iterable + " %}")
                closes.insert(0, "{% endfor %}")
        if "if" in th:
            opens.append("{% if " + jinja_expr(th["if"]) + " %}")
            closes.append("{% endif %}")
        if "unless" in th:
            opens.append("{% if not (" + jinja_expr(th["unless"]) + ") %}")
            closes.append("{% endif %}")

        if opens:
            insertions.append((node["start"], 0, "".join(opens)))
        if closes:
            insertions.append((node["end"], 1, "".join(reversed(closes))))

        if "text" in th or "utext" in th:
            value = jinja_expr(th["text"] if "text" in th else th["utext"])
            suffix = "|safe" if "utext" in th else ""
            replacements.append((node["inner_start"], node["inner_end"], "{{ " + value + suffix + " }}"))

        if node["tag"] == "th:block":
            replacements.append((node["start"], node["tag_end"], ""))
            if node.get("end_start") is not None:
                replacements.append((node["end_start"], node["end"], ""))
            continue

        new_raw, th = attr_insertions(node, raw, th)
        if new_raw != raw:
            replacements.append((node["start"], node["tag_end"], new_raw))

    # Ensure replacements do not overlap; drop the smaller ones when they do.
    replacements.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    cleaned = []
    last_end = -1
    for start, end, text in replacements:
        if start < last_end:
            continue
        cleaned.append((start, end, text))
        last_end = end

    events = [(start, end, text, 0) for start, end, text in cleaned]
    for pos, order, text in insertions:
        events.append((pos, pos, text, -1 if order == 0 else 1))
    events.sort(key=lambda item: (item[0], item[3]))

    out = []
    cursor = 0
    for start, end, text, _kind in events:
        if start < cursor:
            continue
        out.append(src[cursor:start])
        out.append(text)
        cursor = end
    out.append(src[cursor:])
    return "".join(out)


TARGETS = [
    "welcome.html",
    "appointments/calendar.html",
    "appointments/create.html",
    "appointments/edit.html",
    "appointments/index.html",
    "cart/index.html",
    "client/dashboard.html",
    "inventory/index.html",
    "inventory/movements.html",
    "loyalty/index.html",
    "loyalty/show.html",
    "profile/edit.html",
    "reportes/citas.html",
    "reportes/especialistas.html",
    "reportes/ingresos.html",
    "reportes/inventario-bajo.html",
    "reportes/servicios.html",
    "services/index.html",
    "specialists/index.html",
    "store/index.html",
    "users/index.html",
    "dashboard.html",
]


def main():
    targets = sys.argv[1:] or TARGETS
    for rel in targets:
        path = os.path.normpath(os.path.join(BASE, rel))
        with open(path, encoding="utf-8") as handle:
            src = handle.read()
        if "th:" not in src:
            print("skip", rel)
            continue
        result = convert_source(src)
        # Remove the Thymeleaf namespace declaration.
        result = result.replace(' xmlns:th="http://www.thymeleaf.org"', "")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(result)
        remaining = len(re.findall(r"\bth:", result))
        print(f"{rel}: converted, {remaining} th: remaining")


if __name__ == "__main__":
    main()
