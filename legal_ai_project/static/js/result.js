/* ── Result page JS ───────────────────────────────────────────────────── */
(function () {
  'use strict';

  /* ── Verdict hero entrance animation ─────────────────────────────── */
  var hero = document.querySelector('.verdict-hero');
  if (hero) {
    hero.style.opacity = '0';
    hero.style.transform = 'scale(0.94) translateY(10px)';
    hero.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
    setTimeout(function () {
      hero.style.opacity = '1';
      hero.style.transform = 'scale(1) translateY(0)';
    }, 120);
  }

  /* ── Confidence bar ───────────────────────────────────────────────── */
  var confBar = document.getElementById('conf-bar');
  if (confBar) {
    var pct = parseInt(window.CONF_PCT || '0') || 0;
    setTimeout(function () { confBar.style.width = pct + '%'; }, 300);
  }

  /* ── Confidence ring ──────────────────────────────────────────────── */
  var ring = document.getElementById('ring-fill');
  if (ring) {
    var ringPct = parseInt(window.CONF_PCT) || 0;
    if (ringPct > 0) {
      var circumference = 163;
      var offset = circumference - (ringPct / 100) * circumference;
      setTimeout(function () { ring.style.strokeDashoffset = offset; }, 400);
    }
  }

  /* ── Similarity score bars ────────────────────────────────────────── */
  setTimeout(function () {
    document.querySelectorAll('.sim-score-fill').forEach(function (el) {
      el.style.width = (el.dataset.score || 0) + '%';
    });
  }, 700);

  /* ── Block collapse/expand ────────────────────────────────────────── */
  window.toggleBlock = function (id) {
    var el = document.getElementById(id);
    if (el) el.classList.toggle('collapsed');
  };

  /* ── Modals ───────────────────────────────────────────────────────── */
  window.openModal  = function (id) { var m = document.getElementById(id); if (m) m.classList.add('open'); };
  window.closeModal = function (id) { var m = document.getElementById(id); if (m) m.classList.remove('open'); };
  window.closeModalOutside = function (e, id) { if (e.target.id === id) window.closeModal(id); };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.open').forEach(function (m) { m.classList.remove('open'); });
    }
    // Keyboard shortcut: Ctrl+Shift+S = share
    if (e.ctrlKey && e.shiftKey && e.key === 'S') { e.preventDefault(); shareResult(); }
    // Keyboard shortcut: Ctrl+Shift+P = print/PDF
    if (e.ctrlKey && e.shiftKey && e.key === 'P') { e.preventDefault(); printResult(); }
  });

  /* ── Copy summary ─────────────────────────────────────────────────── */
  window.copySummary = function () {
    var el = document.getElementById('summary-text');
    if (!el) return;
    var text = el.innerText || el.textContent;
    navigator.clipboard.writeText(text.trim()).then(function () {
      var btn = document.getElementById('copy-summary-btn');
      if (btn) {
        btn.classList.add('copied');
        btn.innerHTML = '<i class="bi bi-check2"></i> Copied';
        setTimeout(function () {
          btn.classList.remove('copied');
          btn.innerHTML = '<i class="bi bi-clipboard"></i> Copy';
        }, 2000);
      }
    }).catch(function () {});
  };

  /* ── Share result ─────────────────────────────────────────────────── */
  window.shareResult = function () {
    var appellant  = (window.RESULT_APPELLANT  || 'Case').trim();
    var outcome    = (window.RESULT_OUTCOME    || '').trim();
    var confidence = (window.RESULT_CONFIDENCE || '').trim();
    var category   = (window.RESULT_CATEGORY   || '').trim();
    var summary    = '';
    var sumEl = document.getElementById('summary-text');
    if (sumEl) summary = (sumEl.innerText || sumEl.textContent || '').trim().slice(0, 300);

    var shareText = [
      '⚖️ Nyaya Sahayak — Case Analysis',
      '',
      'Case: ' + appellant,
      'Category: ' + category,
      'Outcome: ' + outcome,
      'ML Confidence: ' + confidence,
      '',
      summary ? 'Summary: ' + summary + '...' : '',
      '',
      '— Analyzed by Nyaya Sahayak AI',
    ].filter(Boolean).join('\n');

    navigator.clipboard.writeText(shareText).then(function () {
      var btn = document.getElementById('share-btn');
      if (btn) {
        var orig = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2"></i> Copied!';
        btn.style.color = '#86efac';
        setTimeout(function () { btn.innerHTML = orig; btn.style.color = ''; }, 2500);
      }
    }).catch(function () {});
  };

  /* ── Print / PDF export ───────────────────────────────────────────── */
  window.printResult = function () {
    window.print();
  };

  /* ── Risk meter (rule-based, no AI call) ─────────────────────────── */
  (function buildRiskMeter() {
    var conf     = parseFloat(window.CONF_PCT || '0') / 100;
    var label    = parseInt(window.RESULT_LABEL || '-1');
    var sections = (window.RESULT_SECTIONS || '').split(',').filter(Boolean).length;

    if (label === -1) return; // no prediction

    // Score: 0 (low risk) to 100 (high risk)
    var score = 0;

    // Unfavorable outcome = higher risk
    if (label === 0) score += 50;
    else             score += 10;

    // Low confidence = higher risk
    score += Math.round((1 - conf) * 30);

    // More sections = more complex = slightly higher risk
    score += Math.min(sections * 2, 20);

    score = Math.min(score, 100);

    var level = score < 35 ? 'Low' : score < 65 ? 'Medium' : 'High';
    var color = score < 35 ? '#86efac' : score < 65 ? '#fbbf24' : '#fca5a5';

    var meterEl  = document.getElementById('risk-meter-fill');
    var levelEl  = document.getElementById('risk-level-text');
    var scoreEl  = document.getElementById('risk-score-val');

    if (meterEl) setTimeout(function () { meterEl.style.width = score + '%'; meterEl.style.background = color; }, 600);
    if (levelEl) { levelEl.textContent = level; levelEl.style.color = color; }
    if (scoreEl) scoreEl.textContent = score + '/100';
  })();

})();
