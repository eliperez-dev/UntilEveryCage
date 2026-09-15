import type { DisplayFeature } from './mapProjection';
export interface MapAdapter { mount(container:HTMLElement, onSelect?: (id:string) => void):Promise<void>; update(features:readonly DisplayFeature[],selectedId:string|null):void; destroy():void; }
