XIANGQI-FR3 - START HERE
========================

1. Unzip Xiangqi-FR3.zip to a folder you can write to (for example D:\Games).
   Avoid "Program Files" and folders synced by OneDrive.
2. Double-click  Xiangqi-FR3.bat

The first start checks this PC and installs only what is missing:
  - Python 3.12 (for the current user; other Python versions are kept)
  - the project environment .venv312 (libraries already on the PC are reused)
  - missing Python libraries; if a library has a version this project cannot
    use, you are asked before a compatible copy is added for this project
  - viewer files and vision models (already included in this package)
Then the game starts in the normal way (scripts\windows\RUN.bat).
Later starts only re-check and go straight to the game.

Internet is needed only when something has to be downloaded.

Options
  Xiangqi-FR3.bat --setup-only   check and install, do not start
  Xiangqi-FR3.bat --help         show the game's start options
  Xiangqi-FR3.bat --robot        any RUN.bat option is passed through

The physical robot is never moved by setup. Robot mode follows the operator
guide in README.md and docs\guides\START_PROJECT.md.
Setup log of the last check: build\installer\last-check.json
