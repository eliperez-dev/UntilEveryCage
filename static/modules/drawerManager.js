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

    window.openSearchDrawer = openDrawer;
    window.closeSearchDrawer = closeDrawer;
}
