from __future__ import annotations

import threading
from typing import Callable, Optional

import serial

OnCheckBoard = Callable[[], bool]
OnPlayerDone = Callable[[], None]
OnSetDifficulty = Callable[[int], None]
OnSetColor = Callable[[str], None]  # called with "white" or "black"
OnLine = Callable[[str], None]


class ArduinoUIControllerLink:
    """Serial link for the Arduino UIController.

    This keeps the UI protocol separate from the manual move serial used by
    `arduino_bridge.py`.

    Arduino -> Python messages handled here:
    - CHECK_BOARD
    - PLAYER_DONE
    - SET_DIFFICULTY <n>
    - GET_STATE

    Python -> Arduino messages you can send with the helper methods below:
    - BOARD_OK / BOARD_FAIL
    - BOT_THINKING / BOT_MOVING
    - PLAYER_TURN_WHITE / PLAYER_TURN_BLACK
    - SET_MODE <n>
    - SET_DIFFICULTY <n> (if you want to mirror UI state explicitly)
    """

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        timeout: float = 1.0,
        on_check_board: Optional[OnCheckBoard] = None,
        on_player_done: Optional[OnPlayerDone] = None,
        on_set_difficulty: Optional[OnSetDifficulty] = None,
        on_set_color: Optional[OnSetColor] = None,
        on_line: Optional[OnLine] = None,
    ) -> None:
        self.serial = serial.Serial(port, baud, timeout=timeout)
        self._on_check_board = on_check_board
        self._on_player_done = on_player_done
        self._on_set_difficulty = on_set_difficulty
        self._on_set_color = on_set_color
        self._on_line = on_line

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rx_buffer = ""

    def set_handlers(
        self,
        on_check_board: Optional[OnCheckBoard] = None,
        on_player_done: Optional[OnPlayerDone] = None,
        on_set_difficulty: Optional[OnSetDifficulty] = None,
        on_set_color: Optional[OnSetColor] = None,
        on_line: Optional[OnLine] = None,
    ) -> None:
        self._on_check_board = on_check_board
        self._on_player_done = on_player_done
        self._on_set_difficulty = on_set_difficulty
        self._on_set_color = on_set_color
        self._on_line = on_line

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.serial.close()

    def send(self, command: str) -> None:
        self.serial.write(f"{command}\n".encode())

    def board_ok(self) -> None:
        self.send("BOARD_OK")

    def board_fail(self) -> None:
        self.send("BOARD_FAIL")

    def bot_thinking(self) -> None:
        self.send("BOT_THINKING")

    def bot_moving(self) -> None:
        self.send("BOT_MOVING")

    def move_done(self) -> None:
        self.send("MOVE_DONE")

    def player_turn_white(self) -> None:
        self.send("PLAYER_TURN_WHITE")

    def player_turn_black(self) -> None:
        self.send("PLAYER_TURN_BLACK")

    def set_mode(self, mode: int) -> None:
        self.send(f"SET_MODE {mode}")

    def set_difficulty(self, difficulty: int) -> None:
        self.send(f"SET_DIFFICULTY {difficulty}")

    def get_state(self) -> None:
        self.send("GET_STATE")

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            chunk = self.serial.read(1)
            if not chunk:
                continue

            char = chunk.decode(errors="ignore")
            if char == "\r":
                continue

            if char == "\n":
                line = self._rx_buffer.strip()
                self._rx_buffer = ""
                if line:
                    self._handle_line(line)
            else:
                self._rx_buffer += char

    def _handle_line(self, line: str) -> None:
        if self._on_line is not None:
            self._on_line(line)

        if line == "CHECK_BOARD":
            if self._on_check_board is not None:
                self.board_ok() if self._on_check_board() else self.board_fail()
        elif line == "PLAYER_DONE":
            if self._on_player_done is not None:
                self._on_player_done()
        elif line.startswith("SET_DIFFICULTY "):
            if self._on_set_difficulty is not None:
                try:
                    difficulty = int(line.split(maxsplit=1)[1])
                except (IndexError, ValueError):
                    return
                self._on_set_difficulty(difficulty)
                self.send("OK")
        elif line.startswith("SET_COLOR "):
            if self._on_set_color is not None:
                try:
                    value = int(line.split(maxsplit=1)[1])
                except (IndexError, ValueError):
                    return
                # Arduino sends 0=WHITE, 1=BLACK (matches PlayerTurn enum)
                color = "white" if value == 0 else "black"
                self._on_set_color(color)
