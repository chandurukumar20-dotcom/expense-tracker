/**
 * FinTrack - Expense Tracker Client Script
 * Handles UI interactions, native <dialog> modals, responsive sidebar, and forms.
 */

// -----------------------------------------------------------------------------
// SIDEBAR TOGGLE FOR MOBILE DEVICES
// -----------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('appSidebar');
    const toggleBtn = document.getElementById('sidebarToggleBtn');
    const closeBtn = document.getElementById('sidebarCloseBtn');
    const backdrop = document.getElementById('sidebarBackdrop');

    function openSidebar() {
        if (sidebar) sidebar.classList.add('open');
        if (backdrop) backdrop.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('open');
        if (backdrop) backdrop.classList.remove('active');
        document.body.style.overflow = '';
    }

    if (toggleBtn) toggleBtn.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (backdrop) backdrop.addEventListener('click', closeSidebar);

    // Auto-dismiss Flash Alerts after 6 seconds
    const alerts = document.querySelectorAll('.flash-alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-6px)';
            setTimeout(() => alert.remove(), 400);
        }, 6000);
    });

    // Color picker live text update
    const colorInput = document.getElementById('cat_color');
    const colorText = document.querySelector('.color-preview-text');
    if (colorInput && colorText) {
        colorInput.addEventListener('input', function() {
            colorText.textContent = this.value;
        });
    }
});

// -----------------------------------------------------------------------------
// DELETE CONFIRMATION DIALOG (Native <dialog>)
// -----------------------------------------------------------------------------
function confirmDelete(actionUrl, message = 'Are you sure you want to permanently delete this item?') {
    const modal = document.getElementById('deleteModal');
    const form = document.getElementById('deleteForm');
    const msgEl = document.getElementById('deleteModalMessage');

    if (!modal || !form) {
        if (window.confirm(message)) {
            // Fallback for browsers with dialog disabled
            const f = document.createElement('form');
            f.method = 'POST';
            f.action = actionUrl;
            document.body.appendChild(f);
            f.submit();
        }
        return;
    }

    form.action = actionUrl;
    if (msgEl) msgEl.textContent = message;
    modal.showModal();
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    if (modal) modal.close();
}

// -----------------------------------------------------------------------------
// CUSTOM CATEGORY MODAL (Native <dialog>)
// -----------------------------------------------------------------------------
function openCategoryModal() {
    const modal = document.getElementById('categoryModal');
    if (modal) {
        modal.showModal();
        const firstInput = modal.querySelector('input[name="name"]');
        if (firstInput) firstInput.focus();
    }
}

function closeCategoryModal() {
    const modal = document.getElementById('categoryModal');
    if (modal) modal.close();
}

// Close dialog on clicking backdrop outside card
document.querySelectorAll('dialog.native-modal').forEach(dialog => {
    dialog.addEventListener('click', function(event) {
        const rect = dialog.getBoundingClientRect();
        const isInDialog = (
            rect.top <= event.clientY &&
            event.clientY <= rect.top + rect.height &&
            rect.left <= event.clientX &&
            event.clientX <= rect.left + rect.width
        );
        if (!isInDialog) {
            dialog.close();
        }
    });
});
