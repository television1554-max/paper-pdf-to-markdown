"""
PDF 轉 Markdown 本機工具
- 預設：每頁用 Nougat 在本機 GPU 辨識（公式、上標、表格較正確），
  有文字層時逐頁核對數字，疑似漏掉表格的頁面附上原始文字
- 快速模式：有文字層就直接抽取文字（快，但公式、上標、分數會跑掉）
只使用 Python 內建模組架設網頁，不另外安裝套件，以免影響 nougat 環境的固定版本。
"""
import io
import json
import logging
import os
import queue
import re
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from collections import Counter
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

HOST, PORT = "127.0.0.1", 7860
BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "輸出"
TMP_DIR = BASE / "_暫存"
MODELS = {"small": "0.1.0-small", "base": "0.1.0-base"}

# 判斷「有文字層」的門檻：至少八成頁面各有 100 個以上非空白字元
TEXT_MIN_CHARS = 100
TEXT_PAGE_RATIO = 0.8

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("pdf2md")
log.setLevel(logging.INFO)

jobs = {}          # id -> dict
order = []         # 顯示順序
lock = threading.Lock()
work_q = queue.Queue()
gpu_info = {"name": None, "model": None, "loading": False}


# ---------- 工作狀態 ----------

def update(job_id, **kw):
    with lock:
        if job_id in jobs:
            jobs[job_id].update(kw)


def safe_stem(name):
    stem = Path(name).stem
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).strip(" .")
    return stem or "untitled"


# ---------- 文字層抽取 ----------

def page_texts(pdf_path):
    import pypdfium2
    pdf = pypdfium2.PdfDocument(str(pdf_path))
    try:
        out = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            out.append(tp.get_text_range())
            tp.close()
            page.close()
        return out
    finally:
        pdf.close()


def has_text_layer(texts):
    if not texts:
        return False
    good = sum(1 for t in texts if len(re.sub(r"\s", "", t)) >= TEXT_MIN_CHARS)
    return good / len(texts) >= TEXT_PAGE_RATIO


def clean_text(t):
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\x02", "")   # 行尾斷字符號：frame\x02work → framework
    t = t.replace("\x00", "")
    # 其他控制字元多半是數學字型無法對應的符號，標成 � 讓人知道這裡有東西
    t = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f￾￿]", "�", t)
    return re.sub(r"[ \t]+\n", "\n", t)


def _line_key(line):
    return re.sub(r"\d+", "#", line.strip().lower())


def clean_pages(texts):
    """清理每頁文字，並刪除頁首頁尾（多頁重複出現在頁面頭尾兩行的內容，及單獨的頁碼）。"""
    pages = [clean_text(t).split("\n") for t in texts]
    edges = []
    count = Counter()
    for lines in pages:
        idx = [i for i, l in enumerate(lines) if l.strip()]
        edge = set(idx[:2] + idx[-2:])
        edges.append(edge)
        count.update({_line_key(lines[i]) for i in edge})
    threshold = max(3, len(pages) * 0.3)
    running = {k for k, v in count.items() if k and v >= threshold}
    out = []
    for lines, edge in zip(pages, edges):
        kept = [l for i, l in enumerate(lines)
                if not (i in edge and (_line_key(l) in running or re.fullmatch(r"\d{1,4}", l.strip())))]
        out.append("\n".join(kept).strip())
    return out


def page_marker(n):
    return f"<!-- page {n} -->"


def texts_to_md(texts):
    parts = [f"{page_marker(i + 1)}\n\n{p}" for i, p in enumerate(clean_pages(texts)) if p]
    md = "\n\n".join(parts)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


# ---------- GPU 結果核對 ----------
# Nougat 偶爾會整個略過表格，或卡在重複迴圈。有文字層時逐頁比對小數：
# 文字層有、辨識結果卻沒有的小數太多，就把該頁原始文字附在後面。

DECIMAL = re.compile(r"\d+\.\d+")
MISS_MIN = 12       # 至少缺 12 個小數
MISS_RATIO = 0.5    # 且超過該頁小數的一半


def missing_decimals(text, pred):
    want = Counter(DECIMAL.findall(text))
    got = Counter(DECIMAL.findall(pred))
    return sum((want - got).values()), sum(want.values())


def has_repetition(pred):
    segs = [s.strip() for s in re.split(r"\n|\\\\", pred)]
    segs = [s for s in segs if len(s) >= 15]
    return bool(segs) and Counter(segs).most_common(1)[0][1] >= 10


def fallback_block(n, reason, text):
    fence = "````"
    return (f"> ⚠ 第 {n} 頁：{reason}以下附上該頁 PDF 原始文字層，數字以此為準；"
            f"表格欄位可能錯位，引用前請對照 PDF。\n\n{fence}text\n{text}\n{fence}")


# ---------- Nougat ----------

_model = None
_model_tag = None


def get_model(tag):
    global _model, _model_tag
    if _model is not None and _model_tag == tag:
        return _model
    import torch
    from nougat import NougatModel
    from nougat.utils.checkpoint import get_checkpoint
    from nougat.utils.device import move_to_device

    gpu_info["loading"] = True
    try:
        if _model is not None:
            _model = None
            torch.cuda.empty_cache()
        ckpt = get_checkpoint(None, model_tag=tag)  # 第一次使用會自動下載
        model = NougatModel.from_pretrained(ckpt)
        model = move_to_device(model, bf16=True, cuda=torch.cuda.is_available())
        model.eval()
        _model, _model_tag = model, tag
        gpu_info["model"] = tag
        return model
    finally:
        gpu_info["loading"] = False


def nougat_convert(job_id, pdf_path, tag, batch, texts):
    update(job_id, message="載入模型中（第一次較久）…" if _model_tag != tag else "準備頁面中…")
    import torch
    from nougat.postprocessing import markdown_compatible
    from nougat.utils.dataset import LazyDataset

    model = get_model(tag)
    while True:
        try:
            preds = _nougat_run(job_id, model, pdf_path, batch, torch, LazyDataset)
            return assemble(preds, texts, markdown_compatible)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            if batch <= 1:
                raise RuntimeError("顯示記憶體不足，每批 1 頁仍無法執行")
            batch = max(1, batch // 2)
            log.info("顯示記憶體不足，改為每批 %d 頁重試", batch)
            update(job_id, done=0, message=f"記憶體不足，改為每批 {batch} 頁重試…")


def _nougat_run(job_id, model, pdf_path, batch, torch, LazyDataset):
    dataset = LazyDataset(pdf_path, partial(model.encoder.prepare_input, random_padding=False))
    total = dataset.size
    update(job_id, total=total, done=0, message="轉換頁面影像並辨識中…")
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=batch, shuffle=False,
        collate_fn=LazyDataset.ignore_none_collate,
    )
    preds = []
    for sample, _ in loader:
        if sample is None:
            continue
        with torch.inference_mode():
            output = model.inference(image_tensors=sample, early_stopping=False)
        preds.extend(output["predictions"])
        update(job_id, done=min(len(preds), total))
    return preds


def assemble(preds, texts, markdown_compatible):
    """組合每頁結果，並逐頁核對。回傳 (markdown, 失敗頁數, 需注意的頁碼)。"""
    pages = clean_pages(texts) if texts and len(texts) == len(preds) else [""] * len(preds)
    parts, failed, flagged = [], 0, []
    for n, (pred, text) in enumerate(zip(preds, pages), start=1):
        has_text = len(re.sub(r"\s", "", text)) >= TEXT_MIN_CHARS
        if pred.strip() == "[MISSING_PAGE_POST]":
            if has_text:
                flagged.append(n)
                body = fallback_block(n, "GPU 辨識失敗。", text)
            else:
                failed += 1
                body = f"[MISSING_PAGE_EMPTY:{n}]"
        else:
            body = markdown_compatible(pred).strip()
            miss, total = missing_decimals(text, pred)
            if has_text and miss >= MISS_MIN and miss > total * MISS_RATIO:
                flagged.append(n)
                body += "\n\n" + fallback_block(
                    n, f"GPU 辨識結果可能漏掉表格或數字（原文 {total} 個小數，辨識結果缺 {miss} 個）。", text)
            elif has_repetition(pred):
                flagged.append(n)
                reason = "GPU 辨識結果出現重複迴圈，內容可能不完整。"
                body += "\n\n" + (fallback_block(n, reason, text) if has_text
                                  else f"> ⚠ 第 {n} 頁：{reason}請對照 PDF。")
        parts.append(f"{page_marker(n)}\n\n{body}")
    md = re.sub(r"\n{3,}", "\n\n", "\n\n".join(parts)).strip() + "\n"
    return md, failed, flagged


# ---------- 背景工作 ----------

def worker():
    while True:
        job_id = work_q.get()
        with lock:
            job = dict(jobs.get(job_id, {}))
        if not job:
            continue
        pdf_path = Path(job["tmp"])
        t0 = time.time()
        try:
            update(job_id, state="running", message="讀取文字層…")
            try:
                texts = page_texts(pdf_path)
            except Exception as e:
                raise RuntimeError(f"無法開啟 PDF（檔案可能損壞或加密）：{e}")
            if job["mode"] == "fast" and has_text_layer(texts):
                update(job_id, method="文字層", total=len(texts), done=len(texts))
                md, failed, flagged = texts_to_md(texts), 0, []
            else:
                update(job_id, method="GPU 辨識")
                md, failed, flagged = nougat_convert(
                    job_id, pdf_path, MODELS[job["model"]], job["batch"], texts)

            OUT_DIR.mkdir(exist_ok=True)
            out = OUT_DIR / (safe_stem(job["name"]) + ".md")
            out.write_text(md, encoding="utf-8", newline="\n")
            note = f"；{failed} 頁辨識失敗" if failed else ""
            if flagged:
                note += f"；第 {'、'.join(map(str, flagged))} 頁可能有遺漏，已附原文，請對照 PDF"
            update(job_id, state="done", out=str(out), failed=failed + len(flagged),
                   message=f"完成（{time.time() - t0:.0f} 秒{note}）")
            log.info("完成：%s", out.name)
        except Exception as e:
            log.exception("失敗：%s", job.get("name"))
            update(job_id, state="error", message=str(e) or e.__class__.__name__)
        finally:
            try:
                pdf_path.unlink()
            except OSError:
                pass


# ---------- 網頁伺服器 ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _attachment(self, data, filename, ctype):
        ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
        disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
        self._send(200, data, ctype, {"Content-Disposition": disp})

    def do_GET(self):
        url = urlparse(self.path)
        p = url.path
        if p in ("/", "/index.html"):
            self._send(200, (BASE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif p == "/api/status":
            with lock:
                items = [{k: jobs[i][k] for k in ("id", "name", "state", "method", "done",
                                                  "total", "message", "failed")}
                         for i in order if i in jobs]
            self._send(200, {"jobs": items, "gpu": gpu_info["name"],
                             "model": gpu_info["model"], "out_dir": str(OUT_DIR)})
        elif p.startswith("/api/download/"):
            job_id = p.rsplit("/", 1)[-1]
            with lock:
                job = jobs.get(job_id)
            if not job or job["state"] != "done" or not Path(job["out"]).exists():
                return self._send(404, {"error": "找不到檔案"})
            out = Path(job["out"])
            self._attachment(out.read_bytes(), out.name, "text/markdown; charset=utf-8")
        elif p == "/api/zip":
            with lock:
                outs = [Path(jobs[i]["out"]) for i in order
                        if i in jobs and jobs[i]["state"] == "done"]
            outs = [o for o in outs if o.exists()]
            if not outs:
                return self._send(404, {"error": "沒有已完成的檔案"})
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for o in dict.fromkeys(outs):
                    z.write(o, o.name)
            self._attachment(buf.getvalue(), time.strftime("markdown_%Y%m%d_%H%M%S.zip"),
                             "application/zip")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        p = url.path
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if p == "/api/upload":
            name = q.get("name", "upload.pdf")
            mode = q.get("mode") if q.get("mode") in ("gpu", "fast") else "gpu"
            model = q.get("model") if q.get("model") in MODELS else "small"
            try:
                batch = max(1, min(8, int(q.get("batch", "4"))))
            except ValueError:
                batch = 4
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return self._send(400, {"error": "空檔案"})
            TMP_DIR.mkdir(exist_ok=True)
            job_id = uuid.uuid4().hex
            tmp = TMP_DIR / f"{job_id}.pdf"
            with open(tmp, "wb") as f:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            with open(tmp, "rb") as f:
                magic = f.read(1024)
            if b"%PDF-" not in magic:
                tmp.unlink()
                return self._send(400, {"error": "不是 PDF 檔"})
            with lock:
                jobs[job_id] = {"id": job_id, "name": name, "state": "queued", "method": "",
                                "done": 0, "total": 0, "message": "等待中", "failed": 0,
                                "tmp": str(tmp), "out": "", "mode": mode, "model": model,
                                "batch": batch}
                order.append(job_id)
            work_q.put(job_id)
            self._send(200, {"id": job_id})
        elif p == "/api/clear":
            with lock:
                for i in [i for i in order if jobs[i]["state"] in ("done", "error")]:
                    order.remove(i)
                    jobs.pop(i, None)
            self._send(200, {"ok": True})
        elif p == "/api/open_folder":
            OUT_DIR.mkdir(exist_ok=True)
            os.startfile(str(OUT_DIR))
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})


def detect_gpu():
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info["name"] = torch.cuda.get_device_name(0)
        else:
            gpu_info["name"] = ""
    except Exception:
        gpu_info["name"] = ""


def is_this_tool(port):
    """該連接埠上跑的是不是本工具（而不是其他程式）。"""
    from urllib.request import urlopen
    try:
        with urlopen(f"http://{HOST}:{port}/api/status", timeout=2) as r:
            return json.loads(r.read().decode("utf-8")).get("out_dir") == str(OUT_DIR)
    except Exception:
        return False


def main():
    server = None
    for port in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer((HOST, port), Handler)
            break
        except OSError:
            if is_this_tool(port):
                url = f"http://{HOST}:{port}"
                print(f"工具已經在執行，直接開啟 {url}")
                webbrowser.open(url)
                return
    if server is None:
        raise SystemExit(f"連接埠 {PORT}～{PORT + 19} 都被占用，無法啟動。")
    url = f"http://{HOST}:{port}"
    OUT_DIR.mkdir(exist_ok=True)
    TMP_DIR.mkdir(exist_ok=True)
    for f in TMP_DIR.glob("*.pdf"):  # 清掉上次未完成的暫存
        try:
            f.unlink()
        except OSError:
            pass
    threading.Thread(target=detect_gpu, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    print("=" * 50)
    print(f" PDF 轉 Markdown 工具已啟動：{url}")
    print(f" 輸出資料夾：{OUT_DIR}")
    print(" 使用完畢直接關閉這個視窗即可。")
    print("=" * 50)
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
