"""Lightweight particle system: dust, sparkles, energy sparks and confetti."""
import math
import random

import pygame

from config import settings as S


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color", "kind", "spin", "angle", "gravity")

    def __init__(self, x, y, vx, vy, life, size, color, kind, gravity=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size, self.color, self.kind = size, color, kind
        self.angle = random.uniform(0, 6.28)
        self.spin = random.uniform(-6, 6)
        self.gravity = gravity


class ParticleSystem:
    MAX = 500

    def __init__(self):
        self.items = []

    def clear(self):
        self.items.clear()

    def _add(self, p):
        if len(self.items) < self.MAX:
            self.items.append(p)

    def dust(self, pos, radius, n=3):
        """Dust puffs thrown outwards by the cleaning brush."""
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(0.6, 1.8) * radius
            shade = random.randint(120, 190)
            self._add(Particle(pos[0] + math.cos(a) * radius * 0.5, pos[1] + math.sin(a) * radius * 0.5,
                               math.cos(a) * sp, math.sin(a) * sp - radius * 0.4,
                               random.uniform(0.35, 0.8), random.uniform(0.06, 0.14) * radius,
                               (shade, int(shade * 0.85), int(shade * 0.62)), "dust"))

    def sparkle(self, pos, radius, n=14, color=S.GREEN):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(0.8, 2.4) * radius
            self._add(Particle(pos[0], pos[1], math.cos(a) * sp, math.sin(a) * sp,
                               random.uniform(0.4, 0.9), random.uniform(0.08, 0.16) * radius,
                               random.choice([color, S.WHITE, color]), "star"))

    def energy(self, pos, radius, n=2, color=S.CYAN):
        """Sparks drawn in towards a charging robot."""
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            d = random.uniform(0.9, 1.4) * radius
            life = random.uniform(0.3, 0.6)
            self._add(Particle(pos[0] + math.cos(a) * d, pos[1] + math.sin(a) * d,
                               -math.cos(a) * d / life, -math.sin(a) * d / life,
                               life, random.uniform(0.05, 0.09) * radius, color, "spark"))

    def trail(self, pos, radius, color=S.CYAN):
        self._add(Particle(pos[0] + random.uniform(-0.2, 0.2) * radius, pos[1] + random.uniform(-0.2, 0.2) * radius,
                           0, 0, 0.35, 0.07 * radius, color, "spark"))

    def confetti(self, width, n=6):
        for _ in range(n):
            self._add(Particle(random.uniform(0, width), -10, random.uniform(-40, 40), random.uniform(120, 260),
                               random.uniform(2.5, 4.0), random.uniform(5, 10),
                               random.choice([S.CYAN, S.GREEN, S.ORANGE, S.BLUE, S.WHITE, S.PURPLE]),
                               "confetti", gravity=60))

    def update(self, dt):
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            if p.kind == "dust":
                p.vx *= 1 - min(1.0, 3.0 * dt)
                p.vy *= 1 - min(1.0, 3.0 * dt)
            p.angle += p.spin * dt
            alive.append(p)
        self.items = alive

    def draw(self, surf):
        for p in self.items:
            k = p.life / p.max_life
            if p.kind == "dust":
                r = max(1, int(p.size * (1.6 - 0.6 * k)))
                tmp = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(tmp, (*p.color, int(170 * k)), (r, r), r)
                surf.blit(tmp, (p.x - r, p.y - r))
            elif p.kind == "star":
                r = max(1.0, p.size * k * 1.6)
                c = p.color
                pygame.draw.line(surf, c, (p.x - r, p.y), (p.x + r, p.y), 2)
                pygame.draw.line(surf, c, (p.x, p.y - r), (p.x, p.y + r), 2)
            elif p.kind == "spark":
                r = max(1, int(p.size * (0.5 + k)))
                pygame.draw.circle(surf, tuple(int(c * (0.4 + 0.6 * k)) for c in p.color), (int(p.x), int(p.y)), r)
            else:  # confetti
                w = p.size * abs(math.cos(p.angle)) + 2
                rect = pygame.Rect(0, 0, int(w), int(p.size * 0.6) + 2)
                rect.center = (int(p.x), int(p.y))
                pygame.draw.rect(surf, p.color, rect, border_radius=2)
