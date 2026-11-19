/**
 * Social network marks, in their real brand colours.
 *
 * Text links ("Connect linkedin organization") made the social connections look like form
 * buttons. These are the official marks, served from /studio/social/ so the Studio does not
 * depend on the marketing site or an icon CDN, and drawn beside the network name rather than
 * instead of it — colour is a recognition aid, not the accessible label.
 */

export type Network = {
  id: string;
  label: string;
  file: string;
  note: string;
};

export const SOCIAL_NETWORKS: Network[] = [
  {id: 'facebook', label: 'Facebook', file: 'facebook.svg', note: 'Business Pages you manage'},
  {id: 'instagram', label: 'Instagram', file: 'instagram.svg', note: 'Professional accounts'},
  {id: 'linkedin', label: 'LinkedIn', file: 'linkedin.svg', note: 'Your profile'},
  {id: 'linkedin_organization', label: 'LinkedIn company page', file: 'linkedin.svg', note: 'Requires organization approval'},
  {id: 'x', label: 'X', file: 'x.svg', note: 'Posts and media'},
  {id: 'youtube', label: 'YouTube', file: 'youtube.svg', note: 'Your channel videos'},
  {id: 'tiktok', label: 'TikTok', file: 'tiktok.svg', note: 'Video publishing'},
  {id: 'google_business', label: 'Google Business Profile', file: 'google-business.svg', note: 'Business locations'},
];

export const NETWORK_BY_ID: Record<string, Network> = Object.fromEntries(
  SOCIAL_NETWORKS.map((network) => [network.id, network]));

export function networkLabel(id: string): string {
  return NETWORK_BY_ID[id]?.label || id.replaceAll('_', ' ');
}

export function SocialIcon({network, size = 26}: {network: string; size?: number}) {
  const entry = NETWORK_BY_ID[network];
  if (!entry) return null;
  return (
    <img
      src={'/studio/social/' + entry.file}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      style={{width: size, height: size, display: 'block', flex: '0 0 auto'}}
    />
  );
}
