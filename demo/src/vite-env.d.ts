/// <reference types="vite/client" />

declare module "*.json?raw" {
  const src: string
  export default src
}
