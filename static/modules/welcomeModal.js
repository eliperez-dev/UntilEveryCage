export function initializeWelcomeModal() {
    const welcomeModal = document.getElementById('welcome-modal');
    const welcomeCloseBtn = document.getElementById('welcome-close-btn');
    const welcomeGetStartedBtn = document.getElementById('welcome-get-started-btn');
    const hasVisited = localStorage.getItem('uecVisited');
    
    function closeModal() {
        welcomeModal.classList.add('hidden');
        localStorage.setItem('uecVisited', 'true');
    }
    
    if (!hasVisited) {
        welcomeModal.classList.remove('hidden');
    }
    
    welcomeCloseBtn.addEventListener('click', closeModal);
    welcomeGetStartedBtn.addEventListener('click', closeModal);
    
    welcomeModal.addEventListener('click', (e) => {
        if (e.target === welcomeModal) {
            closeModal();
        }
    });

    // Prevent map interactions through the modal
    if (window.L) {
        L.DomEvent.disableScrollPropagation(welcomeModal);
    }

    const stopPropagation = (e) => e.stopPropagation();
    welcomeModal.addEventListener('touchstart', stopPropagation, { passive: true });
    welcomeModal.addEventListener('touchmove', stopPropagation, { passive: true });
    welcomeModal.addEventListener('touchend', stopPropagation, { passive: true });
    welcomeModal.addEventListener('mousedown', stopPropagation);
    welcomeModal.addEventListener('dblclick', stopPropagation);
    
    window.resetWelcomeModal = function() {
        localStorage.removeItem('uecVisited');
        welcomeModal.classList.remove('hidden');
        console.log('Welcome modal reset. Refresh the page to see it again.');
    };
}
