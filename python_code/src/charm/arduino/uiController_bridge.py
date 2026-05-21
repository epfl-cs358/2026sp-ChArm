from __future__ import annotations

import socket
import threading
from typing import Callable, Optional

OnCheckBoard = Callable[[], bool]
OnPlayerDone = Callable[[], None]
OnSetDifficulty = Callable[[int], None]
OnSetColor = Callable[[str], None]  # called with "white" or "black"
OnCalibration = Callable[[], None]
OnLine = Callable[[str], None]


class ArduinoUIControllerLink:
    """TCP socket link to the ESP32 UI box.

    ESP32 -> Python messages handled here:
    - CHECK_BOARD
    - PLAYER_DONE
    - SET_DIFFICULTY <n>
    - SET_COLOR <n>

    Python -> ESP32 messages:
    - BOARD_OK / BOARD_FAIL
    - BOT_THINKING / BOT_MOVING
    - PLAYER_TURN_WHITE / PLAYER_TURN_BLACK
    - MOVE_DONE
    - SET_MODE <n>
    - SET_DIFFICULTY <n>
    - OK
    """

    def __init__(
        self,
        host: str,
        port: int = 8765,
        on_check_board: Optional[OnCheckBoard] = None,
        on_player_done: Optional[OnPlayerDone] = None,
        on_set_difficulty: Optional[OnSetDifficulty] = None,
        on_set_color: Optional[OnSetColor] = None,
        on_calibration: Optional[OnCalibration] = None,
        on_line: Optional[OnLine] = None,
    ) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((host, port))
        self.lock = threading.Lock()

        self._on_check_board = on_check_board
        self._on_player_done = on_player_done
        self._on_set_difficulty = on_set_difficulty
        self._on_set_color = on_set_color
        self._on_calibration = on_calibration
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
        on_calibration: Optional[OnCalibration] = None,
        on_line: Optional[OnLine] = None,
    ) -> None:
        self._on_check_board = on_check_board
        self._on_player_done = on_player_done
        self._on_set_difficulty = on_set_difficulty
        self._on_set_color = on_set_color
        self._on_calibration = on_calibration

        # Only overwrite _on_line if caller explicitly passes one.
        if on_line is not None:
            self._on_line = on_line

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        print("[UI DEBUG] Starting ESP32 UI reader thread", flush=True)

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        print("[UI DEBUG] Closing ESP32 UI TCP link", flush=True)

        self._stop_event.set()

        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def send(self, command: str) -> None:
        """Send one newline-terminated command to the ESP32."""
        print(f"[PY -> ESP32] {command}", flush=True)
        with self.lock:
            self._sock.sendall(f"{command}\n".encode())

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

    def game_over(self, reason: str) -> None:
        """Send GAME_OVER <reason> to the ESP32.

        reason: 'WHITE_WIN', 'BLACK_WIN', 'STALEMATE', or 'DRAW'
        """
        self.send(f"GAME_OVER {reason}")

    def get_state(self) -> None:
        self.send("GET_STATE")

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._sock.recv(1)
            except OSError as e:
                if not self._stop_event.is_set():
                    print(f"[UI DEBUG] Socket read error: {e}", flush=True)
                break

            if not chunk:
                # Connection closed by ESP32.
                print("[UI DEBUG] ESP32 closed the connection", flush=True)
                break

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
        print(f"[ESP32 -> PY] {line}", flush=True)

        if self._on_line is not None:
            self._on_line(line)

        if line == "CHECK_BOARD":
            self._handle_check_board()
            return

        if line == "PLAYER_DONE":
            self._handle_player_done()
            return

        if line.startswith("SET_DIFFICULTY "):
            self._handle_set_difficulty(line)
            return

        if line.startswith("SET_COLOR "):
            self._handle_set_color(line)
            return

        if line == "CALIBRATION":
            self._handle_calibration()
            return

        if line == "GET_STATE":
            print("[UI DEBUG] GET_STATE received, no handler implemented in Python", flush=True)
            return

        if line in {"OK", "BOARD_OK_ACK", "BOARD_FAIL_ACK", "BOARD_TIMEOUT"}:
            print(f"[UI DEBUG] ESP32 status line: {line}", flush=True)
            return

        print(f"[UI DEBUG] Unknown ESP32 line ignored: {line}", flush=True)

    def _handle_check_board(self) -> None:
        print("[UI DEBUG] CHECK_BOARD received", flush=True)

        if self._on_check_board is None:
            print("[UI DEBUG] No on_check_board handler set, sending BOARD_FAIL", flush=True)
            self.board_fail()
            return

        try:
            ok = self._on_check_board()
        except Exception as e:
            print(f"[UI DEBUG] Exception during on_check_board: {repr(e)}", flush=True)
            import traceback

            traceback.print_exc()
            self.board_fail()
            return

        print(f"[UI DEBUG] on_check_board returned: {ok}", flush=True)

        if ok:
            print("[UI DEBUG] sending BOARD_OK", flush=True)
            self.board_ok()
        else:
            print("[UI DEBUG] sending BOARD_FAIL", flush=True)
            self.board_fail()

    def _handle_player_done(self) -> None:
        print("[UI DEBUG] PLAYER_DONE received", flush=True)

        if self._on_player_done is None:
            print("[UI DEBUG] No on_player_done handler set", flush=True)
            return

        try:
            self._on_player_done()
        except Exception as e:
            print(f"[UI DEBUG] Exception during on_player_done: {repr(e)}", flush=True)
            import traceback

            traceback.print_exc()
            self.set_mode(7)

    def _handle_set_difficulty(self, line: str) -> None:
        if self._on_set_difficulty is None:
            print("[UI DEBUG] SET_DIFFICULTY received but no handler set", flush=True)
            return

        try:
            difficulty = int(line.split(maxsplit=1)[1])
        except (IndexError, ValueError):
            print(f"[UI DEBUG] Invalid SET_DIFFICULTY line: {line}", flush=True)
            return

        print(f"[UI DEBUG] SET_DIFFICULTY received: {difficulty}", flush=True)

        self._on_set_difficulty(difficulty)
        self.send("OK")

    def _handle_set_color(self, line: str) -> None:
        if self._on_set_color is None:
            print("[UI DEBUG] SET_COLOR received but no handler set", flush=True)
            return

        try:
            value = int(line.split(maxsplit=1)[1])
        except (IndexError, ValueError):
            print(f"[UI DEBUG] Invalid SET_COLOR line: {line}", flush=True)
            return

        # ESP32 sends 0=WHITE, 1=BLACK.
        color = "white" if value == 0 else "black"

        print(
            f"[UI DEBUG] SET_COLOR received: value={value}, color={color}",
            flush=True,
        )

        self._on_set_color(color)

        # Acknowledge color selection.
        self.send("OK")

    def _handle_calibration(self) -> None:
        print("[UI DEBUG] CALIBRATION received", flush=True)

        if self._on_calibration is None:
            print("[UI DEBUG] No on_calibration handler set", flush=True)
            return

        try:
            self._on_calibration()
        except Exception as e:
            print(f"[UI DEBUG] Exception during on_calibration: {repr(e)}", flush=True)
            import traceback
            traceback.print_exc()
