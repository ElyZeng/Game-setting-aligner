# Game Setting Aligner

> 一款用於擷取、比較與覆蓋遊戲設定的工具  
> A tool to capture, compare, and override game settings

![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Steam%20%7C%20Epic%20%7C%20GOG-orange)

---

## 功能特色 / Features

- 🎮 **多平台支援 / Multi-platform Support**  
  支援 Steam、Epic Games 及 GOG 三大遊戲平台的設定掃描與管理  
  Supports scanning and managing settings for Steam, Epic Games, and GOG

- 🔍 **設定擷取與比較 / Capture & Compare**  
  自動擷取遊戲設定檔，並與建議設定進行比較  
  Automatically captures game config files and compares them with recommended settings

- ✏️ **設定覆蓋與寫入 / Override & Write**  
  可將推薦設定直接覆蓋至遊戲設定檔  
  Allows overriding game config files with recommended settings

- 📤 **設定匯出 / Config Export**  
  支援將目前遊戲設定匯出以供備份或分享  
  Supports exporting current game settings for backup or sharing

- 🌐 **Wiki API 整合 / Wiki API Integration**  
  透過 PCGamingWiki API 自動查詢遊戲建議設定  
  Queries recommended settings via the PCGamingWiki API

- 🖥️ **圖形化介面 / GUI Interface**  
  基於 CustomTkinter 的現代化 GUI，操作直覺友善  
  Modern and intuitive GUI built with CustomTkinter

---

## 系統需求 / Requirements

- **Python:** 3.8 以上 / 3.8 or above
- **作業系統 / OS:** Windows（建議）/ Linux / macOS

### 依賴套件 / Dependencies

| 套件 / Package   | 版本 / Version |
|-----------------|---------------|
| requests        | >= 2.31.0     |
| vdf             | >= 3.4        |
| beautifulsoup4  | >= 4.12.0     |
| customtkinter   | >= 5.2.0      |
| lxml            | >= 4.9.0      |

---

## 安裝方式 / Installation

1. **複製專案 / Clone the repository**

   ```bash
   git clone https://github.com/ElyZeng/Game-setting-aligner.git
   cd Game-setting-aligner
   ```

2. **安裝依賴 / Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

---

## 使用方式 / Usage

啟動圖形化介面 / Launch the GUI:

```bash
python main.py
```

---

## 專案結構 / Project Structure

```
Game-setting-aligner/
├── main.py                     # 入口點，啟動 GUI / Entry point, launches GUI
├── requirements.txt            # 依賴套件清單 / Dependency list
├── LICENSE
├── .gitignore
├── config_manager/             # 設定檔管理模組 / Config file management
│   ├── __init__.py
│   ├── config_exporter.py      # 設定檔匯出 / Config export
│   ├── package.py              # 套件工具 / Package utilities
│   ├── reader.py               # 設定檔讀取 / Config reader
│   └── writer.py               # 設定檔寫入 / Config writer
├── scanner/                    # 平台掃描模組 / Platform scanner
│   ├── __init__.py
│   ├── steam.py                # Steam 遊戲掃描 / Steam game scanner
│   ├── epic.py                 # Epic Games 掃描 / Epic Games scanner
│   └── gog.py                  # GOG 掃描 / GOG scanner
├── gui/                        # 圖形化介面 / Graphical user interface
│   ├── __init__.py
│   └── app.py                  # CustomTkinter GUI 主程式 / Main GUI app
├── wiki_api/                   # Wiki API 整合 / Wiki API integration
│   ├── __init__.py
│   └── pcgamingwiki.py         # PCGamingWiki API 查詢 / PCGamingWiki queries
└── tests/                      # 測試目錄 / Test directory
```

---

## 授權 / License

本專案採用 [MIT License](LICENSE) 授權。  
This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Ely
