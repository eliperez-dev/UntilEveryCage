// Common footer content
function loadFooter() {
    const footerHTML = `
<div class="footer-container">
    <p>
        <strong>This is a living project and a work in progress.</strong>
        If you have suggestions, see a data error, or want to contribute,
        please visit our <a href="contribute.html">contribute page</a>, join our <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noopener noreferrer">Discord server</a>, or send a secure email to <a href="mailto:untileverycageproject@protonmail.com">untileverycageproject@protonmail.com</a>.
        Your feedback is invaluable.
    </p>
    <p>
        This is an independent, open-source, ad-free project. If you find this tool valuable, please consider 
        <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noopener noreferrer">supporting its server and data costs</a>.
    </p>
    <p class="footer-small-text">
        All data is sourced from public records, including the USDA, APHIS, and the BVL (Germany). Any names and addresses are published for educational or research purposes. We do not encourage illegal activities.
    </p>
    <p class="footer-small-text">
        Source code is licensed under the <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noopener noreferrer">AGPLv3</a>. Compiled data is licensed under <a href="http://creativecommons.org/licenses/by-nc-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-NC-SA 4.0</a>. Kill counter adapted from <a href="https://www.adaptt.org/" target="_blank" rel="noopener noreferrer">ADAPTT</a>. Website inspired by the <a href="https://finalnail.com/" target="_blank" rel="noopener noreferrer">Final Nail</a>.
    </p>
    <p>v1.5.1</p>
</div>`;
    
    const footerPlaceholder = document.getElementById('footer-placeholder');
    if (footerPlaceholder) {
        footerPlaceholder.innerHTML = footerHTML;
    }
}

// Load footer when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadFooter);
} else {
    loadFooter();
}