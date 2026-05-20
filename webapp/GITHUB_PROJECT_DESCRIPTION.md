# ChArm Webapp

I built this webapp as the main operator interface for the ChArm robot. I chose Next.js because I already had experience with it and it let me move fast. The idea was to have a clean UI to drive the whole system without having to run scripts from the terminal every time. It talks to a local Python backend (`api_server.py`) over HTTP, which is the part that actually handles the computer vision and the Arduino communication.

## Dashboard

![Dashboard](screenshots/home.png)

This is the first page you see when you open the app. I wanted a single place to check that everything is ready before running a game session: is the robot connected, is it calibrated, what does the board look like right now. It gives a quick overview of the full pipeline state so you don't have to jump between pages to know if the system is ready.

## Computer Vision Lab (`/lab`)

![Lab](screenshots/lab.png)

This is the page I spent the most time on. The vision pipeline has a lot of parameters (board detection thresholds, CLAHE settings, occupancy scoring, color classification) and I needed a way to tune them interactively without restarting anything. I also added a manual labeling tool so we could annotate images directly from the browser and retrain the KNN color classifier on the fly from those annotations.

## Pipeline Monitor (`/monitor`)

![Monitor](screenshots/monitor.png)

A simpler read-only version of the lab. You pick an image, hit Run, and see every intermediate result: the warped board, the 8x8 grid, which squares are occupied, which pieces are white or black. I use this to quickly sanity-check the pipeline on a new image without touching any settings.

## Scara Calibration (`/robot`)

![Robot](screenshots/robot.png)

This is the page I built to make robot calibration and testing as fast as possible, because we were losing a lot of time running Python scripts by hand every time something changed.

**Physical setup:** the SCARA arm is mounted at the top-right corner of the chess board. From that fixed pivot point, its reach has to cover the full board diagonal at sub-millimeter precision (within 0.5mm) to reliably pick and place pieces on every square, including the far corners.

**Serial connection:** you pick the serial port (default `/dev/ttyUSB0`) and baud rate, then connect. The page detects the Arduino automatically if it's plugged in.

**Homing sequence:** before any move, the arm needs to home itself. The sequence has 5 steps that have to happen in order: Z bottom switch, Z backoff to zero, J1 limit switch, J1 offset to zero, J2 min/max to center. Each step is a separate button so you can stop and debug at any point if something goes wrong.

**Live arm position:** once connected, the page polls the Arduino every second and displays the live X/Y/Z position of the arm. This is critical during calibration because you need to know exactly where the arm is as you jog it to each corner.

**Board corner calibration:** the coordinate mapping from chess squares to robot coordinates is built from three reference points: A1 (bottom-left from the arm's perspective), H1 (bottom-right), and H8 (top-right, closest to the arm pivot). You jog the arm to each corner physically and hit "capture" to record the position. The backend then computes an affine map from those three points and uses it to derive every other square's coordinates. Z hover and Z down heights are also configurable here, as well as per-piece-type heights since taller pieces need a higher pick position.

**Movement tests:** once calibrated, you can test a single square move (type `e4`, hit "Move Square") or a full UCI move (type `e2e4`, hit "Run Move") directly from the browser. You can also select the piece type so the arm picks at the right height. I use this to verify the calibration is accurate before running a full game.

**Game state** is shown below the vision pipeline output on the dashboard, so you can see the inferred board position alongside the raw camera feed and immediately check whether the move detection matched what actually happened on the board.
