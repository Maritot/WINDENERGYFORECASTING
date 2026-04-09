"""Push the generated project report into a shared Google Doc."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO_ROOT / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

from google.oauth2.service_account import Credentials  # type: ignore
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.errors import HttpError  # type: ignore


BLOCKS_OUTPUT = REPO_ROOT / "docs" / "report_blocks.json"
DOCS_OUTPUT = REPO_ROOT / "docs" / "Wind_Energy_Forecasting_Project_Report.md"
DEFAULT_CREDENTIALS = Path.home() / "Downloads" / "virtusa-491703-1d8a81a3516a.json"
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]
TEMPLATE_FONT = "Times New Roman"
LINE_SPACING = 150

FRONT_MATTER_SECTIONS = {
    "STUDENT DECLARATION",
    "BONAFIDE CERTIFICATE",
    "ACKNOWLEDGMENT",
    "CONTENTS",
    "LIST OF FIGURES",
    "LIST OF TABLES",
    "LIST OF ABBREVIATIONS",
    "ABSTRACT",
}
LIST_SECTIONS = {
    "LIST OF FIGURES",
    "LIST OF TABLES",
    "LIST OF ABBREVIATIONS",
}


@dataclass
class ContentBlock:
    kind: str
    text: str = ""
    rows: list[list[str]] | None = None
    anchor_text: str | None = None
    table_style: str | None = None


def parse_document_id(value: str) -> str:
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", value)
    return match.group(1) if match else value.strip()


def load_markdown_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def load_json_blocks(path: Path) -> list[ContentBlock]:
    raw_blocks = json.loads(path.read_text(encoding="utf-8"))
    return [
        ContentBlock(
            kind=str(block["kind"]),
            text=str(block.get("text", "")),
            rows=[[str(cell) for cell in row] for row in block.get("rows", [])] or None,
            anchor_text=block.get("anchor_text"),
            table_style=block.get("table_style"),
        )
        for block in raw_blocks
    ]


def load_blocks(path: Path) -> list[ContentBlock]:
    if path.suffix.lower() == ".json":
        return load_json_blocks(path)
    return parse_markdown_blocks(load_markdown_lines(path))


def is_all_caps_line(text: str) -> bool:
    letters = [character for character in text if character.isalpha()]
    return bool(letters) and all(character.isupper() for character in letters)


def is_front_center_label(text: str) -> bool:
    stripped = text.strip()
    if stripped in {"BY", "PROJECT GUIDE", "TECHNICAL REVIEW"}:
        return True
    return is_all_caps_line(stripped) and len(stripped) <= 48


def looks_like_command(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("uvicorn ", "cd ", "copy ", "npm ", "python ", "py "))


def classify_cover_line(index: int) -> str:
    if index == 0:
        return "cover_title"
    if index <= 3:
        return "cover_subtitle"
    if index <= 7:
        return "cover_minor"
    if index <= 11:
        return "cover_name"
    if index == 12:
        return "cover_minor"
    return "cover_footer"


def split_table_line(section: str, line: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s{2,}", line.strip()) if part.strip()]
    if not parts:
        return []

    expected_columns = 3 if section in {"LIST OF FIGURES", "LIST OF TABLES"} else 2

    if len(parts) == expected_columns:
        return parts

    if expected_columns == 2 and len(parts) > 2:
        return [" ".join(parts[:-1]), parts[-1]]

    if expected_columns == 3 and len(parts) > 3:
        return [parts[0], " ".join(parts[1:-1]), parts[-1]]

    if expected_columns == 3 and len(parts) == 2:
        return [parts[0], parts[1], ""]

    if expected_columns == 2 and len(parts) == 1:
        return [parts[0], ""]

    return parts


def flush_table_rows(
    blocks: list[ContentBlock],
    current_section: str | None,
    pending_rows: list[list[str]],
) -> None:
    if current_section in LIST_SECTIONS and pending_rows:
        blocks.append(ContentBlock("table_section", current_section, pending_rows.copy()))
        pending_rows.clear()


def build_contents_table_rows(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    current_chapter_label: str | None = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if raw_line.startswith("## CHAPTER-"):
            current_chapter_label = raw_line[3:].strip()
            continue
        if raw_line.startswith("### ") and current_chapter_label:
            rows.append([current_chapter_label, raw_line[4:].strip(), ""])
            current_chapter_label = None
            continue
        if raw_line.startswith("#### "):
            rows.append(["", raw_line[5:].strip(), ""])

    return rows


def build_contents_blocks(lines: list[str]) -> list[ContentBlock]:
    front_items = [
        "ABSTRACT",
        "LIST OF FIGURES",
        "LIST OF TABLES",
        "LIST OF ABBREVIATIONS",
    ]
    blocks: list[ContentBlock] = [ContentBlock("contents_header_line", "TITLE\tPage No")]
    blocks.extend(ContentBlock("contents_front_item", item) for item in front_items)
    blocks.append(
        ContentBlock(
            "table_section",
            "CONTENTS",
            build_contents_table_rows(lines),
            anchor_text="LIST OF ABBREVIATIONS",
        )
    )
    return blocks


def parse_markdown_blocks(lines: list[str]) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    cover_index = 0
    current_section: str | None = None
    current_title: str | None = None
    skipped_document_title = False
    pending_table_rows: list[list[str]] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if raw_line.startswith("# "):
            if not skipped_document_title:
                skipped_document_title = True
                continue
        if not stripped:
            continue
        if stripped == "---":
            flush_table_rows(blocks, current_section, pending_table_rows)
            blocks.append(ContentBlock("page_break"))
            current_section = None
            current_title = None
            continue
        if raw_line.startswith("## "):
            flush_table_rows(blocks, current_section, pending_table_rows)
            current_section = raw_line[3:].strip()
            current_title = None
            if current_section.startswith("CHAPTER-"):
                blocks.append(ContentBlock("chapter_label", current_section))
            elif current_section == "CONTENTS":
                blocks.append(ContentBlock("section_heading", current_section))
                blocks.extend(build_contents_blocks(lines))
            else:
                blocks.append(ContentBlock("section_heading", current_section))
            continue
        if raw_line.startswith("### "):
            current_title = raw_line[4:].strip()
            blocks.append(ContentBlock("chapter_title", current_title))
            continue
        if raw_line.startswith("#### "):
            blocks.append(ContentBlock("subheading", raw_line[5:].strip()))
            continue

        if current_section is None:
            blocks.append(ContentBlock(classify_cover_line(cover_index), stripped))
            cover_index += 1
            continue

        if current_section == "CONTENTS":
            continue

        if current_section in LIST_SECTIONS:
            row = split_table_line(current_section, stripped)
            if row:
                pending_table_rows.append(row)
            continue

        if current_section in FRONT_MATTER_SECTIONS and is_front_center_label(stripped):
            blocks.append(ContentBlock("front_center_label", stripped))
            continue

        if current_section == "ABSTRACT" and stripped.startswith("Keywords:"):
            blocks.append(ContentBlock("keywords", stripped))
            continue

        if current_title == "REFERENCES":
            blocks.append(ContentBlock("reference_line", stripped))
            continue

        if looks_like_command(stripped):
            blocks.append(ContentBlock("command_line", stripped))
            continue

        if stripped.endswith(":") and len(stripped) <= 70:
            blocks.append(ContentBlock("body_label", stripped))
            continue

        blocks.append(ContentBlock("body", stripped))

    flush_table_rows(blocks, current_section, pending_table_rows)
    return blocks


def pt(value: float) -> dict:
    return {"magnitude": value, "unit": "PT"}


def text_style(
    *,
    font_size: float,
    bold: bool = False,
    italic: bool = False,
) -> tuple[dict, str]:
    style = {
        "weightedFontFamily": {"fontFamily": TEMPLATE_FONT},
        "fontSize": pt(font_size),
        "bold": bold,
        "italic": italic,
    }
    return style, "weightedFontFamily,fontSize,bold,italic"


def paragraph_style(
    *,
    alignment: str,
    line_spacing: float = LINE_SPACING,
    space_above: float = 0,
    space_below: float = 0,
) -> tuple[dict, str]:
    style = {
        "alignment": alignment,
        "lineSpacing": line_spacing,
        "spaceAbove": pt(space_above),
        "spaceBelow": pt(space_below),
    }
    return style, "alignment,lineSpacing,spaceAbove,spaceBelow"


def block_styles(block: ContentBlock) -> tuple[tuple[dict, str], tuple[dict, str]]:
    kind = block.kind

    if kind == "cover_title":
        return text_style(font_size=18, bold=True), paragraph_style(alignment="CENTER")
    if kind == "cover_subtitle":
        return text_style(font_size=12), paragraph_style(alignment="CENTER")
    if kind == "cover_minor":
        return text_style(font_size=14), paragraph_style(alignment="CENTER")
    if kind == "cover_degree":
        return text_style(font_size=14, bold=True), paragraph_style(alignment="CENTER")
    if kind == "cover_label":
        return text_style(font_size=14), paragraph_style(alignment="CENTER")
    if kind == "cover_name":
        return text_style(font_size=14), paragraph_style(alignment="CENTER")
    if kind == "cover_guide_name":
        return text_style(font_size=14, bold=True), paragraph_style(alignment="CENTER")
    if kind == "cover_guide_role":
        return text_style(font_size=14), paragraph_style(alignment="CENTER")
    if kind == "cover_footer":
        return text_style(font_size=14, bold=True), paragraph_style(alignment="CENTER")
    if kind in {"section_heading", "section_title"} and block.text == "CONTENTS":
        return text_style(font_size=16, bold=True), paragraph_style(alignment="CENTER")
    if kind in {"section_heading", "section_title"}:
        return text_style(font_size=16, bold=True), paragraph_style(alignment="CENTER")
    if kind == "contents_header_line":
        return text_style(font_size=16, bold=True), paragraph_style(alignment="START", line_spacing=105)
    if kind == "contents_front_item":
        return text_style(font_size=16), paragraph_style(alignment="START", line_spacing=105)
    if kind == "list_line":
        return text_style(font_size=12, bold=is_all_caps_line(block.text)), paragraph_style(
            alignment="START"
        )
    if kind == "chapter_label":
        return text_style(font_size=14), paragraph_style(alignment="CENTER")
    if kind == "chapter_title":
        return text_style(font_size=14, bold=True), paragraph_style(alignment="CENTER")
    if kind == "subheading":
        return text_style(font_size=12), paragraph_style(alignment="JUSTIFIED")
    if kind == "front_center_label":
        return text_style(font_size=14, bold=True), paragraph_style(alignment="CENTER")
    if kind == "label":
        return text_style(font_size=14), paragraph_style(alignment="START")
    if kind == "signature_heading":
        return text_style(font_size=14), paragraph_style(alignment="START")
    if kind == "body_label":
        return text_style(font_size=14, bold=True), paragraph_style(alignment="START")
    if kind == "signature":
        return text_style(font_size=14), paragraph_style(alignment="START")
    if kind == "certificate_dual_heading":
        return text_style(font_size=14, bold=True), paragraph_style(alignment="START")
    if kind == "certificate_dual_name":
        return text_style(font_size=14), paragraph_style(alignment="START")
    if kind == "certificate_dual_role":
        return text_style(font_size=14), paragraph_style(alignment="START")
    if kind == "certificate_dual_department":
        return text_style(font_size=14), paragraph_style(alignment="START")
    if kind == "command_line":
        return text_style(font_size=12), paragraph_style(alignment="START")
    if kind == "keywords":
        return text_style(font_size=12), paragraph_style(alignment="JUSTIFIED")
    if kind == "reference_line":
        return text_style(font_size=12), paragraph_style(alignment="JUSTIFIED")
    return text_style(font_size=12), paragraph_style(alignment="JUSTIFIED")


def insert_text_request(index: int, text: str) -> dict:
    return {"insertText": {"location": {"index": index}, "text": text}}


def insert_page_break_request(index: int) -> dict:
    return {"insertPageBreak": {"location": {"index": index}}}


def update_text_style_request(start: int, end: int, style: dict, fields: str) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": style,
            "fields": fields,
        }
    }


def update_paragraph_style_request(start: int, end: int, style: dict, fields: str) -> dict:
    return {
        "updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": style,
            "fields": fields,
        }
    }


def build_document_requests(existing_end_index: int, blocks: list[ContentBlock]) -> tuple[list[dict], int]:
    requests: list[dict] = []
    cursor = 1
    visible_character_count = 0

    if existing_end_index > 2:
        requests.append(
            {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": existing_end_index - 1}}}
        )

    for block in blocks:
        if block.kind == "page_break":
            requests.append(insert_page_break_request(cursor))
            cursor += 1
            continue
        if block.kind == "blank":
            requests.append(insert_text_request(cursor, "\n"))
            cursor += 1
            continue
        if block.kind == "table_section":
            continue

        text = block.text + "\n"
        start = cursor
        end = start + len(block.text)
        requests.append(insert_text_request(start, text))

        text_style_data, paragraph_style_data = block_styles(block)
        requests.append(update_text_style_request(start, end, *text_style_data))
        requests.append(update_paragraph_style_request(start, end, *paragraph_style_data))

        cursor = end + 1
        visible_character_count += len(block.text)

    return requests, visible_character_count


def read_document_summary(document: dict) -> dict:
    body = document.get("body", {}).get("content", [])
    lines: list[str] = []
    page_breaks = 0
    inline_objects = 0
    tables = 0

    for item in body:
        if "table" in item:
            tables += 1
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []):
            if "pageBreak" in element:
                page_breaks += 1
            if "inlineObjectElement" in element:
                inline_objects += 1
            text = element.get("textRun", {}).get("content", "")
            stripped = text.replace("\n", "").strip()
            if stripped:
                lines.append(stripped)

    return {
        "line_count": len(lines),
        "page_breaks": page_breaks,
        "inline_objects": inline_objects,
        "tables": tables,
        "preview": lines[:25],
    }


def find_paragraph_by_text(document: dict, target_text: str, after_index: int = 0) -> dict | None:
    for item in document.get("body", {}).get("content", []):
        if item.get("startIndex", 0) <= after_index:
            continue
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        text = "".join(
            element.get("textRun", {}).get("content", "") for element in paragraph.get("elements", [])
        ).replace("\n", "").strip()
        if text == target_text:
            return item
    return None


def find_table_after_anchor(document: dict, anchor_text: str, after_index: int = 0) -> dict | None:
    anchor_item = find_paragraph_by_text(document, anchor_text, after_index=after_index)
    if anchor_item is None:
        return None
    anchor_end = anchor_item.get("endIndex", 0)
    for item in document.get("body", {}).get("content", []):
        if item.get("startIndex", 0) < anchor_end:
            continue
        if "table" in item:
            return item
    return None


def table_column_alignments(section_title: str, column_count: int) -> list[str]:
    if section_title == "CONTENTS":
        return ["START", "START", "CENTER"]
    if section_title in {"LIST OF FIGURES", "LIST OF TABLES"}:
        return ["CENTER", "CENTER", "CENTER"]
    if section_title == "LIST OF ABBREVIATIONS":
        return ["CENTER", "CENTER"]
    return ["START"] * column_count


def table_widths(section_title: str, column_count: int) -> list[float]:
    if section_title == "CONTENTS" and column_count == 3:
        return [113.15, 255.15, 82.5]
    if section_title == "LIST OF FIGURES" and column_count == 3:
        return [106.1, 262.2, 82.5]
    if section_title == "LIST OF TABLES" and column_count == 3:
        return [99, 262.25, 89.55]
    if section_title == "LIST OF ABBREVIATIONS" and column_count == 2:
        return [144.85, 305.95]
    return [120] * column_count


def build_table_layout_requests(section_title: str, table_item: dict) -> list[dict]:
    requests: list[dict] = []
    table_start = table_item["startIndex"]
    table = table_item["table"]
    column_count = len(table["tableRows"][0]["tableCells"])
    widths = table_widths(section_title, column_count)

    for index, width in enumerate(widths):
        requests.append(
            {
                "updateTableColumnProperties": {
                    "tableStartLocation": {"index": table_start},
                    "columnIndices": [index],
                    "tableColumnProperties": {
                        "widthType": "FIXED_WIDTH",
                        "width": pt(width),
                    },
                    "fields": "width,widthType",
                }
            }
        )

    requests.append(
        {
            "updateTableCellStyle": {
                "tableStartLocation": {"index": table_start},
                "tableCellStyle": {
                    "contentAlignment": "TOP",
                    "paddingTop": pt(1.5),
                    "paddingBottom": pt(1.5),
                    "paddingLeft": pt(2),
                    "paddingRight": pt(2),
                },
                "fields": "contentAlignment,paddingTop,paddingBottom,paddingLeft,paddingRight",
            }
        }
    )

    requests.append(
        {
            "updateTableRowStyle": {
                "tableStartLocation": {"index": table_start},
                "tableRowStyle": {
                    "minRowHeight": pt(12),
                },
                "fields": "minRowHeight",
            }
        }
    )

    return requests


def build_table_population_requests(section_title: str, table_item: dict, rows: list[list[str]]) -> list[dict]:
    requests: list[dict] = []
    table = table_item["table"]
    table_column_count = len(table["tableRows"][0]["tableCells"])
    column_alignments = table_column_alignments(section_title, table_column_count)
    cell_targets: list[tuple[int, list[dict]]] = []

    for row_index, row in enumerate(rows):
        table_row = table["tableRows"][row_index]
        row_values = row[:table_column_count] + [""] * max(0, table_column_count - len(row))
        for column_index, value in enumerate(row_values):
            table_cell = table_row["tableCells"][column_index]
            paragraph = next(
                content["paragraph"] for content in table_cell["content"] if "paragraph" in content
            )
            first_element = paragraph["elements"][0]
            insert_index = first_element["startIndex"]
            if not value:
                continue
            text_end = insert_index + len(value)

            is_header_row = row_index == 0 and section_title != "CONTENTS"
            is_contents_chapter_row = section_title == "CONTENTS" and bool(row[0]) and column_index < 2
            should_bold = is_header_row or is_contents_chapter_row
            font_size = 11 if section_title == "CONTENTS" else 12

            cell_text_style, text_fields = text_style(
                font_size=font_size,
                bold=should_bold,
            )
            cell_paragraph_style, paragraph_fields = paragraph_style(
                alignment=column_alignments[column_index],
                line_spacing=105 if section_title == "CONTENTS" else 115,
            )

            cell_requests = [
                insert_text_request(insert_index, value),
                update_text_style_request(insert_index, text_end, cell_text_style, text_fields),
                update_paragraph_style_request(
                    insert_index, text_end, cell_paragraph_style, paragraph_fields
                ),
            ]
            cell_targets.append((insert_index, cell_requests))

    for _, cell_requests in sorted(cell_targets, key=lambda item: item[0], reverse=True):
        requests.extend(cell_requests)

    return requests


def apply_tables(
    docs,
    document_id: str,
    document: dict,
    blocks: list[ContentBlock],
) -> dict:
    table_blocks = [block for block in blocks if block.kind == "table_section" and block.rows]
    current_document = document
    search_after_index = 0

    for table_block in table_blocks:
        anchor_text = table_block.anchor_text or table_block.text
        style_name = table_block.table_style or table_block.text
        heading_item = find_paragraph_by_text(
            current_document,
            anchor_text,
            after_index=search_after_index,
        )
        if not heading_item:
            raise ValueError(f"Could not find section anchor for table block: {table_block.text}")

        insert_index = heading_item["endIndex"]
        docs.documents().batchUpdate(
            documentId=document_id,
            body={
                "requests": [
                    {
                        "insertTable": {
                            "rows": len(table_block.rows or []),
                            "columns": max(len(row) for row in (table_block.rows or [[]])),
                            "location": {"index": insert_index},
                        }
                    }
                ]
            },
        ).execute()

        current_document = docs.documents().get(documentId=document_id).execute()
        table_item = find_table_after_anchor(
            current_document,
            anchor_text,
            after_index=search_after_index,
        )
        if not table_item:
            raise ValueError(f"Could not find inserted table for section: {table_block.text}")

        layout_requests = build_table_layout_requests(style_name, table_item)
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": layout_requests},
        ).execute()
        current_document = docs.documents().get(documentId=document_id).execute()
        table_item = find_table_after_anchor(
            current_document,
            anchor_text,
            after_index=search_after_index,
        )
        if not table_item:
            raise ValueError(f"Could not find layout-updated table for section: {table_block.text}")

        populate_requests = build_table_population_requests(
            style_name,
            table_item,
            table_block.rows or [],
        )
        docs.documents().batchUpdate(
            documentId=document_id,
            body={"requests": populate_requests},
        ).execute()
        current_document = docs.documents().get(documentId=document_id).execute()
        search_after_index = table_item.get("endIndex", search_after_index)

    return current_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the generated report to Google Docs.")
    parser.add_argument("--doc", required=True, help="Google Doc URL or document id.")
    parser.add_argument(
        "--credentials",
        default=str(DEFAULT_CREDENTIALS),
        help="Path to the service account credentials JSON.",
    )
    parser.add_argument(
        "--source",
        default=str(BLOCKS_OUTPUT),
        help="Structured report block source generated from the workspace report.",
    )
    args = parser.parse_args()

    credentials = Credentials.from_service_account_file(args.credentials, scopes=SCOPES)
    docs = build("docs", "v1", credentials=credentials, cache_discovery=False)
    document_id = parse_document_id(args.doc)
    source_path = Path(args.source)

    blocks = load_blocks(source_path)

    document = docs.documents().get(documentId=document_id).execute()
    title = document.get("title", "Untitled")
    body = document.get("body", {}).get("content", [])
    end_index = body[-1]["endIndex"] if body else 1
    requests, visible_character_count = build_document_requests(end_index, blocks)

    docs.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()
    updated_document = docs.documents().get(documentId=document_id).execute()
    updated_document = apply_tables(docs, document_id, updated_document, blocks)

    rename_status = "skipped"
    try:
        drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        drive.files().update(
            fileId=document_id,
            body={"name": "Wind Energy Forecasting Project Report"},
            fields="id,name",
        ).execute()
        rename_status = "updated"
    except HttpError as error:
        rename_status = f"skipped: {error.resp.status}"

    print(
        json.dumps(
            {
                "document_id": document_id,
                "title": title,
                "blocks": len(blocks),
                "updated_characters": visible_character_count,
                "rename_status": rename_status,
                "verification": read_document_summary(updated_document),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
