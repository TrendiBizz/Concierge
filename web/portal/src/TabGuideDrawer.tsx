import {useEffect, useState} from 'react';
import {Drawer} from 'vaul';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Badge} from '@astryxdesign/core/Badge';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';

type GuideEntry = {
  title: string;
  summary: string;
  steps: string[];
  tip: string;
};

const TAB_GUIDES: Record<string, GuideEntry> = {
  home: {
    title: 'Home Dashboard',
    summary: 'Your daily command centre: new enquiries, open quotes, bookings, and pipeline value at a glance.',
    steps: [
      'Check new enquiries at the top — every call, chat, text, and email appears automatically.',
      'Review any pending email drafts or quotes waiting on your approval.',
      'Use the pause bar at the top anytime you want to temporarily halt all automated replies.',
    ],
    tip: 'Press Cmd+K (or Ctrl+K) from anywhere in Studio to jump straight to any screen.',
  },
  setup: {
    title: '7-Stage Onboarding Hub',
    summary: 'A step-by-step guided walkthrough to configure, test, and launch every channel of Concierge.',
    steps: [
      'Work through Stages 1 to 7 in order, or jump to any stage you want to refine.',
      'Use the built-in live checks (Sandbox Chat, Test Alert, Widget Check, Slot Preview) to verify each piece.',
      'Click "Launch Concierge" in Stage 7 once your readiness scorecard is green.',
    ],
    tip: 'Your progress saves automatically — you can pause and come back from any device.',
  },
  crm: {
    title: 'Enquiries (CRM)',
    summary: 'Every customer enquiry from website chat, phone, voicemail, SMS, email, and Meta lands here.',
    steps: [
      'Filter by stage or channel, or search by customer name, phone, email, or message.',
      'Click Edit on any row to update deal stage, value, internal notes, or your next follow-up time.',
      'Use the menu on each row to read the full conversation transcript or inspect stage history.',
    ],
    tip: 'Click any phone number or email address to call or email the customer in one click.',
  },
  texts: {
    title: 'Unified Inbox & Human Takeover',
    summary: 'Read and reply to live website chats, SMS texts, and Meta messages in one place.',
    steps: [
      'Select any conversation on the left to see what the customer asked and what Concierge replied.',
      'Send one reply yourself and Concierge pauses automatically for that customer so you never talk over each other.',
      'Hand the conversation back to Concierge whenever you are ready.',
    ],
    tip: 'Takeover is per-customer — pausing Concierge for one person leaves it active for everyone else.',
  },
  contacts: {
    title: 'Unified Contacts',
    summary: 'One unified record per person across phone, email, SMS, and chat — repeat customers are merged automatically.',
    steps: [
      'Click Open on any contact to see their complete cross-channel timeline, enquiries, and appointments.',
      'Add extra phone numbers or email addresses under "Also reachable at" to link them to the same person.',
      'Assign an account owner, link them to a Company, or pause/resume the assistant for that contact.',
    ],
    tip: 'Use bulk checkboxes to assign multiple contacts to a team member in one action.',
  },
  companies: {
    title: 'Companies',
    summary: 'Group contacts, enquiries, and open deal values under the business they belong to.',
    steps: [
      'Create a company with its name, domain, and notes.',
      'Link contacts to their company from the Contacts screen to roll up open deals automatically.',
      'Track total open deal count and value per business account.',
    ],
    tip: 'Great for B2B trades, property managers, and commercial accounts with multiple contacts.',
  },
  bookings: {
    title: 'Bookings, Calendar & Live Calls',
    summary: 'Control opening hours, connect Google Calendar, copy your private ICS feed, book appointments, and monitor live calls.',
    steps: [
      'Set your weekly opening hours and slot length, then connect Google Calendar or subscribe via the private ICS feed.',
      'Book an appointment manually or mark existing bookings as Completed, No-show, or Cancelled.',
      'When a phone call is live, monitor the transcript, listen/whisper/join, or click Take Over.',
    ],
    tip: 'Every booking automatically sends a confirmation with a self-serve reschedule/cancel link plus 24h and 2h reminders.',
  },
  pipeline: {
    title: 'Sales Pipeline',
    summary: 'Visual board of every deal by stage (New → Contacted → Booked → Won / Lost) with weighted forecast.',
    steps: [
      'Add offline walk-in or referral deals directly with the "Add deal" button.',
      'Move deals through stages as you quote and win work to keep your forecast accurate.',
      'Record a lost reason when closing out a deal so Reports can show why jobs were lost.',
    ],
    tip: 'Pipeline totals automatically use your business currency and average deal value when a value is not set yet.',
  },
  quotes: {
    title: 'Quotations',
    summary: 'Draft, send, and track customer quotes with line items, tax, terms, and online acceptance.',
    steps: [
      'Build a quote from your Products catalog or custom line items.',
      'Send the quote link to the customer — they can review and accept it online.',
      'Accepted quotes can be converted straight into invoices and trigger connected webhooks.',
    ],
    tip: 'Concierge never invents quote prices in chat — it only quotes rates you explicitly approve.',
  },
  invoices: {
    title: 'Invoices',
    summary: 'Issue customer invoices from accepted quotes and track paid vs outstanding balances.',
    steps: [
      'Create an invoice directly or from an accepted quote.',
      'Share the invoice link with your customer and record payment when settled.',
      'Paid totals automatically feed into your 30-day Revenue Report.',
    ],
    tip: 'Review your tax and payment instructions under Billing & Setup before issuing your first invoice.',
  },
  products: {
    title: 'Products & Rates',
    summary: 'Your approved price list and standard rates. Concierge uses this as its single source of truth.',
    steps: [
      'Add your standard call-out fees, hourly rates, or fixed packages.',
      'Update prices here anytime — Quotes and Concierge answers stay in sync.',
      'Leave custom or complex jobs out of fixed pricing so Concierge offers a site visit or quote instead.',
    ],
    tip: 'A built-in Price Guard stops Concierge from ever guessing a dollar figure that is not listed here.',
  },
  knowledge: {
    title: 'What Concierge Knows',
    summary: 'The approved website pages, FAQs, policies, and documents Concierge reads to answer customers.',
    steps: [
      'Click "Import from website" to pull your latest public pages automatically.',
      'Add plain-English notes for anything not on your site (service areas, call-out fees, after-hours rules).',
      'Test your changes immediately using the Sandbox Chat in the Onboarding Hub.',
    ],
    tip: 'If a customer asks something not covered here, Concierge says so honestly and offers to pass the question to you.',
  },
  integrations: {
    title: 'Integrations, Webhooks & API Keys',
    summary: 'Connect Xero, Microsoft 365 Calendar, ServiceM8, Slack/Teams, Meta Messaging, or Zapier/Make.',
    steps: [
      'Connect Xero (contacts), Microsoft 365 (calendar), or ServiceM8 (jobs) with your own account.',
      'Paste a Slack or Microsoft Teams webhook URL for instant team channel alerts.',
      'Use "Send test event" under Webhook Deliveries to verify your custom CRM webhook end-to-end.',
    ],
    tip: 'Every integration uses your own account permissions and can be disconnected in one click.',
  },
  reports: {
    title: 'Reports & Analytics',
    summary: 'Track 30-day enquiries, accepted quote value, containment rate, response time, and CSAT.',
    steps: [
      'Review enquiry volume by channel (chat, phone, email, SMS) to see where leads come from.',
      'Check containment rate and average response time to measure how much work Concierge handles for you.',
      'Download the full CSV report anytime for Excel or Google Sheets.',
    ],
    tip: 'Everything on this page updates live as enquiries, quotes, and bookings arrive.',
  },
  permissions: {
    title: 'Channels & Permissions',
    summary: 'Explicitly authorize which channels Concierge is allowed to read or send on behalf of your business.',
    steps: [
      'Switch on only the channels you want active (telephone, call recording, email, SMS, social).',
      'Every grant or revocation is recorded in your permanent authorization audit log.',
      'Changes take effect immediately across the entire platform.',
    ],
    tip: 'Nothing sends automatically on email, SMS, or phone until you explicitly authorize that channel.',
  },
  social: {
    title: 'Social Publishing',
    summary: 'Draft, schedule, and approve posts for your connected social accounts — nothing publishes without approval.',
    steps: [
      'Use the Compose tab to draft posts tailored to each connected network.',
      'Switch to Calendar to view scheduled dates, or Your Posts to approve, schedule, or publish.',
      'Connect Facebook, Instagram, LinkedIn, X, TikTok, or Google Business Profile in one click.',
    ],
    tip: 'Video posts automatically publish as native Facebook Videos and Instagram Reels.',
  },
};

const DEFAULT_GUIDE: GuideEntry = {
  title: 'Concierge Studio Guide',
  summary: 'Everything in Concierge works together: enquiries from every channel land in one CRM with full history and controls.',
  steps: [
    'Use the 7-Stage Onboarding Hub in Setup to walk through every feature piece by piece.',
    'Every automated channel has explicit permissions and an instant pause switch.',
    'Open the full online walkthrough anytime at trendibizz.com/guide.',
  ],
  tip: 'Need hands-on help? Email admin@trendibizz.com and we will set up any channel with you.',
};

const TAB_STAGE_VIDEO: Record<string, {stage: number; secs: number}> = {
  setup: {stage: 1, secs: 36},
  knowledge: {stage: 1, secs: 36},
  texts: {stage: 2, secs: 38},
  crm: {stage: 2, secs: 38},
  bookings: {stage: 4, secs: 28},
  permissions: {stage: 5, secs: 39},
  integrations: {stage: 6, secs: 28},
  home: {stage: 7, secs: 38},
};

export function TabGuideDrawer({
  tab,
  onOpenOnboarding,
}: {
  tab: string;
  onOpenOnboarding: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 760px)').matches
  );
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(max-width: 760px)');
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  const guide = TAB_GUIDES[tab] || DEFAULT_GUIDE;
  const stageVideo = TAB_STAGE_VIDEO[tab];

  return (
    <Drawer.Root open={open} onOpenChange={setOpen} direction={isMobile ? 'bottom' : 'right'}>
      <Drawer.Trigger asChild>
        <Button label="Guide" variant="secondary" onClick={() => setOpen(true)} />
      </Drawer.Trigger>
      <Drawer.Portal>
        <Drawer.Overlay className="c-drawer-overlay" />
        <Drawer.Content
          aria-label="Screen guide"
          className={isMobile ? 'c-drawer-content c-drawer-bottom' : 'c-drawer-content c-drawer-right'}
        >
          {isMobile ? <div className="c-drawer-handle" aria-hidden="true" /> : null}
          <VStack gap={4}>
            <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center'}}>
              <Badge label="HOW THIS WORKS" variant="info" />
              <Button label="Close" variant="ghost" onClick={() => setOpen(false)} />
            </HStack>
            <Drawer.Title asChild>
              <Heading level={2}>{guide.title}</Heading>
            </Drawer.Title>
            <Drawer.Description style={{margin: 0, lineHeight: 1.55}}>
              {guide.summary}
            </Drawer.Description>
            <Card>
              <VStack gap={2} style={{padding: 12}}>
                <strong>Step-by-step</strong>
                <ol style={{margin: 0, paddingLeft: 20, lineHeight: 1.6}}>
                  {guide.steps.map((s, i) => (
                    <li key={i} style={{marginBottom: 6}}>{s}</li>
                  ))}
                </ol>
              </VStack>
            </Card>
            <p style={{margin: 0, fontSize: 13, opacity: 0.85}}>
              <strong>Tip:</strong> {guide.tip}
            </p>
            <HStack gap={2} style={{flexWrap: 'wrap', marginTop: 8}}>
              <Button
                label="Open 7-Stage Onboarding Hub"
                variant="primary"
                onClick={() => {
                  setOpen(false);
                  onOpenOnboarding();
                }}
              />
              {stageVideo ? (
                <a
                  href={`https://trendibizz.com/help#stage-${stageVideo.stage}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{display: 'inline-flex', alignItems: 'center', padding: '8px 12px', fontSize: 14, fontWeight: 600}}
                >
                  Watch Stage {stageVideo.stage} video ({stageVideo.secs}s) ↗
                </a>
              ) : null}
              <a
                href="https://trendibizz.com/guide"
                target="_blank"
                rel="noopener noreferrer"
                style={{display: 'inline-flex', alignItems: 'center', padding: '8px 12px', fontSize: 14}}
              >
                Full walkthrough &amp; video ↗
              </a>
            </HStack>
          </VStack>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
