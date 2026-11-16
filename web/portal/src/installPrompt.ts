/**
 * The one place that knows whether this browser can install Concierge as an app.
 *
 * `beforeinstallprompt` fires once, early — often before React has mounted the shell and always
 * before a user signs in. Capturing it inside the signed-in shell (the old behaviour) meant the
 * event was gone by the time an "Install app" button existed, so the button never appeared on
 * Android. This module listens at startup and keeps the event for whoever asks.
 */

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice?: Promise<{outcome: 'accepted' | 'dismissed'}>;
};

let deferred: BeforeInstallPromptEvent | null = null;
const listeners = new Set<(available: boolean) => void>();

function announce() {
  for (const listener of listeners) listener(Boolean(deferred));
}

export function initInstallCapture() {
  if (typeof window === 'undefined') return;
  window.addEventListener('beforeinstallprompt', (event) => {
    // Chrome shows its own mini-infobar unless the page takes over the prompt.
    event.preventDefault();
    deferred = event as BeforeInstallPromptEvent;
    announce();
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    announce();
  });
}

export function installAvailable() {
  return Boolean(deferred);
}

export function onInstallChange(listener: (available: boolean) => void) {
  listeners.add(listener);
  listener(Boolean(deferred));
  return () => { listeners.delete(listener); };
}

export async function promptInstall(): Promise<boolean> {
  if (!deferred) return false;
  const event = deferred;
  await event.prompt();
  const choice = await event.userChoice?.catch(() => undefined);
  // The event can only be used once; a second call must not look like a working button.
  deferred = null;
  announce();
  return choice?.outcome === 'accepted';
}

/** True once the app is running from the home screen rather than a browser tab. */
export function isInstalled() {
  if (typeof window === 'undefined') return false;
  const standalone = window.matchMedia?.('(display-mode: standalone)').matches;
  const iosStandalone = (window.navigator as Navigator & {standalone?: boolean}).standalone === true;
  return Boolean(standalone || iosStandalone);
}

export function isIOS() {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  // iPadOS 13+ reports a desktop Mac user agent, so touch points are the tell.
  return /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}

export function isAndroid() {
  return typeof navigator !== 'undefined' && /Android/i.test(navigator.userAgent || '');
}

export function isMobile() {
  if (typeof navigator === 'undefined') return false;
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '') ||
    (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent || ''));
}

/** The address a QR code should carry: a page that explains and offers the install. */
export function installUrl() {
  const origin = typeof location === 'undefined' ? '' : location.origin;
  return origin + '/studio/install';
}
