# ett_auto_spectate_simple
A simple tool to follow a user while jumping from one room to another in ETT

*based on https://github.com/jerryfromearth/ett-auto-spectate*

# Introduction

ETT has a tool to enter arenas as guest user spectators to watch ongoing matches.
Unfortunately this feature requires the spectator to click on UI elements to follow the user when they enter each new room.
To solve this problem, the `ett_auto_spectate` script will listen to the server to detect when the user is in a room then will proceed clicking on all the right places of the interface to enter the same room as spectator.

## Configuration (resolution and window offset)

Click positions are defined for 1920×1080 and scaled to your setup. You can set:

- **Resolution**: `--res-x` and `--res-y` (defaults: 1920, 1080). Use your actual game window or screen size.
- **Window offset**: `--offset-x` and `--offset-y` (defaults: 0, 0). If the spectator window is not at the top-left of the screen (e.g. it’s in a specific monitor or position), set the offset to the window’s top-left corner.

Example for a 2560×1440 window with its top-left at (100, 50):

```bash
python spectate.py -u YOURUSERNAME --res-x 2560 --res-y 1440 --offset-x 100 --offset-y 50
```

## Limitations
- Lost matches open a UI Menu that messes up with the automation; press M in ETT from PC if this happens.

# How to use it

  1. (important) start your game on the quest so that you'll enter as main user
  2. start the spectator script from your computer, it should be under "C:\Program Files\Oculus\Software\Software\for-fun-labs-eleven-table-tennis-vr\ElevenStartJust2d.bat"
  3. (important) press shift+0 right upon opening the program to save the default camera position
  4. you can now move your camera around with the usual commands (wasdqe, arrows, clicks)
  5. open a terminal and run the command `python spectate.py -u <YOURUSERNAME>` (add `--res-x`, `--res-y`, `--offset-x`, `--offset-y` if your resolution or window position differs from 1920×1080 at 0,0)
  6. (important) switch back to the spectator app and make sure it's open in full screen

To debug, you can run the script with the `-t` option in which case no clicks will be performed but you can check that the mouse positions are mapped correctly.
