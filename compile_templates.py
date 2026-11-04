"""Compile every Jinja template and report syntax errors."""

import os

from jinja2 import TemplateSyntaxError

from shalom import create_app


def main():
    app = create_app()
    root = os.path.join(app.root_path, "templates")
    failures = 0
    with app.app_context():
        for base, _, files in os.walk(root):
            for name in sorted(files):
                if not name.endswith(".html"):
                    continue
                rel = os.path.relpath(os.path.join(base, name), root).replace("\\", "/")
                try:
                    app.jinja_env.get_template(rel)
                except TemplateSyntaxError as exc:
                    failures += 1
                    print(f"{rel}:{exc.lineno}: {exc.message}")
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    print(f"{rel}: {type(exc).__name__}: {exc}")
    print("TEMPLATE FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
