(function(){'use strict';var demo=document.querySelector('.walkthrough');if(!demo)return;
// One step per feature in the checklist beside the walkthrough, in the same order. Illustrative only.
var all=[
['Set up for your business','Your website, FAQs and opening hours go in first.','Concierge is configured with your services, hours, contact details and handover rules, then tested before a channel goes live.','Set up for your business','Setup'],
['Answer the question','“Are you open on Saturday?”','Concierge answers from your website: “Yes, 9am–1pm. Would you like an appointment?”','Customer answers','Answer'],
['Capture the enquiry','“I’m Jamie. I’d like to book.”','Contact details and the conversation are captured together as a new enquiry.','Enquiry capture','Capture'],
['Arrange the booking','“10am would be perfect.”','Concierge offers appointment times based on the hours you set and records the booking.','Appointment booking','Book'],
['Keep the next step clear','“Can someone confirm the price for me?”','Concierge says the team will confirm and adds a follow-up, with a status you can track until it is done.','Follow-up tracking','Follow up'],
['Everything in one place','Jamie’s details, messages and booking.','The contact, each conversation and the booking sit together in your built-in CRM, ready for your team.','Built-in CRM','CRM'],
['Answer on your website','“Do you do weekend call-outs?”','The chat window on your website answers from the information you have approved.','Website chat','Chat'],
['Answer the phone','A customer rings while you are with a client.','Concierge answers the call and captures who called and why for your team. Phone is enabled after provider setup and testing.','Phone calls','Phone'],
['Reply to email','“Could you send me a quote for next week?”','The email becomes an enquiry in your CRM, and Concierge answers from your approved information.','Email','Email'],
['Reply by text','“Running ten minutes late, sorry.”','The text is added to Jamie’s record in your CRM so your team sees it with the booking. SMS is enabled after provider setup and testing.','SMS','SMS'],
['Approve social posts','A post is drafted for this week.','Social posts wait for your approval before anything is published to your connected accounts.','Social post approvals','Social']];
var n=Math.min(all.length,Number(demo.getAttribute('data-steps'))||10),stages=all.slice(0,n);
var rail=demo.querySelector('.walkthrough-steps');function pad(i){return(i<10?'0':'')+i}
rail.innerHTML='';stages.forEach(function(s,i){var b=document.createElement('button');b.type='button';b.setAttribute('data-step',String(i));b.setAttribute('aria-pressed',String(i===0));var sp=document.createElement('span');sp.textContent=pad(i+1);b.appendChild(sp);b.appendChild(document.createTextNode(s[4]));rail.appendChild(b)});
rail.style.setProperty('--wt-cols',String(Math.ceil(n/2)));
var step=0,playing=false,timer;var toggle=demo.querySelector('.walkthrough-toggle'),scene=demo.querySelector('.walkthrough-scene');
function keepVisible(b){if(rail.scrollWidth<=rail.clientWidth)return;var left=b.offsetLeft-rail.offsetLeft-(rail.clientWidth-b.offsetWidth)/2;rail.scrollTo({left:Math.max(0,left),behavior:'smooth'})}
function render(){var s=stages[step];scene.querySelector('.walkthrough-label').textContent=pad(step+1)+' / '+pad(n)+' · '+s[3];scene.querySelector('h3').textContent=s[0];scene.querySelector('.walkthrough-question').textContent=s[1];scene.querySelector('.walkthrough-answer').textContent=s[2];scene.querySelector('.walkthrough-result').textContent='✓ '+s[3];rail.querySelectorAll('[data-step]').forEach(function(b,i){b.setAttribute('aria-pressed',String(i===step));if(i===step)keepVisible(b)});scene.classList.remove('is-changing');requestAnimationFrame(function(){scene.classList.add('is-changing')})}
function play(on){playing=on;demo.querySelector('.walkthrough-launch').hidden=true;clearInterval(timer);scene.setAttribute('aria-live',on?'off':'polite');toggle.textContent=on?'Ⅱ Pause walkthrough':'▶ Resume walkthrough';if(on)timer=setInterval(function(){step=(step+1)%n;render()},4500)}
demo.querySelector('.walkthrough-launch').addEventListener('click',function(){play(true)});toggle.addEventListener('click',function(){play(!playing)});
rail.querySelectorAll('[data-step]').forEach(function(b){b.addEventListener('click',function(){step=Number(b.getAttribute('data-step'));play(false);render()})});
document.addEventListener('visibilitychange',function(){if(document.hidden&&playing)play(false)});render()})();
