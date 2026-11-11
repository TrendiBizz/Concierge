declare module 'online-3d-viewer' {
  export class EmbeddedViewer {
    constructor(parent: HTMLElement, params: object);
    LoadModelFromUrlList(urls: string[]): void;
  }
}
