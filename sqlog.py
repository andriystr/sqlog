import sys
import json
import shutil
import logging
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
from functools import partial
from html.parser import HTMLParser
from contextvars import ContextVar


class HeaderFormatParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._tag_stack = []
        self._format_strings = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {key: val for key, val in attrs}

        if tag in {"d", "delim"}:
            self._format_strings.append(
                {"type": "delimiter", "style": self._attrs_to_style(attrs_dict)}
            )
            return

        self._tag_stack.append({"tag": tag, "attrs": attrs_dict})

    def _attrs_to_style(self, attrs):
        style = {}

        if "color" in attrs:
            style["color"] = attrs["color"]
        if "bg" in attrs:
            style["background"] = attrs["bg"]
        if "background" in attrs:
            style["background"] = attrs["background"]

        return style

    def _style_from_tag(self, tag_name):
        if tag_name == "b":
            return "bold"
        if tag_name == "i":
            return "italic"
        if tag_name == "u":
            return "underline"
        if tag_name == "s":
            return "strike"
        if tag_name in {"pre", "code"}:
            return "code"

    def handle_data(self, data):
        if not self._tag_stack:
            self._format_strings.append({"type": "text", "text": data, "style": None})

        else:
            top_tag = self._tag_stack[-1]
            style = self._attrs_to_style(top_tag["attrs"])

            tag_style = self._style_from_tag(top_tag["tag"])
            if tag_style:
                style["format"] = tag_style

            self._format_strings.append(
                {"type": "text", "text": data, "style": style or None}
            )

    def handle_endtag(self, tag):
        if not self._tag_stack:
            return

        index = None
        for i, t in enumerate(self._tag_stack):
            if t["tag"] == tag:
                index = i

        if index is None:
            return

        self._tag_stack = self._tag_stack[:index]

    def parse_format_string(self, s: str):
        self.feed(s)

        format_strings = self._format_strings.copy()
        self._format_strings.clear()
        self._tag_stack.clear()
        self.reset()

        return format_strings


class SqSection:
    def __init__(self, handler, connection, parent):
        self._handler = handler
        self._conn = connection
        self._parent = parent
        self._header_parser = HeaderFormatParser()

        parent_id = parent.id if parent is not None else None
        self._level = parent.level + 1 if parent is not None else 1

        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO Sections(parent_id, level) VALUES(?, ?)",
                (parent_id, self._level),
            )
            self._section_id = cur.lastrowid

    def __repr__(self):
        parent_id = self._parent.id if self._parent is not None else None
        return f"{self.__class__.__name__}(id={self._section_id}, parent_id={parent_id}, level={self._level})"

    def __enter__(self):
        if self._parent is None:
            return

        self._prev_section = self._handler._get_current_section()
        self._handler._set_current_section(self)

        return self

    def __exit__(self, exc_type, exc_value, tb):
        if self._parent is None:
            return
        self._handler._set_current_section(self._prev_section)

    @property
    def id(self):
        return self._section_id

    @property
    def level(self):
        return self._level

    def add_header_str(self, s: str, html=True):
        if not html:
            with self._conn:
                cur = self._conn.cursor()
                cur.execute(
                    "INSERT INTO Headers(section_id, text, type) VALUES(?, ?, ?)",
                    (self._section_id, s.strip(), "text"),
                )
        else:
            formatted_strings = self._header_parser.parse_format_string(s)
            for fstr in formatted_strings:
                type = fstr["type"]
                text = fstr["text"].strip() if type == "text" else None
                style = fstr["style"] or None
                with self._conn:
                    cur = self._conn.cursor()
                    cur.execute(
                        "INSERT INTO Headers(section_id, text, type, style) VALUES(?, ?, ?, ?)",
                        (self._section_id, text, type, style and json.dumps(style)),
                    )

    def section(self, header: str = "", html=True):
        sec = SqSection(self._handler, self._conn, self)

        if header:
            sec.add_header_str(header, html)
        return sec

    def _add_log(self, record_id: int):
        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO Logs(section_id, record_id) VALUES(?, ?)",
                [self._section_id, record_id],
            )


_SQL_CREATE_TABLES = """

BEGIN;
        
        
CREATE TABLE IF NOT EXISTS Sections(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER,
        level INTEGER NOT NULL,
        FOREIGN KEY (parent_id) REFERENCES Sections(id)
);

        
CREATE TABLE IF NOT EXISTS Headers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id INTEGER,
        text TEXT,
        type TEXT,
        style JSON,
        FOREIGN KEY (section_id) REFERENCES Sections(id)
);


CREATE TABLE IF NOT EXISTS Logs(
        section_id INTEGER,
        record_id INTEGER,
        FOREIGN KEY (section_id) REFERENCES Sections(id),
        FOREIGN KEY (record_id) REFERENCES Records(id)
);

        
CREATE TABLE IF NOT EXISTS Records(
id INTEGER PRIMARY KEY AUTOINCREMENT,

created TEXT,
exc_info JSON,
file_name TEXT,
func_name TEXT,
level_name TEXT,
level_number INTEGER,
line_number INTEGER,
message TEXT,
module TEXT,
millisecond INTEGER,
name TEXT,
path_name TEXT,
process_id INTEGER,
process_name TEXT,
relative_created REAL,
stack_info TEXT,
thread_id INTEGER,
thread_name TEXT,
task_name TEXT
);

        
COMMIT;
        
"""


class SqFileHandler(logging.Handler):
    def __init__(
        self, filename: str, top_header: str = None, end_top_header: str = None
    ):
        super().__init__()
        self._start_datetime = datetime.now()
        top_header = top_header or "Start Logging at {datetime}"
        self._end_top_header = end_top_header or "<d>work time {worktime}"

        self._conn = sqlite3.connect(filename)
        with self._conn:
            cur = self._conn.cursor()
            cur.executescript(_SQL_CREATE_TABLES)

        self._top_section = SqSection(self, self._conn, None)
        start_logging_str = self._start_datetime.strftime("%Y-%m-%d %H:%M:%S,%f")
        self._top_section.add_header_str(top_header.format(datetime=start_logging_str))

        self._current_section = ContextVar("Current Section")
        self._current_section.set(self._top_section)

    def _get_current_section(self):
        return self._current_section.get()

    def _set_current_section(self, sec: SqSection):
        self._current_section.set(sec)

    def add_top_header_str(self, s: str):
        self._top_section.add_header_str(s)

    def _exc_info_to_json(self, exc_info):
        if exc_info is None:
            return None

        exc_type, exc_value, tb = exc_info

        tb_list = [tb]
        cur_tb = tb
        while cur_tb.tb_next is not None:
            cur_tb = cur_tb.tb_next
            tb_list.append(cur_tb)

        tb_dict_list = [self._traceback_to_dict(tb) for tb in tb_list]
        return json.dumps(
            {
                "exception": exc_type.__name__,
                "message": str(exc_value),
                "traceback": tb_dict_list,
            }
        )

    def _add_record(self, record):
        arguments = (
            datetime.fromtimestamp(record.created).strftime(
                "%Y-%m-%d %H:%M:%S,%f"
            ),  # created
            self._exc_info_to_json(record.exc_info),  # exc_info
            record.filename,  # file_name
            record.funcName,  # func_name
            record.levelname,  # level_name
            record.levelno,  # level_number
            record.lineno,  # line_number
            record.msg,  # message
            record.msecs,  # msecs
            record.module,  # module
            record.name,  # name
            record.pathname,  # path_name
            record.process,  # process_id
            record.processName,  # process_name
            record.relativeCreated,  # relative_created
            record.stack_info,  # stack_info
            record.thread,  # thread_id
            record.threadName,  # thread_name
            getattr(record, "taskName", None),  # task_name
        )

        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                """
            INSERT INTO Records(
                    created, exc_info, file_name, func_name, level_name,
                    level_number, line_number, message, module, millisecond,
                    name, path_name, process_id, process_name, relative_created,
                    stack_info, thread_id, thread_name, task_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                arguments,
            )

            return cur.lastrowid

    def emit(self, record):
        record_id = self._add_record(record)
        sec = self._current_section.get()
        sec._add_log(record_id)

        for arg in record.args:
            if not hasattr(arg, "_handler") or arg._handler is not self:
                continue

            if hasattr(arg, "_add_log") and hasattr(arg, "id") and arg.id != sec.id:
                arg._add_log(record_id)

    def section(self, header: str = "", html=True):
        cur_sec = self._current_section.get()
        return cur_sec.section(header, html)

    def close(self):
        worktime = datetime.now() - self._start_datetime
        self._top_section.add_header_str(self._end_top_header.format(worktime=worktime))

        self._conn.close()
        super().close()


def get_sections(connection, with_level=1):
    cur = connection.cursor()
    cur.execute(
        "SELECT id, parent_id, level FROM Sections WHERE level == ? ORDER BY id ASC",
        [with_level],
    )
    return cur.fetchall()


def get_child_sections(connection, with_parent_id):
    cur = connection.cursor()
    cur.execute(
        "SELECT id, parent_id, level FROM Sections WHERE parent_id == ? ORDER BY id ASC",
        [with_parent_id],
    )
    return cur.fetchall()


def get_headers(connection, by_section_id):
    cur = connection.cursor()
    cur.execute(
        "SELECT id, section_id, text, type, style FROM Headers WHERE section_id == ? ORDER BY id ASC",
        [by_section_id],
    )
    return [(*item[:4], item[4] and json.loads(item[4])) for item in cur.fetchall()]


def get_logs(connection, by_section_id):
    cur = connection.cursor()
    cur.execute(
        """
    SELECT
            id, created,
            exc_info, file_name, func_name, level_name,
            level_number, line_number, message, module, millisecond,
            name, path_name, process_id, process_name, relative_created,
            stack_info, thread_id, thread_name, task_name
    FROM Records WHERE id in (SELECT record_id FROM Logs WHERE section_id = ?) ORDER BY id ASC
    """,
        [by_section_id],
    )

    return [
        {
            "id": row[0],
            "section_id": by_section_id,
            "created": row[1],
            "exc_info": row[2],
            "file_name": row[3],
            "func_name": row[4],
            "level_name": row[5],
            "level_number": row[6],
            "line_number": row[7],
            "message": row[8],
            "module": row[9],
            "millisecond": row[10],
            "name": row[11],
            "path_name": row[12],
            "process_id": row[13],
            "process_name": row[14],
            "relative_created": row[15],
            "stack_info": row[16],
            "thread_id": row[17],
            "thread_name": row[18],
            "task_name": row[19],
        }
        for row in cur.fetchall()
    ]


def log_to_format_data(log: dict):
    created = datetime.strptime(log["created"], "%Y-%m-%d %H:%M:%S,%f")
    return {
        "asctime": log["created"],
        "created": created.timestamp(),
        "filename": log["file_name"],
        "funcName": log["func_name"],
        "levelname": log["level_name"],
        "levelno": log["level_number"],
        "lineno": log["line_number"],
        "message": log["message"],
        "module": log["module"],
        "msecs": log["millisecond"],
        "name": log["name"],
        "pathname": log["path_name"],
        "process": log["process_id"],
        "processName": log["process_name"],
        "relativeCreated": log["relative_created"],
        "thread": log["thread_id"],
        "threadName": log["thread_name"],
        "taskName": log["task_name"],
    }


def header_to_org_header(header):
    hid, sec_id, text, type, style = header

    if type == "delimiter":
        return "::"
    if style is None:
        return text
    if "format" not in style:
        return text

    if style["format"] == "bold":
        return f"*{text}*"
    if style["format"] == "italic":
        return f"/{text}/"
    if style["format"] == "underline":
        return f"_{text}_"
    if style["format"] == "code":
        return f"~{text}~"
    if style["format"] == "strike":
        return f"+{text}+"


def get_org_headers(connection, by_section_id):
    headers = get_headers(connection, by_section_id)
    return [header_to_org_header(header) for header in headers]


def write_org_section(connection, out_io, section: tuple, format, level):
    sec_id, parent_id, sec_level = section

    headers = get_org_headers(connection, by_section_id=sec_id)
    print("*" * level, "::", " ".join(filter(str.strip, headers)), file=out_io)

    logs = get_logs(connection, by_section_id=sec_id)
    if logs:
        print(file=out_io)
        for log in logs:
            fmt_log = log_to_format_data(log)
            print(format % fmt_log, file=out_io)
        print(file=out_io)

    sections = get_child_sections(connection, with_parent_id=sec_id)
    for sec in sections:
        write_org_section(connection, out_io, sec, format, level + 1)


_org_header = """# -*- coding: utf-8; mode: org; mode: auto-fill; fill-column: 75; comment-column: 50; -*-
# ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰
#+title: Logs
# ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰
:PROPERTIES:
#+TODO: ✔DEBUG ✔INFO ✔WARNING ✔ERROR ✔CRITICAL
#+STARTUP: indent fold
:END:

"""


def sqlog_to_org(
    connection,
    out_io,
    format="- %(levelname)s :: %(name)s :: %(message)s",
    start_level=1,
):
    sections = get_sections(connection)
    if not sections:
        return "No Sections with level 1"

    print(_org_header, file=out_io)

    for sec in sections:
        write_org_section(connection, out_io, sec, format, start_level)


def get_css_style(header_style):
    if not header_style:
        return ""
    styles = []

    bg_value = header_style.get("background", None)
    bg_css = bg_value and f"background: {bg_value}"
    if bg_css:
        styles.append(bg_css)

    color_value = header_style.get("color", None)
    color_css = color_value and f"color: {color_value}"
    if color_css:
        styles.append(color_css)

    return "; ".join(styles) if styles else ""


def header_to_html_header(header):
    hid, sec_id, text, type, style = header

    css_style = get_css_style(style)
    style_str = css_style and f' style="{css_style}"'

    if type == "delimiter":
        return f'<span class="delimiter"{style_str}>|</span>'
    if style is None:
        return text
    if "format" not in style:
        return f"<span{style_str}>{text}</span>" if style_str else text

    if style["format"] == "bold":
        return f"<b{style_str}>{text}</b>"
    if style["format"] == "italic":
        return f"<i{style_str}>{text}</i>"
    if style["format"] == "underline":
        return f"<u{style_str}>{text}</u>"
    if style["format"] == "code":
        return f"<code{style_str}><pre>{text}</pre></code>"
    if style["format"] == "strike":
        return f"<s{style_str}>{text}</s>"


def get_html_headers(connection, by_section_id):
    headers = get_headers(connection, by_section_id)
    return [header_to_html_header(header) for header in headers]


def write_html_section(connection, out_io, section: tuple, format):
    sec_id, parent_id, sec_level = section

    headers = get_html_headers(connection, by_section_id=sec_id)
    print("<details>", file=out_io)
    print(
        "<summary>",
        " ".join(filter(str.strip, headers)),
        "</summary>",
        sep="",
        file=out_io,
    )

    logs = get_logs(connection, by_section_id=sec_id)
    if logs:
        for log in logs:
            fmt_log = log_to_format_data(log)
            print("<ul>", file=out_io)
            print("<li>", format % fmt_log, "</li>", sep="", file=out_io)
            print("</ul>", file=out_io)

    sections = get_child_sections(connection, with_parent_id=sec_id)
    for sec in sections:
        write_html_section(connection, out_io, sec, format)

    print("</details>", file=out_io)


_html_header = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Logs</title>
    <style>
        * {
            font-size: 25px;
            font-family: Helvetica;
        }

        details details {
            margin-left: 15px;
        }

        details summary {
            font-size: 1.2em;
        }

        .delimiter {
            margin: 0px 8px;
            padding: 6px;
            font-weight: bold;
        }
    </style>
</head>
<body>
"""

_default_format = '<b>%(levelname)s</b> <span class="delimiter">|</span> %(name)s <span class="delimiter">|</span> %(message)s'


def sqlog_to_html(connection, out_io, format=_default_format):
    sections = get_sections(connection)
    if not sections:
        return "No Sections with level 1"

    print(_html_header, file=out_io)

    for sec in sections:
        write_html_section(connection, out_io, sec, format)

    print("</body>\n</html>", file=out_io)


def get_convert_func(args):
    if args.format == "org":
        return sqlog_to_org
    if args.format == "html":
        return sqlog_to_html

    fail_text = 'Error: can\'t detect output format\nChoose format "org" or "html"'

    if not args.output:
        print(fail_text)
        sys.exit(126)

    output = Path(args.output)
    if output.suffix == ".org":
        return sqlog_to_org
    if output.suffix in {".html", ".htm", ".xhtml"}:
        return sqlog_to_html

    print(fail_text)
    sys.exit(126)


def main():
    help_width = shutil.get_terminal_size().columns - 2
    arg_parser = argparse.ArgumentParser(
        "sqlog",
        description="conver .sqlog file",
        formatter_class=partial(argparse.HelpFormatter, max_help_position=help_width),
    )

    arg_parser.add_argument("logfile", metavar="path", help="input file (.sqlog file)")
    arg_parser.add_argument(
        "-f",
        "--format",
        choices=["org", "html"],
        metavar="string",
        help="output file format (org or html)",
    )
    arg_parser.add_argument("-o", "--output", metavar="path", help="output file")
    arg_parser.add_argument(
        "-s",
        "--start_level",
        metavar="int",
        type=int,
        help="start level (for org-mode)",
    )
    arg_parser.add_argument(
        "-l",
        "--log_format",
        metavar="string",
        help="format logs (as in logging.Formatter)",
    )
    args = arg_parser.parse_args()

    convert_func = get_convert_func(args)

    kwargs = {}
    if convert_func is sqlog_to_org and args.start_level:
        kwargs["start_level"] = args.start_level
    if args.log_format:
        kwargs["format"] = args.log_format

    logfile = Path(args.logfile)
    if not logfile.is_file():
        print(f'Error: No such file "{logfile}"')
        sys.exit(126)

    try:
        if not args.output:
            with sqlite3.connect(logfile) as conn:
                res = convert_func(conn, sys.stdout, **kwargs)

        else:
            output = Path(args.output)
            outdir = output.parent
            if str(outdir) == ".":
                outdir = outdir.resolve()
            if not outdir.is_dir():
                print(f"Error: no such directory {outdir}")
                sys.exit(126)

            with output.open("w", encoding="utf-8") as io, sqlite3.connect(
                logfile
            ) as conn:
                res = convert_func(conn, io, **kwargs)

    except OSError as err:
        print(f"{err.__class__.__name__}:", err)
        sys.exit(126)

    if res:
        print(res)


if __name__ == "__main__":
    main()
