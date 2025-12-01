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
    
    window.resetWelcomeModal = function() {
        localStorage.removeItem('uecVisited');
        welcomeModal.classList.remove('hidden');
        console.log('Welcome modal reset. Refresh the page to see it again.');
    };
}
