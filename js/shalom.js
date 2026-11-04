/* SHALOM BEAUTY SALON — área de cliente
   Animaciones y microinteracciones compartidas (mismo lenguaje que el Welcome). */
(function () {
    'use strict';

    // Fade-up / fade-in al hacer scroll (misma técnica que el Welcome)
    (function initFadeUp() {
        var els = document.querySelectorAll('.fade-up,.fade-in');
        if (!els.length) return;
        if (!('IntersectionObserver' in window)) {
            els.forEach(function (el) { el.classList.add('visible'); });
            return;
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (e) {
                if (e.isIntersecting) { e.target.classList.add('visible'); io.unobserve(e.target); }
            });
        }, { threshold: .12 });
        els.forEach(function (el) { io.observe(el); });
    })();

    // Gestor de pestañas: elementos con [data-tab-group] y botones [data-tab-target]
    (function initTabs() {
        var buttons = document.querySelectorAll('[data-tab-target]');
        buttons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                var group = btn.getAttribute('data-tab-group') || 'default';
                var target = btn.getAttribute('data-tab-target');
                document.querySelectorAll('[data-tab-panel="' + group + '"]').forEach(function (panel) {
                    panel.classList.add('d-none');
                });
                var panel = document.querySelector('[data-tab-panel="' + group + '"][data-tab-name="' + target + '"]');
                if (panel) panel.classList.remove('d-none');
                document.querySelectorAll('[data-tab-group="' + group + '"]').forEach(function (b) {
                    b.classList.remove('active');
                });
                btn.classList.add('active');
            });
        });
    })();

    // Flip de tarjeta de fidelidad (físico digital) — mismo patrón que el Welcome
    (function initLoyaltyFlip() {
        var scene = document.querySelector('.loyalty-card-scene.client-loyalty');
        var card = document.querySelector('#loyaltyClientCard');
        var btn = document.querySelector('#loyaltyFlipBtn');
        if (!scene || !card) return;
        var flip = function () { card.classList.toggle('is-flipped'); };
        if (btn) btn.addEventListener('click', flip);
        scene.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(); }
        });
    })();

    // Brillo de sellos recién estampados (solo la primera vez que el cliente los ve)
    (function initNewStamps() {
        var filled = document.querySelectorAll('.stamp.filled[data-stamp]');
        if (!filled.length) return;
        var key = 'shalom_stamps_seen';
        var seen = parseInt(localStorage.getItem(key) || '0', 10);
        var total = 0;
        filled.forEach(function (s) {
            var n = parseInt(s.getAttribute('data-stamp'), 10);
            if (n > total) total = n;
        });
        if (total > seen) {
            for (var i = seen + 1; i <= total; i++) {
                var el = document.querySelector('.stamp.filled[data-stamp="' + i + '"]');
                if (el) el.classList.remove('stamp-animated');
                if (el) { el.classList.add('new-filled'); el.style.animation = 'none'; void el.offsetWidth; el.style.animation = ''; }
            }
            localStorage.setItem(key, String(total));
        }
    })();
})();