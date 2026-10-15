"""
首次安裝：建立 Python 3.10 環境並安裝 Nougat 與 GPU 版 PyTorch。
由「首次安裝.bat」以 Anaconda 內建的 Python 執行，只使用標準函式庫。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_NAME = "pdf2md"
HERE = Path(__file__).resolve().parent
CONDA_BASE = Path(sys.executable).resolve().parent
TORCH = ["torch==2.5.1", "torchvision==0.20.1",
         "--index-url", "https://download.pytorch.org/whl/cu124"]


def step(n, total, msg):
    print(f"\n[{n}/{total}] {msg}", flush=True)


def run(cmd):
    print("  > " + " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd])
    if r.returncode != 0:
        raise SystemExit(f"\n安裝失敗（上面那一步出錯，代碼 {r.returncode}）。"
                         "請把這個視窗的訊息截圖，到 GitHub 的 Issues 回報。")


def find_conda():
    for p in (CONDA_BASE / "Scripts" / "conda.exe", CONDA_BASE / "condabin" / "conda.bat"):
        if p.exists():
            return p
    found = shutil.which("conda")
    if found:
        return Path(found)
    raise SystemExit("找不到 conda。請確認已安裝 Anaconda 或 Miniconda。")


def make_shortcut():
    desktop = Path(os.environ.get("USERPROFILE", "~")).expanduser() / "Desktop"
    if not desktop.exists():
        return False
    target = HERE / "PDF轉MD.bat"
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
        "$s.TargetPath=$env:TGT;$s.WorkingDirectory=$env:WD;"
        "$s.IconLocation='C:\\Windows\\System32\\imageres.dll,2';$s.Save()"
    )
    env = dict(os.environ, LNK=str(desktop / "PDF轉MD.lnk"), TGT=str(target), WD=str(HERE))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env)
    return r.returncode == 0


def main():
    total = 6
    print("=" * 56)
    print(" PDF 轉 Markdown：首次安裝")
    print(" 會下載約 3 GB，需要 10～30 分鐘，視網路速度而定。")
    print("=" * 56)

    conda = find_conda()
    env_dir = CONDA_BASE / "envs" / ENV_NAME
    py = env_dir / "python.exe"

    step(1, total, f"建立 Python 3.10 環境「{ENV_NAME}」")
    if py.exists():
        print("  環境已存在，略過建立。")
    else:
        # 使用 conda-forge，避免 Anaconda 預設頻道要求同意服務條款而中斷
        run([conda, "create", "-n", ENV_NAME, "python=3.10", "-y",
             "--override-channels", "-c", "conda-forge"])
    if not py.exists():
        raise SystemExit(f"找不到 {py}，環境建立可能失敗。")

    step(2, total, "安裝 PyTorch（GPU 版，約 2.5 GB）")
    run([py, "-m", "pip", "install", "--no-warn-script-location", *TORCH])

    step(3, total, "安裝 Nougat 與相關套件")
    run([py, "-m", "pip", "install", "--no-warn-script-location", "-r", HERE / "requirements.txt"])

    step(4, total, "檢查顯示卡")
    r = subprocess.run([str(py), "-c",
                        "import torch;print('OK' if torch.cuda.is_available() else 'NO');"
                        "print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
                       capture_output=True, text=True)
    lines = (r.stdout or "").split("\n")
    if r.returncode != 0:
        print(r.stderr[-1500:])
        if "4551" in (r.stderr or ""):
            print("\n  Windows「智慧型應用程式控制」封鎖了 PyTorch，請見 README 的常見問題。")
        raise SystemExit("\nPyTorch 無法載入，安裝未完成。")
    if lines[0].strip() == "OK":
        print(f"  找到顯示卡：{lines[1].strip()}")
    else:
        print("  沒有找到可用的 NVIDIA 顯示卡。仍可使用，但掃描檔會非常慢。")

    step(5, total, "下載 Nougat 模型（約 250 MB）")
    run([py, "-c", "from nougat.utils.checkpoint import get_checkpoint;"
                   "print(get_checkpoint(None, model_tag='0.1.0-small'))"])

    step(6, total, "完成設定")
    (HERE / "env_path.txt").write_text(str(env_dir), encoding="utf-8")
    if make_shortcut():
        print("  已在桌面建立「PDF轉MD」捷徑。")

    print("\n" + "=" * 56)
    print(" 安裝完成！之後點兩下桌面的「PDF轉MD」即可使用。")
    print("=" * 56)


if __name__ == "__main__":
    main()
