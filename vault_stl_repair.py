#!/usr/bin/env python3
"""VAULT STL repair – repairs the mesh errors of a whole STL library with the Windows 3D model repair
service (Windows.Graphics.Printing3D) – the same one Bambu Studio uses for "Repair model" – and writes
a copy of the library with the repaired files. Windows 10/11 only.

Usage (Python 3.9+; numpy and the winrt packages are installed automatically on first run):
    python vault_stl_repair.py "D:\\VAULT" "D:\\VAULT_repaired"
    python vault_stl_repair.py "D:\\VAULT" "D:\\VAULT_repaired" --workers 2   parallel processes (default 2)
    python vault_stl_repair.py "D:\\VAULT" "D:\\VAULT_repaired" --all         repair files without detected errors too
    python vault_stl_repair.py "D:\\VAULT" "D:\\VAULT_repaired" --only "S6"   only paths containing the text
    python vault_stl_repair.py "D:\\VAULT" "D:\\VAULT_repaired" --skip XL     skip paths containing the text (XL modules:
                                                                      7 million triangles, ~1.5 h each – if you do not print XL)

For every STL file: the mesh is checked (open edges, non-manifold edges, flipped faces – vertices merged at
exactly equal coordinates, like admesh in slicers). A clean file is copied unchanged; a file with errors is
written as a 3MF package in memory, loaded with Printing3D3MFPackage, repaired (Printing3DModel.RepairAsync)
and saved as a binary STL (normals recomputed). All other files (PDF, images) are copied as they are, so the
target folder has exactly the structure of the source.

An interrupted run can be resumed: finished files are skipped (vault_stl_repair.json in the target folder).
The report vault_stl_repair.csv lists errors before and after, triangle counts and time for every file.

Part of the unofficial VAULT configurator (https://github.com/rawel2/Vault-Konfigurator-wydania).
Authors: rawel2 and Claude (Anthropic). MIT licence. VAULT and its STL files © USSA Design.
"""
import argparse
import asyncio
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PACKAGES = ["numpy", "winrt-runtime", "winrt-Windows.Graphics.Printing3D", "winrt-Windows.Foundation",
            "winrt-Windows.Foundation.Collections", "winrt-Windows.Storage.Streams"]
HEADER = b"VAULT STL repair (Windows Printing3D)"
LOG = "vault_stl_repair.json"
REPORT = "vault_stl_repair.csv"

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')


def install_packages():
    try:
        import numpy  # noqa: F401
        import winrt.windows.graphics.printing3d  # noqa: F401
        import winrt.windows.storage.streams  # noqa: F401
        return True
    except ImportError:
        pass
    print("Installing required packages (" + ", ".join(PACKAGES) + ")...", flush=True)
    code = subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", *PACKAGES])
    if code:
        print("Could not install the packages. Install them manually:\n  " + sys.executable + " -m pip install " + " ".join(PACKAGES))
        return False
    return True


# ---------------------------------------------------------------- STL reading, checking, writing

def read_triangles(path):
    """-> float32 array (N, 3, 3) of triangle corners; binary or ASCII STL."""
    import numpy as np

    tri = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    size = path.stat().st_size
    with open(path, "rb") as f:
        head = f.read(84)
    n = int.from_bytes(head[80:84], "little")
    if 84 + n * 50 == size:
        mm = np.memmap(path, dtype=tri, mode="r", offset=84, shape=(n,))
        v = np.array(mm["v"], dtype=np.float32)
        del mm
        return v
    text = path.read_text(errors="ignore")
    nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    return np.array(nums, dtype=np.float32).reshape(-1, 3, 3)


def index_mesh(v):
    """Triangles (N,3,3) -> unique vertices (M,3) and uint32 indices (N,3)."""
    import numpy as np

    pts = np.ascontiguousarray(v.reshape(-1, 3) + np.float32(0))  # +0 turns -0.0 into 0.0
    keys = pts.view(np.dtype((np.void, 12))).ravel()
    uniq, idx = np.unique(keys, return_inverse=True)
    verts = np.ascontiguousarray(uniq.view(np.float32).reshape(-1, 3))
    return verts, np.ascontiguousarray(idx.reshape(-1, 3).astype(np.uint32))


def check(path):
    """Mesh statistics of one STL file (same method as vault_mesh_check.py)."""
    import numpy as np

    v = read_triangles(path)
    n = len(v)
    _, idx = index_mesh(v)
    del v
    nv = int(idx.max()) + 1 if len(idx) else 0
    f = idx.astype(np.int64)
    degenerate = (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])
    f = f[~degenerate]
    a = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    b = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    _, cnt = np.unique(lo * nv + hi, return_counts=True)
    _, cnt_dir = np.unique(a * nv + b, return_counts=True)
    return {"triangles": n, "vertices": nv, "open": int((cnt == 1).sum()), "nonmanifold": int((cnt > 2).sum()),
            "flipped": int((cnt_dir > 1).sum()), "degenerate": int(degenerate.sum())}


def has_errors(r):
    return bool(r["open"] or r["nonmanifold"] or r["flipped"])


def clean(verts, tri):
    """After rounding to float32: merge identical vertices, drop degenerate and duplicated triangles."""
    import numpy as np

    verts, tri = index_mesh(verts[tri])
    f = tri.astype(np.int64)
    ok = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    key = np.ascontiguousarray(np.sort(f, axis=1)).view(np.dtype((np.void, 24))).ravel()
    _, first = np.unique(key, return_index=True)
    keep = np.zeros(len(f), bool)
    keep[first] = True
    return verts, f[keep & ok]


def write_stl(path, verts, tri):
    import numpy as np

    v = verts[tri]
    n = np.cross((v[:, 1] - v[:, 0]).astype(np.float64), (v[:, 2] - v[:, 0]).astype(np.float64))
    length = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, length, out=np.zeros_like(n), where=length > 0)
    data = np.zeros(len(tri), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]))
    data["n"] = n
    data["v"] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(HEADER.ljust(80, b"\0"))
        f.write(len(tri).to_bytes(4, "little"))
        f.write(data.tobytes())
    tmp.replace(path)


# ---------------------------------------------------------------- Windows repair service

def model_xml(verts, tri):
    import numpy as np

    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1" type="model"><mesh><vertices>\n']
    w = io.StringIO()
    np.savetxt(w, verts, fmt='<vertex x="%.9g" y="%.9g" z="%.9g"/>')
    parts.append(w.getvalue())
    parts.append("</vertices><triangles>\n")
    w = io.StringIO()
    np.savetxt(w, tri, fmt='<triangle v1="%d" v2="%d" v3="%d"/>')
    parts.append(w.getvalue())
    parts.append('</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
    return "".join(parts)


def package_3mf(verts, tri):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model_xml(verts, tri))
    return bio.getvalue()


def mesh_arrays(m):
    """Printing3DMesh loaded from a package: positions double x3, indices uint32 x3 (as in PrusaSlicer's FixModelByWin10)."""
    import numpy as np
    import winrt.windows.graphics.printing3d as p3

    d1, d2 = m.vertex_positions_description, m.triangle_indices_description
    if d1.format != p3.Printing3DBufferFormat.PRINTING_3D_DOUBLE or d1.stride != 3:
        raise RuntimeError("unsupported vertex format %s/%s" % (d1.format, d1.stride))
    if d2.format != p3.Printing3DBufferFormat.PRINTING_3D_UINT or d2.stride != 3:
        raise RuntimeError("unsupported triangle format %s/%s" % (d2.format, d2.stride))
    nv, nt = m.vertex_count, m.index_count
    verts = np.frombuffer(bytes(memoryview(m.get_vertex_positions()).cast("B")), dtype=np.float64)[: nv * 3].reshape(-1, 3)
    tri = np.frombuffer(bytes(memoryview(m.get_triangle_indices()).cast("B")), dtype=np.uint32)[: nt * 3].reshape(-1, 3)
    return verts.astype(np.float32), tri.astype(np.int64)


async def repair_async(data):
    import numpy as np
    import winrt.windows.graphics.printing3d as p3
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    dw = DataWriter(stream)
    dw.write_bytes(data)
    await dw.store_async()
    await dw.flush_async()
    dw.detach_stream()
    stream.seek(0)
    package = await p3.Printing3D3MFPackage.load_async(stream)
    model = await package.load_model_from_package_async(stream)
    await model.repair_async()
    meshes = [mesh_arrays(m) for m in model.meshes]
    verts = np.concatenate([m[0] for m in meshes])
    offsets = np.cumsum([0] + [len(m[0]) for m in meshes[:-1]])
    tri = np.concatenate([m[1] + o for m, o in zip(meshes, offsets)])
    return verts, tri


def repair_file(src, dst, force):
    """One STL file: check, repair if needed, write. Returns a log record."""
    t0 = time.time()
    try:
        before = check(src)
        if not force and not has_errors(before):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return {"status": "copied", "before": before, "after": before, "s": round(time.time() - t0, 1)}
        import numpy as np

        verts, tri = index_mesh(read_triangles(src))
        # The USSA files lie 1-28 m away from the origin (exported from a large scene), where float32 has a step of
        # 0.001-0.002 mm – micro-triangles from the repair would collapse when written as STL (XL5² module: 51 new bad
        # edges). The repaired file is therefore written with the centre of its bounding box at (0,0,0); size and shape
        # are unchanged.
        centre = (verts.min(0).astype(np.float64) + verts.max(0).astype(np.float64)) / 2
        data = package_3mf(verts.astype(np.float64) - centre, tri)
        del verts, tri
        verts, tri = asyncio.run(repair_async(data))
        del data
        verts, tri = clean(verts, tri)
        write_stl(dst, verts, tri)
        del verts, tri
        after = check(dst)
        return {"status": "repaired" if not has_errors(after) else "still has errors", "before": before, "after": after,
                "shift": [round(float(x), 3) for x in centre], "s": round(time.time() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": "%s: %s" % (type(e).__name__, e), "s": round(time.time() - t0, 1)}


def _job(args):
    src, dst, force = args
    return src, repair_file(src, dst, force)


# ---------------------------------------------------------------- main

def errors_text(r):
    return "open %d, non-manifold %d, flipped %d" % (r["open"], r["nonmanifold"], r["flipped"]) if r else ""


def hms(s):
    s = int(s)
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


def main():
    ap = argparse.ArgumentParser(description="Repair the STL meshes of a VAULT library with the Windows 3D model repair service")
    ap.add_argument("source", help="library folder (VAULT STL files)")
    ap.add_argument("target", help="target folder for the repaired copy")
    ap.add_argument("--all", action="store_true", help="repair files without detected errors too")
    ap.add_argument("--workers", type=int, default=2, help="parallel processes (default 2; large files need a few GB each)")
    ap.add_argument("--only", action="append", default=[], help="only files whose path contains the text (repeatable)")
    ap.add_argument("--skip", action="append", default=[], help="skip STL files whose path contains the text, e.g. --skip XL (repeatable)")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(errors="replace")
    if sys.platform != "win32":
        print("This tool needs Windows 10/11 (the mesh repair service is part of Windows).")
        return 2
    if not install_packages():
        return 2
    source, target = Path(a.source).resolve(), Path(a.target).resolve()
    if not source.is_dir():
        print("Source folder not found:", source)
        return 2
    if target == source or source in target.parents:
        print("The target folder must not be the source folder or lie inside it:", target)
        return 2
    target.mkdir(parents=True, exist_ok=True)
    log_path = target / LOG
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}

    files = sorted(p for p in source.rglob("*") if p.is_file() and "__MACOSX" not in p.parts and not p.name.startswith("._"))
    if a.only:
        files = [p for p in files if any(t.lower() in p.relative_to(source).as_posix().lower() for t in a.only)]
    stl, other = [], []
    for p in files:
        (stl if p.suffix.lower() == ".stl" else other).append(p)
    if a.skip:  # skipped STL files are left out of the target entirely (e.g. XL modules that do not fit your printer)
        stl = [p for p in stl if not any(t.lower() in p.relative_to(source).as_posix().lower() for t in a.skip)]
    for p in other:
        d = target / p.relative_to(source)
        if not d.exists() or d.stat().st_size != p.stat().st_size:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
    print("Source: %s\nTarget: %s\nSTL files: %d, other files copied: %d" % (source, target, len(stl), len(other)), flush=True)

    todo = []
    for p in stl:
        key = p.relative_to(source).as_posix()
        d = target / p.relative_to(source)
        rec = log.get(key)
        if rec and rec.get("size") == p.stat().st_size and d.exists() and rec.get("status") in ("copied", "repaired") \
                and (rec["status"] == "repaired" or not a.all):
            continue
        todo.append((p, d, a.all))
    todo.sort(key=lambda x: -x[0].stat().st_size)  # largest first – keeps the workers busy until the end
    print("To do: %d (already done: %d)" % (len(todo), len(stl) - len(todo)), flush=True)

    t0 = time.time()
    done = 0
    bytes_total = sum(z[0].stat().st_size for z in todo)
    bytes_done = 0
    workers = max(1, min(a.workers, len(todo) or 1))

    def record(src, r):
        nonlocal done, bytes_done
        done += 1
        key = src.relative_to(source).as_posix()
        r["size"] = src.stat().st_size
        bytes_done += r["size"]
        log[key] = r
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=0), encoding="utf-8")
        if r["status"] == "failed":
            info = r["error"]
        elif r["status"] == "copied":
            info = "no errors, copied"
        else:
            info = "%s -> %s, triangles %d -> %d" % (errors_text(r["before"]), errors_text(r["after"]),
                                                   r["before"]["triangles"], r["after"]["triangles"])
        elapsed = time.time() - t0
        left = elapsed * (bytes_total - bytes_done) / bytes_done if bytes_done else 0
        print("[%d/%d] %s: %s (%s, %.0f s)" % (done, len(todo), key, r["status"], info, r["s"]), flush=True)
        print("    done %d, left %d (%.0f%% of data), elapsed %s, remaining about %s" % (
            done, len(todo) - done, 100 * bytes_done / max(bytes_total, 1), hms(elapsed), hms(left)), flush=True)

    if workers == 1:
        for src, dst, force in todo:
            record(src, repair_file(src, dst, force))
    else:
        with ProcessPoolExecutor(workers) as ex:
            for fut in as_completed([ex.submit(_job, z) for z in todo]):
                record(*fut.result())

    with open(target / REPORT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "status", "triangles before", "triangles after", "open before", "non-manifold before",
                    "flipped before", "open after", "non-manifold after", "flipped after", "seconds", "error"])
        for key in sorted(log):
            r = log[key]
            b, c = r.get("before") or {}, r.get("after") or {}
            w.writerow([key, r["status"], b.get("triangles", ""), c.get("triangles", ""), b.get("open", ""),
                        b.get("nonmanifold", ""), b.get("flipped", ""), c.get("open", ""), c.get("nonmanifold", ""),
                        c.get("flipped", ""), r.get("s", ""), r.get("error", "")])
    counts = {}
    for r in log.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("Finished in %s: %s. Report: %s" % (hms(time.time() - t0), ", ".join("%s %d" % kv for kv in sorted(counts.items())),
                                              target / REPORT))
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
