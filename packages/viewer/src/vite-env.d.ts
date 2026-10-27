/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "live" reads block records from qipu.org's /data (through the dev proxy) instead of the sample */
  readonly VITE_QIPU_DATA?: string;
}
