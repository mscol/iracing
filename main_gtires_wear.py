import pygame
import irsdk
import math
import sys
import time

# Constants
G = 9.81
WINDOW_SIZE = 500
CENTER = WINDOW_SIZE // 2
MAX_G = 3.0
DOT_RADIUS = 8
CIRCLE_RADIUS = CENTER - 60

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE))
pygame.display.set_caption("iRacing G-Ball with Tire Heatmap")
clock = pygame.time.Clock()
font = pygame.font.SysFont("Arial", 16)

# irsdk setup
ir = irsdk.IRSDK()

class State:
    ir_connected = False
    last_car_setup_tick = -1

state = State()

# G-force values
lat_g = 0.0
long_g = 0.0

# Tire class with LCR gradient zones
class Tire:
    def __init__(self):
        self.left = 0.0
        self.center = 0.0
        self.right = 0.0
        self.history = []

    def update(self, load):
        self.left += load * 0.0002
        self.center += load * 0.0003
        self.right += load * 0.0002
        self.history.append(load)
        if len(self.history) > 90000:  # ~25 minutes at 60Hz
            self.history.pop(0)
        self.decay()

    def decay(self):
        self.left *= 0.9997
        self.center *= 0.9997
        self.right *= 0.9997
        self.left = min(max(self.left, 0.0), 1.0)
        self.center = min(max(self.center, 0.0), 1.0)
        self.right = min(max(self.right, 0.0), 1.0)

    def get_color(self, zone):
        val = {'left': self.left, 'center': self.center, 'right': self.right}[zone]
        if val < 0.1:
            return (50, 50, 50)
        elif val < 0.3:
            return (0, 128, 0)
        elif val < 0.5:
            return (255, 255, 0)
        elif val < 0.75:
            return (255, 165, 0)
        else:
            return (255, 0, 0)

lf = Tire()
lr = Tire()
rf = Tire()
rr = Tire()

def check_iracing():
    if state.ir_connected and not (ir.is_initialized and ir.is_connected):
        state.ir_connected = False
        state.last_car_setup_tick = -1
        ir.shutdown()
        print('irsdk disconnected')
    elif not state.ir_connected and ir.startup() and ir.is_initialized and ir.is_connected:
        state.ir_connected = True
        print('irsdk connected')

def loop():
    global lat_g, long_g

    ir.freeze_var_buffer_latest()

    lat = ir['LatAccel'] or 0.0
    long = ir['LongAccel'] or 0.0
    lat_g = (lat / G)
    long_g = (long / G) * -1

    vel_x = ir['VelocityX'] or 0.0
    vel_y = ir['VelocityY'] or 0.0
    vel_z = ir['VelocityZ'] or 0.0

    lat_abs = abs(lat_g)
    long_abs = abs(long_g)

    # Lateral G: Car turning right = lat_g > 0 → load on left tires
    if lat_g > 0:
        rf.update(lat_abs)
        rr.update(lat_abs)
    elif lat_g < 0:
        lf.update(lat_abs)
        lr.update(lat_abs)

    # Longitudinal G: Braking = long_g > 0 → load on front tires
    if long_g > 0:
        lf.update(long_abs)
        rf.update(long_abs)
    elif long_g < 0:
        lr.update(long_abs)
        rr.update(long_abs)

    print(f"G-Lat: {lat_g:.2f}, G-Long: {long_g:.2f} | VelX: {vel_x:.2f}, VelY: {vel_y:.2f}, VelZ: {vel_z:.2f}")

def draw_tire(x, y, tire, label):
    tire_width = 60
    tire_height = 30

    zone_width = tire_width // 3

    pygame.draw.ellipse(screen, tire.get_color('left'), (x, y, zone_width, tire_height))
    pygame.draw.ellipse(screen, tire.get_color('center'), (x + zone_width, y, zone_width, tire_height))
    pygame.draw.ellipse(screen, tire.get_color('right'), (x + 2 * zone_width, y, zone_width, tire_height))

    text = font.render(label, True, (255, 255, 255))
    screen.blit(text, (x + tire_width // 2 - 10, y + tire_height + 4))

def draw_g_ball(lat_g_val, long_g_val):
    screen.fill((0, 0, 0))

    pygame.draw.circle(screen, (100, 100, 100), (CENTER, CENTER), CIRCLE_RADIUS, 2)
    pygame.draw.line(screen, (80, 80, 80), (CENTER, 0), (CENTER, WINDOW_SIZE), 1)
    pygame.draw.line(screen, (80, 80, 80), (0, CENTER), (WINDOW_SIZE, CENTER), 1)

    x = int(CENTER + (lat_g_val / MAX_G) * CIRCLE_RADIUS)
    y = int(CENTER - (long_g_val / MAX_G) * CIRCLE_RADIUS)

    dx = x - CENTER
    dy = y - CENTER
    distance = math.sqrt(dx**2 + dy**2)
    if distance > CIRCLE_RADIUS:
        scale = CIRCLE_RADIUS / distance
        dx *= scale
        dy *= scale
        x = int(CENTER + dx)
        y = int(CENTER + dy)

    # Determine dot color based on lateral G
    lat_abs = abs(lat_g_val)
    if lat_abs == 0:
        dot_color = (255, 255, 255)  # White
    elif lat_abs <= 0.4:
        dot_color = (0, 255, 0)  # Green
    elif lat_abs <= 0.7:
        dot_color = (255, 255, 0)  # Yellow
    elif lat_abs <= 1.1:
        dot_color = (255, 165, 0)  # Orange
    else:
        dot_color = (255, 0, 0)  # Red

    pygame.draw.circle(screen, dot_color, (x, y), DOT_RADIUS)

    text = font.render(f"Lateral G: {lat_g_val:.2f} | Longitudinal G: {long_g_val:.2f}", True, (255, 255, 255))
    screen.blit(text, (10, 10))

    padding = 30
    draw_tire(padding, padding, lf, "LF")
    draw_tire(padding, WINDOW_SIZE - padding - 30, lr, "LR")
    draw_tire(WINDOW_SIZE - padding - 60, padding, rf, "RF")
    draw_tire(WINDOW_SIZE - padding - 60, WINDOW_SIZE - padding - 30, rr, "RR")

    pygame.display.flip()


def run_gball():
    try:
        while True:
            check_iracing()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt

            if state.ir_connected:
                loop()

            draw_g_ball(lat_g, long_g)
            clock.tick(60)

    except KeyboardInterrupt:
        print("Shutting down...")
        ir.shutdown()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    run_gball()
