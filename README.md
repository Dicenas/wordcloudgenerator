# WordCloudGenerator

WordCloudGenerator is a portable desktop-style app for creating custom word clouds.

It lets you enter a recipient name, message, custom word list, word weights, shape mask, color palette, and layout settings. The app generates a downloadable PNG that can be printed or shared.

## Download

Go to the latest GitHub Release and download:

`WordCloudGenerator-Windows.zip`

## How to use on Windows

1. Download `WordCloudGenerator-Windows.zip`.
2. Right-click the ZIP file and choose **Extract All**.
3. Open the extracted folder.
4. Double-click `WordCloudGenerator.exe`.
5. The app will open in your browser.

No Python installation is required.

## Features

* Custom weighted word lists
* Built-in and custom color palettes
* Color picker support
* Custom shape masks
* Recipient name and message in the center
* PNG export
* Portable Windows release

## Running from source

Install Python 3.10, then run:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launcher.py
```

## Building the Windows app

```powershell
.\.venv\Scripts\python.exe -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --windowed `
  --name "WordCloudGenerator" `
  --icon "assets/icon.ico" `
  --add-data "streamlit_app.py;." `
  --add-data "masks;masks" `
  --add-data "assets;assets" `
  --collect-data streamlit `
  --collect-submodules streamlit `
  --copy-metadata streamlit `
  --collect-all wordcloud `
  --exclude-module IPython `
  --exclude-module ipykernel `
  --exclude-module jupyter `
  --exclude-module notebook `
  --exclude-module scipy `
  --exclude-module sklearn `
  --exclude-module torch `
  --exclude-module tensorflow `
  --exclude-module cv2 `
  --exclude-module seaborn `
  --exclude-module plotly `
  launcher.py
```
