import {useEffect, useState} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Divider} from '@astryxdesign/core/Divider';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {QrCode, qrDownloadHref} from './QrCode';
import {installAvailable, installUrl, isAndroid, isInstalled, isIOS, isMobile, onInstallChange, promptInstall} from './installPrompt';

/**
 * The page a QR code points at: put the whole Concierge workspace on the phone.
 *
 * A QR cannot install anything by itself — the phone opens a URL and the browser installs from
 * there. So this page is the honest middle step, and it says which gesture each phone needs:
 * Android shows an Install button (the captured `beforeinstallprompt`), iPhone needs Safari's
 * Share → Add to Home Screen. It explicitly says this is the workspace, not the website chat
 * bubble — the two used to be confused, and a chat QR was handed out as an "app" QR.
 */
export function InstallApp() {
  const [available, setAvailable] = useState(installAvailable());
  const [installed, setInstalled] = useState(isInstalled());
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => onInstallChange(setAvailable), []);

  useEffect(() => {
    const refresh = () => setInstalled(isInstalled());
    window.addEventListener('appinstalled', refresh);
    const query = window.matchMedia?.('(display-mode: standalone)');
    query?.addEventListener?.('change', refresh);
    return () => {
      window.removeEventListener('appinstalled', refresh);
      query?.removeEventListener?.('change', refresh);
    };
  }, []);

  const url = installUrl();
  const ios = isIOS();
  const android = isAndroid();
  const mobile = isMobile();

  async function install() {
    setBusy(true);
    setNote('');
    try {
      const accepted = await promptInstall();
      setNote(accepted
        ? 'Installing — the Concierge icon will appear on your home screen.'
        : 'The install was dismissed. You can try again, or use your browser menu and choose "Install app".');
    } catch {
      setNote('This browser would not open the install prompt. Use its menu and choose "Install app" or "Add to Home Screen".');
    }
    setBusy(false);
  }

  return (
    <VStack gap={4} style={{maxWidth: 620, margin: '6vh auto', padding: '0 20px'}}>
      <VStack gap={1}>
        <HStack gap={2} align="center">
          <Heading level={1}>Put Concierge on this phone</Heading>
          {installed ? <Badge label="installed" variant="success" /> : null}
        </HStack>
        <Text type="supporting">
          This installs the whole workspace — enquiries, quotations, calls, marketing — as an app
          icon that opens full screen. It is not the chat bubble that sits on your website.
        </Text>
      </VStack>

      {installed ? (
        <Card>
          <VStack gap={3}>
            <Heading level={2}>Concierge is already on this phone</Heading>
            <Text>Open it from your home screen. If you cannot find the icon, use your browser menu and choose “Install app” or “Add to Home Screen”.</Text>
            <HStack gap={2}>
              <Button label="Open Concierge" variant="primary" onClick={() => { location.href = '/studio/'; }} />
            </HStack>
          </VStack>
        </Card>
      ) : mobile ? (
        <Card>
          <VStack gap={3}>
            {available ? (
              <>
                <Heading level={2}>One tap to install</Heading>
                <Text>Your browser can install Concierge straight from this page. No app store, no download.</Text>
                <HStack gap={2}>
                  <Button label={busy ? 'Opening…' : 'Install Concierge'} variant="primary" isDisabled={busy} onClick={() => void install()} />
                  <Button label="Open Concierge without installing" variant="ghost" onClick={() => { location.href = '/studio/'; }} />
                </HStack>
              </>
            ) : ios ? (
              <>
                <Heading level={2}>On iPhone or iPad: three taps in Safari</Heading>
                <ol style={{margin: 0, paddingLeft: 22, lineHeight: 1.7}}>
                  <li>Open this page in <strong>Safari</strong> (not the Instagram or Facebook browser).</li>
                  <li>Tap the <strong>Share</strong> button — the square with the arrow pointing up.</li>
                  <li>Scroll and tap <strong>Add to Home Screen</strong>, then <strong>Add</strong>.</li>
                </ol>
                <Text type="supporting">Apple does not let a web page start the install itself. Those taps are the only way, and they give you the same full-screen app.</Text>
              </>
            ) : (
              <>
                <Heading level={2}>{android ? 'Install from the browser menu' : 'Add Concierge to your home screen'}</Heading>
                <Text>
                  This browser has not offered its own install button, but it can still install the app.
                  {android
                    ? ' Tap the ⋮ menu (top right) and choose “Install app” or “Add to Home screen”.'
                    : ' Open this page in Safari and use Share → “Add to Home Screen”.'}
                </Text>
                <Text type="supporting">On Android, Chrome gives the best result. On iPhone the install must be done in Safari — other browsers cannot add to the home screen.</Text>
              </>
            )}
            {note ? <Text type="supporting">{note}</Text> : null}
            <Divider />
            <Text type="supporting">
              Already have the app icon? Open it and sign in with the same email. Nothing else changes —
              this is the same Concierge, with the same enquiries and quotes.
            </Text>
          </VStack>
        </Card>
      ) : (
        <Card>
          <VStack gap={3}>
            <Heading level={2}>Scan this with the phone you want it on</Heading>
            <Text>
              Point the phone camera at the code, then install it there. On Android the page shows an
              <strong> Install</strong> button; on iPhone use Safari’s Share → <strong>Add to Home Screen</strong>.
            </Text>
            <HStack gap={4} align="center" style={{flexWrap: 'wrap'}}>
              <QrCode value={url} size={196} label="QR code for the Concierge install page" />
              <VStack gap={2}>
                <Text weight="semibold">{url}</Text>
                <a download="concierge-install-qr.svg" href={qrDownloadHref(url)} style={{fontSize: 14}}>
                  Download this QR to print
                </a>
                <Button label="Copy the install link" variant="secondary" onClick={() => {
                  void navigator.clipboard?.writeText(url)
                    .then(() => setNote('Install link copied.'))
                    .catch(() => setNote('This browser blocked the clipboard — select the link above.'));
                }} />
              </VStack>
            </HStack>
            {available ? (
              <>
                <Divider />
                <Text type="supporting">You are on a computer. Chrome can also install Concierge here.</Text>
                <HStack gap={2}>
                  <Button label={busy ? 'Opening…' : 'Install on this computer'} variant="secondary" isDisabled={busy} onClick={() => void install()} />
                </HStack>
              </>
            ) : null}
            {note ? <Text type="supporting">{note}</Text> : null}
          </VStack>
        </Card>
      )}

      <HStack gap={2} style={{flexWrap: 'wrap'}}>
        <Button label="Sign in to Concierge" variant="secondary" onClick={() => { location.href = '/studio/'; }} />
      </HStack>
      <Text type="supporting" size="sm">
        The QR code opens this page; your phone does the install. A web page cannot put an icon on
        the home screen without that one tap from you.
      </Text>
    </VStack>
  );
}
