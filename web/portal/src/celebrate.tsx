/**
 * A small confetti burst for moments worth marking — finishing setup, switching on the last
 * permission, sending the first quote.
 *
 * Written here rather than pulled in as a dependency: it is ~60 lines, it must never block
 * rendering, and it must respect `prefers-reduced-motion` (a celebration is not worth making
 * someone motion-sick on a job site).
 */

const COLOURS = ['#c8f560', '#7c5cff', '#22d3ee', '#f472b6', '#fbbf24', '#34d399'];

type Particle = {
  x: number; y: number; vx: number; vy: number;
  size: number; spin: number; angle: number; colour: string; life: number;
};

/** Fire a burst. Safe to call when there is no DOM (tests, SSR). */
export function celebrate(intensity = 1): void {
  if (typeof document === 'undefined') return;
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;

  const canvas = document.createElement('canvas');
  canvas.setAttribute('aria-hidden', 'true');
  canvas.style.cssText =
    'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:9999';
  document.body.appendChild(canvas);
  const rendered = canvas.getContext('2d');
  if (!rendered) { canvas.remove(); return; }
  // Narrowed once here so the animation closure keeps the non-null type.
  const context: CanvasRenderingContext2D = rendered;

  const ratio = window.devicePixelRatio || 1;
  const width = window.innerWidth;
  const height = window.innerHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  context.scale(ratio, ratio);

  const count = Math.round(120 * intensity);
  const particles: Particle[] = Array.from({length: count}, () => {
    const fromLeft = Math.random() < 0.5;
    return {
      x: fromLeft ? width * 0.1 : width * 0.9,
      y: height * 0.62,
      vx: (fromLeft ? 1 : -1) * (2 + Math.random() * 7),
      vy: -(7 + Math.random() * 9),
      size: 5 + Math.random() * 7,
      spin: (Math.random() - 0.5) * 0.4,
      angle: Math.random() * Math.PI,
      colour: COLOURS[Math.floor(Math.random() * COLOURS.length)],
      life: 1,
    };
  });

  const started = performance.now();
  const duration = 2600;

  function frame(now: number) {
    const elapsed = now - started;
    context.clearRect(0, 0, width, height);
    for (const particle of particles) {
      particle.vy += 0.28;          // gravity
      particle.vx *= 0.995;         // drag
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.angle += particle.spin;
      particle.life = Math.max(0, 1 - elapsed / duration);
      context.save();
      context.globalAlpha = particle.life;
      context.translate(particle.x, particle.y);
      context.rotate(particle.angle);
      context.fillStyle = particle.colour;
      context.fillRect(-particle.size / 2, -particle.size / 4, particle.size, particle.size / 2);
      context.restore();
    }
    if (elapsed < duration) requestAnimationFrame(frame);
    else canvas.remove();
  }
  requestAnimationFrame(frame);
}

/** Celebrate once per business, the first time they finish setting up. */
export function celebrateOnce(slug: string): void {
  try {
    const key = 'concierge:celebrated:' + (slug || 'me');
    if (localStorage.getItem(key)) return;
    localStorage.setItem(key, String(Date.now()));
  } catch {
    // Private mode blocks localStorage; a celebration is not worth failing over.
  }
  celebrate();
}
