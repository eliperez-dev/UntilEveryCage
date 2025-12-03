/**
 * Translation Manager
 * Handles loading of locale files and translating the UI.
 */
export class TranslationManager {
    constructor(defaultLocale = 'en') {
        this.currentLocale = defaultLocale;
        this.translations = {};
        this.observers = [];
    }

    /**
     * Initialize the translation manager.
     * Detects user language or uses stored preference.
     */
    async init() {
        const storedLocale = localStorage.getItem('user-locale');
        const browserLocale = navigator.language.split('-')[0];
        this.currentLocale = storedLocale || browserLocale || 'en';
        
        // Fallback to 'en' if we don't support the detected language yet
        // In a real app, we'd check against a list of supported locales
        if (!['en', 'es', 'de', 'fr'].includes(this.currentLocale)) {
            this.currentLocale = 'en';
        }

        await this.loadTranslations(this.currentLocale);
        this.translatePage();
    }

    /**
     * Load translations for a specific locale.
     * @param {string} locale 
     */
    async loadTranslations(locale) {
        try {
            const response = await fetch(`./locales/${locale}.json`);
            if (!response.ok) throw new Error(`Failed to load ${locale} translations`);
            this.translations = await response.json();
            this.currentLocale = locale;
            localStorage.setItem('user-locale', locale);
            document.documentElement.lang = locale;
        } catch (error) {
            console.error('Error loading translations:', error);
            // Fallback to English if loading fails
            if (locale !== 'en') {
                await this.loadTranslations('en');
            }
        }
    }

    /**
     * Get a translated string by key.
     * Supports nested keys (e.g., "nav.home").
     * @param {string} key 
     * @returns {string}
     */
    t(key) {
        const keys = key.split('.');
        let value = this.translations;
        
        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                return key; // Return key if translation missing
            }
        }
        
        return value;
    }

    /**
     * Check if a translation key exists.
     * @param {string} key 
     * @returns {boolean}
     */
    exists(key) {
        const keys = key.split('.');
        let value = this.translations;
        
        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                return false;
            }
        }
        
        return true;
    }

    /**
     * Translate all elements with data-i18n attribute on the page.
     */
    translatePage() {
        document.querySelectorAll('[data-i18n]').forEach(element => {
            const key = element.getAttribute('data-i18n');
            const translation = this.t(key);
            
            // Handle placeholders if needed (simple implementation)
            if (element.tagName === 'INPUT' && element.getAttribute('placeholder')) {
                element.setAttribute('placeholder', translation);
            } else {
                element.innerHTML = translation;
            }
        });
        
        // Notify observers (e.g., for re-rendering dynamic components)
        this.notifyObservers();
    }

    /**
     * Switch language.
     * @param {string} locale 
     */
    async setLanguage(locale) {
        if (locale === this.currentLocale) return;
        await this.loadTranslations(locale);
        this.translatePage();
    }

    subscribe(callback) {
        this.observers.push(callback);
    }

    notifyObservers() {
        this.observers.forEach(cb => cb());
    }
}

export const i18n = new TranslationManager();
