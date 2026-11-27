import {useState} from 'react';
import {Drawer} from 'vaul';
import {Button} from '@astryxdesign/core/Button';
import {Heading} from '@astryxdesign/core/Heading';
import {Badge} from '@astryxdesign/core/Badge';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

// First-run guided setup. Shown once per device after the first sign-in, with a Next button.
// Progress is kept in localStorage so a closed app resumes where it stopped; Skip or finishing
// marks it done. "Guide" in the top bar and the Setup tab (7-stage hub) stay the reference.
const KEY = 'concierge.tour';

type Step = {title: string; body: string; action?: {label: string; run: 'alerts' | 'setup'}};

const STEPS: Step[] = [
  {title: 'Welcome to your Studio', body: 'This takes about a minute. Tap Next and we will walk you through the four things worth knowing. You can skip any time, and the Guide button at the top brings this back.'},
  {title: 'Turn on alerts', body: 'Alerts buzz your phone the moment a customer messages, so you can step in or just watch. Tap the button below and allow notifications when your phone asks.', action: {label: 'Turn on alerts', run: 'alerts'}},
  {title: 'Where your customers land', body: 'Inbox holds every chat, text and call. Enquiries lists each new customer with their name and number filled in. Quotes holds the prices Concierge drafts for you to approve. Open the menu to move between them.'},
  {title: 'Pause everything', body: 'The Pause everything card on Home is your one big switch. Tap it and Concierge stops answering customers until you turn it back on. Use it when you want to reply yourself.'},
  {title: 'Finish setting up', body: 'Setup is seven short stages: your business details, what Concierge may say, your channels, then a test. Your progress saves, so you can stop and come back from any device.', action: {label: 'Open Setup', run: 'setup'}},
];

function read(): number {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'done') return -1;
    const n = Number(v);
    return Number.isInteger(n) && n >= 0 && n < STEPS.length ? n : 0;
  } catch { return 0; }
}
function write(v: string) { try { localStorage.setItem(KEY, v); } catch { /* private mode: tour just shows again */ } }

export function FirstRunTour({token, enableAlerts, goto}: {token: string; enableAlerts: () => Promise<boolean>; goto: (tab: string) => void}) {
  const [step, setStep] = useState(read);
  const [note, setNote] = useState('');
  if (!token || step < 0) return null;
  const last = step === STEPS.length - 1;
  const cur = STEPS[step];
  function finish() { write('done'); setStep(-1); }
  function move(n: number) { write(String(n)); setStep(n); setNote(''); }
  return (
    <Drawer.Root open onOpenChange={(o) => { if (!o) finish(); }} direction="bottom" dismissible>
      <Drawer.Portal>
        <Drawer.Overlay className="c-drawer-overlay" />
        <Drawer.Content aria-label="First-run setup" className="c-drawer-content c-drawer-bottom">
          <div className="c-drawer-handle" aria-hidden="true" />
          <VStack gap={4}>
            <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center'}}>
              <Badge label={`STEP ${step + 1} OF ${STEPS.length}`} variant="info" />
              <Button label="Skip" variant="ghost" onClick={finish} />
            </HStack>
            <div className="c-tour-dots" aria-hidden="true">
              {STEPS.map((_, i) => <span key={i} data-on={i <= step} />)}
            </div>
            <Drawer.Title asChild><Heading level={2}>{cur.title}</Heading></Drawer.Title>
            <Drawer.Description style={{margin: 0, lineHeight: 1.55}}>{cur.body}</Drawer.Description>
            {cur.action ? (
              <Button label={cur.action.label} variant="secondary" onClick={() => {
                if (cur.action!.run === 'alerts') {
                  void enableAlerts().then((ok) => setNote(ok ? 'Alerts are on.' : 'Alerts did not turn on. On iPhone, open the app from the Home Screen icon, then try again. You can skip this.'));
                } else { finish(); goto('setup'); }
              }} />
            ) : null}
            {note ? <p role="status" style={{margin: 0, fontSize: 14}}>{note}</p> : null}
            <HStack gap={2} style={{justifyContent: 'space-between', marginTop: 8}}>
              {step > 0 ? <Button label="Back" variant="ghost" onClick={() => move(step - 1)} /> : <span />}
              <Button label={last ? 'Done' : 'Next'} variant="primary" onClick={() => (last ? finish() : move(step + 1))} />
            </HStack>
          </VStack>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
