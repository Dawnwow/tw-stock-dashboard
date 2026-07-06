# 台股選股儀表板

每日整合台股選股資訊的一頁式儀表板，部署在 GitHub Pages。

**網頁**：https://dawnwow.github.io/tw-stock-dashboard/

## 內容

- **熱門族群**：Yahoo 股市 RSS 新聞關鍵字統計，3 天內 3 則以上新聞的族群亮燈「噴出」
- **精選名單**：注意／處置股 ∩ 族群新聞命中，再剔除量 < 1 萬張或價 < 20 的個股（熱門族群豁免）
- **EBC 交叉參照**：與 EBC 新聞監測重疊的族群標黃
- **剔除清單**：被篩掉的個股與原因，供人工複查

## 檔案結構

| 檔案 | 用途 |
|------|------|
| `index.html` | 儀表板頁面（讀取 `data.js` 渲染） |
| `data.js` | 每日更新的資料檔（由 `fetch_data.py` 產出） |
| `fetch_data.py` | 抓取＋篩選腳本（Python 3 標準庫，零依賴） |

## 每日更新

```bash
python3 fetch_data.py   # 產出 data.js
git add data.js && git commit -m "更新 $(date +%Y-%m-%d) 資料" && git push
```

資料源：Yahoo 股市 RSS、TWSE／TPEx OpenAPI（行情＋注意處置公告）、EBC 監測資料。
