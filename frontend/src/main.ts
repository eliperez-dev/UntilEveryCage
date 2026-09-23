import { mount } from 'svelte';
import './styles/base.css';
import App from './app/App.svelte';
const target = document.getElementById('app');
if (!target) throw new Error('App mount missing');
mount(App, { target });
