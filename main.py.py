"""
Asteroids — PNG sprites + sounds + bg music + menu volume controls

Controls:
  Menu:
    ↑/↓   select Music or SFX
    ←/→   adjust volume 0..100%
    Enter start game
    Esc   quit
  In-game:
    ←/→   rotate
    ↑     thrust (shows tail flame)
    Space shoot
    H     hyperspace
    Esc/Q quit

Folder layout (must match):
  your_project/
    main.py
    assets/
      images/
        ship.png
        asteroid1.png
        asteroid2.png
        asteroid3.png
        space_bg.png
      sounds/
        shoot.wav
        explode.wav
        death.wav   (optional)
        bg_music.wav

Notes:
- Ship PNG should be top-down and naturally "facing up" (nose at the top).
- Bullets spawn from rotated top-center (nose); flame from rotated bottom-center (tail).
"""

import math
import random
import os
import pygame

# ----------------------------
# Window / gameplay settings
# ----------------------------

WIDTH, HEIGHT = 1280, 1024
FPS = 420
BG_COLOR = (5, 7, 12)

BULLET_SPEED = 520.0
BULLET_LIFETIME = 1.2
MAX_BULLETS = 5

SHIP_TURN_SPEED = math.radians(220)
SHIP_THRUST = 300.0
SHIP_FRICTION = 0.9
SHIP_COLLISION_SCALE = 0.75  # % of half-width used as collision radius

ASTEROID_SPEED_RANGE = (60, 160)
ASTEROID_FRAGMENT_COUNT = (2, 3)
ASTEROID_SCALE_MIN = 0.45
ASTEROID_SCALE_MAX = 1.0
ASTEROID_COLLISION_SCALE = 0.85

INVULN_TIME = 2.0
BLINK_HZ = 10.0

# Menu constants
MENU_ITEMS = ["Music Volume", "SFX Volume"]
VOL_STEP = 0.05  # 5% per keypress

# ----------------------------
# Absolute asset paths
# ----------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(ROOT_DIR, "assets", "images")
SOUNDS_DIR = os.path.join(ROOT_DIR, "assets", "sounds")

SHIP_IMG_PATH = os.path.join(IMAGES_DIR, "ship.png")
BG_IMG_PATH = os.path.join(IMAGES_DIR, "space_bg.png")

SND_SHOOT_PATH   = os.path.join(SOUNDS_DIR, "shoot.wav")
SND_EXPLODE_PATH = os.path.join(SOUNDS_DIR, "explode.wav")
SND_DEATH_PATH   = os.path.join(SOUNDS_DIR, "death.wav")
MUSIC_PATH       = os.path.join(SOUNDS_DIR, "bg_music.wav")

def asteroid_image_paths():
    """Collect asteroid*.png in assets/images (sorted)."""
    if not os.path.isdir(IMAGES_DIR):
        return []
    candidates = []
    for fname in os.listdir(IMAGES_DIR):
        low = fname.lower()
        if low.startswith("asteroid") and low.endswith(".png"):
            candidates.append(os.path.join(IMAGES_DIR, fname))
    return sorted(candidates)

# ----------------------------
# Small math helpers
# ----------------------------
def wrap_position(pos):
    x, y = pos
    if x < 0: x += WIDTH
    if x > WIDTH: x -= WIDTH
    if y < 0: y += HEIGHT
    if y > HEIGHT: y -= HEIGHT
    return x, y

def add(a, b): return (a[0] + b[0], a[1] + b[1])
def scale_vec(v, s): return (v[0] * s, v[1] * s)
def from_angle(rad): return (math.cos(rad), math.sin(rad))
def perp(v): return (-v[1], v[0])  # 90° CCW
def circle_collide(p1, r1, p2, r2): return (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 <= (r1+r2)**2

# ----------------------------
# Safe loaders (images / sounds)
# ----------------------------
def load_image_safe(path, fallback_size=(64, 64), fallback_shape="triangle"):
    """Load an image or draw a placeholder if missing."""
    try:
        img = pygame.image.load(path).convert_alpha()
        print(f"[OK] Loaded image: {path}")
        return img
    except Exception as e:
        print(f"[WARN] Could not load {path}: {e}")
        surf = pygame.Surface(fallback_size, pygame.SRCALPHA)
        w, h = fallback_size
        if fallback_shape == "triangle":
            pts = [(w*0.5, 0), (0, h), (w, h)]
            pygame.draw.polygon(surf, (200, 240, 255), pts, width=2)
        else:
            pygame.draw.circle(surf, (180, 210, 220), (w//2, h//2), min(w, h)//2, width=2)
        return surf

def load_background_scaled(path, size):
    """Load and scale background (return None on failure)."""
    try:
        img = pygame.image.load(path).convert()
        img = pygame.transform.smoothscale(img, size)
        print(f"[OK] Loaded background: {path}")
        return img
    except Exception as e:
        print(f"[WARN] Could not load background {path}: {e}")
        return None

class _SilentSound:
    """Fallback when mixer/sound missing; has .play() to avoid crashes."""
    def set_volume(self, *_): pass
    def play(self): pass

def load_sound_safe(path):
    """Return pygame.Sound if possible, otherwise a silent stub."""
    try:
        snd = pygame.mixer.Sound(path)
        print(f"[OK] Loaded sound: {path}")
        return snd
    except Exception as e:
        print(f"[WARN] Could not load sound {path}: {e}")
        return _SilentSound()

def try_start_music(path, volume=0.6):
    """Load and loop bg music. Return True if started."""
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
        pygame.mixer.music.play(-1)  # loop
        print(f"[OK] Music started: {path}")
        return True
    except Exception as e:
        print(f"[WARN] Music not started ({path}): {e}")
        return False

# ----------------------------
# Game objects
# ----------------------------
class Bullet:
    def __init__(self, pos, vel):
        self.pos = pos
        self.vel = vel
        self.age = 0.0
        self.dead = False

    def update(self, dt):
        self.age += dt
        if self.age > BULLET_LIFETIME:
            self.dead = True
            return
        self.pos = add(self.pos, scale_vec(self.vel, dt))
        self.pos = wrap_position(self.pos)

    def draw(self, surf):
           pygame.draw.circle(surf, ("#ff00c8"), (int(self.pos[0]), int(self.pos[1])), 1)
 #   def draw(self, surf):
 #       pygame.draw.rect(
 #           surf, 
 #           ("#ff00c8"),
 #           pygame.Rect(int(self.pos[0]-2), int(self.pos[1]-10), 4, 10)
 #       )

class Asteroid:
    """Image-based asteroid with spin; splits into scaled fragments."""
    def __init__(self, image, pos, vel, scale=1.0, spin=0.0):
        self.base_image = image
        self.scale = scale
        self.angle = random.uniform(0, 360)
        self.spin = spin  # deg/sec

        w, h = self.base_image.get_size()
        sw, sh = max(1, int(w*scale)), max(1, int(h*scale))
        self.image_scaled = pygame.transform.smoothscale(self.base_image, (sw, sh))
        self.image = self.image_scaled
        self.rect = self.image.get_rect(center=pos)

        self.pos = pos
        self.vel = vel
        self.dead = False
        self.radius = 0.5 * self.image.get_width() * ASTEROID_COLLISION_SCALE

    def update(self, dt):
        self.angle = (self.angle + self.spin * dt) % 360
        self.image = pygame.transform.rotozoom(self.image_scaled, -self.angle, 1.0)
        center_before = self.rect.center
        self.rect = self.image.get_rect(center=center_before)

        self.pos = add(self.pos, scale_vec(self.vel, dt))
        self.pos = wrap_position(self.pos)
        self.rect.center = self.pos

    def draw(self, surf):
        surf.blit(self.image, self.rect)

    def split(self):
        new_scale = self.scale * 0.6
        if new_scale < ASTEROID_SCALE_MIN:
            self.dead = True
            return []
        pieces = []
        for _ in range(random.randint(*ASTEROID_FRAGMENT_COUNT)):
            ang = random.random() * 2 * math.pi
            speed = random.uniform(*ASTEROID_SPEED_RANGE)
            vel = add(self.vel, (math.cos(ang)*speed, math.sin(ang)*speed))
            spin = random.uniform(-120, 120)
            pieces.append(Asteroid(self.base_image, self.pos, vel, scale=new_scale, spin=spin))
        self.dead = True
        return pieces


class Ship:
    """
    Bullets spawn from rotated top-center (nose) of the PNG.
    Thrust flame renders at rotated bottom-center (tail) when accelerating.
    """
    def __init__(self, image, sfx):
        self.base_image = image
        self.image = image
        self.rect = self.image.get_rect(center=(WIDTH//2, HEIGHT//2))

        self.pos = (WIDTH/2, HEIGHT/2)
        self.vel = (0.0, 0.0)
        self.angle = -90.0  # degrees (up)
        self.cooldown = 0.0
        self.invuln = 0.0
        self.alive = True

        w, h = self.base_image.get_size()
        self.nose_dist = (h / 2) * 0.95   # near the very top
        self.tail_dist = (h / 2) * 0.90   # near the very bottom

        self.thrusting = False  # for flame drawing
        self.radius = 0.5 * w * SHIP_COLLISION_SCALE

        self.sfx_shoot = sfx.get("shoot", _SilentSound())
        self.sfx_shoot.set_volume(1.0)

    def reset(self):
        self.pos = (WIDTH/2, HEIGHT/2)
        self.vel = (0.0, 0.0)
        self.angle = -90.0
        self.cooldown = 0.0
        self.invuln = INVULN_TIME
        self.alive = True
        self.rect.center = self.pos

    def _nose_pos(self):
        fwd = from_angle(math.radians(self.angle))
        return add(self.pos, scale_vec(fwd, self.nose_dist))

    def _tail_pos(self):
        fwd = from_angle(math.radians(self.angle))
        return add(self.pos, scale_vec(fwd, -self.tail_dist))

    def update(self, dt, keys):
        # rotation
        if keys[pygame.K_LEFT]:
            self.angle -= math.degrees(SHIP_TURN_SPEED * dt)
        if keys[pygame.K_RIGHT]:
            self.angle += math.degrees(SHIP_TURN_SPEED * dt)

        # rotate sprite
        self.image = pygame.transform.rotozoom(self.base_image, -self.angle, 1.0)
        center_before = self.rect.center

        # thrust
        self.thrusting = keys[pygame.K_UP]
        if self.thrusting:
            fwd = from_angle(math.radians(self.angle))
            ax, ay = scale_vec(fwd, SHIP_THRUST)
            self.vel = add(self.vel, scale_vec((ax, ay), dt))

        # damping
        self.vel = scale_vec(self.vel, 1.0 - (1.0 - SHIP_FRICTION) * dt)

        # move + wrap
        self.pos = add(self.pos, scale_vec(self.vel, dt))
        self.pos = wrap_position(self.pos)

        # update rect to new center
        self.rect = self.image.get_rect(center=center_before)
        self.rect.center = self.pos

        # timers
        self.cooldown = max(0.0, self.cooldown - dt)
        self.invuln = max(0.0, self.invuln - dt)

    def fire(self, bullets_out):
        if self.cooldown > 0.0 or len(bullets_out) >= MAX_BULLETS:
            return
        fwd = from_angle(math.radians(self.angle))
        muzzle = add(self._nose_pos(), scale_vec(fwd, 6))  # push past tip
        vel = add(scale_vec(fwd, BULLET_SPEED), self.vel)
        bullets_out.append(Bullet(muzzle, vel))
        self.cooldown = 0.18 # bullet rate
        self.sfx_shoot.play()

    def hyperspace(self):
        self.pos = (random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        self.vel = (0.0, 0.0)
        self.rect.center = self.pos
        self.invuln = 0.8

    def draw(self, surf):
        # tail flame while thrusting
        if self.thrusting:
            tail = self._tail_pos()
            fwd = from_angle(math.radians(self.angle))
            side = perp(fwd)

            flame_len = 18
            flame_w   = 10

            tip   = add(tail, scale_vec(fwd, -flame_len))
            baseL = add(tail, scale_vec(side, -flame_w))
            baseR = add(tail, scale_vec(side,  flame_w))

            pygame.draw.polygon(surf, (255, 120, 30), (tip, baseL, baseR))
            inner_tip = add(tip, scale_vec(fwd, 6))
            pygame.draw.polygon(
                surf, (255, 200, 80),
                (inner_tip, add(baseL, scale_vec(fwd, 4)), add(baseR, scale_vec(fwd, 4)))
            )

        # blink during invulnerability
        if self.invuln > 0.0:
            t = pygame.time.get_ticks() / 1000.0
            if math.sin(t * BLINK_HZ * 2 * math.pi) < 0:
                return

        surf.blit(self.image, self.rect)

# ----------------------------
# Game controller
# ----------------------------
class Game:
    def __init__(self, images, sounds, music_ok):
        ship_img, asteroid_imgs, bg_img = images
        self.sounds = sounds
        self.music_ok = music_ok

        self.ship = Ship(ship_img, {"shoot": sounds.get("shoot")})
        self.asteroid_sources = asteroid_imgs
        self.bg_img = bg_img

        self.asteroids = []
        self.bullets = []

        self.score = 0
        self.lives = 3
        self.wave = 0
        self.state = "menu"

        # volumes (0..1)
        self.music_volume = 500.60
        self.sfx_volume   = 500.90
        self.apply_volumes()

        # menu selection
        self.menu_index = 0

        self.font = pygame.font.SysFont("consolas", 22)
        self.big_font = pygame.font.SysFont("consolas", 48, bold=True)

    # ----- utilities -----
    def apply_volumes(self):
        # music
        if self.music_ok:
            pygame.mixer.music.set_volume(max(0.0, min(1.0, self.music_volume)))
        # sfx
        self.sounds.get("shoot", _SilentSound()).set_volume(max(0.0, min(1.0, self.sfx_volume)))
        self.sounds.get("explode", _SilentSound()).set_volume(max(0.0, min(1.0, self.sfx_volume)))
        self.sounds.get("death", _SilentSound()).set_volume(max(0.0, min(1.0, self.sfx_volume)))

    # ----- state / waves -----
    def start(self):
        self.ship.reset()
        self.asteroids.clear()
        self.bullets.clear()
        self.score = 0
        self.lives = 3
        self.wave = 0
        self.state = "playing"
        self.spawn_wave()

    def spawn_wave(self):
        self.wave += 1
        count = 3 + self.wave
        for _ in range(count):
            img = random.choice(self.asteroid_sources)
            scale = random.uniform(0.8, ASTEROID_SCALE_MAX)

            # ensure not too close to ship at spawn
            while True:
                pos = (random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
                temp_radius = 0.5 * img.get_width() * scale * ASTEROID_COLLISION_SCALE
                if not circle_collide(pos, temp_radius, self.ship.pos, 140):
                    break

            angle = random.random() * 2 * math.pi
            speed = random.uniform(*ASTEROID_SPEED_RANGE)
            vel = (math.cos(angle)*speed, math.sin(angle)*speed)
            spin = random.uniform(-60, 60)
            self.asteroids.append(Asteroid(img, pos, vel, scale=scale, spin=spin))

    # ----- input handling for menu -----
    def handle_menu_key(self, key):
        if key == pygame.K_UP:
            self.menu_index = (self.menu_index - 1) % len(MENU_ITEMS)
        elif key == pygame.K_DOWN:
            self.menu_index = (self.menu_index + 1) % len(MENU_ITEMS)
        elif key == pygame.K_LEFT:
            if self.menu_index == 0:
                self.music_volume = max(0.0, self.music_volume - VOL_STEP)
            else:
                self.sfx_volume = max(0.0, self.sfx_volume - VOL_STEP)
            self.apply_volumes()
        elif key == pygame.K_RIGHT:
            if self.menu_index == 0:
                self.music_volume = min(1.0, self.music_volume + VOL_STEP)
            else:
                self.sfx_volume = min(1.0, self.sfx_volume + VOL_STEP)
            self.apply_volumes()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.start()

    # ----- main update/draw -----
    def update(self, dt):
        if self.state != "playing":
            return

        keys = pygame.key.get_pressed()
        self.ship.update(dt, keys)

        if keys[pygame.K_SPACE]:
            self.ship.fire(self.bullets)
        if keys[pygame.K_h]:
            self.ship.hyperspace()

        for b in self.bullets:
            b.update(dt)
        self.bullets = [b for b in self.bullets if not b.dead]

        for a in self.asteroids:
            a.update(dt)

        # bullets vs asteroids
        new_asteroids = []
        for a in self.asteroids:
            hit_bullet = None
            for b in self.bullets:
                if circle_collide(a.pos, a.radius, b.pos, 2):
                    hit_bullet = b
                    break
            if hit_bullet:
                self.score += max(10, int(a.radius))
                hit_bullet.dead = True
                new_asteroids.extend(a.split())
                self.sounds.get("explode", _SilentSound()).play()
            else:
                new_asteroids.append(a)
        self.asteroids = [a for a in new_asteroids if not a.dead]
        self.bullets = [b for b in self.bullets if not b.dead]

        # ship vs asteroids
        if self.ship.invuln <= 0.0:
            for a in self.asteroids:
                if circle_collide(self.ship.pos, self.ship.radius, a.pos, a.radius):
                    self.ship_die()
                    break

        if not self.asteroids:
            self.spawn_wave()

    def ship_die(self):
        self.lives -= 1
        self.sounds.get("death", _SilentSound()).play()
        if self.lives < 0:
            self.state = "gameover"
        else:
            self.ship.reset()

    def draw(self, surf):
        # background
        if self.bg_img:
            surf.blit(self.bg_img, (0, 0))
        else:
            surf.fill(BG_COLOR)

        if self.state == "menu":
            self.draw_menu(surf)
            return
        if self.state == "gameover":
            self.draw_gameover(surf)
            return

        for a in self.asteroids:
            a.draw(surf)
        for b in self.bullets:
            b.draw(surf)
        self.ship.draw(surf)
        self.draw_ui(surf)

    def draw_ui(self, surf):
        ui = ("#00ff40")
        surf.blit(self.font.render(f"Score: {self.score}", True, ui), (WIDTH - 1250, HEIGHT - 1000))
        surf.blit(self.font.render(f"Wave: {self.wave}", True, ui), (WIDTH - 700, HEIGHT - 970))
        surf.blit(self.font.render(f"Lives: {max(0, self.lives)}", True, ui), (WIDTH - 1250, HEIGHT - 950))
        hint = self.font.render("Arrows rotate/thrust  Space shoot  H hyperspace", True, (170, 180, 200))
        surf.blit(hint, (WIDTH - hint.get_width() - 12, 10))

    def draw_menu(self, surf):
        title = self.big_font.render("404", True, ("#ffc400"))
        prompt = self.font.render("Enter: Start   Esc: Quit", True, (170, 180, 200))

        # slider draw helper
        def draw_slider(x, y, w, h, value, selected):
            pygame.draw.rect(surf, (70, 80, 95), (x, y, w, h), border_radius=6)
            fill_w = int(w * max(0.0, min(1.0, value)))
            pygame.draw.rect(surf, (180, 210, 255), (x, y, fill_w, h), border_radius=6)
            if selected:
                pygame.draw.rect(surf, (230, 240, 255), (x-2, y-2, w+4, h+4), width=2, border_radius=8)

        surf.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//2 - 140))
        surf.blit(prompt, (WIDTH//2 - prompt.get_width()//2, HEIGHT//2 + 130))

        # labels + sliders
        label_music = self.font.render(f"Music Volume: {int(self.music_volume*100)}%", True, (200, 210, 230))
        label_sfx   = self.font.render(f"SFX Volume: {int(self.sfx_volume*100)}%", True, (200, 210, 230))
        lx = WIDTH//2 - 240
        sx = WIDTH//2 - 240
        y0 = HEIGHT//2 - 40
        y1 = HEIGHT//2 + 20

        surf.blit(label_music, (lx, y0 - 28))
        draw_slider(sx, y0, 480, 18, self.music_volume, self.menu_index == 0)

        surf.blit(label_sfx, (lx, y1 - 28))
        draw_slider(sx, y1, 480, 18, self.sfx_volume, self.menu_index == 1)

    def draw_gameover(self, surf):
        title = self.big_font.render("GAME OVER", True, (220, 230, 245))
        score = self.font.render(f"Score: {self.score}  •  Wave: {self.wave}", True, (200, 210, 230))
        prompt = self.font.render("Press ENTER to play again   Esc to quit", True, (170, 180, 200))
        surf.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//2 - 70))
        surf.blit(score, (WIDTH//2 - score.get_width()//2, HEIGHT//2 - 20))
        surf.blit(prompt, (WIDTH//2 - prompt.get_width()//2, HEIGHT//2 + 20))

# ----------------------------
# Boot
# ----------------------------
def main():
    pygame.init()
    try:
        pygame.mixer.init()
    except Exception as e:
        print("[WARN] mixer init failed:", e)

    pygame.display.set_caption("Asteroids — PNG+Sounds+Music (menu volume controls)")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    # Debug paths
    print("[DEBUG] ROOT_DIR:", ROOT_DIR)
    print("[DEBUG] IMAGES_DIR exists:", os.path.isdir(IMAGES_DIR))
    print("[DEBUG] SOUNDS_DIR exists:", os.path.isdir(SOUNDS_DIR))

    # Images
    ship_img = load_image_safe(SHIP_IMG_PATH, fallback_size=(56, 56), fallback_shape="triangle")
    asteroid_imgs = [load_image_safe(p, fallback_size=(128, 128), fallback_shape="circle")
                     for p in asteroid_image_paths()] or \
                    [load_image_safe(os.path.join(IMAGES_DIR, "asteroid1.png"),
                                     fallback_size=(128, 128), fallback_shape="circle")]
    bg_img = load_background_scaled(BG_IMG_PATH, (WIDTH, HEIGHT))

    # Sounds
    sfx = {
        "shoot":   load_sound_safe(SND_SHOOT_PATH),
        "explode": load_sound_safe(SND_EXPLODE_PATH),
        "death":   load_sound_safe(SND_DEATH_PATH),
    }

    # Music
    music_ok = try_start_music(MUSIC_PATH, volume=0.60)

    game = Game((ship_img, asteroid_imgs, bg_img), sfx, music_ok)

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif game.state == "menu":
                    game.handle_menu_key(event.key)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if game.state == "gameover":
                        game.start()

        game.update(dt)
        game.draw(screen)
        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
