/* ── Lincoln Lawyer Chatbot — shared across result & chat pages ───────── */
/* Expects: window.CSRF_TOKEN and window.CHATBOT_URL to be set in template */

(function () {
  'use strict';

  const CSRF = () => window.CSRF_TOKEN  || '';
  const URL  = () => window.CHATBOT_URL || '/chatbot/';

  /* ── Markdown renderer (no external deps) ────────────────────────── */
  function renderMarkdown(text) {
    return text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Bold **text**
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      // Italic *text*
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Inline code `code`
      .replace(/`([^`]+)`/g, '<code style="font-family:\'Inconsolata\',monospace;color:#faff69;font-size:11px;">$1</code>')
      // Bullet lines starting with - or •
      .replace(/^[\-•]\s+(.+)$/gm, '<li>$1</li>')
      // Wrap consecutive <li> in <ul>
      .replace(/(<li>.*<\/li>(\n|$))+/g, function(m) { return '<ul style="margin:6px 0 6px 16px;padding:0;">' + m + '</ul>'; })
      // Numbered list 1. 2. etc
      .replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>')
      // Line breaks
      .replace(/\n\n/g, '</p><p style="margin:6px 0 0;">')
      .replace(/\n/g, '<br>');
  }

  /* ── Typewriter effect ────────────────────────────────────────────── */
  function typewriterAppend(bubble, text, speed) {
    speed = speed || 12;
    // Render markdown first, then type the HTML
    const html = '<p style="margin:0;">' + renderMarkdown(text) + '</p>';
    bubble.innerHTML = '';
    let i = 0;
    const chars = Array.from(html);
    let inTag = false;
    let buffer = '';

    function tick() {
      if (i >= chars.length) {
        bubble.innerHTML = html; // ensure final state is clean
        scrollBottom();
        return;
      }
      // Skip through HTML tags instantly
      if (chars[i] === '<') inTag = true;
      if (inTag) {
        buffer += chars[i];
        if (chars[i] === '>') {
          inTag = false;
          bubble.innerHTML += buffer;
          buffer = '';
        }
        i++;
        tick(); // tags are instant
        return;
      }
      bubble.innerHTML += chars[i];
      i++;
      scrollBottom();
      setTimeout(tick, speed);
    }
    tick();
  }

  /* ── DOM helpers ──────────────────────────────────────────────────── */
  function getContainer() {
    return document.getElementById('chat-messages');
  }

  function scrollBottom() {
    const c = getContainer();
    if (c) c.scrollTop = c.scrollHeight;
  }

  function appendMsg(text, role, animate) {
    const c = getContainer();
    if (!c) return;
    const wrap   = document.createElement('div');
    wrap.className = 'msg-row' + (role === 'user' ? ' user' : '');
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble ' + role;

    if (role === 'bot' && animate) {
      wrap.appendChild(bubble);
      c.appendChild(wrap);
      scrollBottom();
      typewriterAppend(bubble, text, 10);
    } else if (role === 'bot') {
      bubble.innerHTML = '<p style="margin:0;">' + renderMarkdown(text) + '</p>';
      wrap.appendChild(bubble);
      c.appendChild(wrap);
      scrollBottom();
    } else {
      bubble.textContent = text;
      wrap.appendChild(bubble);
      c.appendChild(wrap);
      scrollBottom();
    }
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
      .then(d => { removeTyping(); appendMsg(d.response, 'bot', true); })
      .catch(() => { removeTyping(); appendMsg('Network error — please try again.', 'bot', false); });
  }

  /* ── Public API ───────────────────────────────────────────────────── */
  window.Chatbot = {
    send: function (inputId) {
      const el = document.getElementById(inputId || 'chatInput');
      if (!el) return;
      const q = el.value.trim();
      if (!q) return;
      appendMsg(q, 'user', false);
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
      appendMsg(labels[action] || action, 'user', false);
      postToBot('', action);
    },

    init: function (welcomeMsg) {
      if (welcomeMsg) appendMsg(welcomeMsg, 'bot', false);

      const input = document.getElementById('chatInput');
      if (input) {
        input.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            window.Chatbot.send('chatInput');
          }
        });
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
