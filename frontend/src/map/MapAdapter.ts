import type { DisplayFeature } from './mapProjection';
export interface MapAdapter { mount(container:HTMLElement):Promise<void>; update(features:readonly DisplayFeature[],selectedId:string|null):void; destroy():void; }
