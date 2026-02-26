# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "click>=8.3.1",
#     "mss>=10.1.0",
#     "numpy>=2.4.2",
#     "opencv-python>=4.13.0.92",
#     "pyautogui>=0.9.54",
#     "pydirectinput>=1.0.4",
#     "pywinauto>=0.6.9",
#     "requests>=2.32.5",
#     "rich>=14.3.3",
# ]
# ///
from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from time import sleep

import click
import cv2
import mss
import numpy as np
import pyautogui
import pywinauto
import requests

SERVER_URL = "http://elevenlogcollector-env.js6z6tixhb.us-west-2.elasticbeanstalk.com/ElevenServerLiteSnapshot"
INTERVAL = 1  # slows down clicking around

# Base resolution the mappings were designed for
BASE_W = 1920
BASE_H = 1080


@dataclass(frozen=True)
class ResolutionConfig:
    """Screen resolution and window offset for scaling click positions."""

    res_x: int
    res_y: int
    offset_x: int
    offset_y: int

    @classmethod
    def from_window_rect(cls, rect: tuple[int, int, int, int]) -> ResolutionConfig:
        """Create config from window rect (left, top, right, bottom)."""
        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
        return cls(res_x=width, res_y=height, offset_x=left, offset_y=top)

    def resolve(self, base_x: int, base_y: int) -> tuple[int, int]:
        """Scale base (1920x1080) coordinates to configured resolution and add offset."""
        # Normalize to 0-1 then scale to current res
        norm_x = base_x / BASE_W
        norm_y = base_y / BASE_H

        x = round(norm_x * self.res_x + self.offset_x)
        y = round(norm_y * self.res_y + self.offset_y)
        return (x, y)

    def normalize(self, abs_x: int, abs_y: int) -> tuple[float, float]:
        """Convert absolute screen coordinates to relative (0.0-1.0) window coordinates."""
        rel_x = abs_x - self.offset_x
        rel_y = abs_y - self.offset_y

        norm_x = rel_x / self.res_x
        norm_y = rel_y / self.res_y
        return (norm_x, norm_y)


# Set by main() from CLI or window detection; used by clickButton
_resolution_config: ResolutionConfig | None = None


def find_window_rect(title_pattern: str = "Eleven") -> tuple[int, int, int, int] | None:
    """Find the game window and return its (left, top, right, bottom) rect."""
    try:
        # Connect to application
        app = pywinauto.Application(backend="uia").connect(title_re=title_pattern)
        window = app.window(title_re=title_pattern)

        if not window.exists():
            print(f"Window matching '{title_pattern}' not found.")
            return None

        # Bring to foreground (optional, but good for focus)
        try:
            window.set_focus()
        except Exception:
            pass  # Might fail if already focused or restricted

        rect = window.rectangle()
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception as e:
        print(f"Error finding window: {e}")
        return None


def is_menu_open(
    res_config: ResolutionConfig,
    template_path: str = "templates_1080p/power_menu_icon.jpg",
) -> bool:
    """Check if the menu is open by matching the power icon template."""
    try:
        with mss.mss() as sct:
            # Capture the window area
            monitor = {
                "top": res_config.offset_y,
                "left": res_config.offset_x,
                "width": res_config.res_x,
                "height": res_config.res_y,
            }
            sct_img = sct.grab(monitor)

            # Convert to numpy array (BGRA) then to BGR for OpenCV
            frame = np.array(sct_img)
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Load template
            template = cv2.imread(template_path)
            if template is None:
                # If template missing, warn once?
                return False

            # If window size differs significantly from 1080p, we might need to resize frame or template
            # For now, assuming template is for 1080p and we might need scaling if window != 1080p
            # But prompt said: "normalizing... using a template... once we measure those normalized coordinates"
            # Let's just do direct match for now or resize frame to 1080p

            target_h, target_w = BASE_H, BASE_W
            if frame_bgr.shape[:2] != (target_h, target_w):
                frame_bgr = cv2.resize(frame_bgr, (target_w, target_h))

            res = cv2.matchTemplate(frame_bgr, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)

            return max_val > 0.8  # Threshold

    except Exception as e:
        print(f"Vision error: {e}")
        return False


def retrieve_url(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        return None


class Position:
    x = 0
    y = 0

    def __init__(self, x, y):
        self.x = x
        self.y = y


mappings = {
    "HOME": Position(600, 900),
    "JOINROOM": Position(1850, 470),
    "EXITROOM": Position(1217, 974),
    "FOCUS": Position(960, 540),  # center of 1920x1080, safe spot to click
}


def _focus_window() -> None:
    """Click center of window to bring it into focus before the sequence."""
    clickButton("FOCUS", move_only=False)


def before_and_after_click(func):
    def wrapper(*args, **kwargs):
        _focus_window()
        sleep(INTERVAL)
        type("M")
        sleep(INTERVAL)
        type("0")
        sleep(INTERVAL)
        func(*args, **kwargs)
        type("M")
        return

    return wrapper


def clickButton(button: str, move_only: bool = False) -> None:
    base = mappings[button]
    if _resolution_config is not None:
        x, y = _resolution_config.resolve(base.x, base.y)
    else:
        x, y = base.x, base.y
    pyautogui.moveTo(x, y)
    if not move_only:
        # pyautogui.click()
        pyautogui.mouseDown()
        sleep(0.05)
        pyautogui.mouseUp()
        print(f"Clicked {button}")
    else:
        print(f"Moved to {x, y}")
        sleep(0.3)


@before_and_after_click
def clickListOfButtons(list_of_buttons, move_only=False):
    for button in (
        list_of_buttons if isinstance(list_of_buttons, list) else [list_of_buttons]
    ):
        clickButton(button, move_only=move_only)
        sleep(INTERVAL)


def joinRoom(test):
    clickListOfButtons("HOME JOINROOM".split())


def exitRoom(test):
    clickListOfButtons("HOME EXITROOM".split())


def type(str):
    print(f"Pressed {str}")
    pyautogui.write(str)


def isInRoom(user):
    try:
        content = json.loads(retrieve_url(SERVER_URL))
    except KeyboardInterrupt:
        raise KeyboardInterrupt
    except:
        warnings.warn("Failed to retrieve data from server.")
        return None
    users = [x for x in content["UsersInRooms"] if x["UserName"] == user]
    if len(users) > 0:
        print(users)
        sys.stdout.flush()
        return True

    sys.stdout.flush()
    return False


def print_mouse(res_config: ResolutionConfig | None = None):
    mouse_position = pyautogui.position()

    if res_config:
        # Check if inside window
        if (
            res_config.offset_x
            <= mouse_position[0]
            < res_config.offset_x + res_config.res_x
            and res_config.offset_y
            <= mouse_position[1]
            < res_config.offset_y + res_config.res_y
        ):

            norm_x, norm_y = res_config.normalize(mouse_position[0], mouse_position[1])
            menu_status = "OPEN" if is_menu_open(res_config) else "CLOSED"
            print(
                f"Mouse: {norm_x:.4f}, {norm_y:.4f} (Norm) | Menu: {menu_status} | Pos: {mouse_position[0]}, {mouse_position[1]}",
                end="",
            )
        else:
            print(
                f"Mouse: OUTSIDE | Pos: {mouse_position[0]}, {mouse_position[1]}",
                end="",
            )
    else:
        print(f"Mouse: {mouse_position[0]:04d}, {mouse_position[1]:04d}", end="")
    sys.stdout.write("\r")


@click.command()
@click.option(
    "--test", "-t", is_flag=True, default=False, help="Whether to avoid clicks"
)
@click.option("--user", "-u", help="Username", required=True)
@click.option(
    "--res-x",
    default=BASE_W,
    type=int,
    help="Target screen/window width (default: 1920)",
)
@click.option(
    "--res-y",
    default=BASE_H,
    type=int,
    help="Target screen/window height (default: 1080)",
)
@click.option(
    "--offset-x",
    default=0,
    type=int,
    help="X offset of the active window (e.g. if window is not at 0)",
)
@click.option("--offset-y", default=0, type=int, help="Y offset of the active window")
def main(
    user: str, test: bool, res_x: int, res_y: int, offset_x: int, offset_y: int
) -> None:
    global _resolution_config

    # Initial config from CLI (fallback)
    _resolution_config = ResolutionConfig(
        res_x=res_x, res_y=res_y, offset_x=offset_x, offset_y=offset_y
    )

    print("Starting spectator bot...")

    # Try to find window immediately to update config
    window_rect = find_window_rect()
    if window_rect:
        print(f"Found 'Eleven' window at {window_rect}")
        _resolution_config = ResolutionConfig.from_window_rect(window_rect)
    else:
        print("Window 'Eleven' not found. Using CLI/default resolution config.")

    # it assumes that menu is off in the UI

    while True:
        # Periodically ensure window is found/focused if we want strict window management
        # For now, just re-check if we suspect issues, or stick to initial config.
        # But the plan said "Loop: Find/Ensure window is focused."

        # Let's try to find/focus window every iteration to be robust?
        # Might be too spammy to print "Found window" every time.
        # But we should ensure focus.

        # We can implement a lightweight "ensure focus" here or just let the tool run.
        # Given "Main loop to report mouse position... Check Menu State", let's do that.

        print(f"Waiting until {user} is in a room...")
        inRoom = False
        while not inRoom:
            inRoom = isInRoom(user)
            print_mouse(_resolution_config)
            sleep(INTERVAL)

        # Clear line after loop
        print(" " * 80)
        print(f"User {user} is in a room!", end="\n")
        print("Joining room.")

        # Ensure window is fresh before joining
        rect = find_window_rect()
        if rect:
            _resolution_config = ResolutionConfig.from_window_rect(rect)

        joinRoom(test)

        while inRoom or inRoom is None:
            inRoom = isInRoom(user)
            print_mouse(_resolution_config)
            sleep(INTERVAL)

        print(" " * 80)
        print(f"User {user} is no longer in a room.")
        print("Leaving room.")
        exitRoom(test)


if __name__ == "__main__":
    main(sys.argv[1:])
