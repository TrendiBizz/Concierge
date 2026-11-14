/**
 * A confetti stream for moments worth marking — finishing setup, pressing Continue on
 * permissions, sending the first quote.
 *
 * The first version was a single two-second burst from the lower corners: too little, too fast,
 * and it landed before anyone looked up. This one pours from the top edge of the screen for five
 * seconds and takes another few seconds to clear, so the moment is actually visible.
 *
 * Written here rather than pulled in as a dependency: it must never block rendering, and it must
 * respect `prefers-reduced-motion` (a celebration is not worth making someone motion-sick on a
 * job site).
 */

const COLOURS = ['#c8f560', '#7c5cff', '#22d3ee', '#f472b6', '#fbbf24', '#34d399', '#fb7185', '#a78bfa'];

/** How long new confetti keeps arriving from the top (ms). */
const EMIT_MS = 5000;
/** How long the whole effect runs before the canvas is removed (ms). */
const TOTAL_MS = 9000;

type Piece = {
  x: number; y: number; vx: number; vy: number;
  size: number; spin: number; angle: number; colour: string;
  wobble: number; wobblePhase: number;
};

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

  const pieces: Piece[] = [];
  const perFrame = Math.max(2, Math.round(3 * intensity));

  function spawn(): Piece {
    return {
      // Spread across the whole top edge, slightly off-screen so they enter rather than appear.
      x: Math.random() * width,
      y: -20 - Math.random() * 60,
      vx: (Math.random() - 0.5) * 1.6,
      vy: 1.4 + Math.random() * 2.6,
      size: 6 + Math.random() * 9,
      spin: (Math.random() - 0.5) * 0.25,
      angle: Math.random() * Math.PI,
      colour: COLOURS[Math.floor(Math.random() * COLOURS.length)],
      wobble: 0.4 + Math.random() * 1.2,
      wobblePhase: Math.random() * Math.PI * 2,
    };
  }

  const started = performance.now();

  function frame(now: number) {
    const elapsed = now - started;
    context.clearRect(0, 0, width, height);

    // Keep the stream going for EMIT_MS: this is what makes it read as falling confetti
    // rather than a firework that has already finished by the time you look.
    if (elapsed < EMIT_MS) {
      for (let i = 0; i < perFrame; i += 1) pieces.push(spawn());
    }

    for (let i = pieces.length - 1; i >= 0; i -= 1) {
      const piece = pieces[i];
      piece.wobblePhase += 0.03;
      piece.vy = Math.min(piece.vy + 0.02, 6);          // gentle acceleration
      piece.x += piece.vx + Math.sin(piece.wobblePhase) * piece.wobble;
      piece.y += piece.vy;
      piece.angle += piece.spin;
      if (piece.y > height + 40) { pieces.splice(i, 1); continue; }

      context.save();
      context.translate(piece.x, piece.y);
      context.rotate(piece.angle);
      context.fillStyle = piece.colour;
      context.fillRect(-piece.size / 2, -piece.size / 4, piece.size, piece.size / 2);
      context.restore();
    }

    if (elapsed < TOTAL_MS) requestAnimationFrame(frame);
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
