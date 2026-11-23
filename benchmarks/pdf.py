"""Windows milestone PDF workload. Run once per fresh editor process."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time


def write_fixture(path):
    # Fixed Letter pages, built-in font, no network resources or private documents.
    objects = []
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(24))
    objects.extend([b"<< /Type /Catalog /Pages 2 0 R >>",
                    f"<< /Type /Pages /Count 24 /Kids [{kids}] >>".encode(),
                    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"])
    for i in range(24):
        page = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {5 + i * 2} 0 R /Resources << /Font << /F1 3 0 R >> >> >>")
        lines = [f"(Reading benchmark - page {i + 1}) Tj"]
        lines += [f"T* (Paragraph {n}. A fixed line of plain text for PDF rendering.) Tj"
                  for n in range(1, 36)]
        stream = ("BT /F1 12 Tf 16 TL 45 740 Td\n" + "\n".join(lines) + "\nET").encode()
        objects.extend([page.encode(), f"<< /Length {len(stream)} >>\nstream\n".encode()
                        + stream + b"\nendstream"])
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        data.extend(f"{offset:010} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)


def private_mib():
    # QueryWorkingSet reports one ULONG_PTR per resident page; bit 8 is Shared.
    import mmap
    entries = 65536
    while True:
        buffer = (ctypes.c_size_t * entries)()
        if ctypes.windll.psapi.QueryWorkingSet(ctypes.c_void_p(-1), buffer, ctypes.sizeof(buffer)):
            private = sum(1 for flags in buffer[1:buffer[0]+1] if not flags & 0x100)
            return private * mmap.PAGESIZE / 2**20
        if ctypes.windll.kernel32.GetLastError() != 24:
            raise ctypes.WinError()
        entries *= 2


def run_phase(root, preview, name):
    samples = []
    events = 0
    start = time.perf_counter()
    cpu = time.process_time()
    while (elapsed := time.perf_counter() - start) < 10:
        if name == "Scrolling" and events < 100 and elapsed >= events / 10:
            preview.canvas.event_generate("<MouseWheel>", delta=-120)
            events += 1
        root.update()
        if elapsed >= len(samples):
            samples.append(private_mib())
        time.sleep(0.01)
    duration = time.perf_counter() - start
    cpu_pct = 100 * (time.process_time() - cpu) / (duration * os.cpu_count())
    if name == "Scrolling" and events != 100:
        raise RuntimeError(f"Only {events}/100 wheel events delivered")
    return {"phase": name, "private_MiB": sum(samples)/len(samples),
            "cpu_pct": cpu_pct, "page": preview.index+1, "wheel_events": events}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    project = parser.parse_args().project.resolve()
    sys.path.insert(0, str(project))
    app = runpy.run_path(str(project / "viewer.pyw"))
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reading-benchmark.pdf"
        write_fixture(path)
        root = app["TkinterDnD"].Tk()
        try:
            editor = app["Viewer"](root)
            root.state("normal")
            root.geometry("1060x700")
            editor.browse(path.parent)
            root.update()
            if not editor.show(path):
                raise RuntimeError("PDF failed to open")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            results = [run_phase(root, editor.pdf, name)
                       for name in ("Open idle", "Scrolling", "After scrolling")]
            if results[1]["page"] <= results[0]["page"]:
                raise RuntimeError("The reader did not scroll")
            print(json.dumps({"fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "viewport": [editor.pdf.canvas.winfo_width(), editor.pdf.canvas.winfo_height()],
                              "results": results}), flush=True)
        finally:
            root.destroy()


if __name__ == "__main__":
    main()

