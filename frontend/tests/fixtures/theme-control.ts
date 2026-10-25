import { mount } from 'svelte';
import '../../src/styles/base.css';
import ThemeControl from '../../src/app/ThemeControl.svelte';
import { getTheme, setTheme } from '../../src/features/theme/theme';
import { language } from '../../src/app/language';

language.set('es');

mount(ThemeControl, {
  target: document.getElementById('theme-control')!,
});
Object.assign(window, { getTheme, setTheme });
