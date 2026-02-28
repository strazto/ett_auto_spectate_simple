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
import pydirectinput
import pyautogui
import pywinauto
import requests

SERVER_URL = "http://elevenlogcollector-env.js6z6tixhb.us-west-2.elasticbeanstalk.com/ElevenServerLiteSnapshot"
INTERVAL = 0.2  # slows down clicking around

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

    def resolve(self, norm_x: float, norm_y: float) -> tuple[int, int]:
        """Scale normalized (0.0-1.0) coordinates to configured resolution and add offset."""
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
        except KeyboardInterrupt:
            raise KeyboardInterrupt
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
                return False

            # Resize frame to 1080p for matching if needed
            target_h, target_w = BASE_H, BASE_W
            if frame_bgr.shape[:2] != (target_h, target_w):
                frame_bgr = cv2.resize(frame_bgr, (target_w, target_h))

            res = cv2.matchTemplate(frame_bgr, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)

            return max_val > 0.8  # Threshold
    except KeyboardInterrupt:
        raise KeyboardInterrupt
    except Exception as e:
        print(f"Vision error: {e}")
        return False


def retrieve_url(url):
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
        return response.text
    else:
        warnings.warn(f"Server returned status code {response.status_code}")
        warnings.warn(f"Server returned {response.text}")
        return None


class Position:
    x: float
    y: float

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


mappings = {
    "FRIEND_0": Position(0.8453, 0.4148),
    "JOIN_SELECTED": Position(0.8161, 0.7370),
    "FOCUS_CORNER": Position(0.05, 0.05),
    "LEAVE_ROOM": Position(0.3724, 0.8370),
    "CONFIRM_LEAVE": Position(0.4203, 0.6898),
    "DISMISS_RANKED": Position(0.5473, 0.6954),
}


def _focus_window() -> None:
    """Click corner of window to bring it into focus before the sequence."""
    clickButton("FOCUS_CORNER", move_only=False)

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
        # Fallback if no config (shouldn't happen in loop)
        x, y = int(base.x * BASE_W), int(base.y * BASE_H)

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


def ensure_menu_state(
    res_config: ResolutionConfig, target_open: bool, timeout: int = 5
) -> bool:
    """Ensure menu is in the target state (open/closed). Returns True if successful."""
    _focus_window()
    # Reset camera
    type("0")
    sleep(INTERVAL)
    # First check
    if is_menu_open(res_config) == target_open:
        return True

    # Toggle M
    type("M")
    sleep(INTERVAL)

    # Check again with retries
    for _ in range(timeout):
        if is_menu_open(res_config) == target_open:
            return True
        sleep(INTERVAL)

    return False


def joinRoom(test: bool) -> None:
    if _resolution_config is None:
        print("Cannot join room: Window not found/configured.")
        return

    # 1. Ensure focus
    _focus_window()
    sleep(INTERVAL)

    # 2. Reset menu state (ensure closed first)
    print("Ensuring menu is CLOSED...")
    if not ensure_menu_state(_resolution_config, target_open=False):
        print("Failed to close menu! Attempting to proceed anyway...")

    # 3. Open menu
    print("Opening menu...")
    type("M")
    sleep(INTERVAL)
    if not is_menu_open(_resolution_config):
        print("Menu did not open! Retrying...")
        type("M")
        sleep(1.0)

    # 4. Select friend
    if not test:
        clickButton("FRIEND_0")
        sleep(1.0)

    # 5. Join
    if not test:
        clickButton("JOIN_SELECTED")
        sleep(1.0)
        # Change camera so spectator isnt distracting
        type("9")
    else:
        print("Test mode: Skipping clicks for FRIEND_0 and JOIN_SELECTED")


def exitRoom(test: bool) -> None:
    # Just ensure menu is closed for now
    if _resolution_config:
        ensure_menu_state(_resolution_config, target_open=True)
        clickButton("LEAVE_ROOM")
        sleep(INTERVAL)
        clickButton("CONFIRM_LEAVE")
        sleep(INTERVAL)
        clickButton("DISMISS_RANKED")
        sleep(INTERVAL)


def type(str):
    print(f"Pressed {str}")
    pyautogui.write(str)


def isInRoom(user):
    try:
        resp = retrieve_url(SERVER_URL)
        if not resp:
            warnings.warn("Server returned none")
            return None
        content = json.loads()
    except KeyboardInterrupt:
        raise KeyboardInterrupt
    except Exception as e:
        warnings.warn(f"Failed to retrieve data from server.: {e}")
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
def main(user: str, test: bool) -> None:
    global _resolution_config

    print("Starting spectator bot...")

    # Try to find window immediately to update config
    window_rect = find_window_rect()
    if window_rect:
        print(f"Found 'Eleven' window at {window_rect}")
        _resolution_config = ResolutionConfig.from_window_rect(window_rect)
    else:
        print("Window 'Eleven' not found. Will keep searching...")

    # it assumes that menu is off in the UI

    while True:
        print(f"Waiting until {user} is in a room...")
        inRoom = False
        while not inRoom:
            # Periodically update window config if lost or not found yet
            if _resolution_config is None or not find_window_rect():
                rect = find_window_rect()
                if rect:
                    _resolution_config = ResolutionConfig.from_window_rect(rect)

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
