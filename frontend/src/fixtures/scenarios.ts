import {locations} from './locations'; import type {Profile} from '../domain/publication';
export type Scenario='ready'|'loading'|'empty'|'error'|'restricted';
export function fixture(scenario:Scenario,profile:Profile){ if(scenario==='error') throw new Error('The fixture could not be read.'); if(scenario==='empty') return []; if(scenario==='restricted') return null; return profile==='community'?locations.slice(0,1):locations; }
