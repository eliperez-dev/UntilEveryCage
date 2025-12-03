export function initializeDrawer() {
    const drawer = document.getElementById('search-drawer');
    const toggleBtn = document.getElementById('drawer-toggle-btn');
    const closeBtn = document.getElementById('drawer-close-btn');
    const backdrop = document.getElementById('drawer-backdrop');

    const openDrawer = () => {
        drawer.classList.add('open');
        backdrop.classList.add('open');
        document.body.style.overflow = 'hidden';
    };

    const closeDrawer = () => {
        drawer.classList.remove('open');
        backdrop.classList.remove('open');
        document.body.style.overflow = '';
    };

    toggleBtn.addEventListener('click', openDrawer);
    closeBtn.addEventListener('click', closeDrawer);
    backdrop.addEventListener('click', closeDrawer);

    // Prevent map interactions through the drawer
    if (window.L) {
        L.DomEvent.disableScrollPropagation(drawer);
    }

    // Stop propagation of events that might affect the map
    const stopPropagation = (e) => e.stopPropagation();
    
    // Touch events - use passive: true to allow scrolling
    drawer.addEventListener('touchstart', stopPropagation, { passive: true });
    drawer.addEventListener('touchmove', stopPropagation, { passive: true });
    drawer.addEventListener('touchend', stopPropagation, { passive: true });
    
    // Mouse events
    drawer.addEventListener('mousedown', stopPropagation);
    drawer.addEventListener('dblclick', stopPropagation);
    drawer.addEventListener('click', stopPropagation);

    window.openSearchDrawer = openDrawer;
    window.closeSearchDrawer = closeDrawer;
}
