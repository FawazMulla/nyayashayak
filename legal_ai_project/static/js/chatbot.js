/* ── Lincoln Lawyer Chatbot — shared across result & chat pages ───────── */
/* Expects: window.CSRF_TOKEN and window.CHATBOT_URL to be set in template */

(function () {
  'use strict';

  const CSRF  = () => window.CSRF_TOKEN  || '';
  const URL   = () => window.CHATBOT_URL || '/chatbot/';

  /* ── DOM helpers ──────────────────────────────────────────────────── */
  function getContainer() {
    return document.getElementById('chat-messages');
  }

  function scrollBottom() {
    const c = getContainer();
    if (c) c.scrollTop = c.scrollHeight;
  }

  function appendMsg(text, role) {
    const c = getContainer();
    if (!c) return;
    const wrap   = document.createElement('div');
    wrap.className = 'msg-row' + (role === 'user' ? ' user' : '');
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble ' + role;
    bubble.textContent = text;
    wrap.appendChild(bubble);
    c.appendChild(wrap);
    scrollBottom();
  }

  function showTyping() {
    const c = getContainer();
    if (!c) return;
    const wrap = document.createElement('div');
    wrap.className = 'msg-row';
    wrap.id = 'typing-indicator';
    wrap.innerHTML =
      '<div class="msg-bubble bot" style="padding:8px 12px;">' +
      '<span class="typing-dot"></span>' +
      '<span class="typing-dot"></span>' +
      '<span class="typing-dot"></span></div>';
    c.appendChild(wrap);
    scrollBottom();
  }

  function removeTyping() {
    const t = document.getElementById('typing-indicator');
    if (t) t.remove();
  }

  /* ── API call ─────────────────────────────────────────────────────── */
  function postToBot(query, action) {
    showTyping();
    const mode = window.CHATBOT_MODE || 'case';
    fetch(URL(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': CSRF(),
      },
      body: 'query='  + encodeURIComponent(query) +
            '&action=' + encodeURIComponent(action) +
            '&mode='   + encodeURIComponent(mode),
    })
      .then(r => r.json())
      .then(d => { removeTyping(); appendMsg(d.response, 'bot'); })
      .catch(() => { removeTyping(); appendMsg('Network error — please try again.', 'bot'); });
  }

  /* ── Public API ───────────────────────────────────────────────────── */
  window.Chatbot = {
    send: function (inputId) {
      const el = document.getElementById(inputId || 'chatInput');
      if (!el) return;
      const q = el.value.trim();
      if (!q) return;
      appendMsg(q, 'user');
      el.value = '';
      if (el.tagName === 'TEXTAREA') el.style.height = 'auto';
      postToBot(q, '');
    },

    quickAction: function (action) {
      const labels = {
        explain:   'Explain this case',
        nextsteps: 'What should I do next?',
        risk:      'Risk analysis',
        arguments: 'Generate arguments',
        compare:   'Compare with similar cases',
        eli5:      "Explain like I'm 5",
        general:   'Tell me about Indian legal procedures',
        rights:    'What are my fundamental rights?',
        bail:      'How does bail work in India?',
        appeal:    'How do I file an appeal?',
      };
      appendMsg(labels[action] || action, 'user');
      postToBot('', action);
    },

    init: function (welcomeMsg) {
      if (welcomeMsg) appendMsg(welcomeMsg, 'bot');

      /* Enter key on input */
      const input = document.getElementById('chatInput');
      if (input) {
        input.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            window.Chatbot.send('chatInput');
          }
        });
        /* Auto-resize textarea */
        if (input.tagName === 'TEXTAREA') {
          input.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
          });
        }
      }
    },
  };
})();
