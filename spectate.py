# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "click>=8.3.1",
#     "pyautogui>=0.9.54",
#     "requests>=2.32.5",
# ]
# ///
from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from time import sleep

import click
import pyautogui
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

    def resolve(self, base_x: int, base_y: int) -> tuple[int, int]:
        """Scale base (1920x1080) coordinates to configured resolution and add offset."""
        x = round(base_x * (self.res_x / BASE_W) + self.offset_x)
        y = round(base_y * (self.res_y / BASE_H) + self.offset_y)
        return (x, y)


# Set by main() from CLI; used by clickButton
_resolution_config: ResolutionConfig | None = None


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
    'HOME': Position(600, 900),
    'JOINROOM': Position(1850, 470),
    'EXITROOM': Position(1217, 974),
    'FOCUS': Position(960, 540),  # center of 1920x1080, safe spot to click
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
    for button in list_of_buttons if isinstance(list_of_buttons, list) else [list_of_buttons]:
        clickButton(button, move_only=move_only)
        sleep(INTERVAL)


def joinRoom(test):
    clickListOfButtons("HOME JOINROOM".split())


def exitRoom(test):
    clickListOfButtons("HOME EXITROOM".split())


def type(str):
    print(f"Pressed {str}")
    pyautogui.write(str)


def retrieve_url(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        return None


def isInRoom(user):
    try:
        content = json.loads(retrieve_url(SERVER_URL))
    except KeyboardInterrupt:
        raise KeyboardInterrupt
    except:
        warnings.warn("Failed to retrieve data from server.")
        return None
    users = [x for x in content['UsersInRooms'] if x['UserName'] == user]
    if (len(users) > 0):
        print(users)
        sys.stdout.flush()
        return True

    sys.stdout.flush()
    return False


def print_mouse():
    mouse_position = pyautogui.position()
    print(
        f"Mouse position: {mouse_position[0]:04d}, {mouse_position[1]:04d}", end='')
    sys.stdout.write('\r')


@click.command()
@click.option('--test', '-t', is_flag=True, default=False, help='Whether to avoid clicks')
@click.option('--user', '-u', help='Username', required=True)
@click.option('--res-x', default=BASE_W, type=int, help='Target screen/window width (default: 1920)')
@click.option('--res-y', default=BASE_H, type=int, help='Target screen/window height (default: 1080)')
@click.option('--offset-x', default=0, type=int, help='X offset of the active window (e.g. if window is not at 0)')
@click.option('--offset-y', default=0, type=int, help='Y offset of the active window')
def main(user: str, test: bool, res_x: int, res_y: int, offset_x: int, offset_y: int) -> None:
    global _resolution_config
    _resolution_config = ResolutionConfig(
        res_x=res_x, res_y=res_y, offset_x=offset_x, offset_y=offset_y
    )

    # it assumes that menu is off in the UI

    while True:
        print(f"Waiting until {user} is in a room...")
        inRoom = False
        while not inRoom or inRoom is None:
            inRoom = isInRoom(user)
            print_mouse()
            sleep(INTERVAL)
        print(f"User {user} is in a room!",  end='')
        print(f"Joining room.")
        joinRoom(test)

        while inRoom or inRoom is None:
            inRoom = isInRoom(user)
            print_mouse()
            sleep(INTERVAL)
        print(f"User {user} is no longer in a room.")
        print(f"Leaving room.")
        exitRoom(test)


if __name__ == '__main__':
    main(sys.argv[1:])
