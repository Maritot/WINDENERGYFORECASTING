"""Generate a workspace-specific project report from the FINAL DOCUMENT template."""

from __future__ import annotations

import copy
import importlib.util
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)

W = f"{{{W_NS}}}"

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
TEMPLATE_PATH = Path.home() / "Downloads" / "FINAL DOCUMENT.docx"
CONTENT_PATH = DOCS_DIR / "report_content.py"
DOCX_OUTPUT = DOCS_DIR / "Wind_Energy_Forecasting_Project_Report.docx"
MARKDOWN_OUTPUT = DOCS_DIR / "Wind_Energy_Forecasting_Project_Report.md"


def load_blocks() -> list[dict[str, object]]:
    spec = importlib.util.spec_from_file_location("report_content", CONTENT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load report content from {CONTENT_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    blocks = getattr(module, "REPORT_BLOCKS", None)
    if not isinstance(blocks, list):
        raise ValueError("report_content.py must define REPORT_BLOCKS as a list.")
    return blocks


def body_children(root: ET.Element) -> list[ET.Element]:
    body = root.find(f"{W}body")
    if body is None:
        raise ValueError("Template document has no body element.")
    return list(body)


def paragraph_prototypes(items: list[ET.Element]) -> dict[str, ET.Element]:
    return {
        "blank": items[0],
        "cover_title": items[7],
        "center_heading": items[29],
        "body": items[30],
        "chapter_heading": items[556],
        "subheading": items[42],
        "minor_heading": items[566],
        "screen_heading": items[522],
        "table_heading": items[510],
        "analysis_heading": items[651],
    }


def table_prototypes(items: list[ET.Element]) -> dict[str, ET.Element]:
    return {
        "INDEX_1COL": items[16],
        "TABLE_4COL_TEST": items[512],
        "TABLE_4COL_COMPARISON": items[674],
        "TABLE_2COL": items[684],
    }


def kind_to_prototype(kind: str) -> tuple[str, str | None]:
    mapping = {
        "blank": ("blank", None),
        "cover_title": ("cover_title", None),
        "cover_center": ("body", "center"),
        "cover_center_bold": ("center_heading", None),
        "cover_name_line": ("body", "center"),
        "section_title": ("center_heading", None),
        "body": ("body", None),
        "body_center": ("body", "center"),
        "chapter_heading": ("chapter_heading", None),
        "subheading": ("subheading", None),
        "minor_heading": ("minor_heading", None),
        "screen_heading": ("screen_heading", None),
        "table_heading": ("table_heading", None),
        "analysis_heading": ("analysis_heading", None),
        "reference_line": ("body", None),
    }
    if kind not in mapping:
        raise ValueError(f"Unknown paragraph kind: {kind}")
    return mapping[kind]


def first_run_properties(paragraph: ET.Element) -> ET.Element | None:
    for run in paragraph.findall(f"{W}r"):
        run_properties = run.find(f"{W}rPr")
        if run_properties is not None:
            return copy.deepcopy(run_properties)
    return None


def set_alignment(paragraph: ET.Element, alignment: str | None) -> None:
    if alignment is None:
        return

    paragraph_properties = paragraph.find(f"{W}pPr")
    if paragraph_properties is None:
        paragraph_properties = ET.Element(f"{W}pPr")
        paragraph.insert(0, paragraph_properties)

    justification = paragraph_properties.find(f"{W}jc")
    if justification is None:
        justification = ET.SubElement(paragraph_properties, f"{W}jc")

    justification.set(f"{W}val", alignment)


def make_text_paragraph(prototype: ET.Element, text: str, alignment: str | None = None) -> ET.Element:
    paragraph = copy.deepcopy(prototype)
    paragraph_properties = paragraph.find(f"{W}pPr")

    for child in list(paragraph):
        if child is not paragraph_properties:
            paragraph.remove(child)

    if text:
        run = ET.SubElement(paragraph, f"{W}r")
        run_properties = first_run_properties(prototype)
        if run_properties is not None:
            run.append(run_properties)
        text_node = ET.SubElement(run, f"{W}t")
        if text.startswith(" ") or text.endswith(" ") or "  " in text:
            text_node.set(f"{{{XML_NS}}}space", "preserve")
        text_node.text = text

    set_alignment(paragraph, alignment)
    return paragraph


def page_break_paragraph() -> ET.Element:
    paragraph = ET.Element(f"{W}p")
    run = ET.SubElement(paragraph, f"{W}r")
    page_break = ET.SubElement(run, f"{W}br")
    page_break.set(f"{W}type", "page")
    return paragraph


def set_cell_text(cell: ET.Element, text: str) -> None:
    paragraphs = [child for child in cell if child.tag == f"{W}p"]
    prototype = paragraphs[0] if paragraphs else ET.Element(f"{W}p")

    for child in list(cell):
        if child.tag == f"{W}p":
            cell.remove(child)

    cell.append(make_text_paragraph(prototype, text))


def clone_table_row(prototype: ET.Element, values: list[str]) -> ET.Element:
    row = copy.deepcopy(prototype)
    cells = row.findall(f"{W}tc")
    padded_values = values + [""] * max(0, len(cells) - len(values))

    for cell, value in zip(cells, padded_values):
        set_cell_text(cell, value)

    return row


def build_table(prototype: ET.Element, rows: list[list[str]]) -> ET.Element:
    table = copy.deepcopy(prototype)

    for child in list(table):
        if child.tag == f"{W}tr":
            table.remove(child)

    row_prototypes = prototype.findall(f"{W}tr")
    if not row_prototypes:
        raise ValueError("Template table has no row prototypes.")

    header_row = row_prototypes[0]
    data_row = row_prototypes[1] if len(row_prototypes) > 1 else row_prototypes[0]

    for row_index, row_values in enumerate(rows):
        prototype_row = header_row if row_index == 0 else data_row
        table.append(clone_table_row(prototype_row, row_values))

    return table


def build_document_xml(blocks: list[dict[str, object]]) -> bytes:
    with zipfile.ZipFile(TEMPLATE_PATH) as template_zip:
        root = ET.fromstring(template_zip.read("word/document.xml"))

    items = body_children(root)
    paragraph_map = paragraph_prototypes(items)
    table_map = table_prototypes(items)

    body = root.find(f"{W}body")
    if body is None:
        raise ValueError("Template document has no body element.")

    section_properties = body.find(f"{W}sectPr")
    section_copy = copy.deepcopy(section_properties) if section_properties is not None else None
    for child in list(body):
        body.remove(child)

    for block in blocks:
        kind = str(block["kind"])

        if kind == "page_break":
            body.append(page_break_paragraph())
            continue

        if kind == "table_section":
            style_name = str(block.get("table_style") or "")
            rows = [list(map(str, row)) for row in block.get("rows", [])]
            if style_name not in table_map:
                raise ValueError(f"Unknown table style: {style_name}")
            body.append(build_table(table_map[style_name], rows))
            continue

        prototype_key, alignment = kind_to_prototype(kind)
        body.append(
            make_text_paragraph(
                paragraph_map[prototype_key],
                str(block.get("text", "")),
                alignment=alignment,
            )
        )

    if section_copy is not None:
        body.append(section_copy)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render_markdown(blocks: list[dict[str, object]]) -> str:
    lines = ["# Wind Energy Forecasting Project Report", ""]

    for block in blocks:
        kind = str(block["kind"])
        text = str(block.get("text", ""))

        if kind == "page_break":
            lines.extend(["", "---", ""])
            continue
        if kind == "blank":
            lines.append("")
            continue
        if kind in {"section_title", "chapter_heading"}:
            lines.extend([f"## {text}", ""])
            continue
        if kind in {"subheading", "minor_heading", "screen_heading", "table_heading", "analysis_heading"}:
            lines.extend([f"### {text}", ""])
            continue
        if kind == "table_section":
            for row in block.get("rows", []):
                lines.append(" | ".join(str(cell) for cell in row).rstrip())
            lines.append("")
            continue

        lines.extend([text, ""])

    return "\n".join(lines).strip() + "\n"


def write_outputs(blocks: list[dict[str, object]], document_xml: bytes) -> None:
    with zipfile.ZipFile(TEMPLATE_PATH) as source_zip, zipfile.ZipFile(
        DOCX_OUTPUT, "w", compression=zipfile.ZIP_DEFLATED
    ) as target_zip:
        for item in source_zip.infolist():
            data = document_xml if item.filename == "word/document.xml" else source_zip.read(item.filename)
            target_zip.writestr(item, data)

    MARKDOWN_OUTPUT.write_text(render_markdown(blocks), encoding="utf-8")


def main() -> None:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template document was not found at {TEMPLATE_PATH}")
    if not CONTENT_PATH.exists():
        raise FileNotFoundError(f"Report content file was not found at {CONTENT_PATH}")

    blocks = load_blocks()
    document_xml = build_document_xml(blocks)
    write_outputs(blocks, document_xml)
    print(f"Generated DOCX report at: {DOCX_OUTPUT}")
    print(f"Generated Markdown report at: {MARKDOWN_OUTPUT}")


if __name__ == "__main__":
    main()
