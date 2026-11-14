"""Convert the laser SVGs 1:1 into native vector PDFs (no browser wrapper matrices).

Usage: python3 modell/laser_pdf.py <svg_dir> <pdf_dir>
Each SVG becomes one single-page PDF whose page size equals the SVG width/height (mm),
with paths in native PDF points (1 mm = 72/25.4 pt) and stroke width 0.1 pt.
"""
import pathlib
import re
import sys
import zlib

PT_PER_MM = 72.0 / 25.4
STROKE_PT = 0.1


def parse_svg(svg_text):
    w_mm = float(re.search(r'<svg[^>]*\swidth="([\d.]+)mm"', svg_text).group(1))
    h_mm = float(re.search(r'<svg[^>]*\sheight="([\d.]+)mm"', svg_text).group(1))
    paths = re.findall(r'<path\s+d="([^"]+)"\s*/>', svg_text)
    return w_mm, h_mm, paths


def svg_path_to_pdf_ops(d_str, h_mm):
    tokens = re.findall(r'[MLZ]|[-+]?\d*\.?\d+', d_str)
    ops = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("M", "L"):
            x = float(tokens[i + 1]) * PT_PER_MM
            y = (h_mm - float(tokens[i + 2])) * PT_PER_MM
            ops.append(f"{x:.4f} {y:.4f} {'m' if t == 'M' else 'l'}")
            i += 3
        elif t == "Z":
            ops.append("h")
            i += 1
        else:
            i += 1
    ops.append("S")
    return "\n".join(ops)


def write_pdf(svg_path, pdf_path):
    w_mm, h_mm, paths = parse_svg(svg_path.read_text(encoding="utf-8"))
    w_pt = w_mm * PT_PER_MM
    h_pt = h_mm * PT_PER_MM
    lw_pt = STROKE_PT

    stream_lines = [
        "q",
        f"{lw_pt:g} w",
        "0 J 0 j 4 M",
        "1 0 0 RG",
    ]
    for d in paths:
        stream_lines.append(svg_path_to_pdf_ops(d, h_mm))
    stream_lines.append("Q")
    stream_raw = ("\n".join(stream_lines) + "\n").encode("ascii")
    comp = zlib.compress(stream_raw, 9)

    objs = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.4f} {h_pt:.4f}] "
        f"/Contents 4 0 R /Resources << /ProcSet [/PDF] >> >>\nendobj\n".encode("ascii")
    )
    objs.append(
        f"4 0 obj\n<< /Filter /FlateDecode /Length {len(comp)} >>\nstream\n".encode("ascii")
        + comp
        + b"\nendstream\nendobj\n"
    )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for ob in objs:
        offsets.append(len(out))
        out.extend(ob)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    pdf_path.write_bytes(out)


def main():
    src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    svgs = sorted(src.glob("brett_*.svg")) + [src / "schlitz_testleiste.svg"]
    for svg in svgs:
        out = dst / (svg.stem + ".pdf")
        write_pdf(svg, out)
        print("PDF", out.name, out.stat().st_size)


if __name__ == "__main__":
    main()
