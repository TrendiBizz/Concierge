/*
 * Website AI Concierge - embeddable chat + Grok Voice widget.
 *
 * Install on a client's site with one line:
 *   <script src="https://api.example.com/widget.js" data-key="pk_..." defer></script>
 *
 * Optional attribute: data-autoopen="1" opens the panel on load (used by /demo pages).
 */
(function () {
  "use strict";

  var script = document.currentScript;
  if (!script || window.__ccWidgetLoaded) return;
  window.__ccWidgetLoaded = true;

  var KEY = script.getAttribute("data-key");
  if (!KEY) return;
  var API = new URL(script.src, location.href).origin;
  var AUTOOPEN = script.getAttribute("data-autoopen") === "1";

  // ------------------------------------------------------------ utilities
  function newSessionId() {
    var bytes = new Uint8Array(12);
    crypto.getRandomValues(bytes);
    return Array.prototype.map
      .call(bytes, function (b) {
        return ("0" + b.toString(16)).slice(-2);
      })
      .join("");
  }

  function getSessionId() {
    try {
      var existing = localStorage.getItem("cc_sid");
      if (existing) return existing;
    } catch (e) {}
    var fresh = newSessionId();
    try {
      localStorage.setItem("cc_sid", fresh);
    } catch (e) {}
    return fresh;
  }

  function readUtm() {
    var out = {};
    try {
      new URLSearchParams(location.search).forEach(function (value, key) {
        if (key.indexOf("utm_") === 0) out[key] = value;
      });
    } catch (e) {}
    return out;
  }

  var SID = getSessionId();
  var UTM = readUtm();

  function post(path, body) {
    return fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        if (k === "class") node.className = props[k];
        else if (k === "text") node.textContent = props[k];
        else node.setAttribute(k, props[k]);
      });
    }
    (children || []).forEach(function (c) {
      node.appendChild(c);
    });
    return node;
  }

  // Turn plain text into DOM nodes, making http(s) URLs clickable. Never uses innerHTML.
  function linkify(text, container) {
    var re = /(https?:\/\/[^\s<>"')]+)/g;
    var last = 0;
    var match;
    while ((match = re.exec(text)) !== null) {
      if (match.index > last) container.appendChild(document.createTextNode(text.slice(last, match.index)));
      var a = el("a", { href: match[1], target: "_blank", rel: "noopener noreferrer", text: match[1] });
      container.appendChild(a);
      last = match.index + match[1].length;
    }
    if (last < text.length) container.appendChild(document.createTextNode(text.slice(last)));
  }

  // ----------------------------------------------------------------- audio
  function bytesToB64(bytes) {
    var bin = "";
    var CHUNK = 0x8000;
    for (var i = 0; i < bytes.length; i += CHUNK) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return btoa(bin);
  }

  function f32ToB64Pcm16(f32) {
    var buf = new ArrayBuffer(f32.length * 2);
    var view = new DataView(buf);
    for (var i = 0; i < f32.length; i++) {
      var s = Math.max(-1, Math.min(1, f32[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return bytesToB64(new Uint8Array(buf));
  }

  function b64Pcm16ToF32(b64) {
    var bin = atob(b64);
    var n = bin.length >> 1;
    var out = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var s = (bin.charCodeAt(2 * i + 1) << 8) | bin.charCodeAt(2 * i);
      if (s >= 0x8000) s -= 0x10000;
      out[i] = s / 0x8000;
    }
    return out;
  }

  function resample(f32, fromRate, toRate) {
    if (fromRate === toRate) return f32;
    var ratio = fromRate / toRate;
    var outLen = Math.floor(f32.length / ratio);
    var out = new Float32Array(outLen);
    for (var i = 0; i < outLen; i++) {
      var pos = i * ratio;
      var i0 = Math.floor(pos);
      var i1 = Math.min(i0 + 1, f32.length - 1);
      var frac = pos - i0;
      out[i] = f32[i0] * (1 - frac) + f32[i1] * frac;
    }
    return out;
  }

  var WORKLET_SRC =
    "class CcCapture extends AudioWorkletProcessor{process(inputs){" +
    "var ch=inputs[0]&&inputs[0][0];if(ch){this.port.postMessage(new Float32Array(ch));}return true;}}" +
    "registerProcessor('cc-capture',CcCapture);";

  // ----------------------------------------------------------- build UI
  var config = null;

  function boot(cfg) {
    config = cfg;
    var accent = /^#[0-9a-fA-F]{3,8}$/.test(cfg.accent_color) ? cfg.accent_color : "#2563eb";

    var host = el("div", { id: "cc-root" });
    var shadow = host.attachShadow({ mode: "open" });

    var style = el("style");
    style.textContent =
      ":host{all:initial}" +
      "*{box-sizing:border-box;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}" +
      ".launcher{position:fixed;right:20px;bottom:20px;z-index:2147483000;display:flex;align-items:center;gap:10px;" +
      "background:" + accent + ";color:#fff;border:0;border-radius:999px;padding:14px 20px;font-size:15px;font-weight:600;" +
      "cursor:pointer;box-shadow:0 6px 24px rgba(0,0,0,.25);animation:pulse 2.4s ease-in-out infinite}" +
      ".launcher:hover{filter:brightness(1.08)}" +
      "@keyframes pulse{0%,100%{box-shadow:0 6px 24px rgba(0,0,0,.25)}50%{box-shadow:0 6px 32px " + accent + "99}}" +
      "@media (prefers-reduced-motion:reduce){.launcher{animation:none}}" +
      ".panel{position:fixed;right:20px;bottom:20px;z-index:2147483001;width:380px;max-width:calc(100vw - 24px);" +
      "height:560px;max-height:calc(100vh - 24px);background:#fff;color:#111;border-radius:16px;display:none;" +
      "flex-direction:column;overflow:hidden;box-shadow:0 12px 48px rgba(0,0,0,.3)}" +
      ".panel.open{display:flex}" +
      ".head{background:" + accent + ";color:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between}" +
      ".head b{font-size:15px}.head small{display:block;opacity:.85;font-size:12px;font-weight:400}" +
      ".close{background:transparent;border:0;color:#fff;font-size:22px;cursor:pointer;line-height:1}" +
      ".log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px;background:#f6f7f9}" +
      ".b{max-width:86%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}" +
      ".b a{color:inherit;text-decoration:underline}" +
      ".b.assistant{background:#fff;border:1px solid #e3e5e8;align-self:flex-start}" +
      ".b.user{background:" + accent + ";color:#fff;align-self:flex-end}" +
      ".b.note{align-self:center;background:transparent;color:#555;font-size:12px}" +
      ".status{min-height:20px;padding:2px 14px;font-size:12px;color:#555;background:#f6f7f9}" +
      ".bar{display:flex;gap:8px;padding:10px;border-top:1px solid #e3e5e8;background:#fff}" +
      ".bar input{flex:1;border:1px solid #cfd3d8;border-radius:999px;padding:10px 14px;font-size:16px;outline:none}" +
      ".bar input:focus{border-color:" + accent + "}" +
      ".btn{border:0;border-radius:999px;width:40px;height:40px;cursor:pointer;font-size:16px;background:" + accent + ";color:#fff}" +
      ".btn.mic.on{background:#dc2626}" +
      ".btn[disabled]{opacity:.5;cursor:default}" +
      ".foot{padding:6px 12px 10px;font-size:11px;color:#666;text-align:center;background:#fff}" +
      "@media (max-width:480px){.panel{right:0;bottom:0;width:100vw;max-width:100vw;height:100vh;height:100dvh;max-height:100vh;max-height:100dvh;border-radius:0}}";

    var launcher = el("button", { class: "launcher", type: "button", "aria-label": "Open AI guide" }, [
      el("span", { text: "\u{1F4AC}" }),
      el("span", { text: cfg.cta_text }),
    ]);

    var log = el("div", { class: "log", role: "log", "aria-live": "polite" });
    var status = el("div", { class: "status" });
    var input = el("input", { type: "text", placeholder: "Type your question…", "aria-label": "Message", maxlength: "1000" });
    var sendBtn = el("button", { class: "btn", type: "button", "aria-label": "Send", text: "➤" });
    var micBtn = el("button", { class: "btn mic", type: "button", "aria-label": "Talk to the AI guide", text: "\u{1F3A4}" });
    var closeBtn = el("button", { class: "close", type: "button", "aria-label": "Close", text: "×" });

    var bar = el("div", { class: "bar" }, [input]);
    var voiceSupported =
      cfg.voice_enabled && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && "WebSocket" in window;
    if (voiceSupported) bar.appendChild(micBtn);
    bar.appendChild(sendBtn);

    var panel = el("div", { class: "panel", role: "dialog", "aria-label": cfg.name + " AI guide" }, [
      el("div", { class: "head" }, [
        el("div", {}, [el("b", { text: cfg.name }), el("small", { text: "AI guide" })]),
        closeBtn,
      ]),
      log,
      status,
      bar,
      el("div", { class: "foot", text: "You are chatting with an AI. It can make mistakes. Conversations may be saved to help the team follow up." }),
    ]);

    // A site with a strict Content-Security-Policy (style-src 'self') blocks an inline <style> element,
    // which left the widget unstyled. Constructable stylesheets are not blocked by that policy, so use
    // one when the browser supports it and fall back to the <style> element in older browsers.
    try {
      var sheet = new CSSStyleSheet();
      sheet.replaceSync(style.textContent);
      shadow.adoptedStyleSheets = [sheet];
    } catch (e) {
      shadow.appendChild(style);
    }
    shadow.appendChild(launcher);
    shadow.appendChild(panel);
    document.body.appendChild(host);

    // --------------------------------------------------------- messages
    function addMsg(role, text) {
      var bubble = el("div", { class: "b " + role });
      linkify(text, bubble);
      log.appendChild(bubble);
      log.scrollTop = log.scrollHeight;
      return bubble;
    }

    function setStatus(text) {
      status.textContent = text || "";
    }

    var greeted = false;
    function openPanel() {
      panel.classList.add("open");
      launcher.style.display = "none";
      if (!greeted) {
        greeted = true;
        addMsg("assistant", cfg.greeting);
      }
      input.focus();
    }
    function closePanel() {
      stopVoice();
      panel.classList.remove("open");
      launcher.style.display = "flex";
    }
    launcher.addEventListener("click", openPanel);
    closeBtn.addEventListener("click", closePanel);
    // The host website can open the assistant without submitting a message,
    // starting voice, or reaching into the widget's shadow DOM.
    window.addEventListener("concierge:open", openPanel);
    window.__ccWidgetReady = true;
    window.dispatchEvent(new Event("concierge:ready"));

    // -------------------------------------------------------------- chat
    var busy = false;
    async function sendText() {
      var text = input.value.trim();
      if (!text || busy) return;
      input.value = "";
      busy = true;
      sendBtn.disabled = true;
      addMsg("user", text);
      var typing = addMsg("assistant", "…");
      try {
        var res = await post("/api/v1/chat", {
          key: KEY,
          session_id: SID,
          message: text,
          page_url: location.href,
          utm: UTM,
        });
        typing.remove();
        if (res.status === 429) {
          addMsg("note", "You're sending messages quickly - please wait a moment.");
        } else if (!res.ok) {
          addMsg("assistant", "Sorry, I'm having trouble right now. Please try again in a moment.");
        } else {
          var data = await res.json();
          addMsg("assistant", data.reply);
          if (data.appointment) addMsg("note", "✓ " + data.appointment);
          else if (data.lead_captured) addMsg("note", "✓ Your details were sent to the team.");
        }
      } catch (e) {
        typing.remove();
        addMsg("assistant", "Sorry, I couldn't reach the server. Please check your connection and try again.");
      } finally {
        busy = false;
        sendBtn.disabled = false;
        input.focus();
      }
    }
    sendBtn.addEventListener("click", sendText);
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        sendText();
      }
    });

    // ------------------------------------------------------------- voice
    var ws = null;
    var stream = null;
    var actx = null;
    var captureNode = null;
    var sink = null;
    var playing = [];
    var nextTime = 0;
    var pendingCalls = [];
    var userText = "";
    var assistantText = "";
    var voiceActive = false;
    var sampleBuffer = [];
    var sampleCount = 0;

    function wsSend(obj) {
      if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
    }

    function logVoice(role, text) {
      text = (text || "").trim();
      if (!text) return;
      addMsg(role, text);
      post("/api/v1/voice/log", {
        key: KEY,
        session_id: SID,
        role: role,
        text: text.slice(0, 4000),
        page_url: location.href,
        utm: UTM,
      }).catch(function () {});
    }

    function playChunk(b64) {
      if (!actx) return;
      var f32 = b64Pcm16ToF32(b64);
      if (!f32.length) return;
      var buf = actx.createBuffer(1, f32.length, 24000);
      buf.copyToChannel(f32, 0);
      var src = actx.createBufferSource();
      src.buffer = buf;
      src.connect(actx.destination);
      var startAt = Math.max(actx.currentTime + 0.02, nextTime);
      src.start(startAt);
      nextTime = startAt + buf.duration;
      playing.push(src);
      src.onended = function () {
        var i = playing.indexOf(src);
        if (i >= 0) playing.splice(i, 1);
        if (!playing.length && voiceActive) setStatus("Listening…");
      };
    }

    function interrupt() {
      playing.forEach(function (s) {
        try {
          s.stop();
        } catch (e) {}
      });
      playing = [];
      nextTime = 0;
    }

    function onSamples(f32) {
      sampleBuffer.push(f32);
      sampleCount += f32.length;
      // Send ~100ms batches.
      if (sampleCount < Math.floor(actx.sampleRate / 10)) return;
      var merged = new Float32Array(sampleCount);
      var offset = 0;
      sampleBuffer.forEach(function (chunk) {
        merged.set(chunk, offset);
        offset += chunk.length;
      });
      sampleBuffer = [];
      sampleCount = 0;
      var pcm = resample(merged, actx.sampleRate, 24000);
      wsSend({ type: "input_audio_buffer.append", audio: f32ToB64Pcm16(pcm) });
    }

    async function startMic() {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      var AC = window.AudioContext || window.webkitAudioContext;
      try {
        actx = new AC({ sampleRate: 24000 });
      } catch (e) {
        actx = new AC();
      }
      if (actx.state === "suspended") await actx.resume();

      var source = actx.createMediaStreamSource(stream);
      sink = actx.createGain();
      sink.gain.value = 0; // keeps the capture graph running without echoing the mic
      sink.connect(actx.destination);

      var usedWorklet = false;
      if (actx.audioWorklet && window.AudioWorkletNode) {
        try {
          var url = URL.createObjectURL(new Blob([WORKLET_SRC], { type: "application/javascript" }));
          await actx.audioWorklet.addModule(url);
          URL.revokeObjectURL(url);
          captureNode = new AudioWorkletNode(actx, "cc-capture");
          captureNode.port.onmessage = function (ev) {
            onSamples(ev.data);
          };
          source.connect(captureNode);
          captureNode.connect(sink);
          usedWorklet = true;
        } catch (e) {
          usedWorklet = false; // e.g. the host page's CSP blocks blob: workers
        }
      }
      if (!usedWorklet) {
        captureNode = actx.createScriptProcessor(2048, 1, 1);
        captureNode.onaudioprocess = function (ev) {
          onSamples(new Float32Array(ev.inputBuffer.getChannelData(0)));
        };
        source.connect(captureNode);
        captureNode.connect(sink);
      }
    }

    async function runToolCall(ev) {
      var args = {};
      try {
        args = JSON.parse(ev.arguments || "{}");
      } catch (e) {}
      var result;
      try {
        var res = await post("/api/v1/tools/" + encodeURIComponent(ev.name), {
          key: KEY,
          session_id: SID,
          args: args,
          page_url: location.href,
          utm: UTM,
        });
        result = await res.json();
      } catch (e) {
        result = { ok: false, error: "Network error" };
      }
      if (ev.name === "capture_lead" && result.ok) addMsg("note", "✓ Your details were sent to the team.");
      if (ev.name === "book_appointment" && result.ok && result.confirmation) addMsg("note", "✓ " + result.confirmation);
      if (ev.name === "get_booking_link" && result.ok && result.booking_url) addMsg("assistant", "Book here: " + result.booking_url);
      return { call_id: ev.call_id, output: JSON.stringify(result) };
    }

    function onServerEvent(raw) {
      var ev;
      try {
        ev = JSON.parse(raw);
      } catch (e) {
        return;
      }
      switch (ev.type) {
        case "response.output_audio.delta":
        case "response.audio.delta":
          if (ev.delta) {
            if (userText) {
              logVoice("user", userText);
              userText = "";
            }
            setStatus("Speaking…");
            playChunk(ev.delta);
          }
          break;
        case "input_audio_buffer.speech_started":
          // Barge-in: stop talking when the visitor starts. (Event name per the common realtime
          // convention; harmless if the server never sends it.)
          interrupt();
          break;
        case "conversation.item.input_audio_transcription.updated":
          // Cumulative transcript of what the visitor said.
          userText = ev.transcript || ev.text || userText;
          break;
        case "response.output_audio_transcript.delta":
        case "response.audio_transcript.delta":
          assistantText += ev.delta || "";
          break;
        case "response.function_call_arguments.done":
          pendingCalls.push(runToolCall(ev));
          break;
        case "response.done":
          if (assistantText) {
            logVoice("assistant", assistantText);
            assistantText = "";
          }
          if (pendingCalls.length) {
            var calls = pendingCalls;
            pendingCalls = [];
            // All outputs must be sent before a single response.create.
            Promise.all(calls).then(function (outputs) {
              outputs.forEach(function (o) {
                wsSend({
                  type: "conversation.item.create",
                  item: { type: "function_call_output", call_id: o.call_id, output: o.output },
                });
              });
              wsSend({ type: "response.create" });
            });
          }
          break;
        case "error":
          console.warn("[concierge] voice error", ev);
          setStatus("Voice hit a problem.");
          break;
        default:
          break;
      }
    }

    function stopVoice() {
      voiceActive = false;
      micBtn.classList.remove("on");
      interrupt();
      if (ws) {
        try {
          ws.close();
        } catch (e) {}
        ws = null;
      }
      if (captureNode) {
        try {
          captureNode.disconnect();
        } catch (e) {}
        captureNode = null;
      }
      if (stream) {
        stream.getTracks().forEach(function (t) {
          t.stop();
        });
        stream = null;
      }
      if (actx) {
        try {
          actx.close();
        } catch (e) {}
        actx = null;
      }
      pendingCalls = [];
      userText = "";
      assistantText = "";
      sampleBuffer = [];
      sampleCount = 0;
      setStatus("");
    }

    async function startVoice() {
      voiceActive = true;
      micBtn.classList.add("on");
      setStatus("Connecting…");
      try {
        var res = await post("/api/v1/voice/token", { key: KEY, session_id: SID });
        if (!res.ok) {
          var detail = "";
          try {
            detail = (await res.json()).detail || "";
          } catch (e) {}
          throw new Error(detail || "Voice is unavailable right now.");
        }
        var data = await res.json();
        await startMic();

        // The token travels as a WebSocket subprotocol because browsers cannot set headers.
        var PREFIX = "xai-client-secret.";
        var protocol = data.token.indexOf(PREFIX) === 0 ? data.token : PREFIX + data.token;
        ws = new WebSocket(data.url, [protocol]);
        ws.onopen = function () {
          wsSend({ type: "session.update", session: data.session });
          wsSend({
            type: "conversation.item.create",
            item: {
              type: "message",
              role: "user",
              content: [{ type: "input_text", text: "[The visitor just started a voice conversation. Greet them briefly as the AI guide and ask how you can help.]" }],
            },
          });
          wsSend({ type: "response.create" });
          setStatus("Listening…");
        };
        ws.onmessage = function (ev) {
          if (typeof ev.data === "string") onServerEvent(ev.data);
        };
        ws.onerror = function () {
          setStatus("Voice connection failed.");
        };
        ws.onclose = function () {
          if (voiceActive) {
            stopVoice();
            setStatus("Voice ended. You can keep typing.");
          }
        };
      } catch (e) {
        stopVoice();
        var denied = e && e.name === "NotAllowedError";
        setStatus(denied ? "Microphone access was blocked." : (e && e.message) || "Voice is unavailable right now.");
      }
    }

    micBtn.addEventListener("click", function () {
      if (voiceActive) stopVoice();
      else startVoice();
    });

    if (AUTOOPEN) setTimeout(openPanel, 600);
  }

  fetch(API + "/api/v1/widget-config?key=" + encodeURIComponent(KEY))
    .then(function (r) {
      return r.ok ? r.json() : null;
    })
    .then(function (cfg) {
      if (!cfg) return;
      if (document.body) boot(cfg);
      else document.addEventListener("DOMContentLoaded", function () { boot(cfg); });
    })
    .catch(function () {});
})();
