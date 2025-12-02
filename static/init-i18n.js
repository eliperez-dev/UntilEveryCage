// Import translation manager
import { i18n } from './modules/translationManager.js';

document.addEventListener('DOMContentLoaded', async () => {
    await i18n.init();

    const langSelector = document.getElementById('language-selector');
    if (langSelector) {
        langSelector.value = i18n.currentLocale;
        langSelector.addEventListener('change', (e) => {
            i18n.setLanguage(e.target.value);
        });
    }
});
