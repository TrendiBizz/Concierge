(function () {
  'use strict';
  var demo = document.querySelector('.walkthrough');
  if (!demo) return;
  // One step per feature in the checklist beside the walkthrough, in the same order. Illustrative only.
  // [title, incomingText, conciergeAction, outcomeLabel, tabLabel, incomingRole, conciergeRole]
  var all = [
    [
      'Set up for your business',
      'Your website, FAQs and opening hours go in first.',
      'Concierge is configured with your services, hours, contact details and handover rules, then tested before a channel goes live.',
      'Set up for your business',
      'Setup',
      'Your business',
      'Concierge setup'
    ],
    [
      'Answer the question',
      '“Are you open on Saturday?”',
      'Concierge answers from your website: “Yes, 9am–1pm. Would you like an appointment?”',
      'Customer answers',
      'Answer',
      'Customer asks',
      'Concierge replies'
    ],
    [
      'Capture the enquiry',
      '“I’d like to book an appointment — here are my details.”',
      'Contact details and the conversation are captured together as a new enquiry.',
      'Enquiry capture',
      'Capture',
      'Customer says',
      'Concierge captures'
    ],
    [
      'Arrange the booking',
      '“10am would be perfect.”',
      'Concierge offers appointment times based on the hours you set and records the booking.',
      'Appointment booking',
      'Book',
      'Customer says',
      'Concierge books'
    ],
    [
      'Keep the next step clear',
      '“Can someone confirm the price for me?”',
      'Concierge says the team will confirm and adds a follow-up, with a status you can track until it is done.',
      'Follow-up tracking',
      'Follow up',
      'Customer asks',
      'Concierge tracks'
    ],
    [
      'Everything in one place',
      'The customer’s details, messages and booking.',
      'The contact, each conversation and the booking sit together in your built-in CRM, ready for your team.',
      'Built-in CRM',
      'CRM',
      'Every enquiry',
      'Concierge organises'
    ],
    [
      'Answer on your website',
      '“Do you do weekend call-outs?”',
      'The chat window on your website answers from the information you have approved.',
      'Website chat',
      'Chat',
      'Website visitor',
      'Concierge answers'
    ],
    [
      'Answer the phone',
      'A customer rings while you are with a client.',
      'Concierge answers the call and captures who called and why for your team. Phone is enabled after provider setup and testing.',
      'Phone calls',
      'Phone',
      'Incoming call',
      'Concierge answers'
    ],
    [
      'Reply to email',
      '“Could you send me a quote for next week?”',
      'The email becomes an enquiry in your CRM, and Concierge answers from your approved information.',
      'Email',
      'Email',
      'Customer emails',
      'Concierge replies'
    ],
    [
      'Reply by text',
      '“Running ten minutes late, sorry.”',
      'The text is added to the customer’s record in your CRM so your team sees it with the booking. SMS runs through your paired business smartphone after setup and testing.',
      'SMS',
      'SMS',
      'Customer texts',
      'Concierge updates CRM'
    ],
    [
      'Approve social posts',
      'A post is drafted for this week.',
      'Social posts wait for your approval before anything is published to your connected accounts.',
      'Social post approvals',
      'Social',
      'Draft post',
      'Concierge waits for approval'
    ]
  ];

  var n = Math.min(all.length, Number(demo.getAttribute('data-steps')) || 10);
  var stages = all.slice(0, n);
  var rail = demo.querySelector('.walkthrough-steps');
  var scene = demo.querySelector('.walkthrough-scene');
  var launch = demo.querySelector('.walkthrough-launch');
  var toggle = demo.querySelector('.walkthrough-toggle');
  var prevBtn = demo.querySelector('.walkthrough-prev');
  var nextBtn = demo.querySelector('.walkthrough-next');
  var counter = demo.querySelector('.walkthrough-count');
  var progressFill = demo.querySelector('.walkthrough-progress-fill');
  var progressTrack = demo.querySelector('.walkthrough-progress');
  var reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function pad(i) {
    return (i < 10 ? '0' : '') + i;
  }

  rail.setAttribute('role', 'tablist');
  rail.innerHTML = '';
  stages.forEach(function (s, i) {
    var b = document.createElement('button');
    b.type = 'button';
    b.id = 'wt-tab-' + i;
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-controls', 'wt-panel');
    b.setAttribute('aria-selected', String(i === 0));
    b.setAttribute('tabindex', i === 0 ? '0' : '-1');
    b.setAttribute('data-step', String(i));
    var num = document.createElement('span');
    num.className = 'walkthrough-step-num';
    num.textContent = pad(i + 1);
    var lbl = document.createElement('span');
    lbl.className = 'walkthrough-step-name';
    lbl.textContent = s[4];
    b.appendChild(num);
    b.appendChild(lbl);
    rail.appendChild(b);
  });
  rail.style.setProperty('--wt-cols', String(Math.ceil(n / 2)));

  var tabs = Array.prototype.slice.call(rail.querySelectorAll('[role="tab"]'));
  var step = 0;
  var playing = false;
  var started = false;
  var timer;

  function render() {
    var s = stages[step];
    var pct = Math.round(((step + 1) / n) * 100);
    scene.setAttribute('aria-labelledby', 'wt-tab-' + step);
    scene.querySelector('.walkthrough-label').textContent = 'Step ' + pad(step + 1) + ' of ' + pad(n) + ' · ' + s[3];
    scene.querySelector('h3').textContent = s[0];
    var roleIn = scene.querySelector('.walkthrough-role--in');
    var roleOut = scene.querySelector('.walkthrough-role--out');
    if (roleIn) roleIn.textContent = s[5];
    if (roleOut) roleOut.textContent = s[6];
    scene.querySelector('.walkthrough-question').textContent = s[1];
    scene.querySelector('.walkthrough-answer').textContent = s[2];
    scene.querySelector('.walkthrough-result').textContent = '✓ ' + s[3];
    if (counter) counter.textContent = pad(step + 1) + ' / ' + pad(n);
    if (progressFill) progressFill.style.setProperty('--wt-progress', pct + '%');
    if (progressTrack) {
      progressTrack.setAttribute('aria-valuenow', String(step + 1));
      progressTrack.setAttribute('aria-valuemax', String(n));
    }
    tabs.forEach(function (b, i) {
      var active = i === step;
      b.setAttribute('aria-selected', String(active));
      b.setAttribute('tabindex', active ? '0' : '-1');
      if (i < step) b.setAttribute('data-done', 'true');
      else b.removeAttribute('data-done');
    });
    if (!reducedMotion) {
      scene.classList.remove('is-changing');
      requestAnimationFrame(function () {
        scene.classList.add('is-changing');
      });
    }
  }

  function reveal() {
    if (!started) {
      started = true;
      if (launch) launch.hidden = true;
    }
  }

  function play(on) {
    playing = on;
    reveal();
    clearInterval(timer);
    scene.setAttribute('aria-live', on ? 'off' : 'polite');
    toggle.setAttribute('aria-pressed', String(on));
    toggle.textContent = on ? 'Ⅱ Pause walkthrough' : '▶ Resume walkthrough';
    if (on) {
      timer = setInterval(function () {
        step = (step + 1) % n;
        render();
      }, 4500);
    }
  }

  function goTo(index, focusTab) {
    step = (index + n) % n;
    play(false);
    render();
    if (focusTab && tabs[step]) tabs[step].focus();
  }

  if (launch) {
    launch.addEventListener('click', function () {
      if (reducedMotion) {
        play(false);
        render();
      } else {
        play(true);
      }
    });
  }

  toggle.addEventListener('click', function () {
    play(!playing);
  });

  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      goTo(step - 1, false);
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      goTo(step + 1, false);
    });
  }

  tabs.forEach(function (b) {
    b.addEventListener('click', function () {
      goTo(Number(b.getAttribute('data-step')), false);
    });
  });

  rail.addEventListener('keydown', function (ev) {
    if (ev.key === 'ArrowRight' || ev.key === 'ArrowDown') {
      ev.preventDefault();
      goTo(step + 1, true);
    } else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      goTo(step - 1, true);
    } else if (ev.key === 'Home') {
      ev.preventDefault();
      goTo(0, true);
    } else if (ev.key === 'End') {
      ev.preventDefault();
      goTo(n - 1, true);
    }
  });

  document.addEventListener('visibilitychange', function () {
    if (document.hidden && playing) play(false);
  });

  render();
})();
