import { defineConfig } from 'vite'; import { svelte } from '@sveltejs/vite-plugin-svelte';
export default defineConfig({base:'/v2-preview/',plugins:[svelte()],build:{outDir:'dist',emptyOutDir:true}});
