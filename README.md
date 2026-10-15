# PDF 轉 Markdown（英文論文專用）

把英文學術論文 PDF 批次轉成 Markdown（.md），方便丟給 ChatGPT、Claude 等 AI 閱讀。
連沒有文字層的掃描檔也能轉，全部在自己的電腦上用 NVIDIA 顯示卡運算，**檔案不會上傳到任何地方**。

*Batch-convert English academic PDFs (including scanned ones) to Markdown locally with [Nougat](https://github.com/facebookresearch/nougat) on your own NVIDIA GPU, through a simple browser UI. Windows only.*

## 功能

- 把 PDF 拖進網頁就開始轉換，可一次放很多個
- 公式轉成 LaTeX（例如 `\(10^{3}\)`、`\frac{1}{4}`），章節標題有層級
- **數字核對**：Nougat 偶爾會整個略過表格。有文字層的 PDF 會逐頁比對數字，疑似漏掉的頁面會加上「⚠ 第 N 頁」警告並附上原始文字
- 每頁開頭有 `<!-- page N -->` 頁碼標記，方便引用
- 轉好的檔案可單獨下載、打包成 zip 下載，也會自動存到「輸出」資料夾

## 系統需求

| 項目 | 需求 |
|---|---|
| 作業系統 | Windows 10 / 11 |
| 顯示卡 | NVIDIA 顯示卡，顯示記憶體 4 GB 以上（建議 6 GB）。沒有也能執行，但掃描檔會非常慢 |
| 軟體 | [Anaconda](https://www.anaconda.com/download) 或 Miniconda |
| 硬碟空間 | 約 6 GB |

## 安裝（只需要做一次）

1. 安裝 [Anaconda](https://www.anaconda.com/download)，安裝時選「Just Me」。
2. 在本頁上方點綠色的「Code」→「Download ZIP」，解壓縮到你想放的位置（例如桌面）。
3. 打開解壓縮後的資料夾，點兩下 **`首次安裝.bat`**。
4. 等待安裝完成，約 10～30 分鐘，會下載約 3 GB。完成後桌面會出現「PDF轉MD」捷徑。

## 使用方式

1. 點兩下桌面的 **「PDF轉MD」**。會出現一個黑色視窗（使用期間不要關掉），瀏覽器會自動打開轉檔網頁。
2. 把 PDF 拖進虛線框，或點一下選擇檔案。放進去就會開始轉換。
3. 完成後點「下載 .md」，或「全部下載（.zip）」。結果也會存在資料夾裡的「輸出」。
4. 用完後關掉黑色視窗即可。

第一個檔案要多等約 30 秒載入模型，之後每頁約 2～5 秒（依顯示卡而定）。

### 選項

| 選項 | 說明 |
|---|---|
| 辨識方式 | 預設「GPU 辨識＋數字核對」。「快速」模式直接抽取 PDF 文字層，幾秒就完成，但公式、上標、分數會跑掉（例如 10³ 變成 103） |
| 模型 | 預設 small。base 公式較準，第一次使用會再下載約 1.3 GB |
| 每批頁數 | 顯示記憶體不足時改小 |

### 看懂轉換結果

- **橘色「第 N 頁可能有遺漏」**：那一頁的表格可能沒轉出來。打開 .md 找「⚠ 第 N 頁」，後面附的原始文字中數字是對的，但表格欄位可能錯位。
- **`[MISSING_PAGE…]`**：掃描檔的那一頁辨識失敗，可改用 base 模型重轉。

## 限制

- **只適合英文**（以及其他拉丁字母文字）學術文件。中文、日文等效果很差。
- 圖片不會轉出。
- Nougat 偶爾會在看不清楚的地方產生看似合理但錯誤的內容。**引用任何數字前，請回到 PDF 核對**，特別是表格和公式。
- 沒有文字層的掃描檔無法做數字核對。

## 常見問題

<details>
<summary>安裝時出現 <code>WinError 4551 應用程式控制原則已封鎖此檔案</code></summary>

Windows 11 的「智慧型應用程式控制」封鎖了 PyTorch。到「Windows 安全性」→「應用程式與瀏覽器控制」→「智慧型應用程式控制設定」改為關閉。注意：關閉後可能無法直接開回。學校或公司管理的電腦無法自行解除。
</details>

<details>
<summary>網頁顯示「找不到可用的 GPU」</summary>

確認電腦有 NVIDIA 顯示卡，並已安裝最新的 NVIDIA 驅動程式，然後重新點兩下 `首次安裝.bat`。
</details>

<details>
<summary>轉換時出現「顯示記憶體不足」</summary>

程式會自動減少每批頁數重試。若仍失敗，把「每批頁數」改成 1，並關掉其他使用顯示卡的程式（遊戲、影片剪輯等）。
</details>

<details>
<summary>Anaconda 裝在特殊位置，程式找不到</summary>

在本資料夾建立 `env_path.txt`，內容寫環境資料夾的完整路徑，例如 `D:\anaconda3\envs\pdf2md`。
</details>

## 授權

- 本專案程式碼：[MIT License](LICENSE)
- 本工具使用 Meta 的 [Nougat](https://github.com/facebookresearch/nougat)。Nougat 程式碼為 MIT 授權，**模型權重為 [CC-BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)，僅限非商業用途**。模型不包含在本專案中，安裝時才從 Nougat 官方下載。
- 請只轉換你有權使用的文件。轉出的內容仍屬原作者所有。
