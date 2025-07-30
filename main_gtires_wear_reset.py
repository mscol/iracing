import pygame
import irsdk
import math
import sys
import time
#####
#possible updates
#
#always on top
#rewrite get_color so lat_abs can be used to dynamically assign dot_color instead of manual logic?
#dynamically resize/move GUI elements on screenresize?? lol
#
#
#updates
#
#add velocityX to calc for tire load
#redo timing logic with G61 estimated tire wear
#added Reset Tires button
#

# Constants
G = 9.81
WINDOW_SIZE = 300
CENTER = WINDOW_SIZE // 2
MAX_G = 3.0
DOT_RADIUS = 8
CIRCLE_RADIUS = CENTER - 60

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE), pygame.RESIZABLE, pygame.NOFRAME)
pygame.display.set_caption("CTD G-force/Tire Mgmt")
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

    def update(self, load, dir):
        if dir == "lat+":
            self.left += load * 0.0000305
            self.center += load * 0.00002
            self.right += load * 0.000015
        elif dir == "lat-":
            self.left += load * 0.000015
            self.center += load * 0.00002
            self.right += load * 0.0000305
        elif dir == "long+":
            self.left += load * 0.00002
            self.center += load * 0.00003
            self.right += load * 0.00002
        elif dir == "long-":
            self.left += load * 0.00002
            self.center += load * 0.00003
            self.right += load * 0.00002
        else:
            # fallback for unknown direction
            self.left += load * 0.00002
            self.center += load * 0.00003
            self.right += load * 0.00002
            self.history.append(load)
        if len(self.history) > 90000:  # ~25 minutes at 60Hz
            self.history.pop(0)
        self.decay()

    def decay(self):
        self.left *= 0.999997
        self.center *= 0.999997
        self.right *= 0.999997
        self.left = min(max(self.left, 0.0), 1.0)
        self.center = min(max(self.center, 0.0), 1.0)
        self.right = min(max(self.right, 0.0), 1.0)

    def reset(self):
        self.left = 0.0
        self.center = 0.0
        self.right = 0.0
        self.history.clear()

    def get_color(self, zone):
        val = {'left': self.left, 'center': self.center, 'right': self.right}[zone]
        if val < 0.1:
            return (50, 50, 50)  # dim gray or "inactive"
        val = min(max(val, 0.0), 1.0)  # clamp between 0 and 1
        if val <= 0.75:
            ratio = val / 0.5
            red = min(int(255 * ratio), 255)
            green = 255
        else:
            ratio = (val - 0.5) / 0.5
            red = 255
            green = min(int(255 * (1 - ratio)), 255)
        return (red, green, 0)

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
    print("vel x", vel_x)
    lat_abs = abs(lat_g) + abs(vel_x * 0.001)
    long_abs = abs(long_g) + abs(vel_y * 0.000000001)

    if lat_g > 0: #weight shifting left
        rf.update(lat_abs + .001,"lat+")
        rr.update(lat_abs - .1,"lat+")
    elif lat_g < 0: #weight shifting right
        lf.update(lat_abs + .001,"lat-")
        lr.update(lat_abs - .1,"lat-")

    if long_g > 0: #weight shifting forward
        lf.update(long_abs,"long+")
        rf.update(long_abs,"long+")
    elif long_g < 0: #weight shifting backwards
        lr.update(long_abs - .1,"long-")
        rr.update(long_abs - .1,"long-")

def draw_tire(x, y, tire, label):
    tire_width = 60
    tire_height = 30
    zone_width = tire_width // 3

    pygame.draw.ellipse(screen, tire.get_color('left'), (x, y, zone_width, tire_height))
    pygame.draw.ellipse(screen, tire.get_color('center'), (x + zone_width, y, zone_width, tire_height))
    pygame.draw.ellipse(screen, tire.get_color('right'), (x + 2 * zone_width, y, zone_width, tire_height))

    text = font.render(label, True, (255, 255, 255))
    screen.blit(text, (x + tire_width // 2 - 10, y + tire_height + 4))

def draw_reset_button():
    button_width = 100
    button_height = 30
    button_x = (WINDOW_SIZE - button_width) // 2
    button_y = WINDOW_SIZE - 50

    pygame.draw.rect(screen, (100, 100, 100), (button_x, button_y, button_width, button_height))
    text = font.render("Reset Tires", True, (255, 255, 255))
    screen.blit(text, (button_x + 10, button_y + 5))
    return pygame.Rect(button_x, button_y, button_width, button_height)

def draw_g_ball(lat_g_val, long_g_val):
    screen.fill((0, 0, 0))

    pygame.draw.circle(screen, (100, 100, 100), (CENTER, CENTER), CIRCLE_RADIUS, 2)
    pygame.draw.line(screen, (80, 80, 80), (CENTER, 0), (CENTER, WINDOW_SIZE), 1)
    pygame.draw.line(screen, (80, 80, 80), (0, CENTER), (WINDOW_SIZE, CENTER), 1)

    x = int(CENTER + (lat_g_val / MAX_G) * CIRCLE_RADIUS)
    y = int(CENTER - (long_g_val / MAX_G) * CIRCLE_RADIUS)

    dx = x - CENTER
    dy = y - CENTER
    distance = math.sqrt(dx ** 2 + dy ** 2)
    if distance > CIRCLE_RADIUS:
        scale = CIRCLE_RADIUS / distance
        dx *= scale
        dy *= scale
        x = int(CENTER + dx)
        y = int(CENTER + dy)

    def clamp_color(value):
        return max(0, min(int(value), 255))

    lat_abs = abs(lat_g_val)

    if lat_abs == 0:
        dot_color = (50, 50, 50)  # Grey
    elif lat_abs <= 0.75:
        ratio = lat_abs / 0.5
        red = clamp_color(255 * ratio)
        green = 255
        dot_color = (red, green, 0)
    else:
        ratio = lat_abs / 1.5
        red = 255
        green = clamp_color(255 * (1 - ratio))
        dot_color = (red, green, 0)

    pygame.draw.circle(screen, dot_color, (x, y), DOT_RADIUS)

    text = font.render(f"Lateral G: {lat_g_val:.2f} | Longitudinal G: {long_g_val:.2f}", True, (255, 255, 255))
    screen.blit(text, (10, 10))

    padding = 30
    draw_tire(padding, padding, lf, "LF")
    draw_tire(padding, WINDOW_SIZE - padding - 30, lr, "LR")
    draw_tire(WINDOW_SIZE - padding - 60, padding, rf, "RF")
    draw_tire(WINDOW_SIZE - padding - 60, WINDOW_SIZE - padding - 30, rr, "RR")

    reset_button_rect = draw_reset_button()
    pygame.display.flip()
    return reset_button_rect

def run_gball():
    try:
        while True:
            check_iracing()

            reset_button_rect = draw_g_ball(lat_g, long_g)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if reset_button_rect.collidepoint(event.pos):
                        lf.reset()
                        lr.reset()
                        rf.reset()
                        rr.reset()

            if state.ir_connected:
                loop()

            clock.tick(60)

    except KeyboardInterrupt:
        print("Shutting down...")
        ir.shutdown()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    try:
        run_gball()
    finally:
        pygame.quit()
        sys.exit()
