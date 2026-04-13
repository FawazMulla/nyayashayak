/* ── Upload page JS ───────────────────────────────────────────────────── */
(function () {
  'use strict';

  /* BG canvas animation */
  const canvas = document.getElementById('bg-canvas');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    let W, H, particles = [];

    function resize() { W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight; }
    resize();
    window.addEventListener('resize', resize);

    function rand(a, b) { return Math.random() * (b - a) + a; }

    function Particle(init) {
      this.x = rand(0, W);
      this.y = init ? rand(0, H) : H + 10;
      this.r = rand(0.5, 1.8);
      this.speed = rand(0.15, 0.5);
      this.opacity = rand(0.08, 0.35);
      this.drift = rand(-0.15, 0.15);
      this.color = Math.random() > 0.85 ? '#faff69' : '#ffffff';
    }
    Particle.prototype.update = function () {
      this.y -= this.speed; this.x += this.drift;
      if (this.y < -5) { this.x = rand(0, W); this.y = H + 10; }
    };
    Particle.prototype.draw = function () {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      ctx.fillStyle = this.color;
      ctx.globalAlpha = this.opacity;
      ctx.fill();
    };

    for (let i = 0; i < 120; i++) particles.push(new Particle(true));

    function drawGrid() {
      ctx.globalAlpha = 0.025;
      ctx.strokeStyle = '#faff69';
      ctx.lineWidth = 0.5;
      for (let x = 0; x < W; x += 80) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
      for (let y = 0; y < H; y += 80) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
    }

    (function loop() {
      ctx.clearRect(0, 0, W, H);
      drawGrid();
      ctx.globalAlpha = 1;
      particles.forEach(p => { p.update(); p.draw(); });
      requestAnimationFrame(loop);
    })();
  }

  /* Tabs */
  window.switchTab = function (name, btn) {
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    btn.classList.add('active');
  };

  /* Drop zone */
  const dropZone  = document.getElementById('drop-zone');
  const fileInput = document.getElementById('pdf_file');
  const fileNameEl = document.getElementById('file-name');

  if (fileInput && dropZone) {
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) fileNameEl.textContent = '📎 ' + fileInput.files[0].name;
    });
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault(); dropZone.classList.remove('dragover');
      const file = e.dataTransfer.files[0];
      if (file) {
        const dt = new DataTransfer(); dt.items.add(file);
        fileInput.files = dt.files;
        fileNameEl.textContent = '📎 ' + file.name;
      }
    });
  }

  /* Form submit */
  const form = document.getElementById('upload-form');
  if (form) {
    form.addEventListener('submit', function (e) {
      const file     = fileInput && fileInput.files[0];
      const textVal  = document.getElementById('text_input');
      const activeTab = document.querySelector('.tab-pane.active');

      if (activeTab && activeTab.id === 'tab-pdf' && !file) {
        e.preventDefault(); alert('Please select a PDF file.'); return;
      }
      if (activeTab && activeTab.id === 'tab-text' && textVal &&
          textVal.value.trim().split(/\s+/).filter(Boolean).length < 20) {
        e.preventDefault(); alert('Please paste more text.'); return;
      }
      const spinner = document.getElementById('spinner');
      if (spinner) spinner.classList.add('active');
    });
  }

  window.addEventListener('pageshow', () => {
    const spinner = document.getElementById('spinner');
    if (spinner) spinner.classList.remove('active');
  });
})();
