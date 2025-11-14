import math
import random
import os
import pygame

# Window/ gameplay setting
WIDTH, HEIGHT = 960, 640
FPS = 60
BG_COLOR = (5, 7, 12)

BULLET_SPEED = 520.0
BULLET_LIFETIME = 1.2
MAX_BULLETS = 5

SHIP_TURNS_SPEED = math.radians(220)
SHIP_THRUST = 300.0
SHIP_FRICTION = 0.9
SHIP_COLLISION_SCALE = 0.75

ASTEROID_SPEED_RANGE = (60, 160)
ASTEROID_FRAGMENT_COUNT = (2, 3)
ASTEROID_SCALE_MIN = 0.45
ASTEROID_SCALE_MAX = 1.0
ASTEROID_COLLISION_SCALE = 0.85

INVULN_TIME = 2.0
BLINK_HZ = 10.0

MENU_ITEMS = ["Music Volume", "SFX Volume"]
VOL_STEP = 0.05

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(ROOT_DIR, "assets", "images")
SOUNDS_DIR = os.path.join(ROOT_DIR, "assets", "sounds")

SHIP_IMG_PATH = os.path.join(IMAGES_DIR, "ship.png")
BG_IMG_PATH = os.path.join(IMAGES_DIR, "space_bg.png")

SND_SHOOT_PATH = os.path.join(SOUNDS_DIR, "shoot.wav")
SND_EXPLODE_PATH = os.path.join(SOUNDS_DIR, "explode.wav")
SND_DEATH_PATH = os.path.join(SOUNDS_DIR, "death.wav")
MUSIC_PATH = os.path.join(SOUNDS_DIR, "bg_music.wav")


def asteroid_image_paths():
    if not os.path.isdir(IMAGES_DIR):
        return []
    candidates = []
    for fname in os.listdir(IMAGES_DIR):
        low = fname.lower()
        if low.startswith("asteroid") and low.endswith(".png"):
            candidates.append(os.path.join(IMAGES_DIR, fname))
    return sorted(candidates)


def wrap_position(pos):
    # Accept tuple/list or pygame.Vector2, return same type as input
    if hasattr(pos, "x"):
        x = pos.x % WIDTH
        y = pos.y % HEIGHT
        return pygame.math.Vector2(x, y)
    x, y = pos
    x = x % WIDTH
    y = y % HEIGHT
    return (x, y)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def scale_vector(v, s):
    return (v[0] * s, v[1] * s)


def from_angle(angle_radians):
    return (math.cos(angle_radians), math.sin(angle_radians))


def perp(v):
    return (-v[1], v[0])


def circle_collision(pos1, radius1, pos2, radius2):
    dx = pos1[0] - pos2[0]
    dy = pos1[1] - pos2[1]
    return dx * dx + dy * dy < (radius1 + radius2) ** 2


def load_image_safe(path, fallback_size=(64, 64), fallback_shape="triangle"):
    path = os.path.normpath(path)
    try:
        img = pygame.image.load(path).convert_alpha()
        print(f"[OK] Loaded image: {path}")
        return img
    except Exception as e:
        print(f"[WARN] Could not load image {path}: {e}")
        w, h = int(fallback_size[0]), int(fallback_size[1])
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if fallback_shape == "triangle":
            pts = [(w * 0.5, 0), (w, h), (0, h)]
            pygame.draw.polygon(surf, (200, 240, 255), pts, width=2)
        else:
            pygame.draw.circle(surf, (180, 210, 220), (w // 2, h // 2), min(w, h) // 2, width=2)
        return surf


def load_background_image(path, size=None):
    path = os.path.normpath(path)
    try:
        img = pygame.image.load(path).convert()
        if size is not None:
            img = pygame.transform.smoothscale(img, (int(size[0]), int(size[1])))
        print(f"[OK] Loaded background image: {path}")
        return img
    except Exception as e:
        print(f"[WARN] Could not load background image {path}: {e}")
        return None


class _SilentSound:
    def set_volume(self, *_): pass
    def play(self, *_): pass


def load_sound_safe(path):
    path = os.path.normpath(path)
    try:
        sound = pygame.mixer.Sound(path)
        print(f"[OK] Loaded sound: {path}")
        return sound
    except Exception as e:
        print(f"[WARN] Could not load sound {path}: {e}")
        return _SilentSound()


def try_start_music(path, volume=0.6):
    path = os.path.normpath(path)
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume))))
        pygame.mixer.music.play(-1)
        print(f"[OK] Playing background music: {path}")
        return True
    except Exception as e:
        print(f"[WARN] Failed to play background music ({path}): {e}")
        return False


class Bullet:
    def __init__(self, pos, vel):
        # pos and vel are tuples (x,y)
        self.pos = (float(pos[0]), float(pos[1]))
        self.vel = (float(vel[0]), float(vel[1]))
        self.age = 0.0
        self.dead = False

    def update(self, dt):
        self.age += dt
        if self.age > BULLET_LIFETIME:
            self.dead = True
            return
        self.pos = add(self.pos, scale_vector(self.vel, dt))
        self.pos = wrap_position(self.pos)

    def draw(self, surface):
        pygame.draw.circle(surface, (255, 240, 160), (int(self.pos[0]), int(self.pos[1])), 2)


class Asteroid:
    def __init__(self, pos, vel, image, scale=1.0, spin=0.0):
        # pos, vel: tuple or Vector2; image: pygame.Surface
        self.pos = (float(pos[0]), float(pos[1]))
        self.vel = (float(vel[0]), float(vel[1]))
        self.base_image = image
        self.scale = float(scale)
        self.angle = random.uniform(0.0, 360.0)
        self.spin = float(spin)
        self.dead = False

        # Pre-scale image
        w, h = self.base_image.get_size()
        w_sh = max(1, int(w * self.scale))
        h_sh = max(1, int(h * self.scale))
        self.image_scaled = pygame.transform.smoothscale(self.base_image, (w_sh, h_sh))
        self.image = self.image_scaled
        self.rect = self.image.get_rect(center=(int(self.pos[0]), int(self.pos[1])))

        # Collision radius
        self.radius = 0.5 * self.angle_width() * ASTEROID_COLLISION_SCALE

    def update(self, dt):
        self.pos = add(self.pos, scale_vector(self.vel, dt))
        self.pos = wrap_position(self.pos)
        self.angle = (self.angle + self.spin * dt) % 360
        self.rect.center = (int(self.pos[0]), int(self.pos[1]))

    def draw(self, surf):
        surf.blit(self.image, self.rect)

    def split(self):
        new_scale = self.scale * 0.6
        if new_scale < ASTEROID_SCALE_MIN:
            self.dead = True
            return []
        pieces = []
        # Create 2-3 smaller asteroids
        for _ in range(random.randint(*ASTEROID_FRAGMENT_COUNT)):
            ang = random.random() * 2 * math.pi
            speed = random.uniform(*ASTEROID_SPEED_RANGE)
            val = add(self.val, math.cos(ang) * speed, math.sin(ang) * speed)
            spin = random.uniform(-120.0, 120.0)
            pieces.append(Asteroid(self.pos, val, self.base_image, new_scale, spin))
        self.dead = True
        return pieces