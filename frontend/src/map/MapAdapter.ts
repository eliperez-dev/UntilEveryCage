import type { MapDisplayItem } from './mapProjection';
export interface MapAdapter { mount(container:HTMLElement, onSelect?: (id:string) => void):Promise<void>; update(items:readonly MapDisplayItem[],selectedId:string|null):void; destroy():void; }
