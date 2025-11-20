# 機房氣冷顯熱守恆可視化 Extension（Omniverse Kit）

本專案基於 NVIDIA Omniverse **Kit App Template**，實作一個自訂的 Kit App 與 Python UI Extension，用於機房機櫃（rack）氣冷情境下，依照顯熱守恆公式：

\[
P=m*cp*ΔT
\]

對每個 rack 計算溫差或所需質量流率，並以顏色將狀態可視化（綠 / 黃 / 紅）。


---

## 1. 專案目的與需求對應

需求簡述：

- 在 Omniverse Kit template 中 build 一個 **Kit Editor App**
- 實作一個 **Extension** 加入 Editor 中，提供 UI 面板讓使用者：
  - 模式
    - 設計模式：輸入每個 rack 的總耗能與目標 ΔT     
    - 稽核模式：輸入每個 rack 的總耗能與實際M
  - 每 rack (可用簡單cube示意)欄位（USD 屬性）
    - user:rackPowerW（W，必填）
    - user:mdotActual（kg/s，稽核模式用）
    - 以上屬性需可批次填寫且寫入 USD
  - 顏色視覺化
    - 溫差視圖：以 ΔT將物件上色，並制定一個目標，如小於目標為綠色、等於目標為黃色、大於目標為紅色
  - 體驗
    - 即時更新（改任何數值立即重算與改色）
    - 一鍵啟用/停用顏色覆蓋（不影響屬性值）

---

## 2. 專案結構與命名

本專案沿用 Kit App Template 的標準結構，與本題相關的主要檔案如下：

```text
source/
  apps/
    my_company.my_editor.kit                 # 自訂 Kit App
  extensions/
    my_company.my_python_ui_extension/
      config/
        config.toml                          # Extension 套件
      my_company/
        my_python_ui_extension/
          extension.py                       # 主要 Python UI Extension 實作
      data/
      docs/
      premake5.lua
