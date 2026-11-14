/** A small, consistent icon set. Emoji looked like a phone keyboard: colourful but different
 *  on every machine, and impossible to tint to the section colour. These are 24×24 strokes. */
import type {ReactElement} from 'react';

const paths: Record<string, ReactElement> = {
  home: <path d="M4 11.5 12 4l8 7.5M6 10.5V20h5v-5h2v5h5v-9.5" />,
  chat: <path d="M4 6h16v10H9l-5 4V6Z" />,
  users: <path d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 0a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 20c0-3 2.5-5 5-5s5 2 5 5m1-4.5c2 0 4 1.5 4 4.5" />,
  calendar: <path d="M4 6h16v14H4V6Zm0 5h16M8 3v4m8-4v4" />,
  quote: <path d="M6 3h9l4 4v14H6V3Zm9 0v4h4M9 12h7M9 16h7" />,
  box: <path d="M12 3 3 7.5v9L12 21l9-4.5v-9L12 3Zm0 0v18m9-13.5-9 4.5-9-4.5" />,
  compass: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm3-12-2 5-5 2 2-5 5-2Z" />,
  megaphone: <path d="M4 10v4l11 4V6L4 10Zm11 0h3a3 3 0 0 1 0 6h-3M7 15v3" />,
  image: <path d="M4 5h16v14H4V5Zm0 10 4-4 4 4 3-3 5 5" />,
  chart: <path d="M4 20V4m0 16h16M8 16V9m4 7V6m4 10v-4" />,
  shield: <path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6l7-3Zm-3 9 2.5 2.5L15.5 10" />,
  gear: <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8-3.5-2-1 .3-2.2-2-1.2-1.7 1.4-2-.8-.5-2.2h-2.3l-.5 2.2-2 .8L5.7 7.6l-2 1.2L4 11l-2 1 2 1-.3 2.2 2 1.2 1.7-1.4 2 .8.5 2.2h2.3l.5-2.2 2-.8 1.7 1.4 2-1.2L20 13l2-1Z" />,
  handshake: <path d="M3 12l4-4 3 3 2-2 2 2 3-3 4 4-6 6-2-2-2 2-2-2-2 2-4-4" />,
  folder: <path d="M3 6h6l2 2h10v11H3V6Z" />,
};

export function Icon({name, colour, size = 18}: {name: keyof typeof paths | string; colour?: string; size?: number}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke={colour || 'currentColor'} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"
         style={{flex: 'none'}}>
      {paths[name] || paths.home}
    </svg>
  );
}
