/* ── Result page JS ───────────────────────────────────────────────────── */
(function () {
  'use strict';

  /* Confidence bar */
  const confBar = document.getElementById('conf-bar');
  if (confBar) {
    const pct = parseInt(window.CONF_PCT || '0') || 0;
    setTimeout(() => { confBar.style.width = pct + '%'; }, 300);
  }

  /* Block collapse/expand */
  window.toggleBlock = function (id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('collapsed');
  };

  /* Modals */
  window.openModal  = function (id) { const m = document.getElementById(id); if (m) m.classList.add('open'); };
  window.closeModal = function (id) { const m = document.getElementById(id); if (m) m.classList.remove('open'); };
  window.closeModalOutside = function (e, id) { if (e.target.id === id) window.closeModal(id); };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
    }
  });
})();
