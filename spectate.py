# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "click>=8.3.1",
#     "mss>=10.1.0",
#     "numpy>=2.4.2",
#     "opencv-python>=4.13.0.92",
#     "pyautogui>=0.9.54",
#     "pydirectinput>=1.0.4",
#     "python-dotenv>=1.0.1",
#     "pywinauto>=0.6.9",
#     "requests>=2.32.5",
#     "rich>=14.3.3",
# ]
# ///
from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from dataclasses import dataclass
from enum import Enum, auto
from time import sleep

import click
import cv2
import mss
import numpy as np
import pydirectinput
import pyautogui
import pywinauto
import requests
from dotenv import load_dotenv

DEFAULT_SERVER_BASE_URL = "https://api3.elevenvr.com"
# DEFAULT_SERVER_URL = "http://elevenlogcollector-env.js6z6tixhb.us-west-2.elasticbeanstalk.com/ElevenServerLiteSnapshot"
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


class Position:
    x: float
    y: float

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


MAPPINGS = {
    "FRIEND_0": Position(0.8453, 0.4148),
    "JOIN_SELECTED": Position(0.8161, 0.7370),
    "FOCUS_CORNER": Position(0.05, 0.05),
    "LEAVE_ROOM": Position(0.3724, 0.8370),
    "CONFIRM_LEAVE": Position(0.4203, 0.6898),
    "DISMISS_RANKED": Position(0.5473, 0.6954),
}


class BotState(Enum):
    SEARCHING_WINDOW = auto()
    WAITING_FOR_USER = auto()
    JOINING = auto()
    SPECTATING = auto()
    LEAVING = auto()


class SpectatorBot:
    def __init__(
        self,
        user: str,
        test_mode: bool,
        api_key: str | None = None,
        server_base_url: str | None = None,
    ):
        self.user = user
        self.test_mode = test_mode
        self.api_key = api_key
        self.server_base_url = (
            server_base_url if server_base_url else DEFAULT_SERVER_BASE_URL
        )
        self.user_id = self.get_userid()
        self.state = BotState.SEARCHING_WINDOW
        self.res_config: ResolutionConfig | None = None

    def run(self):
        """Main FSM loop."""
        print(
            f"Starting spectator bot for user: {self.user} (Test Mode: {self.test_mode})"
        )
        if self.api_key:
            print("API Key loaded successfully.")
        else:
            print("Warning: No API Key found.")

        while True:
            try:
                if self.state == BotState.SEARCHING_WINDOW:
                    self._handle_searching_window()
                elif self.state == BotState.WAITING_FOR_USER:
                    self._handle_waiting_for_user()
                elif self.state == BotState.JOINING:
                    self._handle_joining()
                elif self.state == BotState.SPECTATING:
                    self._handle_spectating()
                elif self.state == BotState.LEAVING:
                    self._handle_leaving()
            except KeyboardInterrupt:
                print("\nBot stopped by user.")
                break
            except Exception as e:
                print(f"Unexpected error in state {self.state.name}: {e}")
                sleep(1)

    def _handle_searching_window(self):
        rect = self.find_window_rect()
        if rect:
            self.res_config = ResolutionConfig.from_window_rect(rect)
            print(f"Found 'Eleven' window at {rect}")
            self.state = BotState.WAITING_FOR_USER
        else:
            print("Searching for 'Eleven' window...", end="\r")
            sleep(2)

    def _handle_waiting_for_user(self):
        if not self._check_window_valid():
            return

        print(f"Waiting for {self.user} to enter a room...", end="\r")

        # In waiting state, we print mouse coords for debugging
        self.print_mouse()

        if self.is_in_room():
            print(f"\nUser {self.user} found in room!")
            self.state = BotState.JOINING
        else:
            sleep(INTERVAL)

    def _handle_joining(self):
        if not self._check_window_valid():
            return

        print("Executing join sequence...")

        # Ensure config is present (guaranteed by _check_window_valid)
        assert self.res_config is not None

        # 1. Ensure focus
        self._focus_window()
        sleep(INTERVAL)

        # 2. Reset menu state (ensure closed first)
        print("Ensuring menu is CLOSED...")
        if not self.ensure_menu_state(target_open=False):
            print("Failed to close menu! Attempting to proceed anyway...")

        # 3. Open menu
        print("Opening menu...")
        self._press_key("M")
        sleep(INTERVAL)
        if not self.is_menu_open():
            print("Menu did not open! Retrying...")
            self._press_key("M")
            sleep(1.0)

        # 4. Select friend
        if not self.test_mode:
            self.click_button("FRIEND_0")
            sleep(1.0)
        else:
            print("Test mode: Skipping click FRIEND_0")

        # 5. Join
        if not self.test_mode:
            self.click_button("JOIN_SELECTED")
            sleep(1.0)
            # Change camera so spectator isnt distracting
            self._press_key("9")
        else:
            print("Test mode: Skipping click JOIN_SELECTED")

        self.state = BotState.SPECTATING

    def _handle_spectating(self):
        if not self._check_window_valid():
            return

        # Poll if user is still in room
        in_room = self.is_in_room()

        self.print_mouse()

        if (
            in_room is False
        ):  # Explicit False means successful check returned "not in room"
            print(f"\nUser {self.user} left the room.")
            self.state = BotState.LEAVING
        elif in_room is None:
            # Server error or timeout, stay in spectating but warn
            pass

        sleep(INTERVAL)

    def _handle_leaving(self):
        if not self._check_window_valid():
            return

        print("Leaving room...")

        if self.res_config:
            self.ensure_menu_state(target_open=True)
            self.click_button("LEAVE_ROOM")
            sleep(INTERVAL)
            self.click_button("CONFIRM_LEAVE")
            sleep(INTERVAL)
            self.click_button("DISMISS_RANKED")
            sleep(INTERVAL)

        self.state = BotState.WAITING_FOR_USER

    def _check_window_valid(self) -> bool:
        """Verify window still exists. If not, transition to SEARCHING_WINDOW."""
        rect = self.find_window_rect()
        if not rect:
            print("\nWindow lost! Switching to search mode.")
            self.state = BotState.SEARCHING_WINDOW
            self.res_config = None
            return False

        # Update config in case window moved
        self.res_config = ResolutionConfig.from_window_rect(rect)
        return True

    # --- Helpers ---

    def find_window_rect(
        self, title_pattern: str = "Eleven"
    ) -> tuple[int, int, int, int] | None:
        """Find the game window and return its (left, top, right, bottom) rect."""
        try:
            # Connect to application
            app = pywinauto.Application(backend="uia").connect(title_re=title_pattern)
            window = app.window(title_re=title_pattern)

            if not window.exists():
                return None

            try:
                window.set_focus()
            except Exception:
                pass

            rect = window.rectangle()
            return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            return None

    def get_userid(self) -> str | None:
        resp = self._retrieve_url(f"{self.server_base_url}/accounts/search/{self.user}")
        if not resp:
            warnings.warn("Server returned none")
            return None
        content = json.loads(resp)

        userId: str | None = (
            (x := content) and (x := x["data"]) and (x := x[0]) and x["id"]
        )
        if not userId:
            warnings.warn(f"No userId found from {resp}")

        print(f"Found user_id {userId}")
        return userId

    def is_in_room(self) -> bool | None:
        resp = self._retrieve_url(
            f"{self.server_base_url}/accounts/{self.user_id}/matches",
            {"page[number]": "1", "page[size]": "1"},
        )
        if not resp:
            warnings.warn("Server returned none")
            return None

        content = json.loads(resp)
        state: int | None = (
            (x := content)
            and (x := x["data"])
            and (x := x[0])
            and (x := x["attributes"])
            and x["state"]
        )
        # state is -1 for ongoing
        if state == -1:
            return True

        return False

    def is_in_room_old(self, user: str) -> bool | None:
        try:
            resp = self._retrieve_url(self.server_base_url)
            if not resp:
                warnings.warn("Server returned none")
                return None
            content = json.loads(resp)

            users = [
                x for x in content.get("UsersInRooms", []) if x.get("UserName") == user
            ]
            if len(users) > 0:
                return True
            return False
        except Exception as e:
            warnings.warn(f"Failed to retrieve data from server: {e}")
            return None

    def _retrieve_url(self, url: str, params: dict[str, str] = {}) -> str | None:
        try:
            response = requests.get(
                url, timeout=5, params={"api-key": self.api_key, **params}
            )
            if response.status_code == 200:
                return response.text

            warnings.warn(
                f"request failed {response.status_code} | {response.text} | {response.reason}"
            )
            return None
        except Exception as e:
            warnings.warn(f"Caught exception {e}")
            return None

    def click_button(self, button_name: str, move_only: bool = False) -> None:
        if not self.res_config:
            return

        base = MAPPINGS[button_name]
        x, y = self.res_config.resolve(base.x, base.y)

        pyautogui.moveTo(x, y)
        if not move_only:
            pyautogui.mouseDown()
            sleep(0.05)
            pyautogui.mouseUp()
            print(f"Clicked {button_name}")
        else:
            print(f"Moved to {x, y}")
            sleep(0.3)

    def _focus_window(self) -> None:
        """Click corner of window to bring it into focus."""
        self.click_button("FOCUS_CORNER", move_only=False)

    def _press_key(self, key: str):
        print(f"Pressed {key}")
        pyautogui.write(key)

    def is_menu_open(
        self, template_path: str = "templates_1080p/power_menu_icon.jpg"
    ) -> bool:
        if not self.res_config:
            return False

        try:
            with mss.mss() as sct:
                monitor = {
                    "top": self.res_config.offset_y,
                    "left": self.res_config.offset_x,
                    "width": self.res_config.res_x,
                    "height": self.res_config.res_y,
                }
                sct_img = sct.grab(monitor)
                frame = np.array(sct_img)
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                template = cv2.imread(template_path)
                if template is None:
                    return False

                # Resize frame to 1080p for matching if needed
                target_h, target_w = BASE_H, BASE_W
                if frame_bgr.shape[:2] != (target_h, target_w):
                    frame_bgr = cv2.resize(frame_bgr, (target_w, target_h))

                res = cv2.matchTemplate(frame_bgr, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)

                return max_val > 0.8
        except Exception as e:
            print(f"Vision error: {e}")
            return False

    def ensure_menu_state(self, target_open: bool, timeout: int = 5) -> bool:
        self._focus_window()
        # Reset camera
        self._press_key("0")
        sleep(INTERVAL)

        # First check
        if self.is_menu_open() == target_open:
            return True

        # Toggle M
        self._press_key("M")
        sleep(INTERVAL)

        # Check again with retries
        for _ in range(timeout):
            if self.is_menu_open() == target_open:
                return True
            sleep(INTERVAL)

        return False

    def print_mouse(self):
        mouse_position = pyautogui.position()

        if self.res_config:
            # Check if inside window
            if (
                self.res_config.offset_x
                <= mouse_position[0]
                < self.res_config.offset_x + self.res_config.res_x
                and self.res_config.offset_y
                <= mouse_position[1]
                < self.res_config.offset_y + self.res_config.res_y
            ):
                norm_x, norm_y = self.res_config.normalize(
                    mouse_position[0], mouse_position[1]
                )
                menu_status = "OPEN" if self.is_menu_open() else "CLOSED"
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
@click.option(
    "--debug", "-d", is_flag=True, default=False, help="Enable verbose logging"
)
@click.option("--user", "-u", help="Username", required=True)
def main(user: str, test: bool, debug: bool) -> None:
    load_dotenv()
    api_key = os.getenv("API_KEY")
    server_base_url = os.getenv("SERVER_BASE_URL")

    if debug:
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
        print("Debug logging enabled.")

    bot = SpectatorBot(
        user=user, test_mode=test, api_key=api_key, server_base_url=server_base_url
    )
    bot.run()


if __name__ == "__main__":
    main(sys.argv[1:])
