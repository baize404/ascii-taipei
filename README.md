# ascii-taipei 🌃

A night view of Taipei drawn stage by stage with coloured ASCII characters, right in your terminal.

用彩色 ASCII 字元一筆一筆畫出台北夜景：觀音山、淡水河、圓山大飯店、摩天輪、捷運，最後 101 倒數、放跨年煙火。直接在終端機裡跑。

<img src="preview.png" width="360" alt="ASCII Taipei preview">

▶ [preview.mp4](preview.mp4)（39 秒，9:16）

## 終端機版 / Terminal

```bash
pip install numpy
python taipei.py                    # Ctrl+C 結束
python taipei.py --at 24            # 直接從倒數開始看
python taipei.py --speed 1.5 --fps 24
python taipei.py --256              # 不支援 24-bit 色彩的終端機
```

需要支援 24-bit 色彩的終端機（Windows Terminal、VS Code、iTerm2、macOS Terminal 都可以）。視窗至少 120×40，字體調小一點效果最好。

## 錄成影片 / Record a video

```bash
pip install numpy pillow            # 另外需要 ffmpeg
python taipei.py --record taipei.mp4 --tag @yourname
python taipei.py --record still.png --at 33     # 只存一張圖
```

預設輸出 1080×1920 的直式影片，整個畫面都是夜景。其他選項：

- `--code`：畫面下方加一個編輯器，把 `taipei.py` 一行一行打出來
- `--no-hud`：拿掉左上角的階段和時間（終端機版也能用）
- `--size 1920x1080 --cols 160`：改成橫式

## 動畫流程 / Timeline

整段 39 秒，會一直循環。

| 秒 | 階段 |
| --- | --- |
| 0–3 | 星空出現，月亮從山後升起 |
| 1.5–5 | 觀音山從左邊畫過來 |
| 4–7 | 淡水河 |
| 6–11 | 市區大樓往上長，摩天輪轉起來 |
| 10–13.5 | 圓山大飯店：紅柱子、金色雙層屋頂 |
| 13–18 | 台北 101 從底座一節一節蓋上去 |
| 18–21.5 | 窗戶亮燈，101 由下往上亮成彩虹色 |
| 21.5–24 | 捷運高架橋和列車，劃過一顆流星 |
| 24–29 | 101 外牆倒數 5、4、3、2、1 |
| 29–36.5 | 101 兩側噴出煙火，滿天煙火，打出 HAPPY NEW YEAR |
| 37–39 | 淡出，重新開始 |

## 原理 / How it works

1. 場景依終端機大小先建成好幾層：山、大樓、窗戶、飯店、101、高架橋。每一格存一個字元、一個顏色和一個「出現順序」（0 到 1）。
2. 時間軸把整段分成幾個階段。階段進度到 p 時，只顯示順序 ≤ p 的格子，所以山會從左往右掃過來、大樓往上長、101 一層一層蓋。剛出現的格子會先閃一下白光，像筆尖在畫。
3. 星星、月亮、摩天輪、捷運、流星和煙火每一幀重新計算。最後河面把上方亮著的東西鏡射下來，再用波浪打散成 `|` `!` `:`。
4. 每一幀用 24-bit ANSI 色碼輸出。錄影模式則把每個字元貼成圖片，加上光暈，再交給 ffmpeg 編碼。

Inspired by an ASCII-art reel on Instagram; this is an independent implementation.
