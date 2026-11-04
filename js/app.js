document.addEventListener('DOMContentLoaded', function() {
    var success = document.getElementById('flash-success');
    var error = document.getElementById('flash-error');
    if (success) {
        Swal.fire({ icon: 'success', title: '¡Éxito!', text: success.textContent.trim(), timer: 2500, showConfirmButton: false });
    }
    if (error) {
        Swal.fire({ icon: 'error', title: '¡Error!', text: error.textContent.trim(), timer: 3000, showConfirmButton: false });
    }

    // Suaves animaciones de entrada (fade-in / slide-up) en páginas autenticadas
    var targets = document.querySelectorAll('.card, .dashboard-panel, .stat-card, .table, .alert');
    if (targets.length) {
        targets.forEach(function(el) {
            if (el.dataset.animated) return;
            el.dataset.animated = 'true';
            el.style.opacity = '0';
            el.style.transform = 'translateY(18px)';
            el.style.transition = 'opacity .7s ease, transform .7s ease';
        });
        var io = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: .15 });
        document.querySelectorAll('[data-animated="true"]').forEach(function(el) { io.observe(el); });
    }
});
