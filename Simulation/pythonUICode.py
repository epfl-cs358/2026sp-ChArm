import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import numpy as np
import time
import threading

# ── Arm parameters ────────────────────────────────────────────
J1 = 250.0
J2 = 250.0
GRIPPER_LENGTH = 100.0
MAX_REACH = J1 + J2
MIN_REACH = abs(J1 - J2)

BAUD_RATE = 115200

# ── Shared state ──────────────────────────────────────────────
state = {
    'theta1': 0.0,
    'theta2': 0.0,
    'z': 0.0,
    'target_x': 0.0,
    'target_y': 0.0,
    'target_z': 0.0,
    'done': False,
    'path_x': [],
    'path_y': [],
    'motor_j1': 0.0,
    'motor_j2': 0.0,
    'motor_z':  0.0,
    'joint_j1': 0.0,
    'joint_j2': 0.0,
    'joint_z':  0.0,
}

def find_arduino():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "Arduino" in p.description or "usbmodem" in p.device or "usbserial" in p.device:
            return p.device
    print("Arduino not found. Available ports:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device} - {p.description}")
    idx = int(input("Enter port number: "))
    return ports[idx].device

def forward_kinematics(theta1_deg, theta2_deg):
    t1 = np.radians(theta1_deg)
    t2 = np.radians(theta2_deg)
    x = J1 * np.cos(t1) + J2 * np.cos(t1 + t2)
    y = J1 * np.sin(t1) + J2 * np.sin(t1 + t2)
    return x, y

def format_revs(revs):
    direction = "↻ CW" if revs >= 0 else "↺ CCW"
    return f"{abs(revs):.3f} rev {direction}"

def serial_reader(ser):
    while True:
        if ser.in_waiting:
            try:
                line = ser.readline().decode().strip()
                if line.startswith("POS"):
                    parts = line.replace("POS ", "").split()
                    t1 = float(parts[0].split(":")[1])
                    t2 = float(parts[1].split(":")[1])
                    z  = float(parts[2].split(":")[1])
                    state['theta1'] = t1
                    state['theta2'] = t2
                    state['z'] = z
                    fx, fy = forward_kinematics(t1, t2)
                    state['path_x'].append(fx)
                    state['path_y'].append(fy)
                    state['done'] = False
                elif line.startswith("THETA1:"):
                    state['theta1'] = float(line.split(":")[1])
                elif line.startswith("THETA2:"):
                    state['theta2'] = float(line.split(":")[1])
                    state['z'] = state['target_z']
                elif line.startswith("DELTA"):
                    # Format: DELTA motorJ1:x motorJ2:x motorZ:x jointJ1:x jointJ2:x jointZ:x
                    parts = line.replace("DELTA ", "").split()
                    d = {p.split(":")[0]: float(p.split(":")[1]) for p in parts}
                    state['motor_j1'] = d['motorJ1']
                    state['motor_j2'] = d['motorJ2']
                    state['motor_z']  = d['motorZ']
                    state['joint_j1'] = d['jointJ1']
                    state['joint_j2'] = d['jointJ2']
                    state['joint_z']  = d['jointZ']
                elif line == "DONE":
                    state['done'] = True
                elif "out of reach" in line.lower():
                    print("❌ Out of reach")
                    state['done'] = True
            except:
                pass

def setup_plot():
    fig, (ax_xy, ax_z) = plt.subplots(1, 2, figsize=(14, 6))
    fig.patch.set_facecolor('#1a1a2e')

    # ── Top view ──────────────────────────────────────────────
    ax_xy.set_facecolor('#16213e')
    ax_xy.set_title("Top View (XY)", color='white', fontsize=11)
    ax_xy.set_aspect('equal')
    ax_xy.set_xlim(-100, 500)
    ax_xy.set_ylim(-100, 500)
    ax_xy.axhline(0, color='#333', linewidth=0.5)
    ax_xy.axvline(0, color='#333', linewidth=0.5)
    ax_xy.tick_params(colors='gray')
    for spine in ax_xy.spines.values():
        spine.set_edgecolor('#333')
    ax_xy.set_xlabel('X (mm)', color='gray')
    ax_xy.set_ylabel('Y (mm)', color='gray')

    # Chessboard
    cell = 40
    for row in range(8):
        for col in range(8):
            x0 = 10 + col * cell
            y0 = 10 + row * cell
            color = '#ffffff' if (row + col) % 2 == 0 else '#333333'
            ax_xy.add_patch(plt.Rectangle((x0, y0), cell, cell,
                                          color=color, alpha=0.3, zorder=0))
    ax_xy.add_patch(plt.Rectangle((10, 10), 320, 320,
                                  fill=False, edgecolor='#aaa', linewidth=1.5, zorder=1))

    line_j1,    = ax_xy.plot([], [], color='#e94560', linewidth=4, solid_capstyle='round', zorder=3)
    line_j2,    = ax_xy.plot([], [], color='#00e5ff', linewidth=4, solid_capstyle='round', zorder=3)
    line_path,  = ax_xy.plot([], [], color='#ffa502', linewidth=1.5, alpha=0.6, linestyle='--', zorder=2)
    dot_base,   = ax_xy.plot([0], [0], 'o', color='white', markersize=8, zorder=4)
    dot_j1,     = ax_xy.plot([], [], 'o', color='#e94560', markersize=6, zorder=4)
    dot_j2,     = ax_xy.plot([], [], 'o', color='#00e5ff', markersize=6, zorder=4)
    dot_target, = ax_xy.plot([], [], '*', color='#ffd60a', markersize=14, zorder=5)
    dot_end,    = ax_xy.plot([], [], 'x', color='#2ed573', markersize=10, markeredgewidth=2, zorder=5)

    txt_t1     = ax_xy.text(-90, 470, '', color='#e94560', fontsize=9)
    txt_t2     = ax_xy.text(-90, 445, '', color='#00e5ff', fontsize=9)
    txt_status = ax_xy.text(-90, 420, '', color='#2ed573', fontsize=9)

    # ── Side view ─────────────────────────────────────────────
    ax_z.set_facecolor('#16213e')
    ax_z.set_title("Side View (Z)", color='white', fontsize=11)
    ax_z.set_xlim(-50, 150)
    ax_z.set_ylim(-50, 700)
    ax_z.tick_params(colors='gray')
    for spine in ax_z.spines.values():
        spine.set_edgecolor('#333')
    ax_z.axhline(0, color='#555', linewidth=1)
    ax_z.text(5, 5, 'Ground', color='#555', fontsize=8)
    ax_z.set_ylabel('Z (mm)', color='gray')

    line_zcolumn, = ax_z.plot([], [], color='#aaa', linewidth=6, solid_capstyle='round')
    line_gripper, = ax_z.plot([], [], color='#e94560', linewidth=4, solid_capstyle='round')
    dot_ztip,     = ax_z.plot([], [], 'o', color='#00e5ff', markersize=8)
    dot_ztarget,  = ax_z.plot([], [], '*', color='#ffd60a', markersize=12)
    txt_ztip      = ax_z.text(60, 0, '', color='#00e5ff', fontsize=8)

    # ── Rotation panel ────────────────────────────────────────
    ax_z.text(-40, 680, 'Relative Rotation', color='white', fontsize=9, fontweight='bold')
    ax_z.text(-40, 655, 'motor', color='#888', fontsize=8)
    ax_z.text(30,  655, 'joint', color='#888', fontsize=8)

    txt_mj1 = ax_z.text(-40, 630, '', color='#e94560', fontsize=8)
    txt_jj1 = ax_z.text(30,  630, '', color='#e94560', fontsize=8)
    txt_mj2 = ax_z.text(-40, 605, '', color='#00e5ff', fontsize=8)
    txt_jj2 = ax_z.text(30,  605, '', color='#00e5ff', fontsize=8)
    txt_mz  = ax_z.text(-40, 580, '', color='#ffa502', fontsize=8)
    txt_jz  = ax_z.text(30,  580, '', color='#ffa502', fontsize=8)

    plt.tight_layout()

    return {
        'fig': fig, 'ax_xy': ax_xy, 'ax_z': ax_z,
        'line_j1': line_j1, 'line_j2': line_j2, 'line_path': line_path,
        'dot_j1': dot_j1, 'dot_j2': dot_j2,
        'dot_target': dot_target, 'dot_end': dot_end,
        'txt_t1': txt_t1, 'txt_t2': txt_t2, 'txt_status': txt_status,
        'line_zcolumn': line_zcolumn, 'line_gripper': line_gripper,
        'dot_ztip': dot_ztip, 'dot_ztarget': dot_ztarget, 'txt_ztip': txt_ztip,
        'txt_mj1': txt_mj1, 'txt_jj1': txt_jj1,
        'txt_mj2': txt_mj2, 'txt_jj2': txt_jj2,
        'txt_mz':  txt_mz,  'txt_jz':  txt_jz,
    }

def update_plot(h):
    t1 = state['theta1']
    t2 = state['theta2']
    z  = state['z']

    t1r = np.radians(t1)
    t2r = np.radians(t2)
    j1x = J1 * np.cos(t1r)
    j1y = J1 * np.sin(t1r)
    j2x = j1x + J2 * np.cos(t1r + t2r)
    j2y = j1y + J2 * np.sin(t1r + t2r)

    h['line_j1'].set_data([0, j1x], [0, j1y])
    h['line_j2'].set_data([j1x, j2x], [j1y, j2y])
    h['dot_j1'].set_data([j1x], [j1y])
    h['dot_j2'].set_data([j2x], [j2y])
    h['line_path'].set_data(state['path_x'], state['path_y'])
    h['dot_target'].set_data([state['target_x']], [state['target_y']])

    fx, fy = forward_kinematics(t1, t2)
    err = np.sqrt((state['target_x'] - fx)**2 + (state['target_y'] - fy)**2)
    h['dot_end'].set_data([fx], [fy])
    h['dot_end'].set_color('#2ed573' if err < 1.0 else '#ff4757')

    h['txt_t1'].set_text(f'θ1 = {t1:.1f}°')
    h['txt_t2'].set_text(f'θ2 = {t2:.1f}°')
    if state['done']:
        h['txt_status'].set_text(f'✅ Done  err={err:.2f}mm' if err < 1.0 else f'❌ Error  err={err:.2f}mm')
        h['txt_status'].set_color('#2ed573' if err < 1.0 else '#ff4757')
    else:
        h['txt_status'].set_text('')

    h['line_zcolumn'].set_data([50, 50], [0, z])
    h['line_gripper'].set_data([50, 50], [z, z + GRIPPER_LENGTH])
    h['dot_ztip'].set_data([50], [z])
    h['dot_ztarget'].set_data([50], [state['target_z']])
    h['txt_ztip'].set_position((60, z))
    h['txt_ztip'].set_text(f'{z:.0f}mm')

    # Rotation panel
    h['txt_mj1'].set_text(f'J1: {format_revs(state["motor_j1"])}')
    h['txt_jj1'].set_text(format_revs(state["joint_j1"]))
    h['txt_mj2'].set_text(f'J2: {format_revs(state["motor_j2"])}')
    h['txt_jj2'].set_text(format_revs(state["joint_j2"]))
    h['txt_mz'].set_text( f'Z:  {format_revs(state["motor_z"])}')
    h['txt_jz'].set_text( format_revs(state["joint_z"]))

    h['fig'].canvas.draw_idle()
    h['fig'].canvas.flush_events()

def main():
    print("=" * 50)
    print("  SCARA Live Simulation")
    print("=" * 50)

    port = find_arduino()
    print(f"\nConnecting to: {port}")

    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=2)
        time.sleep(2)
        ser.reset_input_buffer()
        print("Connected!\n")
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    t = threading.Thread(target=serial_reader, args=(ser,), daemon=True)
    t.start()

    plt.ion()
    h = setup_plot()
    plt.show()

    while True:
        print("-" * 40)
        try:
            x = float(input("Enter X (mm): "))
            y = float(input("Enter Y (mm): "))
            z = float(input("Enter Z (mm): "))
        except ValueError:
            print("Please enter a number.")
            continue

        state['target_x'] = x
        state['target_y'] = y
        state['target_z'] = z
        state['done'] = False
        state['path_x'] = []
        state['path_y'] = []
        h['txt_status'].set_text('')

        cmd = f"G X{x} Y{y} Z{z}\n"
        ser.write(cmd.encode())
        ser.flush()
        print(f"Sent: G X{x} Y{y} Z{z}")

        while not state['done']:
            update_plot(h)
            plt.pause(0.01)

        update_plot(h)
        plt.pause(0.01)
        print(f"✅ Move complete.")
        print(f"        motor          joint")
        print(f"   J1:  {format_revs(state['motor_j1'])}  →  {format_revs(state['joint_j1'])}")
        print(f"   J2:  {format_revs(state['motor_j2'])}  →  {format_revs(state['joint_j2'])}")
        print(f"   Z:   {format_revs(state['motor_z'])}  →  {format_revs(state['joint_z'])}")

        again = input("\nTest another coordinate? (y/n): ").strip().lower()
        if again != 'y':
            break

    ser.close()
    plt.ioff()
    plt.show()
    print("Done!")

if __name__ == "__main__":
    main()
