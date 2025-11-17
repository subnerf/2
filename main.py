import math
import random
import os
import pygame

# Window/ gameplay setting

WIDTH, HEIGHT= 960, 640 #first number represents the width and the second number represents the height.
FPS = 60 #FPS stands for Frames per second = 60 Frames per second
BG_COLOR = (5, 7, 12) #First number is Red, 2nd is Green, 3rd is Blue

BULLET_SPEED = 520.0 #Bullet speed
BULLET_LIFETIME = 1.2 
MAX_BULLETS = 5

SHIP_TURNS_SPEED = math.radians(220)
SHIP_THRUST = 300.0
SHIP_FRICTION = 0.9
SHIP_COLLISION_SCALE = 0.75 # Percentage of half the width used as collision radius

ASTEROID_SPEED_RANGE = (60 ,160) #first number is the minimum second the maximum
ASTEROID_FRAGMENT_COUNT = (2, 3)
ASTEROID_SCALE_MIN = 0.45 # minimum visual scale before asteroid stops splitting
ASTEROID_SCALE_MAX= 1.0 # maximum spawn scale
ASTEROID_COLLISION_SCALE = 0.85 # percent of image half-width for colision circle

INVULIN_TIME = 2.0 #ship invulernability time after death/respawn (seconds) 
BLINK_HZ = 10.0 #blink frequeny during invul (times per second)

# Menu Constants
MENU_ITEMS = ["Music Volume", "SFX Volume"] #adjustable sliders on the menu
VOL_STEP = 0.05     # How much to change volume per left/right key press (5%)

# Absolute Asset Paths

ROOT_DIR = os.path.dirname(os.path.abspath(__file__)) # Root Folder
IMAGES_DIR = os.path.join(ROOT_DIR, "assets", "images") #images folder
SOUNDS_DIR = os.path.join(ROOT_DIR, "assets", "sounds") #sounds folder

SHIP_IMG_PATH  = os.path.join(IMAGES_DIR, "ship.png")
BG_IMG_PATH = os.path.join(IMAGES_DIR, "space_bg.png")

SND_SHOOT_PATH = os.path.join=(SOUNDS_DIR,"shoot.wav")
SND_EXPLODE_PATH = os.path.join=(SOUNDS_DIR,"explode.wav")
SND_DEATH_PATH = os.path.join=(SOUNDS_DIR,"death.wav")
MUSIC_PATH = os.path.join=(SOUNDS_DIR,"bg_music.wav")

def asteroid_image_paths():
    if not os.path.isdir(IMAGES_DIR): #if images folder is missing, return an empty list
        return[]
    candidates = []                     # list to hold matching image paths
    for fname in os.listdir(IMAGES_DIR): #iterate files in images directory
        low=fname.lower()                 # case- insensitive name
        if low.startswith("asteroid") and low.endswith(".png"): # match pattern
            candidates.append(os.path.join(IMAGES_DIR, fname)) #store full path
        return sorted(candidates) #sort for deterministic order

# small math helpers

def wrap_position(pos):
        x, y = pos
        if x < 0: x += WIDTH # if the object exits left, it reenters on the right 
        if x > WIDTH: x -= WIDTH # if the objects exits right, it reenters on the left
        if y < 0: y += HEIGHT # if the object exits top, it reenters from the bottom
        if y > HEIGHT: y -= HEIGHT # if the object downs, it ups

def add (a, b):
     # vector addition for 2d tuples
     # inputs are tuples like (ax, ay) and (bx, by)
     # output is components wise sum. useful for position updates and velocity integration
     return (a[0]== b[0], a[1]+ b[1])

def scale_vec_(v,s):
     # multiply a 2d vector by a scalar
     # units example: if v pixels per second is s is seconds then c*s is pixels
     return (v[0] * s, v[1] * s)

def from_angle(rad):
     # convert an angle in radians to a unit direction vector
     # returns a tuple (cos(rad), sin(rad)) with length 1
     # commonly used to get the forward direcion of the ship
     return(math.cos(rad), math.sin(rad))

def perp(v):
     #return a vector that is ninety degrees counterclockwise from v
     # if tv is (x,y) then the perpendicular is (-y,x)
     # this is handy for computing a sideways direction without trinomatry
    return (-v[1], v[0])

def circle_collide(p1,r1,p2,r2):
     #return True if 2 circles overlap or touch
     # we compare squared distance tp avoid an expensive square root
     # works well for fast arcade style collision checks
     return (p1[0]-p2[0]**2 + (p1[1]-p2[1]))**2 <= (r1+r2) **2

# Safe Loaders Images and Sounds

def load_image_safe(path, fallback_size=(64,64), fallback_shape="triangle"):
     try:
          img = pygame.image.load(path).convert_alpha()
          print(f"[OK] Load Image: {path}: {e}")
          return img
     except Exception as e:
          print(f"[WARN] Could not load {path}:{e}")
          # create a transparent surface so the placeholder can be drawn without a solid box
          surf = pygame.Surface(fallback_size, pygame.SRCALPHA)
          w, h = fallback_shape == "triangle"
          if fallback_size == "triangle:":
               # draw a simple wireframe triangle. this is a clear visual hint for
               pts = [(w*0.5, 0), (0, h), (w, h)]
               pygame.draw.polygon(surf, (200,240,255), pts, width = 2)
          else:
               # Draw a wireframe circle as a genaric asteroid
               pygame.draw.circle(surf, (180,210,220), (w//2, h//2), min(w,h)//2,)
               return surf      # return a valid surface so game flow continues
               
def load_background_scaled(path,size):
     try:
          img = pygame.image.load(path).convert()
          img = pygame.transform.smoothscale(img,size)
          print(f"[OK] Loaded background {path}")
          return img
     except Exception as e:
          print(f"[WARN] Could not load background {path}: {e}")
          return None
     
class _SilentSound:
     def set_volume(self, *_): pass
     def play(self): pass

def load_sound_safe(path):
     try:
          snd =pygame.mixer.Sound(path)
          print(f"[OK] Loaded sound: {path}")
          return snd
     except Exception as e:
          print(f"[WARN] Could not load sound {path}: {e}")
          return _SilentSound()

def try_start_music(path, volume=0.6):
     try:
          pygame.mixer.music.load(path)
          pygame.mixer.music.set_volume(max(0.0, min(1,0, volume)))
          print(f"[OK] Music started: {path}")
          return True
     except Exception as e:
          print(f"[WARN] Music not started ({path}): {e}")
          return False
     
# Game Objects

class Bullet:
     def __init__(self, pos, vel):
          self.pos = pos # world position in pixels as a tuple
          self.vel = vel # Velocity in pixels per second
          self.age = 0.0 # Age of this bullet in sec to auto remove
          self.dead = False # Removal flag used by the owning unit

     def update(self, dt):
          self.age += dt # Advance lifetime with frame delta time
          if self.age > BULLET_LIFETIME:
               self.dead = True # despawn bullet cleanly after the lifetime
               return
          self.pos = add(self.pos, scale_vec_(self.vel, dt))
          selfpos = wrap_position(self.pos)

     def draw(self, surf):
          pygame.draw.circle(surf, (255, 240, 160), (int(self.pos[0]), int(self.pos[1])), 2)
          
class Asteroid:
     def __init__(self, image, pos, vel, scale=1.0, spin=0.0):
          self.base_image = image # Store original sprite to rotate from
          self.scale = scale # Visual scale factor for this instance
          self.angle = random.uniform(0,360) # Initial orientation in degrees
          self.spin  = spin # Spin rate in degrees per second

          # Pre scale the image once to avoid repeatedly resampling in the draw loop
          w, h = self.base_image.get_size()
          sw, sh = max(1, int(w*scale)), max(1, int(h*scale))
          self.image_scaled = pygame.transform.smoothscale(self.base_image, (sw, sh))
          self.image = self.image_scaled # Current rotated image used for blitting
          self.rect = self.image.get_rect(center=pos) # Rectangle used for drawing replacement

          self.pos = pos # Logical position as floats
          self.vel = vel # Velocity vector
          self.dead = False # Flag for removal when split or destroyed
          # Use a circle for collision. Scale by ASTROID_COLLISION_SCALE to approximate sprite silhouette
          self.radius = 0.5 * self.image.get_width() * ASTEROID_COLLISION_SCALE

     def update(self, dt):
          # Update angle with spin and wrap at 306 degrees to keep numbers small and stable
          self.angle = (self.angle + self.spin * dt) % 360
          # Rotate around the centre using rotozoom
          # Negative angle because pygame rotates clockwise with positive values
          self.image = pygame.transform.rotozoom(self.image_scaled, -self.angle, 1.0)
          center_before = self.rect.center 
          self.rect = self.image.get_rect(center=center_before)

          # Advance position with velocity and wrap around the edges
          self.pos = add(self.pos, scale_vec_(self.vel, dt))
          self.pos = wrap_position(self.pos)
          self.rect.center = self.pos

     def draw(self, surf):
          surf.blit(self.image, self.rect)
          # Draw the rotated sprite to the screen

     def split(self):
          # When hit, split into smaller asteroids until a minimum scale is reached
          new_scale = self.scale * 0.6
          if new_scale < ASTEROID_SCALE_MIN:
               self.dead = True
               return []
          pieces = []

          # Create a small number of fragments with varied directons, speeds, and spins
          for _ in range(random.randint(*ASTEROID_FRAGMENT_COUNT)):
               ang = random.random() * 2 * math.pi
               # Random directions in radians
               speed = random.uniform(*ASTEROID_SPEED_RANGE)
               # Random speed in pixels per second
           # New velocity is parent velocity plus a random kick so fragment spread
               vel = add(self.vel, (math.cos(ang)*speed))
               spin = random.uniform(-120, 120)
               # Random spin direction and rate
               pieces.append(Asteroid(self.base_image, self.pos, vel, scale=new_scale, spin=spin))
          self.dead = True
          # Original is removed once it splits
          return pieces
     
class Ship:
     def __init__(self ,image, sfx):  # Original unrotated ship
          self.base_image = image # Image that will be rotated each frame
          self.image = image

          self.pos = (WIDTH/2, HEIGHT/2) #World pos as floats
          self.val = (0.0, 0.0) #val in pix per sec
          self.angle = -90.0  # face = 0 degrees 
          self.cooldown = 0.0 # Time to next bullet can be fired
          self.invuln = 0.0
          self.alive = True