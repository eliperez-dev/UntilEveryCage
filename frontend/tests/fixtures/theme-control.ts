import { mount } from 'svelte';
import '../../src/styles/base.css';
import ThemeControl from '../../src/app/ThemeControl.svelte';
import { getTheme, setTheme } from '../../src/features/theme/theme';

mount(ThemeControl, {
  target: document.getElementById('theme-control')!,
  props: { label: 'Apariencia', groupLabel: 'Tema de color', lightLabel: 'Claro', darkLabel: 'Oscuro' },
});
Object.assign(window, { getTheme, setTheme });
