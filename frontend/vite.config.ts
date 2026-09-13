import { defineConfig } from 'vite'; import { svelte } from '@sveltejs/vite-plugin-svelte';
const localApiProxy={ '/api': { target:'http://127.0.0.1:8000', changeOrigin:false } };
export default defineConfig({base:'/v2-preview/',plugins:[svelte()],server:{proxy:localApiProxy},preview:{proxy:localApiProxy},build:{outDir:'dist',emptyOutDir:true}});
